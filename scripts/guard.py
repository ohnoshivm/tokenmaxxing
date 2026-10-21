#!/usr/bin/env python3
"""TOKENMAXXING guard: stop a cold-cache prompt before it is sent.

An opt-in `UserPromptSubmit` hook. When the session has idled past its prompt
cache TTL and the context is large enough that the rebuild is expensive, the
guard blocks once with a short message, so the rebuild happens on a deliberate
re-send (or not at all, if you compact first).

Reads stdin, writes one marker file per warned session and nothing else.
Standard library only; never touches settings.json.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

import statusline

MARKER_DIR = 'tokenmaxxing-guard'
MARKER_TTL_SECONDS = 24 * 60 * 60
DEFAULT_MIN_CONTEXT = 50_000
DEFAULT_GRACE_SECONDS = 120
SAFE_NAME = re.compile(r'[^A-Za-z0-9_.-]')


def _config_dir(override=None):
    if override:
        return Path(override).expanduser().resolve()
    configured = os.environ.get('CLAUDE_CONFIG_DIR')
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / '.claude').resolve()


def _coerce_now(value):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value)).astimezone(timezone.utc)


def _marker_path(config_dir, session_id):
    name = SAFE_NAME.sub('_', str(session_id or ''))[:120] or 'session'
    return Path(config_dir) / MARKER_DIR / f'{name}.json'


def _marker_time(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return datetime.fromisoformat(data['blocked_at'])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _prune(directory, now):
    try:
        entries = list(Path(directory).iterdir())
    except OSError:
        return
    for entry in entries:
        stamp = _marker_time(entry)
        if stamp is None or (now - stamp).total_seconds() > MARKER_TTL_SECONDS:
            try:
                entry.unlink()
            except OSError:
                pass


def _write_marker(path, now):
    path.parent.mkdir(parents=True, exist_ok=True)
    _prune(path.parent, now)
    path.write_text(json.dumps({'blocked_at': now.isoformat(timespec='seconds')}), encoding='utf-8')


def _idle_text(seconds):
    minutes = max(1, int(seconds // 60))
    return f'{minutes}m' if minutes < 60 else f'{minutes // 60}h {minutes % 60:02d}m'


def _allow(why, context=0, idle=0.0):
    return {'decision': 'allow', 'why': why, 'context': context, 'idle': int(idle), 'reason': ''}


def decide(payload, config_dir, min_context=DEFAULT_MIN_CONTEXT, grace=DEFAULT_GRACE_SECONDS, now=None):
    """Return allow/block for one hook payload. Never raises on bad input."""
    now = _coerce_now(now)
    prompt = payload.get('prompt')
    if not isinstance(prompt, str) or not prompt.strip():
        return _allow('empty prompt')
    if prompt.lstrip().startswith('/'):
        return _allow('slash command')
    transcript_path = payload.get('transcript_path')
    if not transcript_path:
        return _allow('no transcript path')
    try:
        transcript, ttl_seconds = statusline._read_transcript(transcript_path)
    except OSError:
        return _allow('transcript unreadable')
    if transcript is None or transcript['timestamp'] is None:
        return _allow('no assistant turn yet')
    context = statusline._context_tokens(transcript['usage'])
    idle = max(0.0, (now - transcript['timestamp']).total_seconds())
    if context < min_context:
        return _allow('context below minimum', context, idle)
    if idle <= ttl_seconds:
        return _allow('cache warm', context, idle)
    marker = _marker_path(config_dir, payload.get('session_id'))
    blocked_at = _marker_time(marker)
    if blocked_at is not None and 0 <= (now - blocked_at).total_seconds() < grace:
        return _allow('already warned, letting the re-send through', context, idle)
    try:
        _write_marker(marker, now)
    except OSError:
        return _allow('marker not writable', context, idle)
    reason = (f"Cache cold (idle {_idle_text(idle)}). Sending re-sends "
              f"~{statusline._format_tokens(context)} tokens. Re-send to continue, "
              "/compact to keep going lighter, or /clear for a new task.")
    return {'decision': 'block', 'why': 'cold cache', 'context': context,
            'idle': int(idle), 'reason': reason, 'marker': str(marker)}


def _hook_snippet(args):
    command = ' '.join([
        'python3', str(Path(__file__).resolve().parents[1] / 'tokenmaxxing.py'), 'guard', '--hook',
        '--min-context', str(getattr(args, 'min_context', DEFAULT_MIN_CONTEXT)),
        '--grace', str(getattr(args, 'grace', DEFAULT_GRACE_SECONDS)),
    ])
    return json.dumps({'hooks': {'UserPromptSubmit': [{'hooks': [
        {'type': 'command', 'command': command}]}]}}, indent=2)


def add_arguments(ap):
    ap.add_argument('--print-hook', action='store_true',
                    help='print the settings.json snippet; never edits settings')
    ap.add_argument('--hook', action='store_true', help='hook entry point: read hook JSON on stdin')
    ap.add_argument('--min-context', type=int, default=DEFAULT_MIN_CONTEXT,
                    help='only warn when the context is at least this many tokens (default 50000)')
    ap.add_argument('--grace', type=int, default=DEFAULT_GRACE_SECONDS,
                    help='seconds after a warning during which the re-send passes (default 120)')
    ap.add_argument('--config-dir', type=Path,
                    help='Claude config directory for markers (default: $CLAUDE_CONFIG_DIR or ~/.claude)')


def run(args, stdin=None, stdout=None, now=None):
    out = stdout if stdout is not None else sys.stdout
    config_dir = _config_dir(getattr(args, 'config_dir', None))
    if getattr(args, 'print_hook', False):
        print(_hook_snippet(args), file=out)
        return 0
    if not getattr(args, 'hook', False):
        print('Choose --print-hook (show the settings snippet) or --hook (hook entry point).', file=out)
        return 2
    source = stdin if stdin is not None else sys.stdin
    try:
        raw = source.read() if hasattr(source, 'read') else source
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('payload must be an object')
    except Exception:
        return 0  # a guard must never break a session
    try:
        verdict = decide(payload, config_dir, getattr(args, 'min_context', DEFAULT_MIN_CONTEXT),
                         getattr(args, 'grace', DEFAULT_GRACE_SECONDS), now)
    except Exception:
        return 0
    if verdict['decision'] == 'block':
        print(json.dumps({'decision': 'block', 'reason': verdict['reason']}), file=out)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='tokenmaxxing guard',
        description='Opt-in UserPromptSubmit hook that warns once when the prompt cache is cold')
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())
