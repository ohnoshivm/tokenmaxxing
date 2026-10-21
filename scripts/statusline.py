#!/usr/bin/env python3
"""Claude Code status line for TOKENMAXXING (standard library only)."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys


TAIL_BYTES = 256 * 1024
DEFAULT_TTL_SECONDS = 5 * 60
ONE_HOUR_TTL_SECONDS = 60 * 60
DEFAULT_WINDOW = 200_000
ONE_MILLION_WINDOW = 1_000_000
FALLBACK_LINE = "status unavailable"


def add_arguments(parser):
    """Add arguments to the statusline subcommand parser."""
    parser.add_argument("--ttl", choices=("5m", "1h"), default=None,
                        help="override inferred prompt-cache TTL")
    parser.add_argument("--window", type=int, default=None,
                        help="override context window size in tokens")
    parser.add_argument("--no-color", action="store_true",
                        help="disable ANSI color output")
    parser.add_argument("--install", action="store_true",
                        help="print the settings.json snippet without changing files")


def _read_stdin(source):
    raw = source.read() if hasattr(source, "read") else source
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("empty statusline input")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("statusline input must be a JSON object")
    return payload


def _timestamp(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_count(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _read_transcript(path):
    """Return the latest real assistant usage and the newest cache-write TTL."""
    latest = None
    recent_write_ttl = None

    with open(os.fspath(path), "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        start = max(0, size - TAIL_BYTES)
        if start:
            handle.seek(start - 1, os.SEEK_SET)
            previous = handle.read(1)
            handle.seek(start, os.SEEK_SET)
            if previous != b"\n":
                handle.readline()  # discard a possibly incomplete first line
        else:
            handle.seek(start, os.SEEK_SET)
        data = handle.read(TAIL_BYTES)

    for raw_line in reversed(data.splitlines()):
        try:
            entry = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(entry, dict):
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        if entry.get("type") != "assistant" and message.get("role") != "assistant":
            continue
        if message.get("model") == "<synthetic>":
            continue
        turn_usage = message.get("usage")
        if not isinstance(turn_usage, dict):
            continue

        if latest is None:
            latest = {
                "usage": turn_usage,
                "timestamp": _timestamp(entry.get("timestamp") or message.get("timestamp")),
            }

        cache_creation = turn_usage.get("cache_creation")
        if isinstance(cache_creation, dict) and recent_write_ttl is None:
            one_hour = _as_count(cache_creation.get("ephemeral_1h_input_tokens"))
            five_minutes = _as_count(cache_creation.get("ephemeral_5m_input_tokens"))
            total_written = _as_count(turn_usage.get("cache_creation_input_tokens"))
            if one_hour or five_minutes or total_written:
                recent_write_ttl = (ONE_HOUR_TTL_SECONDS if one_hour
                                    else DEFAULT_TTL_SECONDS)

        if latest is not None and recent_write_ttl is not None:
            break

    if latest is None:
        return None, DEFAULT_TTL_SECONDS
    return latest, recent_write_ttl or DEFAULT_TTL_SECONDS


def _context_tokens(turn_usage):
    return sum(_as_count(turn_usage.get(key)) for key in (
        "input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ))


def _cache_read_tokens(turn_usage):
    return _as_count(turn_usage.get("cache_read_input_tokens"))


def _window_size(payload, model_id, override):
    if override is not None:
        size = int(override)
    else:
        raw = payload.get("context_window")
        if isinstance(raw, dict):
            raw = raw.get("context_window_size", raw.get("size"))
        try:
            size = int(raw) if raw is not None else 0
        except (TypeError, ValueError, OverflowError):
            size = 0
        if size <= 0:
            size = (ONE_MILLION_WINDOW if "[1m]" in model_id.lower()
                    else DEFAULT_WINDOW)
    if size <= 0:
        raise ValueError("context window must be positive")
    return size


def _format_tokens(tokens):
    tokens = _as_count(tokens)
    if tokens < 1000:
        return str(tokens)
    if tokens < 1_000_000:
        return "{}k".format(int(round(tokens / 1000.0)))
    millions = tokens / 1_000_000.0
    text = "{:.1f}".format(millions).rstrip("0").rstrip(".")
    return text + "m"


def _progress_bar(context, window, width=5):
    ratio = min(1.0, max(0.0, context / float(window)))
    filled = min(width, int(round(ratio * width)))
    return "▓" * filled + "░" * (width - filled)


def _format_remaining(seconds):
    seconds = max(0, int(seconds))
    minutes, remainder = divmod(seconds, 60)
    return "{}:{:02d}".format(minutes, remainder)


def _coerce_now(value):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    parsed = _timestamp(value)
    if parsed is None:
        raise ValueError("invalid clock value")
    return parsed


def _render(payload, transcript, inferred_ttl, args, now):
    turn_usage = transcript["usage"]
    timestamp = transcript["timestamp"]
    if timestamp is None:
        raise ValueError("assistant timestamp missing")

    model = payload.get("model")
    if not isinstance(model, dict):
        model = {}
    model_id = str(model.get("id") or "")
    display_name = str(model.get("display_name") or model_id or "Claude")
    window = _window_size(payload, model_id, getattr(args, "window", None))
    context = _context_tokens(turn_usage)
    cache_read = _cache_read_tokens(turn_usage)
    ttl_override = getattr(args, "ttl", None)
    if ttl_override == "1h":
        ttl_seconds = ONE_HOUR_TTL_SECONDS
    elif ttl_override == "5m":
        ttl_seconds = DEFAULT_TTL_SECONDS
    elif ttl_override is None:
        ttl_seconds = inferred_ttl
    else:
        raise ValueError("invalid TTL override")

    elapsed = max(0.0, (now - timestamp).total_seconds())
    remaining = ttl_seconds - elapsed
    if remaining > 0:
        cache_text = "cache warm " + _format_remaining(remaining + 0.999999)
    else:
        cache_text = "cache cold — next turn rewrites ~{}".format(_format_tokens(context))

    if context:
        hit_text = "hit {}%".format(int(round(100.0 * cache_read / context)))
    else:
        hit_text = "hit n/a"

    ratio = context / float(window)
    pieces = [
        "{} · ctx {}/{} {}".format(
            display_name, _format_tokens(context), _format_tokens(window),
            _progress_bar(context, window)),
        cache_text,
        hit_text,
    ]
    if ratio >= 0.85:
        pieces.append("/compact now")
    elif ratio >= 0.60:
        pieces.append("consider /compact")
    line = " · ".join(pieces)

    no_color = getattr(args, "no_color", False) or "NO_COLOR" in os.environ
    if not no_color:
        if ratio >= 0.85 or remaining <= 0:
            color = "\033[31m"
        elif ratio >= 0.60 or remaining <= 60:
            color = "\033[33m"
        else:
            color = "\033[32m"
        line = color + line + "\033[0m"
    return line


def _print_install(stdout):
    toolkit_entry = (Path(__file__).resolve().parents[1] / "tokenmaxxing.py").resolve()
    command = "python3 {} statusline".format(toolkit_entry)
    snippet = json.dumps(
        {"statusLine": {"type": "command", "command": command}},
        separators=(", ", ": "),
    )
    print("Add this snippet to ~/.claude/settings.json:", file=stdout)
    print(snippet, file=stdout)
    print("Only one statusline can be active.", file=stdout)

    settings_path = Path.home() / ".claude" / "settings.json"
    try:
        with settings_path.open("r", encoding="utf-8") as handle:
            settings = json.load(handle)
    except (OSError, json.JSONDecodeError):
        settings = None
    if isinstance(settings, dict) and "statusLine" in settings:
        print("Existing statusLine in ~/.claude/settings.json:", file=stdout)
        print(json.dumps(settings["statusLine"], indent=2, ensure_ascii=False), file=stdout)
    print("This command only prints instructions; it does not change settings files.", file=stdout)


def run(args, stdin=None, stdout=None, now=None):
    """Render a status line; errors always degrade to a one-line exit-zero fallback."""
    output = stdout if stdout is not None else sys.stdout
    try:
        if getattr(args, "install", False):
            _print_install(output)
            return 0

        payload = _read_stdin(sys.stdin if stdin is None else stdin)
        transcript_path = payload.get("transcript_path")
        if not transcript_path:
            raise ValueError("transcript path missing")
        transcript, inferred_ttl = _read_transcript(transcript_path)
        if transcript is None:
            raise ValueError("assistant usage missing")
        line = _render(payload, transcript, inferred_ttl, args, _coerce_now(now))
        print(line, file=output)
        return 0
    except Exception:
        print(FALLBACK_LINE, file=output)
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="tokenmaxxing statusline",
        description="Show live Claude Code context and prompt-cache status",
    )
    add_arguments(parser)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        print(FALLBACK_LINE)
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
