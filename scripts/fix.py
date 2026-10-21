#!/usr/bin/env python3
"""Plan reversible skill archives; never edit settings or delete skills."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile

import audit
import doctor


VERSION = '2.0.0'
RUN_PATTERN = re.compile(r'^\d{8}T\d{6}Z$')


def add_arguments(parser):
    parser.add_argument('--since', default='30d', help='usage window (default: 30d)')
    parser.add_argument('--config-dir', type=Path, help='Claude config directory')
    parser.add_argument('--keep', nargs='+', action='append', default=[], help='skill names to preserve')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='apply auto-applicable archives')
    mode.add_argument('--undo', nargs='?', const='', help='undo a run (default: most recent)')
    mode.add_argument('--list', action='store_true', help='list archive manifests')
    parser.add_argument('--json', action='store_true', help='machine-readable output')


def largest_sections(path):
    sections, heading, lines = [], '(preamble)', []
    for line in doctor._read_text(path).splitlines(keepends=True):
        match = re.match(r'^#{1,6}\s+(.+?)\s*#*\s*$', line)
        if match:
            if lines:
                sections.append({'heading': heading, 'tokens': doctor._tokens(''.join(lines))})
            heading, lines = match.group(1), []
        lines.append(line)
    if lines:
        sections.append({'heading': heading, 'tokens': doctor._tokens(''.join(lines))})
    return sorted(sections, key=lambda item: -item['tokens'])[:3]


def plan(config_dir, since, keep):
    # Scope usage to this config: another account's sessions cannot justify archiving.
    summary = audit.summarize(audit.collect(since=since, paths=[config_dir / 'projects']))
    report = doctor.collect_report(config_dir=config_dir, measure=False)
    sessions = summary['claude']['sessions']
    used = {item['name'].casefold() for item in summary['skills_used'] if item['count']}
    keep = {name.casefold() for name in keep}
    actions, skipped, records = [], [], []
    directory = config_dir / 'skills'
    for path in doctor._direct_skill_files(directory):
        record = doctor._skill_record(path, 'user')
        # Doctor resolves links for inspection; moves must retain the original link path.
        record['directory'] = path.parent
        records.append(record)
    duplicates = doctor._duplicates(records)
    duplicate_names = {item['name'].casefold() for item in duplicates}
    for duplicate in duplicates:
        actions.append({'kind': 'duplicate', 'name': duplicate['name'], 'auto': False,
                        'estimated_tokens_per_session': 0,
                        'reason': 'Duplicate copies have ambiguous load precedence; review which copy Claude Code loads before archiving.'})
    if sessions < 10:
        skipped.append(f'Unused-skill archive requires at least 10 Claude sessions; found {sessions}.')
    if directory.is_symlink():
        skipped.append('The skills directory itself is a symlink; automatic archives are skipped.')
    for record in records:
        names = {record['name'].casefold(), record['directory'].name.casefold()}
        if (sessions < 10 or directory.is_symlink() or names & (used | keep) or
                record['name'].casefold() in duplicate_names):
            continue
        actions.append({'kind': 'unused', 'name': record['directory'].name, 'auto': True,
                        'src': str(record['directory']), 'estimated_tokens_per_session': record['tokens'],
                        'reason': f'Zero recorded invocations in {sessions} Claude sessions (usage proxy).'})
    optimizers = report['optimizers']
    if optimizers['stacked']:
        active = optimizers['active']
        chosen = next((item['id'] for item in active if item['id'] == 'ponytail'), active[0]['id'])
        settings = doctor._read_json(config_dir / 'settings.json', {})
        registry = doctor._read_json(doctor.REGISTRY_PATH, {})
        plugins = {item['id']: (item.get('claude_plugin') or {}).get('name') for item in registry.get('tools', [])}
        commands = []
        for item in active:
            if item['id'] == chosen:
                continue
            if 'plugin' in item['enabled_as']:
                commands.extend('/plugin disable ' + key for key in doctor._enabled_plugins(settings)
                                if key.split('@', 1)[0] == plugins.get(item['id']))
            if 'skill' in item['enabled_as']:
                source = config_dir / 'skills' / item['id']
                destination = config_dir / ('disabled-' + item['id'])
                commands.append('mv -n ' + shlex.quote(str(source)) + ' ' + shlex.quote(str(destination)))
        profiles = ', '.join(f'{profile}={optimizer}' for profile, optimizer in optimizers['profiles'].items())
        actions.append({'kind': 'optimizers', 'auto': False, 'estimated_tokens_per_session': 0,
                        'reason': f'Keep one optimizer (suggested: {chosen}); profiles: {profiles}. Review these commands; nothing runs automatically.',
                        'commands': commands})
    for item in report['instructions']['files']:
        if (item['loaded_by'] == 'claude' and item['tokens'] >= doctor.INSTRUCTION_FILE_FINDING_TOKENS):
            actions.append({'kind': 'instructions', 'auto': False, 'estimated_tokens_per_session': 0,
                            'reason': f"{item['path']}: move rarely-needed sections into a referenced file.",
                            'sections': largest_sections(Path(item['path']))})
    # Keep the doctor's plugin/MCP/hook findings, including its thresholds and wording.
    for finding in report['findings']:
        if ('Plugin ' in finding['text'] or 'MCP servers' in finding['text'] or
                'Hooks include' in finding['text'] or 'Subagent ' in finding['text']):
            actions.append({'kind': 'overhead', 'auto': False, 'estimated_tokens_per_session': 0,
                            'reason': finding['text']})
    return {'config_dir': str(config_dir), 'claude_sessions': sessions, 'actions': actions, 'skipped': skipped,
            'estimated_tokens_per_session': sum(a['estimated_tokens_per_session'] for a in actions if a['auto']),
            'run_id': None, 'errors': []}


def exists(path):
    return path.exists() or path.is_symlink()


def archive_root(config_dir):
    archive = config_dir / 'tokenmaxxing-archive'
    if archive.is_symlink():
        raise ValueError('Archive directory must not be a symlink')
    return archive


def run_dir(config_dir, run_id):
    if not isinstance(run_id, str) or not RUN_PATTERN.fullmatch(run_id):
        raise ValueError('Invalid archive run id')
    directory = archive_root(config_dir) / run_id
    if directory.is_symlink() or (directory / 'skills').is_symlink():
        raise ValueError('Archive run directories must not be symlinks')
    return directory


def write_manifest(path, manifest):
    if path.is_symlink():
        raise ValueError('Manifest must not be a symlink')
    # Exclusive temporary creation avoids following an existing link or hardlink.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='.manifest-',
                                     dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(manifest, handle, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def apply_plan(report, config_dir):
    actions = [a for a in report['actions'] if a['auto']]
    if not actions:
        return
    now = datetime.now(timezone.utc)
    run_id = now.strftime('%Y%m%dT%H%M%SZ')
    directory = run_dir(config_dir, run_id)
    archive_root(config_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.mkdir(mode=0o700, exist_ok=False)
    (directory / 'skills').mkdir()
    manifest = {'run_id': run_id, 'version': VERSION, 'created': now.isoformat(), 'config_dir': str(config_dir),
                'moves': [{'src': a['src'], 'dst': str(directory / 'skills' / a['name']), 'kind': a['kind'], 'done': False}
                          for a in actions]}
    path = directory / 'manifest.json'
    write_manifest(path, manifest)
    report['run_id'], report['moved'] = run_id, []
    for entry in manifest['moves']:
        source, destination = Path(entry['src']), Path(entry['dst'])
        if exists(destination):
            raise ValueError('Archive destination already exists; refusing to overwrite')
        source.rename(destination)
        entry['done'] = True
        write_manifest(path, manifest)
        report['moved'].append(source.name)


def manifests(config_dir):
    archive = archive_root(config_dir)
    if not archive.is_dir():
        return []
    return sorted((p for p in archive.glob('*/manifest.json')
                   if RUN_PATTERN.fullmatch(p.parent.name)), reverse=True)


def undo(config_dir, run_id):
    available = manifests(config_dir)
    if not run_id:
        if not available:
            return {'run_id': None, 'undone': True, 'restored': [], 'conflicts': [], 'errors': []}
        run_id = available[0].parent.name
    directory = run_dir(config_dir, run_id)
    path = directory / 'manifest.json'
    if path.is_symlink() or (config_dir / 'skills').is_symlink():
        raise ValueError('Manifest and skills root must not be symlinks')
    manifest = doctor._read_json(path)
    if (not isinstance(manifest, dict) or manifest.get('config_dir') != str(config_dir) or
            manifest.get('run_id') != run_id or not isinstance(manifest.get('moves'), list)):
        raise ValueError('Invalid archive manifest or config directory')
    # Validate every move before restoring any: manifests are an input boundary.
    seen = set()
    for entry in manifest['moves']:
        if not isinstance(entry, dict) or not isinstance(entry.get('src'), str) or not isinstance(entry.get('dst'), str):
            raise ValueError('Invalid manifest move')
        source, destination = Path(entry['src']), Path(entry['dst'])
        if (source.parent != config_dir / 'skills' or source.name in ('', '.', '..') or
                destination != directory / 'skills' / source.name or str(source) in seen):
            raise ValueError('Manifest move escapes its skill archive')
        seen.add(str(source))
    report = {'run_id': run_id, 'undone': False, 'restored': [], 'conflicts': [], 'errors': []}
    for entry in reversed(manifest['moves']):
        if entry.get('undone'):
            continue
        source, destination = Path(entry['src']), Path(entry['dst'])
        # Recover a crash after rename but before the done flag reached disk.
        moved = entry.get('done') or (exists(destination) and not exists(source))
        if not moved:
            continue
        if exists(source):
            report['conflicts'].append(source.name + ': source already exists; archive retained')
            continue
        if not exists(destination):
            report['conflicts'].append(source.name + ': archived copy missing')
            continue
        source.parent.mkdir(parents=True, exist_ok=True)
        destination.rename(source)
        entry['undone'] = True
        write_manifest(path, manifest)
        report['restored'].append(source.name)
    report['undone'] = not report['conflicts']
    manifest['undone'] = report['undone']
    write_manifest(path, manifest)
    return report


def print_report(report, args):
    if args.json:
        print(json.dumps(report, indent=2))
        return
    if 'actions' in report:
        print('TOKENMAXXING fix — ' + ('apply' if args.apply else 'dry run (no changes)'))
        for reason in report['skipped']:
            print('  skip: ' + reason)
        for action in report['actions']:
            label = 'archive' if action['auto'] else 'suggest'
            print(f"  [{label}] {action.get('name', action['kind'])}: {action['reason']} "
                  f"(estimate: {action['estimated_tokens_per_session']} tokens/session)")
            for section in action.get('sections', []):
                print(f"    {section['heading']}: ~{section['tokens']} tokens (estimate)")
            for command in action.get('commands', []):
                print('    ' + command)
        print(f"  Total estimated saving: {report['estimated_tokens_per_session']} tokens/session")
        if report.get('run_id'):
            print('  Moved: ' + ', '.join(report.get('moved', [])))
            print('  Undo: python3 tokenmaxxing.py fix --config-dir ' + shlex.quote(report['config_dir']) + ' --undo ' + report['run_id'])
            print('  restart Claude Code sessions to pick up the change')
    elif 'runs' in report:
        for item in report['runs']:
            print(f"  {item['run_id']}: {'undone' if item.get('undone') else 'archived'}")
        if not report['runs']:
            print('No archive runs.')
    elif 'undone' in report:
        print('Undo: ' + ('complete (or already undone)' if report['undone'] else 'conflicts; archive retained'))
        for item in report.get('restored', []) + report.get('conflicts', []):
            print('  ' + item)
    for error in report.get('errors', []):
        print('  error: ' + error)


def run(args):
    report = {'errors': []}
    try:
        config_dir = doctor._config_dir(override=args.config_dir)
        if args.undo is not None:
            report = undo(config_dir, args.undo)
        elif args.list:
            runs = []
            for path in manifests(config_dir):
                run_dir(config_dir, path.parent.name)
                value = doctor._read_json(path, {}) if not path.is_symlink() else {}
                if isinstance(value, dict) and value.get('run_id') == path.parent.name:
                    runs.append({key: value.get(key) for key in ('run_id', 'created', 'version', 'undone')})
            report = {'runs': runs, 'errors': []}
        else:
            since = audit.parse_since(args.since)
            report = plan(config_dir, since, [name for group in args.keep for name in group])
            if args.apply:
                apply_plan(report, config_dir)
    except (OSError, ValueError, argparse.ArgumentTypeError) as error:
        report.setdefault('errors', []).append(str(error))
    print_report(report, args)
    return 1 if report.get('errors') or report.get('conflicts') else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())
