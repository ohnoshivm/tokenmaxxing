import contextlib
import importlib.util
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / 'scripts' / 'audit.py'
spec = importlib.util.spec_from_file_location('tokenmaxxing_audit', AUDIT_PATH)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
cli_spec = importlib.util.spec_from_file_location('tokenmaxxing_cli', ROOT / 'tokenmaxxing.py')
cli = importlib.util.module_from_spec(cli_spec)
cli_spec.loader.exec_module(cli)


def stamp(delta_days=0, delta_hours=0):
    return (datetime.now(timezone.utc) - timedelta(days=delta_days, hours=delta_hours)).isoformat()


def usage(input_tokens=0, cache_read=0, cache_write=0, output=0):
    return {
        'input_tokens': input_tokens,
        'cache_read_input_tokens': cache_read,
        'cache_creation_input_tokens': cache_write,
        'output_tokens': output,
    }


def assistant(mid, at, use=None, counts=None, model='claude-sonnet-4-20250514'):
    return {
        'type': 'assistant',
        'timestamp': at,
        'message': {
            'id': mid,
            'model': model,
            'usage': counts or usage(),
            'content': use or [],
        },
    }


def tool_use(call_id, name='Read', file_path='/repo/src/file.py', command=None):
    inp = {'file_path': file_path}
    if command is not None:
        inp = {'command': command}
    return {'type': 'tool_use', 'id': call_id, 'name': name, 'input': inp}


def tool_result(call_id, content='result'):
    return {'type': 'user', 'timestamp': stamp(), 'message': {
        'content': [{'type': 'tool_result', 'tool_use_id': call_id, 'content': content}],
    }}


def write_jsonl(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(event) + '\n' for event in events), encoding='utf-8')
    return path


def project_file(root, name='project-name', session='session-a'):
    return root / name / f'{session}.jsonl'


