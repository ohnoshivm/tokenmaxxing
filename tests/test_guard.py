import argparse
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import guard
from test_audit import ROOT, assistant, usage, write_jsonl


class TestGuard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / 'config'
        self.config.mkdir()
        self.settings = self.config / 'settings.json'
        self.settings.write_bytes(b'{ "test-settings": true }\n')
        self.env = patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.config)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        parser = argparse.ArgumentParser()
        guard.add_arguments(parser)
        self.args = parser.parse_args(['--hook'])
        self.transcript = self.root / 'session.jsonl'
        self.payload = {'session_id': 'test-session', 'transcript_path': str(self.transcript),
                        'hook_event_name': 'UserPromptSubmit', 'prompt': 'continue'}
        self.write_transcript()

    def write_transcript(self, idle=840, context=129000, one_hour=False):
        counts = usage(input_tokens=1000, cache_read=context - 1000)
        if one_hour:
            counts['cache_creation'] = {'ephemeral_1h_input_tokens': 1000}
        write_jsonl(self.transcript, [assistant('latest', (self.now - timedelta(seconds=idle)).isoformat(), counts=counts)])

    def run_hook(self, payload=None, now=None):
        output = io.StringIO()
        raw = json.dumps(self.payload if payload is None else payload)
        code = guard.run(self.args, stdin=io.StringIO(raw), stdout=output, now=now or self.now)
        self.assertEqual(code, 0)
        self.assertEqual(self.settings.read_bytes(), b'{ "test-settings": true }\n')
        return output.getvalue()

    def test_warm_cache_allows_without_output_or_marker(self):
        self.write_transcript(idle=100)
        self.assertEqual(self.run_hook(), '')
        self.assertFalse((self.config / 'tokenmaxxing-guard').exists())

    def test_cold_small_context_allows(self):
        self.write_transcript(context=10000)
        self.assertEqual(self.run_hook(), '')

    def test_cold_large_blocks_once_with_user_reason_and_no_context(self):
        decision = json.loads(self.run_hook())
        self.assertEqual(decision['decision'], 'block')
        self.assertIn('129k tokens', decision['reason'])
        self.assertIn('Re-send', decision['reason'])
        self.assertNotIn('additionalContext', json.dumps(decision))
        self.assertTrue(decision['hookSpecificOutput']['suppressOriginalPrompt'])
        self.assertEqual(len(list((self.config / 'tokenmaxxing-guard').glob('*.marker'))), 1)
        self.assertEqual(self.run_hook(), '')
        self.assertEqual(self.run_hook(now=self.now + timedelta(seconds=119)), '')
        self.assertEqual(json.loads(self.run_hook(now=self.now + timedelta(seconds=121)))['decision'], 'block')

    def test_slash_command_allows_without_reading_transcript(self):
        self.payload['prompt'] = ' /compact'
        with patch.object(guard.statusline, '_read_transcript', side_effect=AssertionError('must skip')):
            self.assertEqual(self.run_hook(), '')
        self.assertFalse((self.config / 'tokenmaxxing-guard').exists())

    def test_malformed_missing_and_invalid_fields_fail_open(self):
        for raw in ('{', 'null', '[]', '42', '', '{"prompt": 4}'):
            output = io.StringIO()
            self.assertEqual(guard.run(self.args, stdin=io.StringIO(raw), stdout=output), 0)
            self.assertEqual(output.getvalue(), '')
        for payload in ({}, {**self.payload, 'session_id': None}, {**self.payload, 'prompt': []},
                        {**self.payload, 'transcript_path': str(self.root / 'missing')}):
            self.assertEqual(self.run_hook(payload), '')

    def test_one_hour_ttl_and_thresholds(self):
        self.write_transcript(idle=1800, one_hour=True)
        self.assertEqual(self.run_hook(), '')
        self.write_transcript(idle=3601, one_hour=True)
        self.assertEqual(json.loads(self.run_hook())['decision'], 'block')
        self.payload['session_id'] = 'threshold'
        self.write_transcript(idle=300, context=50000)
        self.assertEqual(self.run_hook(), '')
        self.write_transcript(idle=301, context=50000)
        self.assertEqual(json.loads(self.run_hook())['decision'], 'block')

    def test_marker_key_cannot_escape_and_old_markers_pruned(self):
        self.payload['session_id'] = '../../outside'
        directory = self.config / 'tokenmaxxing-guard'
        directory.mkdir()
        stale = directory / ('a' * 64 + '.marker')
        stale.write_text('old')
        timestamp = (self.now - timedelta(days=2)).timestamp()
        os.utime(stale, (timestamp, timestamp))
        self.assertEqual(json.loads(self.run_hook())['decision'], 'block')
        self.assertFalse(stale.exists())
        self.assertFalse((self.root / 'outside').exists())
        self.assertEqual(len(list(directory.iterdir())), 1)

    def test_unwritable_or_symlinked_marker_directory_fails_open(self):
        with patch.object(guard, '_mark', side_effect=OSError('denied')):
            self.assertEqual(self.run_hook(), '')
        external = self.root / 'external'
        external.mkdir()
        (self.config / 'tokenmaxxing-guard').symlink_to(external, target_is_directory=True)
        self.assertEqual(self.run_hook(), '')
        self.assertEqual(list(external.iterdir()), [])

    def test_print_hook_writes_nothing(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        parser = argparse.ArgumentParser()
        guard.add_arguments(parser)
        output = io.StringIO()
        guard.run(parser.parse_args(['--print-hook']), stdout=output)
        snippet = json.loads(output.getvalue())
        self.assertIn('guard --hook', snippet['hooks']['UserPromptSubmit'][0]['hooks'][0]['command'])
        self.assertEqual({str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)

    def test_fifty_megabyte_transcript_under_two_hundred_ms(self):
        self.now = datetime.now(timezone.utc)
        self.write_transcript()
        final = self.transcript.read_bytes()
        line = json.dumps({'type': 'user', 'message': {'content': 'x' * 1000}}).encode() + b'\n'
        with self.transcript.open('wb') as handle:
            for _ in range((50 * 1024 * 1024) // len(line) + 1):
                handle.write(line)
            handle.write(final)
        started = time.perf_counter()
        result = subprocess.run([sys.executable, str(ROOT / 'tokenmaxxing.py'), 'guard', '--hook'],
                                input=json.dumps(self.payload), capture_output=True, text=True)
        elapsed = time.perf_counter() - started
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['decision'], 'block')
        # gstack-timing-ok: the approved spec explicitly requires a <200 ms CLI check.
        self.assertLess(elapsed, .2, 'guard subprocess took {:.3f}s'.format(elapsed))


if __name__ == '__main__':
    unittest.main()
