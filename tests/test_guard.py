import contextlib
import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
import sys
sys.path.insert(0, str(SCRIPTS))
import guard


UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def write_transcript(path, timestamp, *, context=129000, cache_creation=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    cache_creation = cache_creation or {}
    usage = {
        "input_tokens": context,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": sum(cache_creation.values()),
        "cache_creation": cache_creation,
        "output_tokens": 10,
    }
    event = {"type": "assistant", "timestamp": timestamp.isoformat(), "message": {
        "model": "claude-sonnet-4", "usage": usage, "content": [],
    }}
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    return path


class TestGuard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.config = self.home / ".claude"
        self.config.mkdir()
        self.settings = self.config / "settings.json"
        self.settings_bytes = b'{"hooks": {"UserPromptSubmit": []}}\n'
        self.settings.write_bytes(self.settings_bytes)
        self.transcript = self.base / "session.jsonl"

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, *, prompt="continue", session_id="session-1", transcript=None):
        return {"session_id": session_id, "transcript_path": str(transcript or self.transcript),
                "prompt": prompt}

    def invoke(self, payload=None, *, now=NOW, input_text=None, min_context=50000, grace=120):
        output = io.StringIO()
        args = SimpleNamespace(hook=True, print_hook=False, min_context=min_context, grace=grace)
        source = io.StringIO(input_text if input_text is not None else json.dumps(payload or {}))
        with patch.object(guard.doctor, "_config_dir", return_value=self.config):
            with contextlib.redirect_stdout(output):
                code = guard.run(args, stdin=source, stdout=output, now=now)
        return code, output.getvalue()

    def test_warm_cache_allows_silently(self):
        write_transcript(self.transcript, NOW - datetime.timedelta(minutes=2))

        code, output = self.invoke(self.payload())

        self.assertEqual(code, 0)
        self.assertEqual(output, "")
        self.assertFalse((self.config / "tokenmaxxing-guard").exists())

    def test_one_hour_cache_ttl_is_inferred(self):
        write_transcript(self.transcript, NOW - datetime.timedelta(minutes=10),
                         cache_creation={"ephemeral_1h_input_tokens": 129000})

        code, output = self.invoke(self.payload())

        self.assertEqual(code, 0)
        self.assertEqual(output, "")

    def test_cold_small_context_allows_silently(self):
        write_transcript(self.transcript, NOW - datetime.timedelta(minutes=10), context=1000)

        code, output = self.invoke(self.payload())

        self.assertEqual(code, 0)
        self.assertEqual(output, "")
        self.assertFalse((self.config / "tokenmaxxing-guard").exists())

    def test_cold_large_context_blocks_once_and_writes_marker(self):
        write_transcript(self.transcript, NOW - datetime.timedelta(minutes=14))

        code, output = self.invoke(self.payload())

        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual(result["decision"], "block")
        self.assertIn("Cache cold (idle 14m)", result["reason"])
        self.assertIn("~129k tokens", result["reason"])
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        marker_files = list((self.config / "tokenmaxxing-guard").glob("*.json"))
        self.assertEqual(len(marker_files), 1)
        self.assertTrue(result["hookSpecificOutput"]["suppressOriginalPrompt"])

    def test_resend_within_grace_period_allows_silently(self):
        write_transcript(self.transcript, NOW - datetime.timedelta(minutes=14))
        self.invoke(self.payload())

        code, output = self.invoke(self.payload(), now=NOW + datetime.timedelta(seconds=30))

        self.assertEqual(code, 0)
        self.assertEqual(output, "")

    def test_slash_command_passes_without_marker(self):
        write_transcript(self.transcript, NOW - datetime.timedelta(minutes=14))

        code, output = self.invoke(self.payload(prompt="/compact"))

        self.assertEqual(code, 0)
        self.assertEqual(output, "")
        self.assertFalse((self.config / "tokenmaxxing-guard").exists())

    def test_malformed_stdin_and_missing_transcript_fail_open(self):
        code, output = self.invoke(input_text="{")
        self.assertEqual((code, output), (0, ""))

        write_transcript(self.transcript, NOW - datetime.timedelta(minutes=14))
        code, output = self.invoke({"session_id": "session-1", "prompt": "continue"})
        self.assertEqual((code, output), (0, ""))

    def test_old_markers_are_pruned(self):
        marker = guard._marker_path(self.config, "old-session")
        marker.parent.mkdir(parents=True)
        marker.write_text("{}", encoding="utf-8")
        old = (NOW - datetime.timedelta(days=2)).timestamp()
        os.utime(marker, (old, old))
        write_transcript(self.transcript, NOW - datetime.timedelta(minutes=2))

        code, output = self.invoke(self.payload(session_id="new-session"))

        self.assertEqual((code, output), (0, ""))
        self.assertFalse(marker.exists())

    def test_print_hook_is_valid_json_and_never_writes_settings(self):
        output = io.StringIO()
        args = SimpleNamespace(print_hook=True, hook=False)
        with contextlib.redirect_stdout(output):
            code = guard.run(args, stdout=output)

        snippet = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertIn("UserPromptSubmit", snippet["hooks"])
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)
        self.assertFalse((self.config / "tokenmaxxing-guard").exists())

    def test_50mb_transcript_allow_path_finishes_under_200ms(self):
        self.transcript.parent.mkdir(parents=True, exist_ok=True)
        assistant = {
            "type": "assistant", "timestamp": (NOW - datetime.timedelta(minutes=2)).isoformat(),
            "message": {"model": "claude-sonnet-4", "usage": {
                "input_tokens": 129000, "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_creation": {"ephemeral_5m_input_tokens": 0}, "output_tokens": 10,
            }, "content": []},
        }
        with self.transcript.open("wb") as handle:
            handle.write(b'{"type":"user","message":{"content":"')
            for _ in range(50):
                handle.write(b"x" * (1024 * 1024))
            handle.write(b'"}}\n')
            handle.write(json.dumps(assistant).encode("utf-8") + b"\n")

        started = time.perf_counter()
        code, output = self.invoke(self.payload())
        elapsed = time.perf_counter() - started

        self.assertEqual((code, output), (0, ""))
        self.assertLess(elapsed, 0.2, f"guard took {elapsed:.3f}s for a 50MB transcript")


if __name__ == "__main__":
    unittest.main()
