#!/usr/bin/env python3
"""TOKENMAXXING audit: measure where tokens actually go, from local session logs.

Reads Claude Code transcripts (~/.claude*/projects/**/*.jsonl) and Codex rollouts
(~/.codex/sessions/**/*.jsonl). Read-only, offline, standard library only.
Nothing is uploaded; transcript text is never printed except short tool labels.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import statistics
import sys

# Relative cost weights per token, using Anthropic's documented prompt-caching
# multipliers (cache read 0.1x, 5-minute write 1.25x, 1-hour write 2x base input)
# and a 5x output/input price ratio. A ranking signal, not an invoice.
WEIGHTS = {'input': 1.0, 'cache_write_5m': 1.25, 'cache_write_1h': 2.0, 'cache_read': 0.1, 'output': 5.0}
CHARS_PER_TOKEN = 4  # rough estimate for tool output; usage fields are exact
REBUILD_MIN = 20_000  # cache write this large while reading less than it = prefix rebuilt
MODEL_TIERS_PATH = Path(__file__).resolve().parents[1] / 'policy' / 'model-tiers.json'
CHECK_RE = re.compile(
    r'^\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:\'[^\']*\'|"[^"]*"|\S*)\s+)*(?:'
    r'pytest(?:\d+(?:\.\d+)?)?(?:\s|$)|'
    r'python(?:\d+(?:\.\d+)?)?\s+-m\s+(?:unittest|pytest)(?:\s|$)|'
    r'(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:test|build|lint|typecheck|check)(?:\s|$)|'
    r'(?:vitest|jest|tsc|eslint|ruff|mypy)(?:\s|$)|'
    r'cargo\s+(?:test|build|check|clippy)(?:\s|$)|'
    r'go\s+(?:test|build|vet)(?:\s|$)|'
    r'make\s+(?:test|check|build)(?:\s|$)|'
    r'(?:gradle|mvn)(?:\s+.*)?\s+test(?:\s|$)|'
    r'swift\s+(?:test|build)(?:\s|$)|'
    r'playwright\s+test(?:\s|$))', re.IGNORECASE)


def _command_segments(command):
    if not isinstance(command, str):
        return []
    segments, start, quote, escaped, index = [], 0, None, False, 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
        elif char == '\\' and quote != "'":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in ("'", '"', '`'):
            quote = char
        elif command.startswith('&&', index):
            segments.append(command[start:index])
            index += 1
            start = index + 1
        elif char in ';|':
            segments.append(command[start:index])
            start = index + 1
        index += 1
    segments.append(command[start:])
    return segments


def _check_segment(command):
    for segment in _command_segments(command):
        if CHECK_RE.match(segment):
            return ' '.join(segment.strip().split())
    return None


def is_check_command(command):
    """Return whether a shell command starts any simple segment with a check invocation."""
    return _check_segment(command) is not None


def _normalized_check(command):
    segment = _check_segment(command)
    return ' '.join(segment.lower().split()) if segment else None


def _is_commit_command(command):
    return any(re.match(r'^\s*git\s+commit\b', segment, re.IGNORECASE)
               and '--dry-run' not in segment.lower()
               for segment in _command_segments(command))


def _skill_parts(value):
    if not isinstance(value, str):
        return None, None
    value = value.strip().lstrip('/')
    if not value:
        return None, None
    name = value.split(None, 1)[0]
    plugin = None
    if name.startswith('plugin:'):
        rest = name[len('plugin:'):]
        if '/' in rest:
            plugin, name = rest.split('/', 1)
        elif ':' in rest:
            plugin, name = rest.split(':', 1)
        else:
            plugin, name = 'plugin', rest
    elif ':' in name:
        plugin, name = name.split(':', 1)
    return (plugin or None, name or None)


def _record_skill(session, value):
    plugin, name = _skill_parts(value)
    if not name:
        return
    if plugin:
        session.plugin_skills[plugin][name] += 1
    else:
        session.skills_used[name] += 1


def _command_names(text):
    if not isinstance(text, str):
        return []
    names = []
    marker, close = '<command-name>', '</command-name>'
    start = 0
    while True:
        start = text.find(marker, start)
        if start < 0:
            break
        start += len(marker)
        end = text.find(close, start)
        if end < 0:
            break
        names.append(text[start:end].strip())
        start = end + len(close)
    return names


def _record_command_skills(session, event):
    """Read only command metadata and tags; never surface transcript text in reports."""
    stack = [event]
    found = set()
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            command_name = value.get('command_name')
            if isinstance(command_name, str):
                found.add(_skill_parts(command_name))
            for key, child in value.items():
                if key in ('content', 'text') and isinstance(child, str):
                    for name in _command_names(child):
                        found.add(_skill_parts(name))
                elif isinstance(child, (dict, list)):
                    stack.append(child)
        elif isinstance(value, list):
            stack.extend(value)
    for plugin, name in found:
        if name:
            if plugin:
                session.plugin_skills[plugin][name] += 1
            else:
                session.skills_used[name] += 1


def claude_roots():
    roots = []
    env = os.environ.get('CLAUDE_CONFIG_DIR')
    if env:
        roots.append(Path(env).expanduser() / 'projects')
    roots += sorted(Path.home().glob('.claude*/projects'))
    seen, out = set(), []
    for r in roots:
        if r.is_dir() and r.resolve() not in seen:
            seen.add(r.resolve())
            out.append(r)
    return out


def codex_root():
    return Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser() / 'sessions'


def parse_ts(s):
    try:
        value = datetime.fromisoformat(s.replace('Z', '+00:00'))
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    except (AttributeError, ValueError):
        return None


def est_tokens(content):
    """Estimate tokens of a tool_result payload (string or list of blocks); images ignored."""
    if isinstance(content, str):
        return len(content) // CHARS_PER_TOKEN
    if isinstance(content, list):
        return sum(len(b.get('text', '')) // CHARS_PER_TOKEN for b in content if isinstance(b, dict))
    return 0


def tool_label(name, inp):
    """Short, non-sensitive description of a tool call: file path or first words of a command."""
    if not isinstance(inp, dict):
        return name
    for key in ('file_path', 'path', 'notebook_path'):
        if isinstance(inp.get(key), str):
            value = inp[key]
            if len(value) > 60:
                value = '…' + value[-60:]
            return f'{name} {value}'
    for key in ('pattern', 'url', 'query'):
        if isinstance(inp.get(key), str):
            return f'{name} {inp[key][:70]}'
    if isinstance(inp.get('command'), str):
        return f'{name} `{" ".join(inp["command"].split())[:60]}`'
    return name


def project_name(path):
    """Claude Code encodes cwd as a dash-joined directory name; keep the last two parts."""
    parts = [p for p in path.split('-') if p]
    return '/'.join(parts[-2:]) if parts else path


class Session:
    __slots__ = ('id', 'project', 'agent', 'start', 'turns', 'usage', 'models', 'baseline',
                 'rebuilds', 'results', 'reads', 'subagent', 'work', 'skills_used',
                 'plugin_skills', 'work_calls', 'work_order', 'last_edit_order',
                 'verified_check_after_edit', 'distinct_passing_checks', 'model_weighted')

    def __init__(self, sid, project, agent, subagent=False):
        self.id, self.project, self.agent, self.subagent = sid, project, agent, subagent
        self.start, self.turns, self.baseline = None, 0, None
        self.usage = Counter()
        self.models = Counter()
        self.model_weighted = Counter()
        self.work = Counter()
        self.skills_used = Counter()
        self.plugin_skills = defaultdict(Counter)
        self.work_calls = {}
        self.work_order = 0
        self.last_edit_order = None
        self.verified_check_after_edit = False
        self.distinct_passing_checks = set()
        self.rebuilds = []   # cache_write tokens per rebuild event
        self.results = []    # (est_tokens, label, carry_turns)
        self.reads = Counter()

    def weighted(self):
        return sum(self.usage[k] * w for k, w in WEIGHTS.items())


def in_window(ts, since=None, until=None):
    if ts is None:
        return True
    if since and ts < since:
        return False
    if until and ts >= until:
        return False
    return True


def _tool_record(session, call_id, name, inp):
    """Track a tool call without retaining or printing its input text."""
    if not isinstance(inp, dict):
        inp = {}
    name = str(name or '')
    lowered = name.casefold()
    edit = lowered in ('edit', 'multiedit', 'write', 'notebookedit', 'apply_patch')
    shell = lowered in ('bash', 'shell', 'shell_command', 'shell_exec', 'exec_command',
                        'run_shell', 'execute', 'terminal')
    command = inp.get('command') or inp.get('cmd')
    check = _normalized_check(command) if shell else None
    session.work_order += 1
    record = {
        'edit': edit,
        'check': check,
        'commit': shell and isinstance(command, str) and _is_commit_command(command),
        'order': session.work_order,
    }
    if check:
        session.work['checks'] += 1
    if call_id is None:
        call_id = f'__work_{session.work_order}'
    session.work_calls[call_id] = record
    return call_id


def _complete_tool(session, call_id, success):
    record = session.work_calls.pop(call_id, None)
    if record is None:
        return
    session.work_order += 1
    if success is None:
        return
    if success:
        if record['edit']:
            session.work['edits'] += 1
            session.last_edit_order = session.work_order
            session.verified_check_after_edit = False
        if record['check']:
            session.work['checks_passed'] += 1
            session.distinct_passing_checks.add(record['check'])
            if (session.last_edit_order is not None
                    and record['order'] > session.last_edit_order):
                session.verified_check_after_edit = True
        if record['commit']:
            session.work['commits'] += 1
    elif record['check']:
        session.work['checks_failed'] += 1


def _codex_args(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {'command': value}
        except ValueError:
            return {'command': value}
    return {}


def _codex_exit_code(value):
    if not isinstance(value, dict):
        return None
    for key in ('exit_code', 'exitCode', 'return_code', 'returncode'):
        code = value.get(key)
        if isinstance(code, int) and not isinstance(code, bool):
            return code
    if isinstance(value.get('success'), bool):
        return 0 if value['success'] else 1
    for key in ('output', 'result', 'content'):
        nested = value.get(key)
        if isinstance(nested, dict):
            code = _codex_exit_code(nested)
            if code is not None:
                return code
        elif isinstance(nested, str):
            try:
                parsed = json.loads(nested)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                code = _codex_exit_code(parsed)
                if code is not None:
                    return code
            match = re.search(r'(?:exit[_ ]code|return code)\s*[:=]?\s*(-?\d+)', nested, re.IGNORECASE)
            if match:
                return int(match.group(1))
    return None


def _codex_work_event(session, event):
    payload = event.get('payload') if isinstance(event.get('payload'), dict) else event
    event_type = str(payload.get('type') or event.get('type') or '').casefold()
    call_id = payload.get('call_id') or payload.get('id') or payload.get('tool_call_id')
    if event_type in ('function_call_output', 'custom_tool_call_output', 'shell_exec_output',
                      'exec_command_output'):
        code = _codex_exit_code(payload)
        _complete_tool(session, call_id, None if code is None else code == 0)
        return
    if event_type in ('patch_apply_end', 'apply_patch_output'):
        success = payload.get('success')
        code = _codex_exit_code(payload)
        if isinstance(success, bool) or code is not None:
            session.work_order += 1
            if success is True or code == 0:
                session.work['edits'] += 1
                session.last_edit_order = session.work_order
                session.verified_check_after_edit = False
        return
    if event_type not in ('function_call', 'custom_tool_call', 'apply_patch', 'shell_exec',
                          'exec_command', 'shell_command', 'bash', 'terminal'):
        return
    name = payload.get('name') or event_type
    args = _codex_args(payload.get('arguments', payload.get('input', payload)))
    if str(name).casefold() in ('apply_patch', 'patch') and not args:
        args = {'command': ''}
    tracked_id = _tool_record(session, call_id, name, args)
    code = _codex_exit_code(payload)
    if code is not None or isinstance(payload.get('success'), bool):
        success = (code == 0) if code is not None else payload.get('success')
        _complete_tool(session, tracked_id, success)


def _model_tiers():
    try:
        with MODEL_TIERS_PATH.open(encoding='utf-8') as handle:
            values = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(values, dict):
        return {}
    patterns = values.get('patterns', values)
    return patterns if isinstance(patterns, dict) else {}


def _model_tier(model, tiers):
    import fnmatch
    lowered = model.casefold()
    for pattern, tier in tiers.items():
        if isinstance(pattern, str) and fnmatch.fnmatchcase(lowered, pattern.casefold()):
            if tier in ('premium', 'standard', 'economy'):
                return tier
    return 'unknown'


def parse_claude(path, since=None, until=None, seen_msgs=None, seen_tool_ids=None, root=None):
    """Parse one Claude Code transcript into a Session (or None if empty/out of range)."""
    path = Path(path)
    seen_msgs = seen_msgs if seen_msgs is not None else set()
    seen_tool_ids = seen_tool_ids if seen_tool_ids is not None else set()
    if root is not None:
        try:
            relative = path.relative_to(Path(root))
        except ValueError:
            relative = path
    else:
        relative = (Path(path.parent.parent.parent.name, path.parent.name)
                    if 'subagents' in path.parts else Path(path.parent.name))
    sub = 'subagents' in relative.parts
    project = project_name(relative.parts[0] if relative.parts else path.parent.name)
    s = Session(path.stem, project, 'claude', sub)
    calls = {}
    fresh_calls, result_ids = set(), set()
    pending = []  # [est_tokens, label, turn_index] awaiting carry computation
    first_api_message = True
    baseline_allowed = True

    def close_segment():
        for item in pending:
            s.results.append((item[0], item[1], max(s.turns - item[2], 0)))
        pending.clear()

    with path.open(encoding='utf-8', errors='replace') as f:
        for line in f:
            head = line[:160]
            if '"type":"api-request' in head or '"type":"attachment"' in head:
                continue  # huge request snapshots and hook payloads; never needed
            if 'compact_boundary' in line[:400]:
                try:
                    boundary = json.loads(line)
                except ValueError:
                    boundary = {}
                if in_window(parse_ts(boundary.get('timestamp')), since, until):
                    close_segment()
                continue
            if ('"assistant"' not in line and '"tool_result"' not in line
                    and 'command-name' not in line and 'command_name' not in line):
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            kind, msg = o.get('type'), o.get('message') or {}
            if kind == 'assistant':
                mid = msg.get('id') or o.get('uuid')
                model = msg.get('model')
                is_api_message = bool(model and model != '<synthetic>')
                duplicate = is_api_message and mid in seen_msgs if mid else False
                if is_api_message and first_api_message:
                    first_api_message = False
                    if duplicate:
                        baseline_allowed = False
                content = msg.get('content') or []
                ts = parse_ts(o.get('timestamp'))
                for b in content if isinstance(content, list) else []:
                    if isinstance(b, dict) and b.get('type') == 'tool_use':
                        call_id = b.get('id')
                        if not call_id or call_id in seen_tool_ids:
                            continue
                        seen_tool_ids.add(call_id)
                        fresh_calls.add(call_id)
                        inp = b.get('input') or {}
                        name = b.get('name', '?')
                        calls[call_id] = tool_label(name, inp)
                        if (in_window(ts, since, until) and name == 'Skill'
                                and isinstance(inp, dict)):
                            _record_skill(s, inp.get('skill'))
                        if in_window(ts, since, until):
                            _tool_record(s, call_id, name, inp)
                        if (in_window(ts, since, until) and b.get('name') == 'Read'
                                and isinstance(inp.get('file_path'), str)):
                            s.reads[inp['file_path']] += 1
                if not is_api_message:
                    continue
                if mid:
                    seen_msgs.add(mid)
                if duplicate or not in_window(ts, since, until):
                    continue
                u = msg.get('usage') or {}
                inp_t = u.get('input_tokens') or 0
                cr = u.get('cache_read_input_tokens') or 0
                cw = u.get('cache_creation_input_tokens') or 0
                split = u.get('cache_creation') or {}
                cw1h = split.get('ephemeral_1h_input_tokens') or 0
                cw5m = cw - cw1h if split else cw
                s.usage.update({'input': inp_t, 'cache_read': cr, 'cache_write_5m': cw5m,
                                'cache_write_1h': cw1h, 'output': u.get('output_tokens') or 0})
                s.models[model] += 1
                s.model_weighted[model] += (inp_t * WEIGHTS['input'] + cr * WEIGHTS['cache_read']
                                            + cw5m * WEIGHTS['cache_write_5m']
                                            + cw1h * WEIGHTS['cache_write_1h']
                                            + (u.get('output_tokens') or 0) * WEIGHTS['output'])
                if s.baseline is None and baseline_allowed:
                    s.baseline = inp_t + cr + cw
                    s.start = ts
                elif cw >= REBUILD_MIN and cr < cw:
                    s.rebuilds.append(cw)
                s.turns += 1
            elif kind == 'user':
                if not in_window(parse_ts(o.get('timestamp')), since, until):
                    continue
                _record_command_skills(s, o)
                content = msg.get('content')
                for b in content if isinstance(content, list) else []:
                    if isinstance(b, dict) and b.get('type') == 'tool_result':
                        call_id = b.get('tool_use_id')
                        if not call_id or call_id not in fresh_calls or call_id in result_ids:
                            continue
                        result_ids.add(call_id)
                        t = est_tokens(b.get('content'))
                        if t:
                            pending.append([t, calls.get(call_id, '?'), s.turns])
                        is_error = b.get('is_error')
                        success = (not is_error) if isinstance(is_error, bool) else None
                        _complete_tool(s, call_id, success)
    close_segment()
    return s if s.turns or s.skills_used or s.plugin_skills else None


def parse_codex(path, since=None, until=None, seen_sessions=None):
    """Codex logs cumulative token_count events; the last one is the session total."""
    seen_sessions = seen_sessions if seen_sessions is not None else set()
    s = Session(path.stem, '?', 'codex')
    last, model, limits, meta_id = None, None, None, None
    previous_model_usage = Counter()
    with path.open(encoding='utf-8', errors='replace') as f:
        for line in f:
            if not any(marker in line for marker in (
                    '"token_count"', '"turn_context"', '"session_meta"',
                    '"function_call"', '"function_call_output"', '"custom_tool_call"',
                    '"custom_tool_call_output"', '"apply_patch"', '"patch_apply_end"',
                    '"shell_exec"', '"shell_exec_output"', '"exec_command"',
                    '"user_message"', '"command-name"', '"command_name"')):
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            p = o.get('payload') or {}
            if isinstance(p, dict):
                ptype = p.get('type')
                if (o.get('type') in ('user', 'user_message') or p.get('role') == 'user'
                        or ptype in ('user', 'user_message')):
                    _record_command_skills(s, o)
            _codex_work_event(s, o)
            if o.get('type') == 'session_meta':
                meta_id = p.get('id') or meta_id
                s.project = '/'.join(Path(p.get('cwd', '?')).parts[-2:])
                s.start = parse_ts(p.get('timestamp') or o.get('timestamp'))
            elif o.get('type') == 'turn_context':
                model = p.get('model') or model
            elif p.get('type') == 'token_count' and p.get('info'):
                last = p['info']
                limits = p.get('rate_limits') or limits
                s.turns += 1
                if model:
                    s.models[model] += 1
                cumulative = last.get('total_token_usage') or {}
                cached = cumulative.get('cached_input_tokens') or 0
                current_model_usage = {
                    'input': max((cumulative.get('input_tokens') or 0) - cached, 0),
                    'cache_read': cached,
                    'output': cumulative.get('output_tokens') or 0,
                }
                added = {key: max(value - previous_model_usage[key], 0)
                         for key, value in current_model_usage.items()}
                weighted_delta = sum(added[key] * WEIGHTS[key] for key in added)
                s.model_weighted[model or 'unknown'] += weighted_delta
                previous_model_usage = Counter(current_model_usage)
    if not last or not in_window(s.start, since, until):
        return None
    if meta_id and meta_id in seen_sessions:
        return None
    if meta_id:
        seen_sessions.add(meta_id)
    tot = last.get('total_token_usage') or {}
    cached = tot.get('cached_input_tokens') or 0
    s.usage.update({'input': max((tot.get('input_tokens') or 0) - cached, 0), 'cache_read': cached,
                    'output': tot.get('output_tokens') or 0,
                    'reasoning': tot.get('reasoning_output_tokens') or 0})
    s.baseline = limits  # stash latest rate-limit snapshot for reporting
    return s


def collect(since=None, project=None, paths=None, until=None, skip_untouched=True):
    files = []
    roots = paths or claude_roots()
    if isinstance(roots, (str, Path)):
        roots = [roots]
    for root in roots:
        root = Path(root).expanduser().resolve()
        if root.is_dir():
            files += [('claude', p.resolve(), root) for p in root.rglob('*.jsonl')]
    if paths is None and codex_root().is_dir():
        root = codex_root().resolve()
        files += [('codex', p.resolve(), root) for p in root.rglob('*.jsonl')]
    dated = []
    for agent, path, root in files:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except OSError:
            continue
        if skip_untouched and since and mtime < since:
            continue  # untouched since the window began
        dated.append((mtime, agent, path, root))
    dated.sort(key=lambda item: (item[0], str(item[2])))

    seen_msgs, seen_tool_ids, seen_codex_sessions = set(), set(), set()
    sessions = []
    for _, agent, p, root in dated:
        try:
            if agent == 'claude':
                s = parse_claude(p, since, until, seen_msgs, seen_tool_ids, root)
            else:
                s = parse_codex(p, since, until, seen_codex_sessions)
        except OSError:
            continue
        if s and (not project or project.lower() in s.project.lower()):
            sessions.append(s)
    return sessions


def fmt(n):
    n = float(n)
    for unit, div in (('B', 1e9), ('M', 1e6), ('k', 1e3)):
        if abs(n) >= div:
            return f'{n / div:.1f}{unit}'
    return f'{n:.0f}'


def pct(a, b):
    return f'{100 * a / b:.0f}%' if b else '—'


def _work_summary(sessions):
    counts = Counter()
    distinct = 0
    verified = unverified = 0
    skill_counts = Counter()
    plugin_counts = defaultdict(Counter)
    model_weights = Counter()
    weighted_units = sum(s.weighted() for s in sessions)
    tiers = _model_tiers()
    for session in sessions:
        counts.update(session.work)
        distinct += len(session.distinct_passing_checks)
        if session.work['edits']:
            if session.verified_check_after_edit:
                verified += 1
            else:
                unverified += 1
        skill_counts.update(session.skills_used)
        for plugin, skills in session.plugin_skills.items():
            plugin_counts[plugin].update(skills)
        if session.model_weighted:
            model_weights.update(session.model_weighted)
        elif session.models:
            model_weights[session.models.most_common(1)[0][0]] += session.weighted()
        elif session.weighted():
            model_weights['unknown'] += session.weighted()

    checks_passed = counts['checks_passed']
    checks_finished = checks_passed + counts['checks_failed']
    edited = verified + unverified
    tier_weights = Counter()
    unknown_models = []
    for model, amount in model_weights.items():
        tier = _model_tier(model, tiers)
        tier_weights[tier] += amount
        if tier == 'unknown':
            unknown_models.append(model)
    model_mix = {
        tier: {'weighted_units': round(tier_weights[tier]),
               'share': round(tier_weights[tier] / weighted_units, 4) if weighted_units else None}
        for tier in ('premium', 'standard', 'economy', 'unknown')
    }
    return {
        'edits': counts['edits'],
        'checks': counts['checks'],
        'checks_passed': checks_passed,
        'checks_failed': counts['checks_failed'],
        'distinct_passing_checks': distinct,
        'commits': counts['commits'],
        'verified_edit_sessions': verified,
        'unverified_edit_sessions': unverified,
        'weighted_units': round(weighted_units),
        'usage_per_passing_check': round(weighted_units / checks_passed, 2) if checks_passed else None,
        'usage_per_distinct_passing_check': round(weighted_units / distinct, 2) if distinct else None,
        'rework_rate': round(counts['checks_failed'] / checks_finished, 4) if checks_finished else None,
        'verified_edit_share': round(verified / edited, 4) if edited else None,
        'premium_share': model_mix['premium']['share'],
        'model_mix': model_mix,
        'unknown_models': sorted(unknown_models, key=str.casefold),
        'skills_used': {
            'by_name': dict(sorted(skill_counts.items(), key=lambda item: item[0].casefold())),
            'by_plugin': {
                plugin: dict(sorted(skills.items(), key=lambda item: item[0].casefold()))
                for plugin, skills in sorted(plugin_counts.items(), key=lambda item: item[0].casefold())
            },
        },
    }


def summarize(sessions, top=10):
    """Build a JSON-serialisable report plus prioritised findings."""
    claude = [s for s in sessions if s.agent == 'claude']
    codex = [s for s in sessions if s.agent == 'codex']
    total = Counter()
    for s in claude:
        total.update(s.usage)
    prompt = total['input'] + total['cache_read'] + total['cache_write_5m'] + total['cache_write_1h']
    weighted = {k: total[k] * w for k, w in WEIGHTS.items()}
    wsum = sum(weighted.values()) or 1

    by_model, by_project = defaultdict(Counter), defaultdict(float)
    for s in claude:
        for m, n in s.models.items():
            by_model[m]['turns'] += n
        if not s.models:
            continue
        main = s.models.most_common(1)[0][0]
        by_model[main]['weighted'] += s.weighted()
        by_project[s.project] += s.weighted()

    mains = [s for s in claude if not s.subagent and s.baseline is not None]
    baselines = sorted(s.baseline for s in mains)
    rebuilds = [(cw, s) for s in claude for cw in s.rebuilds]

    tools, results = defaultdict(lambda: [0, 0, 0.0]), []
    for s in claude:
        for t, label, carry in s.results:
            name = label.split(' ', 1)[0]
            tools[name][0] += 1
            tools[name][1] += t
            tools[name][2] += t * carry * WEIGHTS['cache_read']
            results.append((t, carry, label, s.project))
    results.sort(key=lambda r: -r[0] * (1 + r[1] * WEIGHTS['cache_read']))
    rereads = sorted(((n, f, s.project) for s in claude for f, n in s.reads.items() if n >= 3), reverse=True)
    sub_w = sum(s.weighted() for s in claude if s.subagent)

    report = {
        'claude': {
            'sessions': len(mains), 'subagent_transcripts': len(claude) - len(mains),
            'api_turns': sum(s.turns for s in claude),
            'tokens': dict(total), 'cache_hit_rate': round(total['cache_read'] / prompt, 4) if prompt else None,
            'weighted_units': round(wsum), 'weighted_share': {k: round(v / wsum, 4) for k, v in weighted.items()},
            'subagent_weighted_share': round(sub_w / wsum, 4),
            'tool_output_tokens': sum(t for s in claude for t, _, _ in s.results),
            'starting_context': {
                'median': statistics.median(baselines) if baselines else None,
                'p90': baselines[int(0.9 * (len(baselines) - 1))] if baselines else None,
                'max': baselines[-1] if baselines else None},
            'cache_rebuilds': {'count': len(rebuilds), 'tokens': sum(c for c, _ in rebuilds)},
            'by_model': {m: {'turns': v['turns'], 'weighted_units': round(v['weighted'])}
                         for m, v in sorted(by_model.items(), key=lambda kv: -kv[1]['weighted'])},
            'by_project': {p: round(w) for p, w in sorted(by_project.items(), key=lambda kv: -kv[1])[:top]},
            'tool_output': {n: {'calls': c, 'est_tokens': t, 'est_carry_units': round(carry)}
                            for n, (c, t, carry) in sorted(tools.items(), key=lambda kv: -kv[1][1])[:top]},
            'largest_tool_results': [{'est_tokens': t, 'turns_carried': c, 'call': l, 'project': p}
                                     for t, c, l, p in results[:top]],
            'repeated_reads': [{'reads': n, 'file': f, 'project': p} for n, f, p in rereads[:top]],
        },
        'codex': None,
    }
    if codex:
        ct = Counter()
        cm = Counter()
        for s in codex:
            ct.update(s.usage)
            cm.update(s.models)
        cprompt = ct['input'] + ct['cache_read']
        latest = max((s for s in codex if s.baseline), key=lambda s: s.start or datetime.min.replace(tzinfo=timezone.utc), default=None)
        report['codex'] = {'sessions': len(codex), 'tokens': dict(ct),
                           'cache_hit_rate': round(ct['cache_read'] / cprompt, 4) if cprompt else None,
                           'models': dict(cm.most_common(top)),
                           'latest_rate_limits': latest.baseline if latest else None}
    work = _work_summary(sessions)
    skills_used = work.pop('skills_used')
    report['work'] = work
    report['skills_used'] = skills_used
    report['findings'] = findings(report)
    return report


def findings(r):
    """Turn measurements into ranked, specific actions. Thresholds are deliberate and documented."""
    c, out = r['claude'], []
    if not c['api_turns']:
        out.append('No Claude Code usage found for this window.')
    share = c['weighted_share']
    hit = c['cache_hit_rate'] or 0
    base = c['starting_context']['median'] or 0
    if base > 30_000:
        out.append(f'Sessions start at a median {fmt(base)} tokens before your first word. Run '
                   '`tokenmaxxing doctor` and trim always-loaded CLAUDE.md, skills, agents and MCP servers.')
    writes = share['cache_write_5m'] + share['cache_write_1h']
    if writes > 0.35:
        out.append(f'Cache writes are {pct(writes, 1)} of weighted cost. Fewer model/tool/config switches '
                   'mid-session, fewer long idle gaps, and fresh sessions for unrelated work keep the prefix warm.')
    if c['cache_rebuilds']['count'] >= 5:
        out.append(f"{c['cache_rebuilds']['count']} full-prefix cache rebuilds ({fmt(c['cache_rebuilds']['tokens'])} tokens). "
                   'Usual causes: idle past the cache TTL, model or effort switches, editing CLAUDE.md/MCP mid-session.')
    if hit and hit < 0.8:
        out.append(f'Cache hit rate is {pct(hit, 1)} (healthy agent loops sit above 90%). Keep stable instructions first and avoid churn.')
    if share['output'] > 0.4:
        out.append(f"Output is {pct(share['output'], 1)} of weighted cost. Ask for diffs/edits, not full-file rewrites; cap prose.")
    big = [x for x in c['largest_tool_results'] if x['est_tokens'] >= 10_000]
    if big:
        x = big[0]
        out.append(f"{len(big)} tool results of 10k+ tokens (largest ~{fmt(x['est_tokens'])}: {x['call']}). "
                   'Filter with `| tail`/`grep`, `--quiet`, or Read with offset/limit — results stay in context every later turn.')
    if c['repeated_reads']:
        x = c['repeated_reads'][0]
        out.append(f"{len(c['repeated_reads'])} files were Read 3+ times in one session (worst: {x['reads']}x {x['file']}). "
                   'Rely on the earlier read or a scoped range instead.')
    if c['subagent_weighted_share'] > 0.4:
        out.append(f"Subagents consume {pct(c['subagent_weighted_share'], 1)} of weighted cost. Each cold start re-pays the "
                   'system prompt; delegate only work that is large and independent.')
    work = r.get('work', {})
    if work.get('rework_rate') is not None and work['rework_rate'] > 0.25:
        out.append(f"Failed checks are {pct(work['rework_rate'], 1)} of checks with a known result. "
                   'Tighten briefs or run targeted checks first.')
    if work.get('verified_edit_share') is not None and work['verified_edit_share'] < 0.5:
        out.append(f"Only {pct(work['verified_edit_share'], 1)} of edit sessions ended with a passing check after the last edit.")
    return out or ['No major waste pattern crossed the thresholds. Measure again after workflow changes.']


def print_report(r, since_label):
    c = r['claude']
    say = print
    say(f'TOKENMAXXING audit — {since_label}\n')
    if c['api_turns']:
        t = c['tokens']
        say(f"Claude Code: {c['sessions']} sessions, {c['subagent_transcripts']} subagent runs, {c['api_turns']} API turns")
        say(f"  fresh input {fmt(t.get('input', 0))} · cache read {fmt(t.get('cache_read', 0))} · "
            f"cache write {fmt(t.get('cache_write_5m', 0) + t.get('cache_write_1h', 0))} · output {fmt(t.get('output', 0))}")
        say(f"  cache hit rate {pct(c['cache_hit_rate'] or 0, 1)} · weighted cost units {fmt(c['weighted_units'])}")
        say('  cost share: ' + ' · '.join(f'{k} {pct(v, 1)}' for k, v in c['weighted_share'].items() if v >= 0.005))
        sc = c['starting_context']
        say(f"  starting context per session: median {fmt(sc['median'] or 0)}, p90 {fmt(sc['p90'] or 0)}, max {fmt(sc['max'] or 0)}")
        say(f"  cache rebuilds: {c['cache_rebuilds']['count']} ({fmt(c['cache_rebuilds']['tokens'])} tokens)\n")
        sections = [
            ('By model (weighted units)', [f"{m:<28} {fmt(v['weighted_units']):>8}  {v['turns']} turns" for m, v in c['by_model'].items()]),
            ('By project (weighted units)', [f'{p:<40} {fmt(w):>8}' for p, w in c['by_project'].items()]),
            ('Tool output (estimated tokens entering context)',
             [f"{n:<28} {fmt(v['est_tokens']):>8} in {v['calls']} calls · carry ~{fmt(v['est_carry_units'])} units"
              for n, v in c['tool_output'].items()]),
            ('Largest tool results', [f"~{fmt(x['est_tokens']):>6}  carried {x['turns_carried']:>3} turns  {x['call']}"
                                      for x in c['largest_tool_results']]),
            ('Repeated reads in one session', [f"{x['reads']}x  {x['file']}" for x in c['repeated_reads']]),
        ]
        for title, rows in sections:
            if rows:
                say(title)
                for row in rows:
                    say('  ' + row)
                say('')
    x = r['codex']
    if x:
        t = x['tokens']
        say(f"Codex: {x['sessions']} sessions · fresh input {fmt(t.get('input', 0))} · cached {fmt(t.get('cache_read', 0))} · "
            f"output {fmt(t.get('output', 0))} (reasoning {fmt(t.get('reasoning', 0))}) · cache hit {pct(x['cache_hit_rate'] or 0, 1)}")
        say('  models: ' + ', '.join(f'{m} ({n} turns)' for m, n in x['models'].items()))
        lim = x['latest_rate_limits'] or {}
        for key in ('primary', 'secondary'):
            w = lim.get(key)
            if isinstance(w, dict) and w.get('used_percent') is not None:
                hours = (w.get('window_minutes') or 0) / 60
                reset = datetime.fromtimestamp(w['resets_at'], timezone.utc).isoformat(timespec='minutes') if w.get('resets_at') else '?'
                say(f"  latest {hours:g}h window: {w['used_percent']:g}% used, resets {reset}")
        say('')
    work = r['work']
    edit_sessions = work['verified_edit_sessions'] + work['unverified_edit_sessions']
    say('Work (proxy — counted from tool calls, not a quality judgement)')
    say(f"  edits {work['edits']} · checks {work['checks']} ({work['checks_passed']} passed, "
        f"{work['checks_failed']} failed) · commits {work['commits']}")
    rework = pct(work['rework_rate'], 1) if work['rework_rate'] is not None else 'n/a'
    verified = pct(work['verified_edit_share'], 1) if work['verified_edit_share'] is not None else 'n/a'
    say(f"  rework rate {rework} · verified-edit sessions {work['verified_edit_sessions']}/"
        f"{edit_sessions} ({verified})")
    passing = work['usage_per_passing_check']
    say(f"  usage per passing check {fmt(passing) + ' units' if passing is not None else 'n/a'}")
    distinct = work['usage_per_distinct_passing_check']
    say(f"  usage per distinct passing check {fmt(distinct) + ' units' if distinct is not None else 'n/a'}")
    mix = work['model_mix']
    mix_parts = [f"{tier} {pct(mix[tier]['share'], 1)}" for tier in ('premium', 'standard', 'economy')
                 if mix[tier]['share'] is not None and mix[tier]['weighted_units']]
    if mix['unknown']['weighted_units']:
        mix_parts.append(f"unknown {pct(mix['unknown']['share'], 1)}")
    say('  model mix: ' + (' · '.join(mix_parts) if mix_parts else 'n/a')
        + ' (lower usually = cheaper; check quality)')
    if work['unknown_models']:
        say('  unknown models: ' + ', '.join(work['unknown_models']))
    say('')
    say('Findings (highest impact first)')
    for i, f in enumerate(r['findings'], 1):
        say(f'  {i}. {f}')
    say('\nWeighted units use documented cache multipliers (read 0.1x, write 1.25x/2x) and 5x output; '
        'tool sizes are ~4 chars/token estimates.')


COMPARE_METRICS = (
    ('weighted_units_per_turn', 'Weighted units / turn'),
    ('cache_hit_rate', 'Cache hit rate'),
    ('median_starting_context', 'Median starting context'),
    ('cache_rebuilds_per_100_turns', 'Cache rebuilds / 100 turns'),
    ('tool_output_tokens_per_turn', 'Tool output tokens / turn'),
    ('output_tokens_per_turn', 'Output tokens / turn'),
)
WORK_COMPARE_METRICS = (
    ('usage_per_passing_check', 'Usage per passing check'),
    ('usage_per_distinct_passing_check', 'Usage per distinct passing check'),
    ('rework_rate', 'Rework rate'),
    ('verified_edit_share', 'Verified-edit share'),
    ('premium_share', 'Premium share'),
)


def compare_metrics(report):
    c = report['claude']
    turns = c['api_turns']
    values = {key: None for key, _ in COMPARE_METRICS}
    if turns:
        tokens = c['tokens']
        weighted = sum(tokens.get(key, 0) * weight for key, weight in WEIGHTS.items())
        values = {
            'weighted_units_per_turn': weighted / turns,
            'cache_hit_rate': c['cache_hit_rate'],
            'median_starting_context': c['starting_context']['median'],
            'cache_rebuilds_per_100_turns': c['cache_rebuilds']['count'] * 100 / turns,
            'tool_output_tokens_per_turn': c['tool_output_tokens'] / turns,
            'output_tokens_per_turn': tokens.get('output', 0) / turns,
        }
    work = report.get('work', {})
    values.update({key: work.get(key) for key, _ in WORK_COMPARE_METRICS})
    values['checks_passed'] = work.get('checks_passed')
    values['distinct_passing_checks'] = work.get('distinct_passing_checks')
    return {'api_turns': turns, **{key: round(value, 4) if isinstance(value, (int, float))
                                   else value for key, value in values.items()}}


def build_comparison(current, previous):
    current_values = compare_metrics(current)
    previous_values = compare_metrics(previous)
    delta = {'api_turns': current_values['api_turns'] - previous_values['api_turns']}
    for key, _ in COMPARE_METRICS + WORK_COMPARE_METRICS:
        now, before = current_values[key], previous_values[key]
        delta[key] = round(now - before, 4) if isinstance(now, (int, float)) and isinstance(before, (int, float)) else None
    return {'current': current_values, 'previous': previous_values, 'delta': delta}


def print_comparison(data):
    print('\nWindow comparison (per Claude API turn)')
    turns_delta = data['delta']['api_turns']
    print(f"  API turns: {fmt(data['current']['api_turns'])} current · {fmt(data['previous']['api_turns'])} previous · "
          f"delta {'+' if turns_delta >= 0 else '-'}{fmt(abs(turns_delta))}")
    for key, label in COMPARE_METRICS:
        current, previous, delta = (data[period][key] for period in ('current', 'previous', 'delta'))
        if key in ('cache_hit_rate', 'cache_rebuilds_per_100_turns'):
            scale = 100 if key == 'cache_hit_rate' else 1
            precision = 0 if key == 'cache_hit_rate' else 1
            values = (f'{current * scale:.{precision}f}%' if current is not None else '—',
                      f'{previous * scale:.{precision}f}%' if previous is not None else '—',
                      f'{delta * scale:+.1f} pp' if delta is not None else '—')
        else:
            values = (fmt(current) if current is not None else '—',
                      fmt(previous) if previous is not None else '—',
                      ('+' if delta >= 0 else '-') + fmt(abs(delta)) if delta is not None else '—')
        change = f' ({delta / previous:+.0%})' if delta is not None and previous else ''
        direction = ''
        if delta is not None:
            if key == 'output_tokens_per_turn':
                direction = 'neutral'
            elif delta == 0:
                direction = 'unchanged'
            else:
                better = delta > 0 if key == 'cache_hit_rate' else delta < 0
                direction = 'better' if better else 'worse'
        suffix = f' · {direction}' if direction else ''
        print(f'  {label}: {values[0]} current · {values[1]} previous · delta {values[2]}{change}{suffix}')
    if 'checks_passed' not in data['current']:
        return
    current_checks = data['current'].get('checks_passed') or 0
    previous_checks = data['previous'].get('checks_passed') or 0
    too_few_checks = min(current_checks, previous_checks) < 5
    for key, label in WORK_COMPARE_METRICS:
        if too_few_checks and key != 'premium_share':
            print(f'  {label}: n/a (too few checks)')
            continue
        current, previous, delta = (data[period].get(key) for period in ('current', 'previous', 'delta'))
        if current is None or previous is None or delta is None:
            print(f'  {label}: — current · — previous · delta —')
            continue
        if key in ('rework_rate', 'verified_edit_share', 'premium_share'):
            values = (f'{current:.0%}', f'{previous:.0%}', f'{delta * 100:+.1f} pp')
            change = f' ({delta / previous:+.0%})' if previous else ''
        else:
            values = (fmt(current), fmt(previous),
                      ('+' if delta >= 0 else '-') + fmt(abs(delta)))
            change = f' ({delta / previous:+.0%})' if previous else ''
        if key == 'premium_share':
            direction = 'neutral'
        elif delta == 0:
            direction = 'unchanged'
        elif key in ('verified_edit_share',):
            direction = 'better' if delta > 0 else 'worse'
        else:
            direction = 'better' if delta < 0 else 'worse'
        print(f'  {label}: {values[0]} current · {values[1]} previous · delta {values[2]}{change} · {direction}')


def parse_since(text, now=None):
    if not text or text == 'all':
        return None
    unit = text[-1]
    if unit in 'dh' and text[:-1].isdigit():
        delta = timedelta(days=int(text[:-1])) if unit == 'd' else timedelta(hours=int(text[:-1]))
        return (now or datetime.now(timezone.utc)) - delta
    d = parse_ts(text)
    if d is None:
        raise argparse.ArgumentTypeError('use 7d, 24h, all, or an ISO date')
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def add_arguments(ap):
    ap.add_argument('--since', default='30d', help='window: 7d, 24h, all, or ISO date (default 30d)')
    ap.add_argument('--project', help='only projects whose name contains this text')
    ap.add_argument('--path', type=Path, action='append', help='transcript directory (repeatable; disables auto-discovery)')
    ap.add_argument('--top', type=int, default=10, help='rows per table')
    ap.add_argument('--json', action='store_true', help='machine-readable output')
    ap.add_argument('--compare', action='store_true', help='compare with the immediately preceding window of equal length')


def run(args):
    compare = getattr(args, 'compare', False)
    now = datetime.now(timezone.utc)
    try:
        since = parse_since(args.since, now)
    except argparse.ArgumentTypeError as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    if compare and since is None:
        print('error: --compare requires a bounded --since window; use a duration or ISO date instead of all',
              file=sys.stderr)
        return 2
    if compare:
        window = now - since
        if window <= timedelta(0):
            print('error: --compare requires a --since date earlier than now', file=sys.stderr)
            return 2
        previous_since = since - window
        sessions = collect(since, args.project, args.path, until=now)
        previous = collect(previous_since, args.project, args.path, until=since, skip_untouched=False)
    else:
        sessions = collect(since, args.project, args.path)
    report = summarize(sessions, args.top)
    if compare:
        report['compare'] = build_comparison(report, summarize(previous, args.top))
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report, f'last {args.since}' if since else 'all time')
        if compare:
            print_comparison(report['compare'])
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='Measure token spend from local Claude Code and Codex logs')
    add_arguments(ap)
    return run(ap.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())
