#!/usr/bin/env python3
"""TOKENMAXXING audit: measure where tokens actually go, from local session logs.

Reads Claude Code transcripts (~/.claude*/projects/**/*.jsonl) and Codex rollouts
(~/.codex/sessions/**/*.jsonl). Read-only, offline, standard library only.
Nothing is uploaded; transcript text is never printed except short tool labels.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import fnmatch
import json
import os
import re
import shlex
from pathlib import Path
import statistics
import sys

# Relative cost weights per token, using Anthropic's documented prompt-caching
# multipliers (cache read 0.1x, 5-minute write 1.25x, 1-hour write 2x base input)
# and a 5x output/input price ratio. A ranking signal, not an invoice.
WEIGHTS = {'input': 1.0, 'cache_write_5m': 1.25, 'cache_write_1h': 2.0, 'cache_read': 0.1, 'output': 5.0}
CHARS_PER_TOKEN = 4  # rough estimate for tool output; usage fields are exact
REBUILD_MIN = 20_000  # cache write this large while reading less than it = prefix rebuilt


CHECK_PATTERN = re.compile(
    r'^(?:\S*/)?(?:pytest|vitest|jest|tsc|eslint|ruff|mypy)(?=\s|$)|'
    r'^(?:\S*/)?python(?:\d+(?:\.\d+)*)?\s+-m\s+(?:unittest|pytest)(?=\s|$)|'
    r'^(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:test|build|lint|typecheck|check)(?=\s|$)|'
    r'^cargo\s+(?:test|build|check|clippy)(?=\s|$)|^go\s+(?:test|build|vet)(?=\s|$)|'
    r'^make\s+(?:test|check|build)(?=\s|$)|^(?:\S*/)?(?:gradle|gradlew|mvn)\s+(?:.*\s)?test(?=\s|$)|'
    r'^swift\s+(?:test|build)(?=\s|$)|^playwright\s+test(?=\s|$)'
)
EDIT_TOOLS = {'Edit', 'MultiEdit', 'Write', 'NotebookEdit', 'apply_patch'}
SHELL_TOOLS = {'Bash', 'shell', 'shell_command', 'exec_command'}
MODEL_TIERS = Path(__file__).resolve().parents[1] / 'policy' / 'model-tiers.json'


def shell_segments(command):
    if isinstance(command, list) and all(isinstance(x, str) for x in command):
        if len(command) >= 3 and Path(command[0]).name in ('bash', 'sh', 'zsh') and 'c' in command[1]:
            command = command[2]
        else:
            return [command]
    if not isinstance(command, str):
        return []
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|\n')
        lexer.whitespace = ' \t\r'
        lexer.whitespace_split = True
        segments, current = [], []
        for word in lexer:
            if word and all(c in ';&|\n' for c in word):
                if current:
                    segments.append(current)
                current = []
            else:
                current.append(word)
        if current:
            segments.append(current)
        return segments
    except ValueError:
        return []


def check_commands(command):
    return [shlex.join(words) for words in shell_segments(command)
            if CHECK_PATTERN.match(' '.join(words))]


def skill_invocation(session, name):
    if not isinstance(name, str):
        return
    name = name.strip().lstrip('/').split()[0] if name.strip().lstrip('/') else ''
    if not name:
        return
    plugin, name = name.rsplit(':', 1) if ':' in name else (None, name)
    session.skills_used[(plugin, name)] += 1
    return plugin, name


def slash_invocation(session, content):
    if isinstance(content, list):
        content = '\n'.join(b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') in ('text', 'input_text'))
    if not isinstance(content, str):
        return
    tagged = re.search(r'<command-name>\s*/?([^<\s]+)\s*</command-name>', content)
    plain = re.match(r'^\s*/([\w:.-]+)(?:\s|$)', content)
    if tagged or plain:
        return skill_invocation(session, (tagged or plain).group(1))


def work_call(session, name, inp, position):
    if name == 'Skill':
        skill_invocation(session, inp.get('skill'))
    command = inp.get('command', inp.get('cmd', '')) if name in SHELL_TOOLS else ''
    checks = check_commands(command)
    if checks:
        session.work['checks'] += 1
    commit = False
    for words in shell_segments(command):
        if not words or Path(words[0]).name != 'git' or '--dry-run' in words:
            continue
        index = 1
        while index < len(words) and words[index] in ('-C', '-c', '--git-dir', '--work-tree'):
            index += 2
        if index < len(words) and words[index] == 'commit':
            commit = True
    normalized = tuple(shlex.join(words) for words in shell_segments(command)) if checks else ()
    return name in EDIT_TOOLS, normalized, commit, position


def work_result(session, call, success):
    if call is None or success is None:
        return
    edit, checks, commit, position = call
    if edit and success:
        session.work['edits'] += 1
        session.last_edit = max(session.last_edit, position)
    if checks:
        session.work['checks_passed' if success else 'checks_failed'] += 1
        if success:
            session.passing_checks.add(tuple(checks))
            session.last_passing_check = max(session.last_passing_check, position)
    if commit and success:
        session.work['commits'] += 1


def codex_outcome(output):
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return codex_outcome(parsed)
        match = re.search(r'(?:Process exited with code|exited with (?:code|status)|Exit code:)\s*(-?\d+)', output)
        if match:
            return int(match.group(1)) == 0
        if output.startswith('Success.'):
            return True
        if output.startswith(('Failed', 'Error:', 'error:', 'apply_patch verification failed')):
            return False
    if isinstance(output, dict):
        code = output.get('exit_code')
        if code is None and isinstance(output.get('metadata'), dict):
            code = output['metadata'].get('exit_code')
        if isinstance(code, int):
            return code == 0
        if isinstance(output.get('success'), bool):
            return output['success']
    return None


def work_summary(sessions):
    counts, skills, models = Counter(), Counter(), Counter()
    for session in sessions:
        counts.update(session.work)
        counts['distinct_passing_checks'] += len(session.passing_checks)
        if session.work['edits']:
            key = ('verified_edit_sessions' if session.last_passing_check > session.last_edit
                   else 'unverified_edit_sessions')
            counts[key] += 1
        skills.update(session.skills_used)
        models.update(session.model_units)
    work = {key: counts[key] for key in ('edits', 'checks', 'checks_passed', 'checks_failed', 'commits',
                                       'distinct_passing_checks', 'verified_edit_sessions', 'unverified_edit_sessions')}
    weighted = sum(session.weighted() for session in sessions)
    work['weighted_units'] = weighted
    work['usage_per_passing_check_raw'] = weighted / counts['checks_passed'] if counts['checks_passed'] else None
    work['usage_per_passing_check'] = weighted / counts['distinct_passing_checks'] if counts['distinct_passing_checks'] else None
    work['usage_per_distinct_passing_check'] = work['usage_per_passing_check']
    known_checks = counts['checks_passed'] + counts['checks_failed']
    edited = counts['verified_edit_sessions'] + counts['unverified_edit_sessions']
    work['rework_rate'] = counts['checks_failed'] / known_checks if known_checks else None
    work['verified_edit_share'] = counts['verified_edit_sessions'] / edited if edited else None
    tiers = json.loads(MODEL_TIERS.read_text(encoding='utf-8'))
    mix, unknown = Counter(), []
    for model, units in models.items():
        tier = next((tier for pattern, tier in tiers.items() if fnmatch.fnmatchcase(model.lower(), pattern)), 'unknown')
        mix[tier] += units
        if tier == 'unknown':
            unknown.append(model)
    total = sum(mix.values())
    work['model_mix'] = {tier: mix[tier] / total if total else None
                         for tier in ('premium', 'standard', 'economy', 'unknown')}
    work['premium_share'] = work['model_mix']['premium']
    work['unknown_models'] = sorted(unknown)
    return work, [{'name': name, 'plugin': plugin, 'count': count}
                  for (plugin, name), count in sorted(skills.items(), key=lambda x: (x[0][1], x[0][0] or ''))]


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
                 'rebuilds', 'results', 'reads', 'subagent', 'work', 'skills_used', 'model_units',
                 'last_edit', 'last_passing_check', 'passing_checks')

    def __init__(self, sid, project, agent, subagent=False):
        self.id, self.project, self.agent, self.subagent = sid, project, agent, subagent
        self.start, self.turns, self.baseline = None, 0, None
        self.usage = Counter()
        self.models = Counter()
        self.rebuilds = []   # cache_write tokens per rebuild event
        self.results = []    # (est_tokens, label, carry_turns)
        self.reads = Counter()
        self.work, self.skills_used, self.model_units = Counter(), Counter(), Counter()
        self.last_edit = self.last_passing_check = -1
        self.passing_checks = set()

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


def parse_claude(path, since=None, until=None, seen_msgs=None, seen_tool_ids=None, root=None, seen_user_msgs=None):
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
    calls, work_calls = {}, {}
    seen_user_msgs = seen_user_msgs if seen_user_msgs is not None else set()
    fresh_calls, result_ids = set(), set()
    pending = []  # [est_tokens, label, turn_index] awaiting carry computation
    first_api_message = True
    baseline_allowed = True

    def close_segment():
        for item in pending:
            s.results.append((item[0], item[1], max(s.turns - item[2], 0)))
        pending.clear()

    with path.open(encoding='utf-8', errors='replace') as f:
        for position, line in enumerate(f):
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
            if '"assistant"' not in line and '"user"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if not isinstance(o, dict):
                continue
            kind, msg = o.get('type'), o.get('message') or {}
            if not isinstance(msg, dict):
                continue
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
                        if not isinstance(inp, dict):
                            inp = {}
                        if in_window(ts, since, until):
                            work_calls[call_id] = work_call(s, b.get('name', '?'), inp, position)
                        calls[call_id] = tool_label(b.get('name', '?'), inp)
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
                weighted_before = s.weighted()
                inp_t = u.get('input_tokens') or 0
                cr = u.get('cache_read_input_tokens') or 0
                cw = u.get('cache_creation_input_tokens') or 0
                split = u.get('cache_creation') or {}
                cw1h = split.get('ephemeral_1h_input_tokens') or 0
                cw5m = cw - cw1h if split else cw
                s.usage.update({'input': inp_t, 'cache_read': cr, 'cache_write_5m': cw5m,
                                'cache_write_1h': cw1h, 'output': u.get('output_tokens') or 0})
                s.models[model] += 1
                s.model_units[model] += s.weighted() - weighted_before
                if s.baseline is None and baseline_allowed:
                    s.baseline = inp_t + cr + cw
                    s.start = ts
                elif cw >= REBUILD_MIN and cr < cw:
                    s.rebuilds.append(cw)
                s.turns += 1
            elif kind == 'user':
                if not in_window(parse_ts(o.get('timestamp')), since, until):
                    continue
                content = msg.get('content')
                uid = o.get('uuid') or msg.get('id')
                if not uid or uid not in seen_user_msgs:
                    slash_invocation(s, content)
                    if uid:
                        seen_user_msgs.add(uid)
                for b in content if isinstance(content, list) else []:
                    if isinstance(b, dict) and b.get('type') == 'tool_result':
                        call_id = b.get('tool_use_id')
                        if not call_id or call_id not in fresh_calls or call_id in result_ids:
                            continue
                        result_ids.add(call_id)
                        work_result(s, work_calls.get(call_id), not b.get('is_error', False))
                        t = est_tokens(b.get('content'))
                        if t:
                            pending.append([t, calls.get(call_id, '?'), s.turns])
    close_segment()
    return s if s.turns or s.work or s.skills_used else None


def parse_codex(path, since=None, until=None, seen_sessions=None):
    """Codex logs cumulative token_count events; the last one is the session total."""
    seen_sessions = seen_sessions if seen_sessions is not None else set()
    s = Session(path.stem, '?', 'codex')
    last, model, limits, meta_id = None, None, None, None
    work_calls, result_ids = {}, set()
    last_weighted = 0
    user_sources = defaultdict(Counter)
    with path.open(encoding='utf-8', errors='replace') as f:
        for position, line in enumerate(f):
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if not isinstance(o, dict):
                continue
            p = o.get('payload') or {}
            if not isinstance(p, dict):
                continue
            kind = p.get('type')
            call_id = p.get('call_id')
            if in_window(parse_ts(o.get('timestamp')), since, until):
                if kind in ('function_call', 'custom_tool_call', 'exec_command_begin', 'patch_apply_begin') and call_id not in work_calls:
                    inp = p.get('arguments', p.get('input', {}))
                    if isinstance(inp, str):
                        try:
                            inp = json.loads(inp)
                        except ValueError:
                            inp = {}
                    if not isinstance(inp, dict):
                        inp = {}
                    name = p.get('name', '')
                    if kind == 'exec_command_begin':
                        name, inp = 'exec_command', {'command': p.get('command')}
                    elif kind == 'patch_apply_begin':
                        name = 'apply_patch'
                    if call_id:
                        work_calls[call_id] = work_call(s, name.rsplit('.', 1)[-1], inp, position)
                elif kind in ('function_call_output', 'custom_tool_call_output', 'exec_command_end', 'patch_apply_end') and call_id not in result_ids:
                    outcome = codex_outcome(p.get('output', p))
                    if outcome is not None:
                        work_result(s, work_calls.get(call_id), outcome)
                        result_ids.add(call_id)
                elif kind in ('user_message', 'message') and (kind == 'user_message' or p.get('role') == 'user'):
                    key = slash_invocation(s, p.get('message', p.get('content')))
                    if key:
                        previous_count = max((counts[key] for counts in user_sources.values()), default=0)
                        user_sources[o.get('type')][key] += 1
                        if user_sources[o.get('type')][key] <= previous_count:
                            s.skills_used[key] -= 1  # event_msg and response_item mirror the same user turn
            if o.get('type') == 'session_meta':
                meta_id = p.get('id') or meta_id
                s.project = '/'.join(Path(p.get('cwd', '?')).parts[-2:])
                s.start = parse_ts(p.get('timestamp') or o.get('timestamp'))
            elif o.get('type') == 'turn_context':
                model = p.get('model') or model
            elif p.get('type') == 'token_count' and p.get('info'):
                last = p['info']
                limits = p.get('rate_limits') or limits
                total_usage = last.get('total_token_usage') or {}
                cached = total_usage.get('cached_input_tokens') or 0
                weighted_now = (max((total_usage.get('input_tokens') or 0) - cached, 0) +
                                cached * WEIGHTS['cache_read'] + (total_usage.get('output_tokens') or 0) * WEIGHTS['output'])
                s.model_units[model or 'unknown'] += max(0, weighted_now - last_weighted)
                last_weighted = weighted_now
                s.turns += 1
                if model:
                    s.models[model] += 1
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

    seen_msgs, seen_tool_ids, seen_codex_sessions, seen_user_msgs = set(), set(), set(), set()
    sessions = []
    for _, agent, p, root in dated:
        try:
            if agent == 'claude':
                s = parse_claude(p, since, until, seen_msgs, seen_tool_ids, root, seen_user_msgs)
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
        main = s.models.most_common(1)[0][0] if s.models else 'unknown'
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
    report['work'], report['skills_used'] = work_summary(sessions)
    report['findings'] = findings(report)
    return report


def findings(r):
    """Turn measurements into ranked, specific actions. Thresholds are deliberate and documented."""
    c, out = r['claude'], []
    work = r.get('work', {})
    if (work.get('rework_rate') or 0) > .25:
        out.append('Work proxy: failed checks exceed 25% of known outcomes; failed checks are being paid for twice — tighten briefs / run targeted tests first.')
    if work.get('verified_edit_share') is not None and work['verified_edit_share'] < .5:
        out.append('Work proxy: edits often end without a passing check (verified-edit share below 50%).')
    if not c['api_turns']:
        return out or ['No Claude Code usage found for this window.']
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
        print_work(r['work'])
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
    if not c['api_turns']:
        print_work(r['work'])
    say('Findings (highest impact first)')
    for i, f in enumerate(r['findings'], 1):
        say(f'  {i}. {f}')
    say('\nWeighted units use documented cache multipliers (read 0.1x, write 1.25x/2x) and 5x output; '
        'tool sizes are ~4 chars/token estimates.')


def print_work(w):
    print('Work (proxy — counted from tool calls, not a quality judgement)')
    print(f"  edits {w['edits']} · checks {w['checks']} ({w['checks_passed']} passed, {w['checks_failed']} failed) · commits {w['commits']}")
    edited = w['verified_edit_sessions'] + w['unverified_edit_sessions']
    print(f"  rework rate {pct(w['rework_rate'] or 0, 1) if w['rework_rate'] is not None else '—'} · "
          f"verified-edit sessions {w['verified_edit_sessions']}/{edited} ({pct(w['verified_edit_sessions'], edited)})")
    value = fmt(w['usage_per_passing_check']) + ' units' if w['usage_per_passing_check'] is not None else 'n/a'
    print(f"  usage per passing check {value} (distinct commands per session: {w['distinct_passing_checks']})")
    print('  model mix: ' + ' · '.join(f'{tier} {pct(share, 1)}' for tier, share in w['model_mix'].items() if share is not None))
    print('  premium share: lower usually = cheaper, check quality')
    if w['unknown_models']:
        print('  unknown model tiers: ' + ', '.join(w['unknown_models']))
    print('')


WORK_COMPARE_METRICS = (
    ('usage_per_passing_check', 'Usage per passing check'),
    ('rework_rate', 'Rework rate'),
    ('verified_edit_share', 'Verified-edit share'),
    ('premium_share', 'Premium share'),
)


COMPARE_METRICS = (
    ('weighted_units_per_turn', 'Weighted units / turn'),
    ('cache_hit_rate', 'Cache hit rate'),
    ('median_starting_context', 'Median starting context'),
    ('cache_rebuilds_per_100_turns', 'Cache rebuilds / 100 turns'),
    ('tool_output_tokens_per_turn', 'Tool output tokens / turn'),
    ('output_tokens_per_turn', 'Output tokens / turn'),
)


def compare_metrics(report):
    c = report['claude']
    turns = c['api_turns']
    if not turns:
        return {'api_turns': 0, **{key: None for key, _ in COMPARE_METRICS}}
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
    return {'api_turns': turns, **{key: round(value, 4) if value is not None else None
                                   for key, value in values.items()}}


def build_comparison(current, previous):
    current_values = compare_metrics(current)
    previous_values = compare_metrics(previous)
    delta = {'api_turns': current_values['api_turns'] - previous_values['api_turns']}
    for key, _ in COMPARE_METRICS:
        now, before = current_values[key], previous_values[key]
        delta[key] = round(now - before, 4) if now is not None and before is not None else None
    enough = min(current['work']['checks_passed'], previous['work']['checks_passed']) >= 5
    for key, _ in WORK_COMPARE_METRICS:
        now = current['work'][key] if enough else None
        before = previous['work'][key] if enough else None
        current_values[key], previous_values[key] = now, before
        delta[key] = now - before if now is not None and before is not None else None
    return {'current': current_values, 'previous': previous_values, 'delta': delta, 'work_too_few_checks': not enough}


def print_comparison(data):
    print('\nWindow comparison (per Claude API turn)')
    turns_delta = data['delta']['api_turns']
    print(f"  API turns: {fmt(data['current']['api_turns'])} current · {fmt(data['previous']['api_turns'])} previous · "
          f"delta {'+' if turns_delta >= 0 else '-'}{fmt(abs(turns_delta))}")
    metrics = COMPARE_METRICS + (WORK_COMPARE_METRICS if 'work_too_few_checks' in data else ())
    for key, label in metrics:
        if (key, label) in WORK_COMPARE_METRICS and data.get('work_too_few_checks'):
            print(f'  {label}: n/a (too few checks)')
            continue
        current, previous, delta = (data[period][key] for period in ('current', 'previous', 'delta'))
        if key in ('cache_hit_rate', 'cache_rebuilds_per_100_turns', 'rework_rate', 'verified_edit_share', 'premium_share'):
            scale = 1 if key == 'cache_rebuilds_per_100_turns' else 100
            precision = 1 if key == 'cache_rebuilds_per_100_turns' else 0
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
            if key in ('output_tokens_per_turn', 'premium_share'):
                direction = 'neutral'
            elif delta == 0:
                direction = 'unchanged'
            else:
                better = delta > 0 if key in ('cache_hit_rate', 'verified_edit_share') else delta < 0
                direction = 'better' if better else 'worse'
        suffix = f' · {direction}' if direction else ''
        print(f'  {label}: {values[0]} current · {values[1]} previous · delta {values[2]}{change}{suffix}')


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
