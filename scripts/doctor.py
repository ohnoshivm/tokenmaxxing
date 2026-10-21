#!/usr/bin/env python3
"""Read-only audit of fixed Claude Code context overhead."""
import argparse
import ast
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys

import audit


CHARS_PER_TOKEN = 4
MCP_SERVER_LIMIT = 5
INSTRUCTION_FILE_FINDING_TOKENS = 1_000
PLUGIN_SKILL_FINDING_COUNT = 5
PLUGIN_SKILL_FINDING_TOKENS = 500
AGENT_DESCRIPTION_FINDING_TOKENS = 500
RISKY_HOOK_EVENTS = ('SessionStart', 'UserPromptSubmit')
REGISTRY_PATH = Path(__file__).resolve().parents[1] / 'policy' / 'optimizer-registry.json'
OPTIMIZER_PROFILES = {
    'balanced': 'ponytail',
    'deep-reasoning': 'occam',
    'full-product': 'whittle',
}


def _home():
    return Path.home()


def _config_dir(home=None, override=None):
    home = home or _home()
    if override:
        return Path(override).expanduser().resolve()
    configured = os.environ.get('CLAUDE_CONFIG_DIR')
    if configured:
        return Path(configured).expanduser().resolve()
    return (home / '.claude').resolve()


def _config_source(override=None):
    if override:
        return '--config-dir'
    return 'CLAUDE_CONFIG_DIR' if os.environ.get('CLAUDE_CONFIG_DIR') else 'default'


def _read_text(path):
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except (OSError, UnicodeError):
        return ''


def _read_json(path, default=None):
    try:
        with path.open(encoding='utf-8') as handle:
            value = json.load(handle)
        return value
    except (OSError, UnicodeError, ValueError):
        return default


def _tokens(text):
    return len(text) // CHARS_PER_TOKEN


def _path_key(path):
    try:
        return str(path.resolve())
    except OSError:
        return str(path.absolute())


def _project_dirs(project_dir):
    current = project_dir.resolve()
    while True:
        yield current
        if current.parent == current:
            break
        current = current.parent


def _import_paths(text, source, home):
    """Return one-level @path imports from a CLAUDE.md body."""
    paths = []
    # Imports are paths beginning with ~, ./, ../, or a simple relative name.
    for match in re.finditer(r'(?<![\w])@([^\s<>"\'`]+)', text):
        raw = match.group(1).rstrip('),.;:!?]')
        if not raw:
            continue
        if raw.startswith('~/'):
            candidate = home / raw[2:]
        else:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = source.parent / candidate
        try:
            if candidate.is_file():
                paths.append(candidate.resolve())
        except OSError:
            continue
    return paths


def _instruction_files(project_dir, config_dir, home):
    files, seen = [], set()

    def add(path, loaded_by, source):
        key = _path_key(path)
        if key in seen or not path.is_file():
            return
        seen.add(key)
        content = _read_text(path)
        files.append({
            'path': key,
            'loaded_by': loaded_by,
            'source': source,
            'tokens': _tokens(content),
        })
        if loaded_by == 'claude' and path.name in ('CLAUDE.md', 'CLAUDE.local.md'):
            for imported in _import_paths(content, path, home):
                add(imported, 'claude', 'import')

    add(config_dir / 'CLAUDE.md', 'claude', 'global')
    for directory in _project_dirs(project_dir):
        for filename in ('CLAUDE.md', 'CLAUDE.local.md'):
            add(directory / filename, 'claude', 'project')
        add(directory / '.claude' / 'CLAUDE.md', 'claude', 'project')
        add(directory / 'AGENTS.md', 'codex', 'project')
    return files


def _scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, str) else value[1:-1]
        except (ValueError, SyntaxError):
            return value[1:-1]
    return value


