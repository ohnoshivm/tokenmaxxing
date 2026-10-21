#!/usr/bin/env python3
"""Plan and safely archive unused Claude Code skills, with manifest-based undo."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import audit
import doctor


VERSION = '2.0.0'
MIN_CLAUDE_SESSIONS = 10
RUN_ID_RE = re.compile(r'^\d{8}T\d{6}Z$')


def _run_id(config_dir, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    archive = config_dir / 'tokenmaxxing-archive'
    while (archive / now.strftime('%Y%m%dT%H%M%SZ')).exists():
        now += timedelta(seconds=1)
    return now.strftime('%Y%m%dT%H%M%SZ')


def _lexists(path):
    return path.exists() or path.is_symlink()


def _move_path(src, dst):
    if _lexists(dst):
        raise FileExistsError(str(dst))
    if not _lexists(src):
        raise FileNotFoundError(str(src))
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)


def _write_manifest(path, manifest):
    descriptor, temporary_name = tempfile.mkstemp(prefix='.manifest-', suffix='.tmp', dir=path.parent)
    temporary = Path(temporary_name)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _skill_candidates(config_dir):
    skills_dir = config_dir / 'skills'
    if not skills_dir.is_dir() or skills_dir.is_symlink():
        return []
    candidates = []
    try:
        children = sorted(skills_dir.iterdir(), key=lambda path: path.name.casefold())
    except OSError:
        return []
    for directory in children:
        skill_file = directory / 'SKILL.md'
        if (directory.is_dir() or directory.is_symlink()) and skill_file.is_file():
            record = doctor._skill_record(skill_file, 'user')
            candidates.append((directory, record))
    return candidates


def _skill_sections(path):
    text = doctor._read_text(path)
    headings = list(re.finditer(r'(?m)^#{1,6}\s+(.+?)\s*#*\s*$', text))
    if not headings:
        return [{'heading': '(unheaded content)', 'tokens': doctor._tokens(text)}]
    sections = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        sections.append({
            'heading': match.group(1).strip(),
            'tokens': doctor._tokens(text[match.start():end]),
        })
    return sorted(sections, key=lambda item: (-item['tokens'], item['heading'].casefold()))[:5]


def _keep_names(values):
    kept = set()
    for value in values or []:
        kept.update(item.casefold() for item in (value if isinstance(value, (list, tuple)) else [value]))
    return kept


def _optimizer_action(doctor_report, config_dir):
    optimizers = doctor_report.get('optimizers', {})
    active = optimizers.get('active', [])
    if len(active) < 2:
        return None
    profiles = optimizers.get('profiles', {})
    keep_id = active[0]['id']
    keep_profile = next((name for name, optimizer in profiles.items() if optimizer == keep_id), None)
    commands = []
    for item in active[1:]:
        optimizer_id = item['id']
        enabled_as = item.get('enabled_as', [])
        if 'plugin' in enabled_as:
            commands.append('/plugin disable ' + optimizer_id)
        if 'skill' in enabled_as:
            source = config_dir / 'skills' / optimizer_id
            destination = source.with_name(source.name + '.disabled')
            commands.append('mv {} {}'.format(shlex.quote(str(source)), shlex.quote(str(destination))))
    profile_map = ', '.join(f'{name}={optimizer}' for name, optimizer in profiles.items()) or 'none recorded'
    keep_text = f'keep {keep_id}' + (f' ({keep_profile} profile)' if keep_profile else '')
    command_text = '; '.join(commands) if commands else 'disable one optimizer after choosing which to keep'
    return {
        'type': 'stacked_optimizers',
        'status': 'suggest',
        'estimate_tokens_per_session': None,
        'message': f"Stacked coding-behavior optimizers are active. Suggested default: {keep_text}; "
                   f"disable the others with: {command_text}. Profiles: {profile_map}.",
    }


def _plan(args, config_dir, now=None):
    try:
        since = audit.parse_since(getattr(args, 'since', '30d'), now)
    except argparse.ArgumentTypeError as error:
        raise ValueError(str(error))
    doctor_report = doctor.collect_report(
        project_dir=Path.cwd(), measure=False, config_dir=config_dir)
    sessions = audit.collect(since=since, paths=[config_dir / 'projects'])
    usage = audit.summarize(sessions)
    claude_sessions = usage['claude']['sessions']
    used = {name.casefold(): count for name, count in usage.get('skills_used', {}).get('by_name', {}).items()}
    keep = _keep_names(getattr(args, 'keep', []))
    run_id = _run_id(config_dir, now)
    moves, actions = [], []
    candidates = _skill_candidates(config_dir)
    user_records = [record for _, record in candidates]
    duplicates = doctor._duplicates(user_records)

    if claude_sessions < MIN_CLAUDE_SESSIONS:
        actions.append({
            'type': 'unused_skill_archive',
            'status': 'skipped',
            'estimate_tokens_per_session': None,
            'message': f"Unused user skills were not considered: at least {MIN_CLAUDE_SESSIONS} Claude sessions "
                       f"are required in the window; found {claude_sessions}.",
        })
    else:
        archive_dir = config_dir / 'tokenmaxxing-archive' / run_id / 'skills'
        for directory, record in candidates:
            name = record['name']
            if name.casefold() in keep or directory.name.casefold() in keep:
                actions.append({
                    'type': 'unused_skill_archive', 'status': 'kept', 'skill': name,
                    'estimate_tokens_per_session': None,
                    'message': f"Kept user skill {name!r} because it was named in --keep.",
                })
                continue
            if used.get(name.casefold(), 0):
                continue
            estimated = record['tokens']
            move = {
                'src': str(directory),
                'dst': str(archive_dir / directory.name),
                'kind': 'unused_skill',
                'skill': name,
                'estimate_tokens_per_session': estimated,
            }
            moves.append(move)
            actions.append({
                'type': 'unused_skill_archive', 'status': 'archive', 'skill': name,
                'source': str(directory), 'estimate_tokens_per_session': estimated,
                'message': f"Archive unused user skill {name!r}.",
            })

    planned_sources = {move['src'] for move in moves}
    for duplicate in duplicates:
        name = duplicate['name']
        copies = [(directory, record) for directory, record in candidates
                  if record['name'].casefold() == name.casefold()]
        if all(str(directory) in planned_sources for directory, _ in copies):
            continue
        if name.casefold() in keep:
            continue
        actions.append({
            'type': 'duplicate_skill',
            'status': 'suggest',
            'skill': name,
            'estimate_tokens_per_session': None,
            'message': f"Duplicate user skill name {name!r} has {len(copies)} copies in the same scope. "
                       "Doctor cannot determine which same-scope copy Claude Code loads, so no copy will be moved automatically.",
        })

    optimizer = _optimizer_action(doctor_report, config_dir)
    if optimizer:
        actions.append(optimizer)

    for item in doctor_report.get('instructions', {}).get('files', []):
        path = Path(item.get('path', ''))
        if (item.get('loaded_by') != 'claude'
                or path.name not in ('CLAUDE.md', 'CLAUDE.local.md')
                or item.get('tokens', 0) < doctor.INSTRUCTION_FILE_FINDING_TOKENS):
            continue
        sections = _skill_sections(path)
        labels = ', '.join(f"{section['heading']} (~{section['tokens']} tokens estimate)"
                           for section in sections)
        actions.append({
            'type': 'oversized_instructions',
            'status': 'suggest',
            'file': str(path),
            'sections': sections,
            'estimate_tokens_per_session': None,
            'message': f"{path} is ~{item['tokens']} tokens. Largest sections: {labels}. "
                       "Consider moving rarely-needed sections into a referenced file.",
        })

    for finding in doctor_report.get('findings', []):
        message = finding.get('text', '')
        if (message.startswith('Plugin ') or 'MCP servers exceed' in message
                or message.startswith('Hooks include')):
            actions.append({
                'type': 'configuration_overhead',
                'status': 'suggest',
                'impact_tokens': finding.get('impact_tokens', 0),
                'estimate_tokens_per_session': None,
                'message': message,
            })

    return {
        'config_dir': str(config_dir),
        'since': getattr(args, 'since', '30d'),
        'claude_sessions': claude_sessions,
        'dry_run': not getattr(args, 'apply', False),
        'run_id': run_id if moves else None,
        'actions': actions,
        'moves': moves,
        'estimated_tokens_per_session': sum(move['estimate_tokens_per_session'] for move in moves),
    }


def _apply(plan, config_dir):
    if not plan['moves']:
        return {'moved': [], 'run_id': None, 'errors': []}
    archive_root = config_dir / 'tokenmaxxing-archive'
    if archive_root.is_symlink():
        raise ValueError('archive path is a symlink; refusing to write outside the config directory')
    archive_root.mkdir(parents=True, exist_ok=True)
    run_dir = archive_root / plan['run_id']
    run_dir.mkdir(exist_ok=False)
    skills_dir = run_dir / 'skills'
    skills_dir.mkdir()
    manifest_path = run_dir / 'manifest.json'
    manifest = {
        'run_id': plan['run_id'],
        'version': VERSION,
        'created': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'config_dir': str(config_dir),
        'moves': [
            {'src': move['src'], 'dst': move['dst'], 'kind': move['kind'], 'done': False}
            for move in plan['moves']
        ],
    }
    _write_manifest(manifest_path, manifest)
    moved, errors = [], []
    for index, entry in enumerate(manifest['moves']):
        try:
            _move_path(Path(entry['src']), Path(entry['dst']))
        except OSError as error:
            entry['error'] = str(error)
            errors.append({'src': entry['src'], 'error': str(error)})
            _write_manifest(manifest_path, manifest)
            continue
        entry['done'] = True
        _write_manifest(manifest_path, manifest)
        moved.append(plan['moves'][index])
    return {'moved': moved, 'run_id': plan['run_id'], 'errors': errors}


def _read_manifest(path):
    try:
        with path.open(encoding='utf-8') as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _runs(config_dir):
    archive_root = config_dir / 'tokenmaxxing-archive'
    if archive_root.is_symlink() or not archive_root.is_dir():
        return []
    runs = []
    try:
        manifests = archive_root.glob('*/manifest.json')
        for path in manifests:
            if path.is_symlink():
                continue
            manifest = _read_manifest(path)
            if (manifest and RUN_ID_RE.match(str(manifest.get('run_id', '')))
                    and manifest.get('run_id') == path.parent.name):
                runs.append((manifest.get('created', ''), path, manifest))
    except OSError:
        return []
    return sorted(runs, key=lambda item: (str(item[0]), item[2]['run_id']), reverse=True)


def _manifest_paths(config_dir, run_id, manifest):
    run_dir = config_dir / 'tokenmaxxing-archive' / run_id
    archive_skills = run_dir / 'skills'
    if (run_dir.is_symlink() or manifest.get('run_id') != run_id
            or manifest.get('config_dir') != str(config_dir)
            or not isinstance(manifest.get('moves'), list)
            or (config_dir / 'skills').is_symlink() or archive_skills.is_symlink()):
        raise ValueError('manifest does not match this config directory or run')
    paths = []
    for entry in manifest['moves']:
        if not isinstance(entry, dict):
            raise ValueError('manifest contains an invalid move')
        src, dst = Path(str(entry.get('src', ''))), Path(str(entry.get('dst', '')))
        if (not src.is_absolute() or not dst.is_absolute()
                or src.name in ('', '.', '..') or dst.name in ('', '.', '..')
                or src.parent != config_dir / 'skills'
                or dst.parent != archive_skills
                or not isinstance(entry.get('kind'), str)):
            raise ValueError('manifest contains a move outside its archive or user skills directory')
        paths.append((entry, src, dst))
    return paths


def _undo(config_dir, requested_run_id=None):
    runs = _runs(config_dir)
    if requested_run_id:
        if not RUN_ID_RE.match(requested_run_id):
            return {'status': 'error', 'message': 'RUN_ID must have the form YYYYMMDDTHHMMSSZ', 'moved': [], 'conflicts': []}, 2
        selected = next((item for item in runs if item[2]['run_id'] == requested_run_id), None)
    else:
        selected = runs[0] if runs else None
    if not selected:
        return {'status': 'not_found', 'message': 'No archive run found.', 'moved': [], 'conflicts': []}, 1
    _, manifest_path, manifest = selected
    run_id = manifest['run_id']
    try:
        paths = _manifest_paths(config_dir, run_id, manifest)
    except ValueError as error:
        return {'status': 'error', 'run_id': run_id, 'message': str(error), 'moved': [], 'conflicts': []}, 1
    if manifest.get('undone') is True:
        return {'status': 'already_undone', 'run_id': run_id, 'moved': [], 'conflicts': []}, 0
    moved, conflicts = [], []
    for entry, src, dst in paths:
        if not entry.get('done') and not _lexists(dst):
            continue
        if _lexists(src):
            conflicts.append({'src': str(src), 'dst': str(dst), 'reason': 'source already exists'})
            continue  # already restored, or refused because a newer source exists
        if not _lexists(dst):
            conflicts.append({'src': str(src), 'dst': str(dst), 'reason': 'archived item is missing'})
            continue
        try:
            _move_path(dst, src)
        except OSError as error:
            conflicts.append({'src': str(src), 'dst': str(dst), 'reason': str(error)})
            continue
        entry['done'] = False
        _write_manifest(manifest_path, manifest)
        moved.append({'src': str(src), 'dst': str(dst)})
    if conflicts:
        manifest['undone'] = False
        _write_manifest(manifest_path, manifest)
        return {'status': 'conflict', 'run_id': run_id, 'moved': moved, 'conflicts': conflicts}, 1
    manifest['undone'] = True
    _write_manifest(manifest_path, manifest)
    return {'status': 'undone', 'run_id': run_id, 'moved': moved, 'conflicts': []}, 0


def _list(config_dir):
    result = []
    for _, _, manifest in _runs(config_dir):
        moves = manifest.get('moves', [])
        done = sum(1 for item in moves if isinstance(item, dict) and item.get('done'))
        status = ('undone' if manifest.get('undone') is True else
                  'partial' if manifest.get('undone') is False else 'applied' if done else 'empty')
        result.append({'run_id': manifest['run_id'], 'created': manifest.get('created'),
                       'status': status, 'moves': len(moves), 'done': done})
    return result


def _print_plan(plan):
    label = 'dry run' if plan['dry_run'] else 'apply'
    print(f"TOKENMAXXING fix — last {plan['since']} ({label})")
    print(f"  Claude sessions in window: {plan['claude_sessions']}")
    for action in plan['actions']:
        status = action['status']
        estimate = action.get('estimate_tokens_per_session')
        suffix = f" · estimate ~{estimate} tokens/session" if estimate is not None else ' · estimate n/a'
        print(f"  [{status}] {action['message']}{suffix}")
    print(f"  Total planned saving: ~{plan['estimated_tokens_per_session']} tokens/session estimate")
    if plan['dry_run']:
        print('  Dry run only; no files moved. Re-run with --apply to archive eligible skills.')


def _print_undo(result):
    print(f"TOKENMAXXING fix undo — {result.get('run_id', '')}: {result['status']}")
    for item in result.get('moved', []):
        print(f"  restored {item['dst']} -> {item['src']}")
    for item in result.get('conflicts', []):
        print(f"  refused {item['dst']} -> {item['src']}: {item['reason']}")
    if result.get('message'):
        print('  ' + result['message'])


def add_arguments(parser):
    parser.add_argument('--since', default='30d', help='audit window: 30d, 7d, 24h, all, or ISO date')
    parser.add_argument('--config-dir', type=Path, help='Claude config directory (default: doctor config path)')
    parser.add_argument('--keep', action='append', nargs='+', default=[], metavar='NAME',
                        help='keep a user skill by name (repeatable)')
    parser.add_argument('--apply', action='store_true', help='move eligible skills into the archive')
    parser.add_argument('--json', action='store_true', help='print machine-readable output')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--undo', nargs='?', const='', default=None, metavar='RUN_ID',
                       help='restore a run (default: most recent)')
    modes.add_argument('--list', action='store_true', help='list archived runs')


def run(args):
    config_dir = doctor._config_dir(doctor._home(), getattr(args, 'config_dir', None))
    json_output = getattr(args, 'json', False)
    if ((getattr(args, 'list', False) or getattr(args, 'undo', None) is not None)
            and (getattr(args, 'apply', False) or getattr(args, 'keep', []))):
        print('error: --apply and --keep can only be used for an archive plan', file=sys.stderr)
        return 2
    if getattr(args, 'list', False):
        runs = _list(config_dir)
        if json_output:
            print(json.dumps({'runs': runs}, indent=2))
        else:
            print('TOKENMAXXING fix archive runs')
            if not runs:
                print('  No archive runs found.')
            for item in runs:
                print(f"  {item['run_id']} · {item['status']} · {item['done']}/{item['moves']} moved")
        return 0
    if getattr(args, 'undo', None) is not None:
        result, code = _undo(config_dir, getattr(args, 'undo') or None)
        if json_output:
            print(json.dumps(result, indent=2))
        else:
            _print_undo(result)
        return code
    try:
        plan = _plan(args, config_dir)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    if not getattr(args, 'apply', False):
        if json_output:
            print(json.dumps(plan, indent=2, ensure_ascii=False))
        else:
            _print_plan(plan)
        return 0
    try:
        applied = _apply(plan, config_dir)
    except (OSError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    applied_estimate = sum(move['estimate_tokens_per_session'] for move in applied['moved'])
    plan.update({'dry_run': False, 'moved': applied['moved'], 'run_id': applied['run_id'],
                 'errors': applied['errors'],
                 'applied_estimated_tokens_per_session': applied_estimate,
                 'restart_message': ('Restart Claude Code sessions to pick up the change.'
                                     if applied['moved'] else None),
                 'undo_command': (f"python3 tokenmaxxing.py fix --undo {applied['run_id']}"
                                 if applied['run_id'] else None)})
    if json_output:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        _print_plan(plan)
        if applied['moved']:
            for move in applied['moved']:
                print(f"  moved {move['src']} -> {move['dst']} · estimate ~{move['estimate_tokens_per_session']} tokens/session")
            print(f"  Total estimated saving: ~{applied_estimate} tokens/session")
            print(f"  Undo with: {plan['undo_command']}")
            print('  Restart Claude Code sessions to pick up the change.')
        else:
            print('  No files moved.')
        for error in applied['errors']:
            print(f"  [error] {error['src']}: {error['error']}")
    return 1 if applied['errors'] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='tokenmaxxing fix', description='Safely archive unused user skills')
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())
