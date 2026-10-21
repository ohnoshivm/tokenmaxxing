import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from test_audit import audit, assistant, stamp, tool_use, tool_result, usage, write_jsonl


def result(call_id, failed=False):
    event = tool_result(call_id)
    event['message']['content'][0]['is_error'] = failed
    return event


class TestWork(unittest.TestCase):
    def claude(self, calls):
        events = []
        for index, (name, inp, failed) in enumerate(calls):
            call = {'type': 'tool_use', 'id': str(index), 'name': name, 'input': inp}
            events.append(assistant(str(index), stamp(), [call], usage(100)))
            if failed is not None:
                events.append(result(str(index), failed))
        with tempfile.TemporaryDirectory() as tmp:
            return audit.parse_claude(write_jsonl(Path(tmp) / 'session.jsonl', events))

    def test_claude_results_checks_edits_commits_and_order(self):
        session = self.claude([
            ('Bash', {'command': 'pytest'}, False),
            ('Edit', {}, False), ('Write', {}, True),
            ('Bash', {'command': 'echo pytest'}, False),
            ('Bash', {'command': 'python3 -m unittest'}, True),
            ('Bash', {'command': 'git commit -m ok'}, False),
            ('Bash', {'command': 'git commit -m fail'}, True),
            ('Bash', {'command': 'git commit --dry-run'}, False),
            ('Bash', {'command': 'npm test'}, None),
        ])
        work = audit.summarize([session])['work']
        self.assertEqual((work['edits'], work['checks'], work['checks_passed'], work['checks_failed'], work['commits']),
                         (1, 3, 1, 1, 1))
        self.assertEqual(work['unverified_edit_sessions'], 1)
        self.assertEqual(work['verified_edit_sessions'], 0)

    def test_passing_after_last_edit_and_distinct_checks(self):
        session = self.claude([('Edit', {}, False), ('Bash', {'command': 'pytest  -q'}, False),
                               ('Bash', {'command': ' pytest -q '}, False)])
        work = audit.summarize([session])['work']
        self.assertEqual(work['verified_edit_sessions'], 1)
        self.assertEqual(work['distinct_passing_checks'], 1)
        self.assertEqual(work['usage_per_passing_check_raw'], session.weighted() / 2)
        self.assertEqual(work['usage_per_passing_check'], session.weighted())
        session = self.claude([('Edit', {}, False), ('Bash', {'command': 'pytest'}, False), ('Write', {}, False)])
        self.assertEqual(audit.summarize([session])['work']['unverified_edit_sessions'], 1)

    def test_check_pattern_segments_and_quoted_commands(self):
        yes = ['pytest -q', 'python3 -m unittest discover', 'pnpm run typecheck', 'bun test', 'cargo clippy',
               'go vet ./...', 'make check', './gradlew clean test', 'mvn -q test', 'swift build',
               'playwright test', 'cd app && npm test', 'echo hello; ruff check .', 'cat f | mypy app',
               'echo ok\npytest', '/usr/bin/python3 -m pytest']
        no = ['echo pytest', 'printf "pytest; npm test"', 'cat pytest.log', 'echo "x && pytest"', 'git show test', 'pytest-wrapper', 'npm test-fixture']
        for command in yes:
            with self.subTest(command=command):
                self.assertTrue(audit.check_commands(command))
        for command in no:
            with self.subTest(command=command):
                self.assertFalse(audit.check_commands(command))

    def test_skills_tool_and_slash_sources_with_plugin_field(self):
        events = [assistant('first', stamp(), [
            {'type': 'tool_use', 'id': 's1', 'name': 'Skill', 'input': {'skill': 'review'}},
            {'type': 'tool_use', 'id': 's2', 'name': 'Skill', 'input': {'skill': 'studio:build'}}]),
            {'type': 'user', 'uuid': 'slash1', 'timestamp': stamp(), 'message': {'content':
                '<command-message>review</command-message><command-name>/review</command-name>'}},
            {'type': 'user', 'uuid': 'slash2', 'timestamp': stamp(), 'message': {'content': [
                {'type': 'text', 'text': '<command-name>/studio:build</command-name>'}]}},
            {'type': 'user', 'timestamp': stamp(), 'message': {'content': '/manual arg'}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = write_jsonl(Path(tmp) / 'session.jsonl', events)
            skills = audit.summarize([audit.parse_claude(path)])['skills_used']
        self.assertEqual(skills, [
            {'name': 'build', 'plugin': 'studio', 'count': 2},
            {'name': 'manual', 'plugin': None, 'count': 1},
            {'name': 'review', 'plugin': None, 'count': 2}])

    def test_unknown_model_and_tier_weighted_mix(self):
        session = self.claude([('Edit', {}, False)])
        session.model_units.clear()
        session.model_units.update({'claude-opus-5': 50, 'gpt-6.1-sol': 30, 'gpt-6-luna': 10,
                                    'deepseek-v4': 5, 'mystery': 5})
        work = audit.summarize([session])['work']
        self.assertEqual(work['premium_share'], .8)
        self.assertEqual(work['unknown_models'], ['mystery'])
        self.assertEqual(work['model_mix']['unknown'], .05)

    def test_codex_function_custom_patch_and_shell_events(self):
        events = [
            {'type': 'session_meta', 'timestamp': stamp(), 'payload': {'id': 'codex-work', 'cwd': '/repo'}},
            {'type': 'turn_context', 'payload': {'model': 'gpt-6.1-sol'}},
        ]
        def call(kind, cid, name, arguments):
            events.append({'type': 'response_item', 'timestamp': stamp(), 'payload':
                           {'type': kind, 'call_id': cid, 'name': name, 'arguments': arguments}})
        def output(kind, cid, value):
            events.append({'type': 'response_item', 'timestamp': stamp(), 'payload':
                           {'type': kind, 'call_id': cid, 'output': value}})
        call('custom_tool_call', 'p1', 'apply_patch', 'patch')
        output('custom_tool_call_output', 'p1', 'Success. Updated the following files:\nM file.py')
        call('custom_tool_call', 'p2', 'apply_patch', 'patch')
        output('custom_tool_call_output', 'p2', 'Failed to find expected lines')
        call('function_call', 'c1', 'exec_command', json.dumps({'cmd': 'pytest -q'}))
        output('function_call_output', 'c1', 'Process exited with code 0\nOutput:\npassed')
        call('function_call', 'c2', 'shell', json.dumps({'command': ['bash', '-lc', 'npm test']}))
        output('function_call_output', 'c2', json.dumps({'exit_code': 1}))
        call('function_call', 'c3', 'exec_command', {'cmd': 'git commit -m test'})
        output('function_call_output', 'c3', {'exit_code': 0})
        call('function_call', 'c4', 'exec_command', {'cmd': 'git commit --dry-run'})
        output('function_call_output', 'c4', {'exit_code': 0})
        call('function_call', 'c5', 'exec_command', {'cmd': 'pytest --collect-only'})
        output('function_call_output', 'c5', 'still running')
        events.append({'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
            'total_token_usage': {'input_tokens': 100, 'output_tokens': 10}}}})
        with tempfile.TemporaryDirectory() as tmp:
            session = audit.parse_codex(write_jsonl(Path(tmp) / 'rollout.jsonl', events))
        work = audit.summarize([session])['work']
        self.assertEqual((work['edits'], work['checks'], work['checks_passed'], work['checks_failed'], work['commits']),
                         (1, 3, 1, 1, 1))
        self.assertEqual(work['verified_edit_sessions'], 1)
        self.assertEqual(work['premium_share'], 1)

    def test_compare_too_few_and_directions(self):
        session = self.claude([('Edit', {}, False), ('Bash', {'command': 'pytest'}, False)])
        report = audit.summarize([session])
        comparison = audit.build_comparison(report, report)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            audit.print_comparison(comparison)
        self.assertIn('Usage per passing check: n/a (too few checks)', output.getvalue())
        self.assertIsNone(comparison['delta']['usage_per_passing_check'])
        session.work['checks_passed'] = 5
        report = audit.summarize([session])
        self.assertIsNotNone(audit.build_comparison(report, report)['delta']['usage_per_passing_check'])


    def test_distinct_checks_preserve_directory_and_session(self):
        session = self.claude([('Bash', {'command': 'cd first && pytest'}, False),
                               ('Bash', {'command': 'cd second && pytest'}, False)])
        self.assertEqual(audit.summarize([session])['work']['distinct_passing_checks'], 2)
        self.assertEqual(audit.summarize([session, session])['work']['distinct_passing_checks'], 4)

    def test_slash_only_and_resumed_user_message_deduplication(self):
        event = {'type': 'user', 'uuid': 'shared-slash', 'timestamp': stamp(),
                 'message': {'content': '<command-name>/manual</command-name>'}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(root / 'original.jsonl', [event])
            write_jsonl(root / 'resumed.jsonl', [event, assistant('new', stamp())])
            report = audit.summarize(audit.collect(paths=[root]))
        self.assertEqual(report['skills_used'], [{'name': 'manual', 'plugin': None, 'count': 1}])

    def test_codex_native_execution_events(self):
        events = [
            {'type': 'session_meta', 'timestamp': stamp(), 'payload': {'id': 'native', 'cwd': '/repo'}},
            {'type': 'event_msg', 'payload': {'type': 'patch_apply_begin', 'call_id': 'patch'}},
            {'type': 'event_msg', 'payload': {'type': 'patch_apply_end', 'call_id': 'patch', 'success': True}},
            {'type': 'event_msg', 'payload': {'type': 'exec_command_begin', 'call_id': 'check', 'command': ['pytest']}},
            {'type': 'event_msg', 'payload': {'type': 'exec_command_end', 'call_id': 'check', 'exit_code': 0}},
            {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': 10}}}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            session = audit.parse_codex(write_jsonl(Path(tmp) / 'rollout.jsonl', events))
        work = audit.summarize([session])['work']
        self.assertEqual((work['edits'], work['checks_passed'], work['verified_edit_sessions']), (1, 1, 1))

    def test_work_findings_thresholds(self):
        session = self.claude([('Edit', {}, False), ('Bash', {'command': 'pytest'}, True)])
        findings = audit.summarize([session])['findings']
        self.assertTrue(any('failed checks' in f for f in findings))
        self.assertTrue(any('edits often end' in f for f in findings))


if __name__ == '__main__':
    unittest.main()