def _frontmatter(text):
    """Read only simple YAML frontmatter name and description fields."""
    lines = text.lstrip('\ufeff').splitlines()
    if not lines or lines[0].strip() != '---':
        return {'name': '', 'description': ''}
    end = next((i for i in range(1, len(lines)) if lines[i].strip() in ('---', '...')), len(lines))
    fields = {'name': '', 'description': ''}
    index = 1
    while index < end:
        line = lines[index]
        match = re.match(r'^\s*(name|description)\s*:\s*(.*)$', line)
        if not match:
            index += 1
            continue
        key, value = match.groups()
        stripped = value.strip()
        if key == 'description' and stripped in ('|', '>', '|-', '>-', '|+', '>+'):
            block = []
            index += 1
            while index < end:
                child = lines[index]
                if child and not child[0].isspace():
                    break
                block.append(child.strip())
                index += 1
            fields[key] = ('\n' if stripped.startswith('|') else ' ').join(x for x in block if x)
            continue
        fields[key] = _scalar(stripped)
        index += 1
    return fields


def _skill_record(path, source):
    fields = _frontmatter(_read_text(path))
    frontmatter_name = fields['name'].strip()
    name = frontmatter_name or path.parent.name
    description = fields['description'].strip()
    return {
        'name': name,
        'source': source,
        'path': _path_key(path),
        'description_tokens': _tokens(description),
        'tokens': _tokens(frontmatter_name + description),
    }


def _direct_skill_files(directory):
    if not directory.is_dir():
        return []
    try:
        return sorted(path for path in directory.glob('*/SKILL.md') if path.is_file())
    except OSError:
        return []


def _plugin_records(value):
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _hook_info(value):
    hooks = value.get('hooks') if isinstance(value, dict) else None
    if not isinstance(hooks, dict):
        return [], 0
    events = sorted(str(event) for event in hooks)
    count = 0
    for event_hooks in hooks.values():
        if isinstance(event_hooks, list):
            count += len(event_hooks)
        elif isinstance(event_hooks, dict):
            nested = event_hooks.get('hooks')
            count += len(nested) if isinstance(nested, list) else 1
        elif event_hooks is not None:
            count += 1
    return events, count


def _enabled_plugins(settings):
    enabled = settings.get('enabledPlugins', {}) if isinstance(settings, dict) else {}
    if not isinstance(enabled, dict):
        return []
    return sorted(key for key, value in enabled.items() if isinstance(key, str) and value is True)


def _plugin_data(config_dir, settings, installed, known_skills):
    plugins, plugin_skill_records = [], []
    installed_map = installed.get('plugins', {}) if isinstance(installed, dict) else {}
    if not isinstance(installed_map, dict):
        installed_map = {}
    for plugin_key in _enabled_plugins(settings):
        skill_files, agent_files, command_files = [], [], []
        plugin_hook_events, hook_count = [], 0
        for record in _plugin_records(installed_map.get(plugin_key)):
            install_raw = record.get('installPath')
            if not isinstance(install_raw, str) or not install_raw:
                continue
            install_path = Path(install_raw).expanduser()
            if not install_path.is_absolute():
                install_path = config_dir / install_path
            skill_files.extend(_direct_skill_files(install_path / 'skills'))
            for folder, found in (('agents', agent_files), ('commands', command_files)):
                directory = install_path / folder
                try:
                    found.extend(path for path in directory.glob('*.md') if path.is_file())
                except OSError:
                    pass
            hooks_path = install_path / 'hooks' / 'hooks.json'
            hooks_value = _read_json(hooks_path, {})
            events, count = _hook_info(hooks_value)
            plugin_hook_events.extend(events)
            hook_count += count
        unique_skill_files = {_path_key(path): path for path in skill_files}
        skill_records = []
        for path in sorted(unique_skill_files.values()):
            key = _path_key(path)
            if key not in known_skills:
                record = _skill_record(path, 'plugin ' + plugin_key)
                skill_records.append(record)
                plugin_skill_records.append(record)
                known_skills.add(key)
        plugins.append({
            'name': plugin_key,
            'skills': len(unique_skill_files),
            'agents': len({_path_key(path) for path in agent_files}),
            'commands': len({_path_key(path) for path in command_files}),
            'hooks': hook_count,
            'hook_events': sorted(set(plugin_hook_events)),
            'always_loaded_tokens': sum(item['tokens'] for item in skill_records),
        })
    plugins.sort(key=lambda item: (-item['always_loaded_tokens'], item['name']))
    return plugins, plugin_skill_records


