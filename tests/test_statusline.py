import builtins
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import statusline


def usage(input_tokens=100, cache_read=9900, cache_creation=0,
          ephemeral_5m=0, ephemeral_1h=0):
    return {
        "input_tokens": input_tokens,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_creation,
        "cache_creation": {
            "ephemeral_5m_input_tokens": ephemeral_5m,
            "ephemeral_1h_input_tokens": ephemeral_1h,
        },
    }


def assistant_line(timestamp, turn_usage, model="claude-opus-5-5"):
    return json.dumps({
        "type": "assistant",
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "message": {
            "role": "assistant",
            "model": model,
            "usage": turn_usage,
        },
    })


class TrackingReader:
    def __init__(self, handle):
        self.handle = handle
        self.bytes_read = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return self.handle.__exit__(*exc_info)

    def seek(self, *args):
        return self.handle.seek(*args)

    def tell(self):
        return self.handle.tell()

    def read(self, size=-1):
        data = self.handle.read(size)
        self.bytes_read += len(data)
        return data

    def readline(self, size=-1):
        data = self.handle.readline(size)
        self.bytes_read += len(data)
        return data


class StatuslineTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.transcript = self.root / "transcript.jsonl"
        self.now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    def write_lines(self, *lines):
        self.transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_status(self, payload, ttl=None, window=None, now=None):
        output = io.StringIO()
        args = SimpleNamespace(
            install=False,
            ttl=ttl,
            window=window,
            no_color=True,
        )
        result = statusline.run(
            args,
            stdin=io.StringIO(json.dumps(payload)),
            stdout=output,
            now=now or self.now,
        )
        return result, output.getvalue().strip()

    def payload(self, transcript=None, **extra):
        result = {
            "transcript_path": str(transcript or self.transcript),
            "model": {"id": "claude-opus-5-5", "display_name": "Opus 5.5"},
            "context_window": 200000,
        }
        result.update(extra)
        return result

    def test_five_minute_warm_and_cold_boundary(self):
        self.write_lines(assistant_line(self.now - timedelta(seconds=299), usage()))
        result, line = self.run_status(self.payload())
        self.assertEqual(result, 0)
        self.assertIn("cache warm 0:01", line)
        self.assertIn("ctx 10k/200k", line)
        self.assertIn("hit 99%", line)

        self.write_lines(assistant_line(self.now - timedelta(seconds=300), usage()))
        result, line = self.run_status(self.payload())
        self.assertEqual(result, 0)
        self.assertIn("cache cold — next turn rewrites ~10k", line)

    def test_one_hour_warm_and_cold_boundary(self):
        one_hour_usage = usage(cache_creation=400, ephemeral_1h=400)
        self.write_lines(assistant_line(self.now - timedelta(seconds=3599), one_hour_usage))
        result, line = self.run_status(self.payload())
        self.assertEqual(result, 0)
        self.assertIn("cache warm 0:01", line)

        self.write_lines(assistant_line(self.now - timedelta(seconds=3600), one_hour_usage))
        result, line = self.run_status(self.payload())
        self.assertEqual(result, 0)
        self.assertIn("cache cold — next turn rewrites ~10k", line)

    def test_ttl_override(self):
        self.write_lines(assistant_line(self.now - timedelta(seconds=600), usage()))
        _, default_line = self.run_status(self.payload())
        _, override_line = self.run_status(self.payload(), ttl="1h")
        self.assertIn("cache cold", default_line)
        self.assertIn("cache warm 50:00", override_line)

    def test_synthetic_message_is_skipped(self):
        real = assistant_line(self.now - timedelta(seconds=20), usage(input_tokens=200, cache_read=800))
        synthetic = assistant_line(self.now, usage(input_tokens=999999), model="<synthetic>")
        self.write_lines(real, synthetic)
        _, line = self.run_status(self.payload())
        self.assertIn("ctx 1k/200k", line)
        self.assertNotIn("999k", line)

    def test_malformed_json_line_is_ignored(self):
        self.write_lines(assistant_line(self.now - timedelta(seconds=10), usage()), "{not json")
        result, line = self.run_status(self.payload())
        self.assertEqual(result, 0)
        self.assertIn("ctx 10k/200k", line)

    def test_missing_transcript_uses_fallback(self):
        result, line = self.run_status(self.payload(transcript=self.root / "missing.jsonl"))
        self.assertEqual(result, 0)
        self.assertEqual(line, statusline.FALLBACK_LINE)

    def test_large_transcript_reads_only_its_tail(self):
        latest = assistant_line(self.now - timedelta(seconds=15), usage(input_tokens=321, cache_read=678))
        with self.transcript.open("wb") as handle:
            handle.write(b"x" * (1024 * 1024 + 128))
            handle.write(b"\n")
            handle.write(latest.encode("utf-8") + b"\n")

        original_open = builtins.open
        readers = []

        def tracking_open(*args, **kwargs):
            reader = TrackingReader(original_open(*args, **kwargs))
            readers.append(reader)
            return reader

        with mock.patch("builtins.open", side_effect=tracking_open):
            result, line = self.run_status(self.payload())

        self.assertEqual(result, 0)
        self.assertIn("ctx 999/200k", line)
        self.assertEqual(len(readers), 1)
        self.assertLessEqual(readers[0].bytes_read, statusline.TAIL_BYTES + 1024)

    def test_no_color_environment_disables_ansi(self):
        self.write_lines(assistant_line(self.now - timedelta(seconds=10), usage()))
        with mock.patch.dict(os.environ, {"NO_COLOR": ""}):
            output = io.StringIO()
            args = SimpleNamespace(install=False, ttl=None, window=None, no_color=False)
            statusline.run(args, stdin=io.StringIO(json.dumps(self.payload())),
                           stdout=output, now=self.now)
        self.assertNotIn("\x1b[", output.getvalue())

    def test_compaction_thresholds_and_window_override(self):
        self.write_lines(assistant_line(self.now - timedelta(seconds=10),
                                        usage(input_tokens=130000, cache_read=0)))
        _, line = self.run_status(self.payload(), window=200000)
        self.assertIn("consider /compact", line)

        self.write_lines(assistant_line(self.now - timedelta(seconds=10),
                                        usage(input_tokens=170000, cache_read=0)))
        _, line = self.run_status(self.payload(), window=200000)
        self.assertIn("/compact now", line)
        self.assertNotIn("consider /compact", line)

    def test_context_window_fallback_and_one_million_model(self):
        self.write_lines(assistant_line(self.now - timedelta(seconds=10), usage()))
        payload = self.payload()
        payload.pop("context_window")
        payload["model"]["id"] = "claude-opus-[1m]"
        _, line = self.run_status(payload)
        self.assertIn("ctx 10k/1m", line)

    def test_install_prints_snippet_and_never_writes_settings(self):
        with tempfile.TemporaryDirectory() as home:
            settings_dir = Path(home) / ".claude"
            settings_dir.mkdir()
            settings = settings_dir / "settings.json"
            original = '{"statusLine":{"type":"command","command":"echo existing"}}\n'
            settings.write_text(original, encoding="utf-8")
            output = io.StringIO()
            args = SimpleNamespace(install=True)
            with mock.patch.dict(os.environ, {"HOME": home}):
                result = statusline.run(args, stdout=output)

            self.assertEqual(result, 0)
            self.assertIn('"command": "python3 ' + str(ROOT / "tokenmaxxing.py") + ' statusline"',
                          output.getvalue())
            self.assertIn("Only one statusline can be active", output.getvalue())
            self.assertIn("echo existing", output.getvalue())
            self.assertEqual(settings.read_text(encoding="utf-8"), original)

        with tempfile.TemporaryDirectory() as home:
            output = io.StringIO()
            with mock.patch.dict(os.environ, {"HOME": home}):
                statusline.run(SimpleNamespace(install=True), stdout=output)
            self.assertFalse((Path(home) / ".claude" / "settings.json").exists())


if __name__ == "__main__":
    unittest.main()
