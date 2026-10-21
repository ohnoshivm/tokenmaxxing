#!/usr/bin/env python3
"""TOKENMAXXING fix: turn audit/doctor findings into reversible actions.

Default is a dry run. `--apply` only moves files, never deletes them, and writes
a manifest first so `--undo` can put everything back. Standard library only;
settings.json and provider config are never written.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

import audit
import doctor

ARCHIVE_DIR = 'tokenmaxxing-archive'
MIN_CLAUDE_SESSIONS = 10
HEADING = re.compile(r'^(#{1,3})\s+(.+?)\s*$')


def _now():
    return datetime.now(timezone.utc)


def _user_skill_dirs(config_dir):
    """Skill directories directly under <config>/skills; the link itself for symlinks."""
    skills_dir = config_dir / 'skills'
    if not skills_dir.is_dir():
        return []
    found = []
    try:
        entries = sorted(skills_dir.iterdir())
    except OSError:
        return []
    for entry in entries:
        if entry.name.startswith('.'):
            continue
        skill_md = entry / 'SKILL.md'
        if not skill_md.is_file():
            continue
        fields = doctor._frontmatter(doctor._read_text(skill_md))
        name = fields['name'].strip() or entry.name
        found.append({
            'dir': entry,
            'name': name,
            'tokens': doctor._tokens(name + fields['description'].strip()),
        })
    return found


def _used_names(skills, plugin_skills):
    used = {key.casefold() for key in skills}
    for scoped in plugin_skills:
        used.add(scoped.casefold())
        if ':' in scoped:
            used.add(scoped.partition(':')[2].casefold())
    return used


def _sections(text, limit=5):
    """Largest heading sections of an instruction file, by estimated tokens."""
    blocks, heading, body = [], 'preamble', []
    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            blocks.append((heading, body))
            heading, body = match.group(2), []
        else:
            body.append(line)
    blocks.append((heading, body))
    sized = [{'section': name, 'tokens': doctor._tokens('\n'.join(lines))} for name, lines in blocks]
    return sorted((item for item in sized if item['tokens']), key=lambda item: -item['tokens'])[:limit]


def _skill_actions(config_dir, since_label, claude_sessions, used, keep, report):
    actions = []
    for skill in _user_skill_dirs(config_dir):
        name = skill['name']
        if name.casefold() in {item.casefold() for item in keep} or skill['dir'].name.casefold() in {
                item.casefold() for item in keep}:
            actions.append({'kind': 'skill', 'name': name, 'auto': False, 'est_tokens': 0,
                            'detail': 'kept by --keep'})
            continue
        if claude_sessions < MIN_CLAUDE_SESSIONS:
            actions.append({'kind': 'skill', 'name': name, 'auto': False, 'est_tokens': 0,
                            'detail': f'skipped: window has {claude_sessions} Claude sessions '
                                      f'(needs {MIN_CLAUDE_SESSIONS}) to tell used from unused'})
            continue
        if name.casefold() in used or skill['dir'].name.casefold() in used:
            continue
        actions.append({'kind': 'skill', 'name': name, 'dir': skill['dir'], 'auto': True,
                        'est_tokens': skill['tokens'],
                        'detail': f'0 invocations in {since_label}'})
    for duplicate in report['skills']['duplicates']:
        actions.append({
            'kind': 'duplicate', 'name': duplicate['name'], 'auto': False, 'est_tokens': 0,
            'detail': f"{duplicate['count']} copies ({', '.join(duplicate['sources'])}); "
                      'which copy Claude Code loads is not determinable from disk, so rename or remove one by hand',
        })
    return actions


def _suggestions(actions, report):
    active = [item['id'] for item in report['optimizers']['active']]
    if len(active) > 1:
        profiles = ', '.join(f'{name}={tool}' for name, tool in report['optimizers']['profiles'].items())
        commands = ' '.join(f'/plugin disable {name}' for name in active[1:])
        actions.append({'kind': 'optimizers', 'name': ', '.join(active), 'auto': False, 'est_tokens': 0,
                        'detail': f'keep one coding-behavior optimizer; disable the rest: {commands}. '
                                  f'Profiles: {profiles}'})
    for item in report['instructions']['files']:
        if item['loaded_by'] != 'claude' or item['tokens'] < doctor.INSTRUCTION_FILE_FINDING_TOKENS:
            continue
        sections = _sections(doctor._read_text(Path(item['path'])))
        listing = ', '.join(f"{section['section']} (~{audit.fmt(section['tokens'])})" for section in sections)
        actions.append({'kind': 'instructions', 'name': item['path'], 'auto': False,
                        'est_tokens': item['tokens'],
                        'detail': f"~{audit.fmt(item['tokens'])} tokens; largest sections: {listing}. "
                                  'Move rarely-needed sections into a referenced file'})
    for finding in report['findings']:
        if finding['priority'] == 'HIGH' and finding['impact_tokens'] == 0:
            continue  # stacked optimizers are reported above with exact commands
        actions.append({'kind': finding['priority'].lower(), 'name': 'doctor finding', 'auto': False,
                        'est_tokens': finding['impact_tokens'], 'detail': finding['text']})
    return actions


def build_plan(config_dir, since='30d', keep=(), project_dir=None):
    since_dt = audit.parse_since(since, _now())
    sessions = audit.collect(since=since_dt)
    skills, plugin_skills = audit.skill_usage(sessions)
    claude_sessions = sum(1 for s in sessions if s.agent == 'claude' and not s.subagent)
    report = doctor.collect_report(project_dir=project_dir, measure=False, config_dir=config_dir)
    actions = _skill_actions(config_dir, f'last {since}', claude_sessions,
                             _used_names(skills, plugin_skills), keep, report)
    actions = _suggestions(actions, report)
    return {
        'config_dir': str(config_dir),
        'since': since,
        'claude_sessions': claude_sessions,
        'actions': actions,
    }


def _write_manifest(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def _new_run_id(base):
    stamp = _now().strftime('%Y%m%dT%H%M%SZ')
    run_id, counter = stamp, 1
    while (base / run_id).exists():
        counter += 1
        run_id = f'{stamp}-{counter}'
    return run_id


def apply_plan(plan, version):
    config_dir = Path(plan['config_dir'])
    archive = config_dir / ARCHIVE_DIR
    run_id = _new_run_id(archive)
    run_dir = archive / run_id
    movers = [item for item in plan['actions'] if item['auto']]
    manifest = {
        'run_id': run_id,
        'version': version,
        'created': _now().isoformat(timespec='seconds'),
        'config_dir': str(config_dir),
        'moves': [{'src': str(item['dir']), 'dst': str(run_dir / 'skills' / item['dir'].name),
                   'kind': 'skill', 'name': item['name'], 'est_tokens': item['est_tokens'], 'done': False}
                  for item in movers],
    }
    manifest_path = run_dir / 'manifest.json'
    # Written before the first move so a crash still leaves an undoable record.
    _write_manifest(manifest_path, manifest)
    for entry in manifest['moves']:
        source, target = Path(entry['src']), Path(entry['dst'])
        try:
            if target.exists() or target.is_symlink():
                raise FileExistsError(f'{target} already exists')
            target.parent.mkdir(parents=True, exist_ok=True)
            os.rename(source, target)  # moves a symlink as a link, never its target
            entry['done'] = True
        except OSError as error:
            entry['error'] = str(error)
        _write_manifest(manifest_path, manifest)
    return run_id, manifest_path, manifest


def _manifests(config_dir):
    root = Path(config_dir) / ARCHIVE_DIR
    try:
        paths = sorted(root.glob('*/manifest.json'), reverse=True)
    except OSError:
        return []
    out = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            out.append((path, data))
    return out


def undo(config_dir, run_id=None):
    found = _manifests(config_dir)
    if not found:
        return {'ok': False, 'error': f'no fix runs found under {Path(config_dir) / ARCHIVE_DIR}'}
    if run_id:
        found = [(path, data) for path, data in found if data.get('run_id') == run_id]
        if not found:
            return {'ok': False, 'error': f'no run {run_id} under {Path(config_dir) / ARCHIVE_DIR}'}
    path, manifest = found[0]
    if manifest.get('undone_at'):
        return {'ok': True, 'run_id': manifest.get('run_id'), 'already_undone': True, 'restored': [],
                'conflicts': []}
    restored, conflicts = [], []
    for entry in manifest.get('moves', []):
        if not entry.get('done') or entry.get('undone'):
            continue
        source, target = Path(entry['src']), Path(entry['dst'])
        if source.exists() or source.is_symlink():
            conflicts.append({'src': str(source), 'reason': 'path already exists again'})
            continue
        try:
            source.parent.mkdir(parents=True, exist_ok=True)
            os.rename(target, source)
            entry['undone'] = True
            restored.append(str(source))
        except OSError as error:
            conflicts.append({'src': str(source), 'reason': str(error)})
    if not conflicts:
        manifest['undone_at'] = _now().isoformat(timespec='seconds')
    _write_manifest(path, manifest)
    return {'ok': True, 'run_id': manifest.get('run_id'), 'restored': restored,
            'conflicts': conflicts, 'already_undone': False}


def _list_runs(config_dir):
    runs = []
    for _, manifest in _manifests(config_dir):
        moves = manifest.get('moves', [])
        runs.append({
            'run_id': manifest.get('run_id'),
            'created': manifest.get('created'),
            'moved': sum(1 for entry in moves if entry.get('done')),
            'undone': bool(manifest.get('undone_at')),
            'manifest': str(Path(config_dir) / ARCHIVE_DIR / str(manifest.get('run_id')) / 'manifest.json'),
        })
    return runs


def _tool_command(*parts):
    return ' '.join(['python3', str(Path(__file__).resolve().parents[1] / 'tokenmaxxing.py'), *parts])


def _human(plan, applied=None, undo_info=None, runs=None, apply_requested=False):
    lines = []
    if runs is not None:
        lines.append(f"Fix runs under {Path(plan['config_dir']) / ARCHIVE_DIR}")
        for run in runs:
            state = 'undone' if run['undone'] else f"{run['moved']} moved"
            lines.append(f"  {run['run_id']}  {run['created']}  {state}")
        return '\n'.join(lines) if len(lines) > 1 else lines[0] + '\n  none'
    if undo_info is not None:
        if not undo_info['ok']:
            return f"error: {undo_info['error']}"
        if undo_info['already_undone']:
            return f"Run {undo_info['run_id']} was already undone; nothing moved."
        lines.append(f"Restored {len(undo_info['restored'])} path(s) from run {undo_info['run_id']}")
        for path in undo_info['restored']:
            lines.append(f'  + {path}')
        for conflict in undo_info['conflicts']:
            lines.append(f"  ! not restored: {conflict['src']} ({conflict['reason']})")
        if undo_info['conflicts']:
            lines.append('Resolve the paths above, then run the same --undo again.')
        return '\n'.join(lines)

    if applied:
        mode = 'apply'
    elif apply_requested:
        mode = 'apply requested, nothing to move (no files changed)'
    else:
        mode = 'dry run (no files changed)'
    lines.append(f"TOKENMAXXING fix — {mode} · window last {plan['since']} · "
                 f"{plan['claude_sessions']} Claude sessions")
    lines.append(f"Config dir: {plan['config_dir']}")
    auto = [item for item in plan['actions'] if item['auto']]
    skipped = [item for item in plan['actions'] if item['kind'] == 'skill' and not item['auto']]
    manual = [item for item in plan['actions'] if item['kind'] not in ('skill', 'duplicate')]
    duplicates = [item for item in plan['actions'] if item['kind'] == 'duplicate']
    if auto:
        lines.append('Archive unused skills (auto)')
        for item in auto:
            lines.append(f"  - {item['name']} (~{audit.fmt(item['est_tokens'])} tokens/session, {item['detail']})")
    else:
        lines.append('Archive unused skills (auto): nothing to archive')
    for item in skipped:
        lines.append(f"  · {item['name']}: {item['detail']}")
    if duplicates:
        lines.append('Duplicate skill copies (manual)')
        for item in duplicates:
            lines.append(f"  · {item['name']}: {item['detail']}")
    if manual:
        lines.append('Suggested (manual)')
        for item in manual:
            lines.append(f"  · {item['detail']}")
    total = sum(item['est_tokens'] for item in auto)
    lines.append(f"Estimated saving: ~{audit.fmt(total)} tokens per session (estimate, doctor\'s skill metadata method)")
    if applied:
        manifest = applied['manifest']
        moved = [entry for entry in manifest['moves'] if entry.get('done')]
        archive = Path(manifest['config_dir']) / ARCHIVE_DIR / manifest['run_id']
        lines.append(f"Moved {len(moved)} skill(s) to {archive}")
        for entry in moved:
            lines.append(f"  {entry['name']} -> {entry['dst']}")
        failed = [entry for entry in manifest['moves'] if entry.get('error')]
        for entry in failed:
            lines.append(f"  ! {entry['name']}: {entry['error']}")
        lines.append(f"Undo: {_tool_command('fix', '--undo', manifest['run_id'], '--config-dir', plan['config_dir'])}")
        lines.append('Restart Claude Code sessions to pick up the change.')
    elif auto:
        lines.append(f"Apply with: {_tool_command('fix', '--apply', '--config-dir', plan['config_dir'])}")
    return '\n'.join(lines)


def add_arguments(ap):
    ap.add_argument('--since', default='30d', help='usage window: 7d, 24h, all, or ISO date (default 30d)')
    ap.add_argument('--config-dir', type=Path, help='Claude config directory (default: $CLAUDE_CONFIG_DIR or ~/.claude)')
    ap.add_argument('--project-dir', type=Path, default=Path.cwd(), help='project root to inspect for duplicates')
    ap.add_argument('--keep', action='append', default=[], metavar='NAME', help='never archive this skill (repeatable)')
    ap.add_argument('--apply', action='store_true', help='execute the auto-applicable actions')
    ap.add_argument('--undo', nargs='?', const='', metavar='RUN_ID', help='restore a previous run (default: most recent)')
    ap.add_argument('--list', action='store_true', help='list past runs from their manifests')
    ap.add_argument('--json', action='store_true', help='machine-readable output')


def run(args):
    config_dir = doctor._config_dir(doctor._home(), getattr(args, 'config_dir', None))
    version = '2.0.0'
    if getattr(args, 'list', False):
        runs = _list_runs(config_dir)
        if getattr(args, 'json', False):
            print(json.dumps({'config_dir': str(config_dir), 'runs': runs}, indent=2))
        else:
            print(_human({'config_dir': str(config_dir)}, runs=runs))
        return 0
    if getattr(args, 'undo', None) is not None:
        info = undo(config_dir, getattr(args, 'undo') or None)
        if getattr(args, 'json', False):
            print(json.dumps(info, indent=2))
        else:
            print(_human({'config_dir': str(config_dir)}, undo_info=info))
        return 0 if info['ok'] else 2
    try:
        plan = build_plan(config_dir, args.since, args.keep or (), args.project_dir)
    except (OSError, argparse.ArgumentTypeError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    applied = None
    apply_requested = bool(getattr(args, 'apply', False))
    if apply_requested and any(item['auto'] for item in plan['actions']):
        run_id, manifest_path, manifest = apply_plan(plan, version)
        applied = {'run_id': run_id, 'manifest_path': str(manifest_path), 'manifest': manifest}
    if getattr(args, 'json', False):
        payload = {'dry_run': applied is None, **plan,
                   'actions': [{key: value for key, value in item.items() if key != 'dir'}
                               for item in plan['actions']],
                   'estimated_tokens_per_session': sum(item['est_tokens'] for item in plan['actions']
                                                      if item['auto'])}
        if applied:
            payload['applied'] = applied
        print(json.dumps(payload, indent=2))
    else:
        print(_human(plan, applied, apply_requested=apply_requested))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='tokenmaxxing fix',
                                     description='Archive unused context and suggest fixes; reversible, dry run by default')
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())