def _subagents(config_dir, project_dir):
    records, seen = [], set()
    for source, directory in (
        ('user', config_dir / 'agents'),
        ('project', project_dir / '.claude' / 'agents'),
    ):
        try:
            paths = sorted(directory.glob('*.md')) if directory.is_dir() else []
        except OSError:
            paths = []
        for path in paths:
            key = _path_key(path)
            if key in seen:
                continue
            seen.add(key)
            fields = _frontmatter(_read_text(path))
            description = fields['description']
            records.append({
                'name': fields['name'] or path.stem,
                'source': source,
                'path': key,
                'description_tokens': _tokens(description),
            })
    return records


def _transport(server):
    if not isinstance(server, dict):
        return 'unknown'
    kind = server.get('type')
    if isinstance(kind, str):
        normalized = kind.strip().lower()
        if normalized in ('stdio', 'http', 'sse', 'websocket'):
            return normalized
        if normalized:
            return 'other'
    if server.get('url'):
        return 'http'
    if server.get('command'):
        return 'stdio'
    return 'unknown'


def _mcp_servers(home, project_dir):
    servers = []
    global_config = _read_json(home / '.claude.json', {})
    if isinstance(global_config, dict):
        _append_servers(servers, global_config.get('mcpServers'))
        projects = global_config.get('projects')
        if isinstance(projects, dict):
            project_entry = projects.get(_path_key(project_dir))
            if not isinstance(project_entry, dict):
                project_entry = projects.get(str(project_dir))
            if isinstance(project_entry, dict):
                _append_servers(servers, project_entry.get('mcpServers'))
    project_config = _read_json(project_dir / '.mcp.json', {})
    if isinstance(project_config, dict):
        _append_servers(servers, project_config.get('mcpServers'))
    return sorted(servers, key=lambda item: (item['name'].lower(), item['transport']))


def _append_servers(output, value):
    if not isinstance(value, dict):
        return
    for name, settings in value.items():
        # Only names and transport labels leave this function; never serialize the server config.
        if isinstance(name, str):
            output.append({'name': name, 'transport': _transport(settings)})


def _settings_hook_records(config_dir, project_dir):
    records = []
    for label, path in (
        ('global', config_dir / 'settings.json'),
        ('project', project_dir / '.claude' / 'settings.json'),
    ):
        value = _read_json(path, {})
        events, count = _hook_info(value)
        if events:
            records.append({'source': label, 'events': events, 'hooks': count})
    return records


def _optimizer_status(settings, skill_files, registry_path=REGISTRY_PATH):
    registry = _read_json(Path(registry_path), {})
    tools = registry.get('tools', []) if isinstance(registry, dict) else []
    enabled = _enabled_plugins(settings)
    enabled_names = {key.split('@', 1)[0].lower() for key in enabled}
    skill_dirs = {path.parent.name.lower() for path in skill_files}
    active = []
    for tool in tools if isinstance(tools, list) else []:
        if not isinstance(tool, dict) or not isinstance(tool.get('id'), str):
            continue
        tool_id = tool['id']
        plugin = tool.get('claude_plugin')
        plugin_name = plugin.get('name') if isinstance(plugin, dict) else None
        reasons = []
        if isinstance(plugin_name, str) and plugin_name.lower() in enabled_names:
            reasons.append('plugin')
        if tool_id.lower() in skill_dirs:
            reasons.append('skill')
        if reasons:
            active.append({'id': tool_id, 'enabled_as': reasons})
    return {'active': active, 'stacked': len(active) > 1, 'profiles': OPTIMIZER_PROFILES}


def _duplicates(skill_records):
    by_name = defaultdict(list)
    for skill in skill_records:
        by_name[skill['name'].casefold()].append(skill)
    duplicates = []
    for grouped in by_name.values():
        sources = sorted({item['source'] for item in grouped})
        if len(grouped) > 1:
            duplicates.append({
                'name': grouped[0]['name'],
                'sources': sources,
                'count': len(grouped),
            })
    return sorted(duplicates, key=lambda item: item['name'].casefold())


