#!/usr/bin/env python3
"""Opt-in, cache-cold guard for Claude Code's UserPromptSubmit hook."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys

import doctor
import statusline


MARKER_DIR = "tokenmaxxing-guard"
MARKER_MAX_AGE = 24 * 60 * 60


def add_arguments(parser):
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--print-hook", action="store_true",
                       help="print a settings.json snippet without changing settings")
    modes.add_argument("--hook", action="store_true",
                       help="handle a Claude Code UserPromptSubmit payload from stdin")
    parser.add_argument("--min-context", type=int, default=50_000,
                        help="minimum estimated context tokens to block (default: 50000)")
    parser.add_argument("--grace", type=int, default=120,
                        help="seconds after a block during which re-sends pass (default: 120)")


def _marker_path(config_dir, session_id):
    key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return Path(config_dir) / MARKER_DIR / (key + ".json")


def _prune_markers(directory, now):
    cutoff = now.timestamp() - MARKER_MAX_AGE
    try:
        markers = directory.glob("*.json")
        for marker in markers:
            try:
                if marker.stat().st_mtime < cutoff:
                    marker.unlink()
            except OSError:
                continue
    except OSError:
        pass


def _recent_marker(marker, now, grace):
    try:
        return now.timestamp() - marker.stat().st_mtime <= grace
    except OSError:
        return False


def _write_marker(marker, session_id, now, grace):
    marker.parent.mkdir(parents=True, exist_ok=True)
    if _recent_marker(marker, now, grace):
        return False
    try:
        marker.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return False
    try:
        fd = os.open(os.fspath(marker), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    except OSError:
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"session_id": session_id, "created_at": now.isoformat()}, handle)
            handle.write("\n")
        os.utime(marker, (now.timestamp(), now.timestamp()))
    except OSError:
        try:
            marker.unlink()
        except OSError:
            pass
        return False
    return True


def _hook_snippet():
    entry = Path(__file__).resolve().parents[1] / "tokenmaxxing.py"
    command = " ".join(shlex.quote(part) for part in (
        sys.executable, str(entry), "guard", "--hook"))
    return {
        "hooks": {
            "UserPromptSubmit": [{
                "hooks": [{"type": "command", "command": command, "timeout": 2}]
            }]
        }
    }


def _payload(stdin):
    raw = stdin.read()
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("empty hook input")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("hook input must be an object")
    prompt = value.get("prompt")
    transcript = value.get("transcript_path")
    session_id = value.get("session_id")
    if not isinstance(prompt, str) or not isinstance(transcript, str) or not transcript:
        raise ValueError("hook input is missing prompt or transcript_path")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("hook input is missing session_id")
    return prompt, Path(transcript), session_id


def _block_result(context, idle_seconds):
    minutes = int(idle_seconds // 60)
    reason = (
        "Cache cold (idle {}m). Sending re-sends ~{} tokens. Re-send to continue, "
        "/compact to keep going lighter, or /clear for a new task."
    ).format(minutes, statusline._format_tokens(context))
    return {
        "decision": "block",
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "suppressOriginalPrompt": True,
        },
    }


def _handle_hook(args, stdin, stdout, now):
    try:
        prompt, transcript_path, session_id = _payload(stdin)
        config_dir = doctor._config_dir()
        marker_dir = config_dir / MARKER_DIR
        _prune_markers(marker_dir, now)
        if prompt.lstrip().startswith("/"):
            return 0

        latest, ttl = statusline._read_transcript(transcript_path)
        if latest is None or latest.get("timestamp") is None:
            return 0
        context = statusline._context_tokens(latest["usage"])
        timestamp = latest["timestamp"]
        idle_seconds = max(0.0, (now - timestamp).total_seconds())
        if idle_seconds <= ttl or context < args.min_context:
            return 0

        marker = _marker_path(config_dir, session_id)
        if not _write_marker(marker, session_id, now, max(0, args.grace)):
            return 0
        stdout.write(json.dumps(_block_result(context, idle_seconds)) + "\n")
        return 0
    except Exception:
        # Hook failures must never prevent the user's prompt from reaching Claude.
        return 0


def run(args, stdin=None, stdout=None, now=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if args.print_hook:
        stdout.write(json.dumps(_hook_snippet(), indent=2) + "\n")
        return 0
    now = statusline._coerce_now(now)
    return _handle_hook(args, stdin, stdout, now)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="tokenmaxxing guard")
    add_arguments(parser)
    sys.exit(run(parser.parse_args()))