class TestAudit(unittest.TestCase):
    def test_repeated_message_id_logged_three_times_counts_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            response = assistant('same-message', stamp(), [tool_use('call-one')], usage(100, 40, 20, 10))
            repeated = json.loads(json.dumps(response))
            transcript = write_jsonl(project_file(root), [response, repeated, repeated, tool_result('call-one', 'x' * 400)])

            sessions = audit.collect(paths=[root])
            report = audit.summarize(sessions)

            self.assertEqual(report['claude']['api_turns'], 1)
            self.assertEqual(report['claude']['tokens']['input'], 100)
            self.assertEqual(len(report['claude']['largest_tool_results']), 1)
            self.assertEqual(report['claude']['largest_tool_results'][0]['call'], 'Read /repo/src/file.py')
            self.assertEqual(report['claude']['repeated_reads'], [])
            self.assertTrue(transcript.is_file())

    def test_resumed_transcript_dedupes_and_skips_continuation_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_ts = stamp(delta_hours=4)
            original = assistant('shared-response', first_ts, [tool_use('shared-call')], usage(10))
            first = write_jsonl(project_file(root, session='session-original'), [original, tool_result('shared-call')])
            resumed = assistant('shared-response', first_ts, [tool_use('shared-call')], usage(9000))
            new_turn = assistant('new-response', stamp(), counts=usage(20))
            second = write_jsonl(project_file(root, session='session-resumed'),
                                 [resumed, tool_result('shared-call'), new_turn])
            mtime = datetime.now().timestamp()
            os.utime(first, (mtime - 2, mtime - 2))
            os.utime(second, (mtime - 1, mtime - 1))

            report = audit.summarize(audit.collect(since=audit.parse_since('30d'), paths=[root]))

            self.assertEqual(report['claude']['api_turns'], 2)
            self.assertEqual(report['claude']['tokens']['input'], 30)
            self.assertEqual(report['claude']['sessions'], 1)
            self.assertEqual(report['claude']['starting_context']['median'], 10)
            self.assertEqual(report['claude']['tool_output']['Read']['calls'], 1)
            self.assertEqual(len(report['claude']['largest_tool_results']), 1)

    def test_subagent_project_comes_from_discovery_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'acme-project-name' / 'session-a' / 'subagents' / 'agent-123.jsonl'
            write_jsonl(path, [assistant('agent-turn', stamp(), counts=usage(30))])

            sessions = audit.collect(paths=[root])

            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].project, 'project/name')
            self.assertTrue(sessions[0].subagent)

    def test_compact_boundary_closes_tool_result_carry_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = [
                assistant('turn-one', stamp(), [tool_use('large-call')], usage(10)),
                tool_result('large-call', 'x' * 400),
                {'type': 'compact_boundary', 'timestamp': stamp()},
                assistant('turn-two', stamp(), counts=usage(10)),
            ]
            write_jsonl(project_file(root), events)

            session = audit.collect(paths=[root])[0]

            self.assertEqual(session.results[0][2], 0)

    def test_cache_rebuild_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = [
                assistant('turn-one', stamp(), counts=usage(100, 0, 500, 10)),
                assistant('turn-two', stamp(), counts=usage(100, 1000, 25000, 10)),
            ]
            write_jsonl(project_file(root), events)

            report = audit.summarize(audit.collect(paths=[root]))

            self.assertEqual(report['claude']['cache_rebuilds']['count'], 1)
            self.assertEqual(report['claude']['cache_rebuilds']['tokens'], 25000)

    def test_codex_uses_last_cumulative_token_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rollout.jsonl'
            write_jsonl(path, [
                {'type': 'session_meta', 'timestamp': stamp(), 'payload': {'id': 'codex-session', 'cwd': '/repo/app'}},
                {'type': 'turn_context', 'payload': {'model': 'gpt-test'}},
                {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
                    'total_token_usage': {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 5}}}},
                {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
                    'total_token_usage': {'input_tokens': 500, 'cached_input_tokens': 200, 'output_tokens': 40}}}},
            ])

            session = audit.parse_codex(path)

            self.assertEqual(session.usage['input'], 300)
            self.assertEqual(session.usage['cache_read'], 200)
            self.assertEqual(session.usage['output'], 40)
            self.assertEqual(session.turns, 2)

    def test_codex_session_meta_id_dedupes_forked_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_dir = root / 'sessions'
            events = [
                {'type': 'session_meta', 'timestamp': stamp(), 'payload': {'id': 'same-session', 'cwd': '/repo/app'}},
                {'type': 'turn_context', 'payload': {'model': 'gpt-test'}},
                {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
                    'total_token_usage': {'input_tokens': 500, 'cached_input_tokens': 200, 'output_tokens': 40}}}},
            ]
            first = write_jsonl(sessions_dir / 'older.jsonl', events)
            second = write_jsonl(sessions_dir / 'fork.jsonl', events)
            mtime = datetime.now().timestamp()
            os.utime(first, (mtime - 2, mtime - 2))
            os.utime(second, (mtime - 1, mtime - 1))

            with patch.object(audit, 'claude_roots', return_value=[]), \
                    patch.object(audit, 'codex_root', return_value=sessions_dir):
                sessions = audit.collect(since=audit.parse_since('30d'))

            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].id, 'older')

    def test_large_result_and_repeated_reads_trigger_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = [tool_use(f'read-{i}') for i in range(3)]
            tools.append(tool_use('large-result', name='Bash', command='  cat   large.log  '))
            events = [assistant('one-turn', stamp(), tools, usage(100, 1000, 0, 10))]
            events.extend(tool_result(f'read-{i}', 'small') for i in range(3))
            events.append(tool_result('large-result', 'x' * 44_000))
            write_jsonl(project_file(root), events)

            report = audit.summarize(audit.collect(paths=[root]))

            self.assertEqual(report['claude']['repeated_reads'][0]['reads'], 3)
            self.assertGreaterEqual(report['claude']['largest_tool_results'][0]['est_tokens'], 10_000)
            self.assertTrue(any('tool results of 10k+' in item for item in report['findings']))
            self.assertTrue(any('files were Read 3+ times' in item for item in report['findings']))

    def test_run_emits_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(project_file(root), [assistant('turn', stamp(), counts=usage(7))])
            args = SimpleNamespace(since='30d', project=None, path=[root], top=10, json=True, compare=False)
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                code = audit.run(args)

            self.assertEqual(code, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report['claude']['api_turns'], 1)
            self.assertIn('work', report)
            self.assertIn('skills_used', report)

    def test_tool_labels_keep_path_tail_and_collapse_commands(self):
        path = '/' + 'prefix/' * 20 + 'final-file.py'
        label = audit.tool_label('Read', {'file_path': path})
        self.assertTrue(label.endswith('…' + path[-60:]))
        self.assertEqual(audit.tool_label('Bash', {'command': '  git   status\n --short  '}),
                         'Bash `git status --short`')

    def test_compare_splits_timestamps_into_equal_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = [
                assistant('previous-turn', stamp(delta_days=10), counts=usage(100, 0, 0, 10)),
                assistant('current-turn', stamp(delta_days=2), counts=usage(200, 100, 0, 50)),
            ]
            write_jsonl(project_file(root), events)
            args = SimpleNamespace(since='7d', project=None, path=[root], top=10, json=True, compare=True)
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                code = audit.run(args)
            report = json.loads(output.getvalue())

            self.assertEqual(code, 0)
            self.assertEqual(report['claude']['api_turns'], 1)
            self.assertEqual(report['compare']['current']['api_turns'], 1)
            self.assertEqual(report['compare']['previous']['api_turns'], 1)
            self.assertEqual(report['compare']['current']['output_tokens_per_turn'], 50)
            self.assertEqual(report['compare']['previous']['output_tokens_per_turn'], 10)
            self.assertEqual(report['compare']['delta']['output_tokens_per_turn'], 40)

    def test_compare_text_formats_values_changes_and_directions(self):
        current = dict(zip((key for key, _ in audit.COMPARE_METRICS), (47113.68, .97, 60000, 1.2, 500, 300)))
        previous = dict(zip((key for key, _ in audit.COMPARE_METRICS), (31620, .98, 80000, 1, 0, 200)))
        data = {'current': {'api_turns': 1000, **current},
                'previous': {'api_turns': 2000, **previous},
                'delta': {'api_turns': -1000, **{key: current[key] - previous[key] for key in current}}}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            audit.print_comparison(data)
        rendered = output.getvalue()
        self.assertIn('47.1k current · 31.6k previous · delta +15.5k (+49%) · worse', rendered)
        self.assertIn('97% current · 98% previous · delta -1.0 pp (-1%) · worse', rendered)
        self.assertIn('60.0k current · 80.0k previous · delta -20.0k (-25%) · better', rendered)
        self.assertIn('1.2% current · 1.0% previous · delta +0.2 pp (+20%) · worse', rendered)
        self.assertIn('500 current · 0 previous · delta +500 · worse', rendered)
        self.assertIn('300 current · 200 previous · delta +100 (+50%) · neutral', rendered)

    def test_compare_text_handles_missing_and_unchanged_values(self):
        values = {key: None for key, _ in audit.COMPARE_METRICS}
        values['cache_hit_rate'] = .95
        data = {'current': {'api_turns': 1, **values}, 'previous': {'api_turns': 1, **values},
                'delta': {'api_turns': 0, **{key: None for key in values}, 'cache_hit_rate': 0}}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            audit.print_comparison(data)
        self.assertIn('95% current · 95% previous · delta +0.0 pp (+0%) · unchanged', output.getvalue())
        self.assertIn('— current · — previous · delta —', output.getvalue())
        data['current']['cache_hit_rate'] = .96
        data['delta']['cache_hit_rate'] = .01
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            audit.print_comparison(data)
        self.assertIn('delta +1.0 pp (+1%) · better', output.getvalue())

    def test_cli_audit_and_version_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(project_file(root), [assistant('cli-turn', stamp(), counts=usage(7))])
            result = subprocess.run([sys.executable, str(ROOT / 'tokenmaxxing.py'), 'audit',
                                     '--path', str(root), '--json'], text=True, capture_output=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['claude']['api_turns'], 1)

        result = subprocess.run([sys.executable, str(ROOT / 'tokenmaxxing.py'), '--version'],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'tokenmaxxing 1.5.0')

        result = subprocess.run([sys.executable, str(ROOT / 'tokenmaxxing.py'), '--help'],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ('audit', 'doctor', 'statusline'):
            self.assertIn(name, result.stdout)

    def test_compare_rejects_unbounded_all_window(self):
        args = SimpleNamespace(since='all', project=None, path=None, top=10, json=True, compare=True)
        error = io.StringIO()

        with contextlib.redirect_stderr(error):
            code = audit.run(args)

        self.assertEqual(code, 2)
        self.assertIn('requires a bounded --since', error.getvalue())

    def test_missing_lazy_subcommand_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = io.StringIO()
            with patch.object(cli, 'ROOT', Path(tmp)), contextlib.redirect_stdout(output):
                code = cli.main(['doctor'])

        self.assertEqual(code, 2)
        self.assertIn('scripts/doctor.py is missing', output.getvalue())


if __name__ == '__main__':
    unittest.main()