def _findings(report, home=None):
    findings = []
    optimizer_ids = [item['id'] for item in report['optimizers']['active']]
    if len(optimizer_ids) > 1:
        profiles = ', '.join(f'{name}={optimizer}' for name, optimizer in report['optimizers']['profiles'].items())
        findings.append({
            'priority': 'HIGH',
            'impact_tokens': 0,
            'text': f"{len(optimizer_ids)} coding-behavior optimizers are active: {', '.join(optimizer_ids)}. "
                    f'Keep one at a time; profiles: {profiles}.',
        })
    for item in report['instructions']['files']:
        if item['loaded_by'] == 'claude' and item['tokens'] >= INSTRUCTION_FILE_FINDING_TOKENS:
            findings.append({
                'priority': 'MEDIUM',
                'impact_tokens': item['tokens'],
                'text': f"{item['path']} is ~{audit.fmt(item['tokens'])} tokens; move rarely-needed sections into a referenced file.",
            })
    for plugin in report['plugins']:
        if (plugin['skills'] >= PLUGIN_SKILL_FINDING_COUNT or
                plugin['always_loaded_tokens'] >= PLUGIN_SKILL_FINDING_TOKENS):
            findings.append({
                'priority': 'MEDIUM',
                'impact_tokens': plugin['always_loaded_tokens'],
                'text': f"Plugin {plugin['name']} adds {plugin['skills']} skills (~{audit.fmt(plugin['always_loaded_tokens'])} tokens); disable if unused.",
            })
    agent_tokens = [item for item in report['subagents']['items']
                    if item['description_tokens'] >= AGENT_DESCRIPTION_FINDING_TOKENS]
    for item in agent_tokens:
        findings.append({
            'priority': 'MEDIUM',
            'impact_tokens': item['description_tokens'],
            'text': f"Subagent {item['name']} has a ~{audit.fmt(item['description_tokens'])}-token description; shorten it to the routing cues needed at startup.",
        })
    duplicate_count = len(report['skills']['duplicates'])
    if duplicate_count:
        findings.append({
            'priority': 'LOW',
            'impact_tokens': 0,
            'text': f'{duplicate_count} duplicate skill names are present across sources; remove or rename the copies to make selection clearer.',
        })
    if report['mcp']['count'] > MCP_SERVER_LIMIT:
        findings.append({
            'priority': 'MEDIUM',
            'impact_tokens': 0,
            'text': f"{report['mcp']['count']} MCP servers exceed the {MCP_SERVER_LIMIT}-server threshold; defer or remove unused servers because their tool schemas add context.",
        })
    flagged = sorted({event for record in report['hooks']['settings'] + report['hooks']['plugins']
                      for event in record['events'] if event in RISKY_HOOK_EVENTS})
    if flagged:
        findings.append({
            'priority': 'MEDIUM',
            'impact_tokens': 0,
            'text': 'Hooks include ' + ' and '.join(flagged) + '; check whether their injected text is necessary on every session or turn.',
        })
    order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
    if report.get('config_dir_source') == 'CLAUDE_CONFIG_DIR' and home is not None:
        other = (Path(home) / '.claude').resolve()
        if other != Path(report['config_dir']) and ((other / 'CLAUDE.md').is_file() or (other / 'skills').is_dir()):
            findings.append({
                'priority': 'LOW',
                'impact_tokens': 0,
                'text': 'Another Claude config exists at ~/.claude; run `doctor --config-dir ~/.claude` to audit it too.',
            })
    findings.sort(key=lambda item: (order[item['priority']], -item['impact_tokens'], item['text']))
    return findings


