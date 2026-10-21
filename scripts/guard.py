#!/usr/bin/env python3
"""Opt-in UserPromptSubmit cache guard; silent, exit-zero on every allow path."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys

import doctor
import statusline


MARKER_PATTERN = re.compile(r'^[0-9a-f]{64}\.marker$')


def add_arguments(parser):
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--print-hook', action='store_true', help='print a settings snippet; never install it')
    mode.add_argument('--hook', action='store_true', help='read UserPromptSubmit JSON on stdin')
    parser.add_argument('--min-context', type=int, default=50000, help='minimum context tokens (default: 50000)')
    parser.add_argument('--grace', type=int, default=120, help='seconds to allow a re-send after blocking (default: 120)')


def _mark(config_dir, session_id, now, grace):
    directory = config_dir / 'tokenmaxxing-guard'
    if directory.is_symlink():
        raise ValueError('marker directory must not be a symlink')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    timestamp = now.timestamp()
    for path in directory.glob('*.marker'):
        if MARKER_PATTERN.fullmatch(path.name) and not path.is_symlink() and path.is_file():
            if timestamp - path.stat().st_mtime > 86400:
                path.unlink()
    marker = directory / (hashlib.sha256(session_id.encode('utf-8')).hexdigest() + '.marker')
    if marker.is_symlink():
        raise ValueError('marker must not be a symlink')
    if marker.exists():
        if timestamp - marker.stat().st_mtime < grace:
            return False
        marker.unlink()
    # Exclusive creation makes simultaneous submissions share one grace marker.
    fd = os.open(str(marker), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        handle.write(str(timestamp) + '\n')
    os.utime(marker, (timestamp, timestamp))
    return True


def _print_hook(args, stdout):
    entry = Path(__file__).resolve().parents[1] / 'tokenmaxxing.py'
    command = '{} {} guard --hook --min-context {} --grace {}'.format(
        shlex.quote(sys.executable), shlex.quote(str(entry)), args.min_context, args.grace)
    print(json.dumps({'hooks': {'UserPromptSubmit': [{'hooks': [
        {'type': 'command', 'command': command, 'timeout': 5}
    ]}]}}, indent=2), file=stdout)


def run(args, stdin=None, stdout=None, now=None):
    output = sys.stdout if stdout is None else stdout
    try:
        if args.min_context < 0 or args.grace < 0:
            return 0
        if args.print_hook:
            _print_hook(args, output)
            return 0
        payload = statusline._read_stdin(sys.stdin if stdin is None else stdin)
        prompt, session_id, path = (payload.get(key) for key in ('prompt', 'session_id', 'transcript_path'))
        if (not isinstance(prompt, str) or not isinstance(session_id, str) or not session_id or
                not isinstance(path, str) or not path):
            return 0
        if payload.get('hook_event_name', 'UserPromptSubmit') != 'UserPromptSubmit':
            return 0
        if prompt.lstrip().startswith('/'):
            return 0
        transcript, ttl = statusline._read_transcript(path)
        if transcript is None or transcript['timestamp'] is None:
            return 0
        clock = statusline._coerce_now(now)
        idle = (clock - transcript['timestamp']).total_seconds()
        context = statusline._context_tokens(transcript['usage'])
        if idle <= ttl or context < args.min_context:
            return 0
        if not _mark(doctor._config_dir(), session_id, clock, args.grace):
            return 0
        reason = ('Cache cold (estimate; idle {}m). Sending re-sends ~{} tokens. '
                  'Re-send to continue, /compact to keep going lighter, or /clear for a new task.').format(
                      int(idle // 60), statusline._format_tokens(context))
        # UserPromptSubmit reason is user-visible and is not added to model context.
        print(json.dumps({'decision': 'block', 'reason': reason, 'hookSpecificOutput': {
            'hookEventName': 'UserPromptSubmit', 'suppressOriginalPrompt': True}}), file=output)
    except Exception:
        return 0  # A broken guard must never break a session or leak hook input.
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())
