import importlib.util
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('tokenmaxxing_guard', SCRIPTS / 'guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

NOW = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)


def assistant_turn(idle_minutes, context=120_000, ttl_1h=False):
    at = (NOW - timedelta(minutes=idle_minutes)).isoformat()
    usage = {'input_tokens': 1_000, 'cache_read_input_tokens': context - 1_000,
             'cache_creation_input_tokens': 0, 'output_tokens': 10}
    if ttl_1h:
        usage['cache_creation'] = {'ephemeral_1h_input_tokens': 5_000, 'ephemeral_5m_input_tokens': 0}
    return {'type': 'assistant', 'timestamp': at,
            'message': {'id': 'msg_1', 'model': 'claude-sonnet-5-5', 'usage': usage,
                        'content': [{'type': 'text', 'text': 'done'}]}}


def write_transcript(path, *turns):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(turn) for turn in turns) + '\n', encoding='utf-8')
    return path


def payload(path, prompt='keep going', session_id='session-1'):
    return {'session_id': session_id, 'transcript_path': str(path), 'cwd': '/work',
            'prompt': prompt, 'hook_event_name': 'UserPromptSubmit'}


def args(**overrides):
    values = {'print_hook': False, 'hook': True, 'min_context': 50_000, 'grace': 120,
              'config_dir': None}
    values.update(overrides)
    return SimpleNamespace(**values)


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config = self.tmp / 'claude'
        self.config.mkdir()
        self.addCleanup(lambda: __import__('shutil').rmtree(self.tmp, ignore_errors=True))

    def transcript(self, *turns):
        return write_transcript(self.tmp / 'transcript.jsonl', *turns)

    def hook(self, body, options=None):
        out = io.StringIO()
        code = guard.run(options or args(config_dir=self.config), stdin=io.StringIO(body),
                         stdout=out, now=NOW)
        return code, out.getvalue()

    def markers(self):
        return sorted((self.config / guard.MARKER_DIR).glob('*.json'))

    def test_warm_cache_is_allowed(self):
        path = self.transcript(assistant_turn(2))
        code, output = self.hook(json.dumps(payload(path)))
        self.assertEqual(code, 0)
        self.assertEqual(output, '')
        self.assertEqual(self.markers(), [])

    def test_cold_cache_with_small_context_is_allowed(self):
        path = self.transcript(assistant_turn(30, context=10_000))
        code, output = self.hook(json.dumps(payload(path)))
        self.assertEqual(code, 0)
        self.assertEqual(output, '')
        self.assertEqual(self.markers(), [])

    def test_cold_cache_with_large_context_blocks_once(self):
        path = self.transcript(assistant_turn(14))
        code, output = self.hook(json.dumps(payload(path)))
        self.assertEqual(code, 0)
        verdict = json.loads(output)
        self.assertEqual(verdict['decision'], 'block')
        self.assertIn('Cache cold (idle 14m)', verdict['reason'])
        self.assertIn('~120k tokens', verdict['reason'])
        self.assertIn('/compact', verdict['reason'])
        self.assertEqual(len(self.markers()), 1)

    def test_resend_within_grace_is_allowed(self):
        path = self.transcript(assistant_turn(14))
        self.hook(json.dumps(payload(path)))
        code, output = self.hook(json.dumps(payload(path, prompt='go ahead')))
        self.assertEqual(code, 0)
        self.assertEqual(output, '')
        self.assertEqual(len(self.markers()), 1)

    def test_block_is_repeated_after_the_grace_window(self):
        path = self.transcript(assistant_turn(14))
        self.hook(json.dumps(payload(path)))
        later = NOW + timedelta(seconds=121)
        out = io.StringIO()
        guard.run(args(config_dir=self.config), stdin=io.StringIO(json.dumps(payload(path))),
                  stdout=out, now=later)
        self.assertEqual(json.loads(out.getvalue())['decision'], 'block')

    def test_slash_command_is_allowed(self):
        path = self.transcript(assistant_turn(60))
        for prompt in ('/compact', '  /clear'):
            code, output = self.hook(json.dumps(payload(path, prompt=prompt)))
            self.assertEqual(code, 0)
            self.assertEqual(output, '')
        self.assertEqual(self.markers(), [])

    def test_long_ttl_keeps_the_cache_warm(self):
        path = self.transcript(assistant_turn(20, ttl_1h=True))
        code, output = self.hook(json.dumps(payload(path)))
        self.assertEqual(output, '')
        self.assertEqual(self.markers(), [])

    def test_malformed_stdin_exits_zero_silently(self):
        for body in ('', 'not json', '[]', 'null'):
            code, output = self.hook(body)
            self.assertEqual((code, output), (0, ''))

    def test_missing_transcript_exits_zero(self):
        code, output = self.hook(json.dumps(payload(self.tmp / 'nope.jsonl')))
        self.assertEqual((code, output), (0, ''))

    def test_missing_session_id_still_gets_a_marker(self):
        path = self.transcript(assistant_turn(20))
        code, output = self.hook(json.dumps(payload(path, session_id='')))
        self.assertEqual(json.loads(output)['decision'], 'block')
        self.assertEqual([item.name for item in self.markers()], ['session.json'])

    def test_stale_markers_are_pruned(self):
        stale = self.config / guard.MARKER_DIR / 'old.json'
        stale.parent.mkdir(parents=True)
        stale.write_text(json.dumps({'blocked_at': (NOW - timedelta(days=2)).isoformat()}))
        path = self.transcript(assistant_turn(30))
        self.hook(json.dumps(payload(path)))
        self.assertFalse(stale.exists())
        self.assertEqual(len(self.markers()), 1)

    def test_print_hook_writes_no_files(self):
        out = io.StringIO()
        code = guard.run(args(print_hook=True, hook=False, config_dir=self.config), stdout=out, now=NOW)
        self.assertEqual(code, 0)
        snippet = json.loads(out.getvalue())
        command = snippet['hooks']['UserPromptSubmit'][0]['hooks'][0]['command']
        self.assertIn('tokenmaxxing.py guard --hook', command)
        self.assertIn('--min-context 50000', command)
        self.assertFalse((self.config / guard.MARKER_DIR).exists())

    def test_without_a_mode_it_asks_for_one(self):
        out = io.StringIO()
        code = guard.run(args(hook=False), stdout=out, now=NOW)
        self.assertEqual(code, 2)
        self.assertIn('--print-hook', out.getvalue())

    def test_large_transcript_stays_under_200ms(self):
        path = self.tmp / 'big.jsonl'
        filler = b'{"type":"user","message":{"role":"user","content":"' + b'x' * 400 + b'"}}\n'
        with path.open('wb') as handle:
            handle.write(filler * ((50 * 1024 * 1024) // len(filler)))
            handle.write(json.dumps(assistant_turn(30)).encode() + b'\n')
        size_mb = path.stat().st_size / (1024 * 1024)
        started = time.perf_counter()
        verdict = guard.decide(payload(path), self.config, now=NOW)
        elapsed = time.perf_counter() - started
        self.assertGreater(size_mb, 45)
        self.assertEqual(verdict['decision'], 'block')
        self.assertLess(elapsed, 0.2, f'guard took {elapsed * 1000:.0f} ms on {size_mb:.0f} MB')


if __name__ == '__main__':
    unittest.main()