def collect_report(project_dir=None, measure=True, config_dir=None):
    home = _home().resolve()
    project_dir = Path(project_dir or Path.cwd()).expanduser().resolve()
    override = config_dir
    config_dir = _config_dir(home, override)
    settings = _read_json(config_dir / 'settings.json', {})
    installed = _read_json(config_dir / 'plugins' / 'installed_plugins.json', {})

    instruction_files = _instruction_files(project_dir, config_dir, home)
    skill_records = []
    known_skills = set()
    for source, directory in (
        ('user', config_dir / 'skills'),
        ('project', project_dir / '.claude' / 'skills'),
    ):
        for path in _direct_skill_files(directory):
            key = _path_key(path)
            if key not in known_skills:
                skill_records.append(_skill_record(path, source))
                known_skills.add(key)
    plugins, plugin_skill_records = _plugin_data(config_dir, settings, installed, known_skills)
    skill_records.extend(plugin_skill_records)
    skill_records.sort(key=lambda item: (item['name'].casefold(), item['source'], item['path']))

    subagent_items = _subagents(config_dir, project_dir)
    mcp_servers = _mcp_servers(home, project_dir)
    settings_hooks = _settings_hook_records(config_dir, project_dir)
    plugin_hooks = [{'plugin': item['name'], 'events': item['hook_events'], 'hooks': item['hooks']}
                    for item in plugins if item['hook_events']]
    optimizer = _optimizer_status(settings, [Path(item['path']) for item in skill_records])

    claude_instruction_tokens = sum(item['tokens'] for item in instruction_files if item['loaded_by'] == 'claude')
    codex_instruction_tokens = sum(item['tokens'] for item in instruction_files if item['loaded_by'] == 'codex')
    skill_tokens = sum(item['tokens'] for item in skill_records)
    subagent_tokens = sum(item['description_tokens'] for item in subagent_items)
    estimated = claude_instruction_tokens + skill_tokens + subagent_tokens

    report = {
        'project_dir': str(project_dir),
        'config_dir': str(config_dir),
        'config_dir_source': _config_source(override),
        'instructions': {
            'files': instruction_files,
            'claude_tokens': claude_instruction_tokens,
            'codex_agents_tokens': codex_instruction_tokens,
        },
        'skills': {
            'count': len(skill_records),
            'tokens': skill_tokens,
            'longest_descriptions': sorted(
                ({'name': item['name'], 'source': item['source'], 'tokens': item['description_tokens']}
                 for item in skill_records),
                key=lambda item: (-item['tokens'], item['name'].casefold(), item['source']),
            )[:5],
            'duplicates': _duplicates(skill_records),
        },
        'plugins': plugins,
        'subagents': {
            'count': len(subagent_items),
            'tokens': subagent_tokens,
            'items': subagent_items,
        },
        'mcp': {
            'count': len(mcp_servers),
            'servers': mcp_servers,
            'over_threshold': len(mcp_servers) > MCP_SERVER_LIMIT,
        },
        'hooks': {
            'settings': settings_hooks,
            'plugins': plugin_hooks,
        },
        'optimizers': optimizer,
        'estimated_always_loaded_tokens': estimated,
        'measured': None,
    }
    if measure:
        since = datetime.now(timezone.utc) - timedelta(days=30)
        try:
            sessions = audit.collect(since=since)
            summary = audit.summarize(sessions)
            starting = summary['claude']['starting_context']
            report['measured'] = {
                'sessions': summary['claude'].get('sessions', 0),
                'median': starting.get('median'),
                'p90': starting.get('p90'),
            }
        except (OSError, ValueError, KeyError, TypeError):
            report['measured'] = {'sessions': 0, 'median': None, 'p90': None}
    report['findings'] = _findings(report, home)
    return report


def _human_report(report):
    lines = [f"Config dir: {report['config_dir']} (from {report['config_dir_source']})", '',
             f"TOKENMAXXING doctor — project {report['project_dir']}", '']
    ins = report['instructions']
    claude_files = [item for item in ins['files'] if item['loaded_by'] == 'claude']
    codex_files = [item for item in ins['files'] if item['loaded_by'] == 'codex']
    lines.append(f"Instructions: Claude ~{audit.fmt(ins['claude_tokens'])} tokens across {len(claude_files)} files")
    for item in claude_files:
        lines.append(f"  ~{audit.fmt(item['tokens'])} {item['path']}")
    lines.append(f"Codex AGENTS.md: ~{audit.fmt(ins['codex_agents_tokens'])} tokens across {len(codex_files)} files")

    skills = report['skills']
    lines.append(f"Skills: {skills['count']}; always-loaded metadata ~{audit.fmt(skills['tokens'])} tokens")
    if skills['longest_descriptions']:
        longest = ', '.join(f"{item['name']} ({audit.fmt(item['tokens'])})" for item in skills['longest_descriptions'])
        lines.append('  Longest descriptions: ' + longest)
    if skills['duplicates']:
        duplicates = ', '.join(f"{item['name']} ({item['count']})" for item in skills['duplicates'][:8])
        if len(skills['duplicates']) > 8:
            duplicates += f", +{len(skills['duplicates']) - 8} more"
        lines.append(f"  Duplicate names: {len(skills['duplicates'])} — {duplicates}")
    else:
        lines.append('  Duplicate names: none')

    lines.append('Enabled plugins (ranked by always-loaded skill metadata):')
    if report['plugins']:
        for item in report['plugins']:
            hooks = ','.join(item['hook_events']) or 'none'
            lines.append(f"  {item['name']}: {item['skills']} skills (~{audit.fmt(item['always_loaded_tokens'])} tokens), "
                         f"{item['agents']} agents, {item['commands']} commands, {item['hooks']} hooks [{hooks}]")
    else:
        lines.append('  none enabled')

    subagents = report['subagents']
    lines.append(f"Subagents: {subagents['count']} descriptions, ~{audit.fmt(subagents['tokens'])} tokens")
    mcp = report['mcp']
    lines.append(f"MCP servers: {mcp['count']} (server names and transport only; schemas are not estimated)")
    if mcp['servers']:
        lines.append('  ' + ', '.join(f"{item['name']} [{item['transport']}]" for item in mcp['servers']))

    lines.append('Hooks:')
    hook_records = report['hooks']['settings'] + report['hooks']['plugins']
    if hook_records:
        for item in report['hooks']['settings']:
            lines.append(f"  {item['source']} settings: {', '.join(item['events'])}")
        for item in report['hooks']['plugins']:
            lines.append(f"  plugin {item['plugin']}: {', '.join(item['events'])}")
        risky = sorted({event for item in hook_records for event in item['events'] if event in RISKY_HOOK_EVENTS})
        if risky:
            lines.append('  Review injected-text hooks: ' + ', '.join(risky))
    else:
        lines.append('  no hook events found')

    active = report['optimizers']['active']
    optimizer_text = ', '.join(f"{item['id']} ({'/'.join(item['enabled_as'])})" for item in active) or 'none'
    lines.append(f"Coding-behavior optimizers: {optimizer_text}")
    lines.append(f"Estimated always-loaded tokens: ~{audit.fmt(report['estimated_always_loaded_tokens'])}")
    measured = report['measured']
    if measured is None:
        lines.append('Measured starting context: skipped (--no-measure)')
    elif measured.get('median') is None:
        lines.append('Measured starting context (last 30d): unavailable; no Claude baseline found')
    else:
        median = measured['median']
        p90 = measured.get('p90')
        share = audit.pct(report['estimated_always_loaded_tokens'], median)
        gap = median - report['estimated_always_loaded_tokens']
        lines.append(f"Measured starting context (last 30d): median ~{audit.fmt(median)}, p90 ~{audit.fmt(p90 or 0)}; "
                     f"static estimate is {share} of median, remainder ~{audit.fmt(gap)} includes harness system prompt + tool schemas")

    lines.extend(['', 'Fixes (highest impact first)'])
    if report['findings']:
        for index, finding in enumerate(report['findings'], 1):
            lines.append(f"  {index}. [{finding['priority']}] {finding['text']}")
    else:
        lines.append('  No findings crossed the configured thresholds.')
    lines.append('')
    lines.append('Estimates use file characters ÷ 4; measured starting context is from local session logs.')
    return '\n'.join(lines)


def add_arguments(ap):
    ap.add_argument('--project-dir', type=Path, default=Path.cwd(), help='project root to inspect (default: current directory)')
    ap.add_argument('--config-dir', type=Path, help='Claude config directory to audit (default: $CLAUDE_CONFIG_DIR or ~/.claude)')
    ap.add_argument('--no-measure', action='store_true', help='skip reading the last 30 days of local session logs')
    ap.add_argument('--json', action='store_true', help='print machine-readable JSON')


def run(args):
    report = collect_report(
        project_dir=getattr(args, 'project_dir', None),
        measure=not getattr(args, 'no_measure', False),
        config_dir=getattr(args, 'config_dir', None),
    )
    if getattr(args, 'json', False):
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_human_report(report))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='Audit fixed Claude Code context overhead (read-only)')
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())
