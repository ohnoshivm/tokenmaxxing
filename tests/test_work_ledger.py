import contextlib
import importlib.util
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('tokenmaxxing_audit_work', SCRIPTS / 'audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def stamp(delta_minutes=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=delta_minutes)).isoformat()


def usage(input_tokens=10, cache_read=0, cache_write=0, output=1):
    return {
        'input_tokens': input_tokens,
        'cache_read_input_tokens': cache_read,
        'cache_creation_input_tokens': cache_write,
        'output_tokens': output,
    }


def assistant(mid, calls, counts=None, model='claude-sonnet-5-5', at=None):
    return {
        'type': 'assistant',
        'timestamp': at or stamp(),
        'message': {'id': mid, 'model': model, 'usage': counts or usage(), 'content': calls},
    }


def tool_use(call_id, name, **inp):
    return {'type': 'tool_use', 'id': call_id, 'name': name, 'input': inp}


def result(call_id, is_error=None, content='ok'):
    block = {'type': 'tool_result', 'tool_use_id': call_id, 'content': content}
    if is_error is not None:
        block['is_error'] = is_error
    return {'type': 'user', 'timestamp': stamp(), 'message': {'content': [block]}}


def prompt(text):
    return {'type': 'user', 'timestamp': stamp(), 'message': {'role': 'user', 'content': text}}


def write_jsonl(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(event) + '\n' for event in events), encoding='utf-8')
    return path


def transcript(root, name='project-name', session='session-a'):
    return root / name / f'{session}.jsonl'


def summarize(events, **kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_jsonl(transcript(root), events)
        return audit.summarize(audit.collect(paths=[root], **kwargs))


class CheckPatternTests(unittest.TestCase):
    def test_matches_wrapped_and_extended_checks(self):
        for command in ('npx tsc --noEmit', 'npx vitest run', 'npx playwright test',
                        'pnpm exec tsc', 'pnpm dlx vitest run', 'bunx eslint .',
                        'uv run pytest', 'poetry run pytest', 'python -m pytest',
                        'python3 -m unittest', 'FOO=1 npx tsc', 'cd app && bunx vitest',
                        'npm run test:unit', 'pnpm build:prod', 'yarn lint:fix',
                        'bun run check:types', 'next build', 'vite build', 'astro check',
                        'svelte-check', 'node --test', 'deno test'):
            with self.subTest(command=command):
                self.assertTrue(audit.is_check_command(command), command)

    def test_matches_common_check_commands(self):
        for command in ('pytest -q', 'python3 -m unittest discover -s tests', 'npm test',
                        'pnpm run lint', 'yarn build', 'bun typecheck', 'vitest run', 'jest --ci',
                        'tsc -p .', 'eslint src', 'ruff check .', 'mypy scripts', 'cargo test',
                        'cargo clippy --all', 'go test ./...', 'go vet ./...', 'make check',
                        'make test', './gradlew test', 'mvn -q test', 'swift test',
                        'playwright test e2e', 'cd app && pytest -x', 'FOO=1 pytest',
                        'npx vitest run', 'uv run pytest'):
            with self.subTest(command=command):
                self.assertTrue(audit.is_check_command(command), command)

    def test_does_not_match_lookalikes(self):
        for command in ('echo pytest', 'cat tests/test_audit.py', 'grep -r pytest .',
                        'git commit -m "run pytest"', 'ls', '', 'jestfoo', 'tscfoo',
                        'pytestfoo', 'eslintfoo', 'tsc-rs', 'npx jestfoo', 'pnpm dlx tscfoo',
                        'next buildfoo', 'playwright testfoo', 'npm run testing',
                        'echo npx vitest', 'grep pytest', 'FOO=1 echo pytest'):
            with self.subTest(command=command):
                self.assertFalse(audit.is_check_command(command), command)

    def test_commit_detection_skips_dry_run(self):
        self.assertTrue(audit.has_commit('git add -A && git commit -m "x"'))
        self.assertFalse(audit.has_commit('git commit --dry-run -m "x"'))
        self.assertFalse(audit.has_commit('echo git commit'))


class WorkLedgerTests(unittest.TestCase):
    def test_omitted_error_means_success_only_with_a_result(self):
        report = summarize([
            assistant('t1', [tool_use('e1', 'Edit', file_path='/repo/a.py'),
                             tool_use('e2', 'Write', file_path='/repo/b.py')]),
            result('e1'),
            assistant('t2', [tool_use('c1', 'Bash', command='pytest'),
                             tool_use('c2', 'Bash', command='npm test'),
                             tool_use('g1', 'Bash', command='git commit -m "x"')]),
            result('c1'),
            result('g1'),
        ])
        work = report['work']
        self.assertEqual(work['edits'], 1)
        self.assertEqual(work['checks'], 2)
        self.assertEqual(work['checks_passed'], 1)
        self.assertEqual(work['checks_failed'], 0)
        self.assertEqual(work['verified_edit_sessions'], 1)
        self.assertEqual(work['commits'], 1)

    def test_counts_successful_and_failed_edits(self):
        report = summarize([
            assistant('t1', [tool_use('e1', 'Write', file_path='/repo/a.py'),
                             tool_use('e2', 'Edit', file_path='/repo/b.py'),
                             tool_use('e3', 'Read', file_path='/repo/c.py')]),
            result('e1', is_error=False),
            result('e2', is_error=True),
            result('e3', is_error=False),
        ])

        self.assertEqual(report['work']['edits'], 1)
        self.assertEqual(report['work']['unverified_edit_sessions'], 1)
        self.assertEqual(report['work']['verified_edit_sessions'], 0)

    def test_counts_checks_by_outcome_and_ignores_unknown(self):
        report = summarize([
            assistant('t1', [tool_use('c1', 'Bash', command='pytest -q'),
                             tool_use('c2', 'Bash', command='npm test'),
                             tool_use('c3', 'Bash', command='make check'),
                             tool_use('c4', 'Bash', command='tsc')]),
            result('c1', is_error=False),
            result('c2', is_error=True),
            result('c3'),
        ])

        work = report['work']
        self.assertEqual(work['checks'], 4)
        self.assertEqual(work['checks_passed'], 2)
        self.assertEqual(work['checks_failed'], 1)
        self.assertEqual(work['rework_rate'], 0.3333)

    def test_echo_pytest_is_not_a_check(self):
        report = summarize([
            assistant('t1', [tool_use('c1', 'Bash', command='echo pytest')]),
            result('c1', is_error=False),
        ])
        self.assertEqual(report['work']['checks'], 0)

    def test_passing_check_after_last_edit_marks_session_verified(self):
        verified = summarize([
            assistant('t1', [tool_use('e1', 'Write', file_path='/repo/a.py')]),
            result('e1', is_error=False),
            assistant('t2', [tool_use('c1', 'Bash', command='python3 -m unittest')]),
            result('c1', is_error=False),
        ])
        unverified = summarize([
            assistant('t1', [tool_use('c1', 'Bash', command='pytest')]),
            result('c1', is_error=False),
            assistant('t2', [tool_use('e1', 'Write', file_path='/repo/a.py')]),
            result('e1', is_error=False),
        ])

        self.assertEqual(verified['work']['verified_edit_sessions'], 1)
        self.assertEqual(verified['work']['unverified_edit_sessions'], 0)
        self.assertEqual(verified['work']['verified_edit_share'], 1.0)
        self.assertEqual(unverified['work']['verified_edit_sessions'], 0)
        self.assertEqual(unverified['work']['unverified_edit_sessions'], 1)
        self.assertEqual(unverified['work']['verified_edit_share'], 0.0)

    def test_failing_check_does_not_verify(self):
        report = summarize([
            assistant('t1', [tool_use('e1', 'Write', file_path='/repo/a.py')]),
            result('e1', is_error=False),
            assistant('t2', [tool_use('c1', 'Bash', command='pytest')]),
            result('c1', is_error=True),
        ])
        self.assertEqual(report['work']['unverified_edit_sessions'], 1)

    def test_commits_require_success(self):
        report = summarize([
            assistant('t1', [tool_use('c1', 'Bash', command='git add -A && git commit -m "x"'),
                             tool_use('c2', 'Bash', command='git commit -m "y"'),
                             tool_use('c3', 'Bash', command='git commit --dry-run -m "z"')]),
            result('c1', is_error=False),
            result('c2', is_error=True),
            result('c3', is_error=False),
        ])
        self.assertEqual(report['work']['commits'], 1)

    def test_distinct_passing_checks_dedupes_repeats(self):
        report = summarize([
            assistant('t1', [tool_use('c1', 'Bash', command='pytest -q'),
                             tool_use('c2', 'Bash', command='pytest   -q'),
                             tool_use('c3', 'Bash', command='make check')]),
            result('c1', is_error=False),
            result('c2', is_error=False),
            result('c3', is_error=False),
        ])

        self.assertEqual(report['work']['checks_passed'], 3)
        self.assertEqual(report['work']['distinct_passing_checks'], 2)
        # Dividing by distinct checks is not a better number: it exposes repeat runs.
        self.assertGreater(report['work']['usage_per_distinct_passing_check'],
                           report['work']['usage_per_passing_check'])

    def test_out_of_window_tool_calls_are_not_counted(self):
        old = stamp(delta_minutes=60 * 24 * 10)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(transcript(root), [
                assistant('t1', [tool_use('c1', 'Bash', command='pytest')], at=old),
                result('c1', is_error=False),
                assistant('t2', [tool_use('c2', 'Bash', command='npm test')], at=stamp()),
                result('c2', is_error=False),
            ])
            report = audit.summarize(audit.collect(since=audit.parse_since('1d'), paths=[root]))

        self.assertEqual(report['work']['checks_passed'], 1)


class SkillUsageTests(unittest.TestCase):
    def test_skill_tool_calls_and_plugin_prefix(self):
        report = summarize([
            assistant('t1', [tool_use('s1', 'Skill', skill='frontend-design', args='x'),
                             tool_use('s2', 'Skill', skill='whittle:verify'),
                             tool_use('s3', 'Skill', skill='frontend-design')]),
        ])

        self.assertEqual(report['skills_used']['frontend-design'], 2)
        self.assertEqual(report['skills_used']['verify'], 1)
        self.assertEqual(report['skills_used_plugin'], {'whittle:verify': 1})

    def test_slash_commands_count_as_skill_invocations(self):
        report = summarize([
            prompt('<command-name>/frontend-design</command-name>\n'
                   '<command-message>frontend-design</command-message>'),
            prompt('<command-name>/compact</command-name>'),
            prompt('<command-name>/whittle:verify</command-name>'),
            assistant('t1', []),
        ])

        self.assertEqual(report['skills_used']['frontend-design'], 1)
        self.assertEqual(report['skills_used']['compact'], 1)
        self.assertEqual(report['skills_used']['verify'], 1)
        self.assertEqual(report['skills_used_plugin'], {'whittle:verify': 1})

    def test_slash_commands_in_text_blocks_count(self):
        event = {'type': 'user', 'timestamp': stamp(), 'message': {
            'role': 'user',
            'content': [{'type': 'text', 'text': '<command-name>/design-review</command-name>'}],
        }}
        report = summarize([event, assistant('t1', [])])
        self.assertEqual(report['skills_used'], {'design-review': 1})

    def test_skill_counts_combine_both_sources(self):
        report = summarize([
            assistant('t1', [tool_use('s1', 'Skill', skill='design-review')]),
            prompt('<command-name>/design-review</command-name>'),
        ])
        self.assertEqual(report['skills_used']['design-review'], 2)


class ModelTierTests(unittest.TestCase):
    def test_unknown_model_is_listed_separately(self):
        report = summarize([assistant('t1', [], model='mystery-model-9')])

        self.assertEqual(report['work']['model_mix']['unknown'], 1.0)
        self.assertEqual(report['work']['unknown_models'], ['mystery-model-9'])
        self.assertEqual(report['work']['premium_share'], 0.0)

    def test_premium_share_splits_by_model(self):
        report = summarize([
            assistant('t1', [], model='claude-opus-5-5'),
            assistant('t2', [], model='claude-haiku-5-5'),
        ])
        mix = report['work']['model_mix']
        self.assertEqual(mix['premium'], 0.5)
        self.assertEqual(mix['economy'], 0.5)
        self.assertEqual(mix['unknown'], 0.0)

    def test_model_tier_patterns_load_from_policy_file(self):
        self.assertEqual(audit.model_tier('claude-opus-5-5'), 'premium')
        self.assertEqual(audit.model_tier('gpt-6.1-sol-high'), 'premium')
        self.assertEqual(audit.model_tier('gpt-6-luna-high'), 'standard')
        self.assertEqual(audit.model_tier('deepseek-v4.1-flash'), 'economy')
        self.assertEqual(audit.model_tier('claude-haiku-4-5'), 'economy')
        self.assertEqual(audit.model_tier('something-else'), 'unknown')


class CodexWorkTests(unittest.TestCase):
    def _session(self, items, raw_calls=()):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rollout.jsonl'
            events = [
                {'type': 'session_meta', 'timestamp': stamp(), 'payload': {'id': 'codex-1', 'cwd': '/repo/app'}},
                {'type': 'turn_context', 'payload': {'model': 'gpt-6-luna-high'}},
                {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
                    'total_token_usage': {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 5}}}},
            ]
            for call in raw_calls:
                events.append({'type': 'response_item', 'payload': call})
            for item in items:
                events.append({'type': 'event_msg', 'payload': {'type': 'item_completed', 'item': item}})
            write_jsonl(path, events)
            return audit.parse_codex(path)

    def test_counts_command_executions_and_file_changes(self):
        session = self._session([
            {'type': 'CommandExecution', 'command': ['/bin/zsh', '-lc', 'pytest -q'], 'exit_code': 0,
             'status': 'completed'},
            {'type': 'FileChange', 'status': 'completed', 'changes': {'/repo/a.py': {'type': 'add'}}},
            {'type': 'CommandExecution', 'command': ['/bin/zsh', '-lc', 'npm test'], 'exit_code': 1,
             'status': 'failed'},
            {'type': 'CommandExecution', 'command': ['/bin/zsh', '-lc', 'git commit -m "x"'],
             'exit_code': 0, 'status': 'completed'},
        ])

        self.assertEqual(session.work['checks'], 2)
        self.assertEqual(session.work['checks_passed'], 1)
        self.assertEqual(session.work['checks_failed'], 1)
        self.assertEqual(session.work['edits'], 1)
        self.assertEqual(session.work['commits'], 1)

    def test_exec_events_take_precedence_over_raw_calls(self):
        session = self._session([
            {'type': 'CommandExecution', 'command': ['bash', '-lc', 'pytest'],
             'exit_code': 1, 'status': 'completed'},
            {'type': 'FileChange', 'status': 'completed', 'changes': {}},
        ], raw_calls=[
            {'type': kind, 'name': 'exec', 'status': 'completed',
             'input': json.dumps({'command': ['bash', '-lc', 'pytest']})}
            for kind in ('function_call', 'custom_tool_call')
        ] + [{'type': 'custom_tool_call', 'name': 'apply_patch', 'status': 'completed'}])

        self.assertEqual(session.work['edits'], 1)
        self.assertEqual(session.work['checks'], 1)
        self.assertEqual(session.work['checks_passed'], 0)
        self.assertEqual(session.work['checks_failed'], 1)

    def test_missing_codex_outcome_stays_unknown(self):
        session = self._session([
            {'type': 'CommandExecution', 'command': ['bash', '-lc', 'pytest']},
            {'type': 'FileChange', 'changes': {}},
        ])
        self.assertEqual(session.work['edits'], 0)
        self.assertEqual(session.work['checks'], 1)
        self.assertEqual(session.work['checks_passed'], 0)
        self.assertEqual(session.work['checks_failed'], 0)

    def test_falls_back_to_custom_tool_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rollout.jsonl'
            write_jsonl(path, [
                {'type': 'session_meta', 'timestamp': stamp(), 'payload': {'id': 'codex-2', 'cwd': '/repo/app'}},
                {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
                    'total_token_usage': {'input_tokens': 100, 'output_tokens': 5}}}},
                {'type': 'response_item', 'payload': {
                    'type': 'custom_tool_call', 'name': 'apply_patch', 'status': 'completed'}},
                {'type': 'response_item', 'payload': {
                    'type': 'custom_tool_call', 'name': 'exec', 'status': 'completed',
                    'input': json.dumps({'command': ['bash', '-lc', 'cargo test']})}},
            ])
            session = audit.parse_codex(path)

        self.assertEqual(session.work['edits'], 1)
        self.assertEqual(session.work['checks_passed'], 1)


class OutputTests(unittest.TestCase):
    def test_json_contains_work_and_skills_and_prints_work_block(self):
        events = [
            assistant('t1', [tool_use('e1', 'Write', file_path='/repo/a.py'),
                             tool_use('s1', 'Skill', skill='design-review')]),
            result('e1', is_error=False),
            assistant('t2', [tool_use('c1', 'Bash', command='pytest')]),
            result('c1', is_error=False),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(transcript(root), events)
            args = SimpleNamespace(since='30d', project=None, path=[root], top=10, json=True, compare=False)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(audit.run(args), 0)
            report = json.loads(output.getvalue())

            args.json = False
            text = io.StringIO()
            with contextlib.redirect_stdout(text):
                self.assertEqual(audit.run(args), 0)

        self.assertEqual(report['work']['checks_passed'], 1)
        self.assertEqual(report['skills_used'], {'design-review': 1})
        rendered = text.getvalue()
        self.assertIn('Work (proxy — counted from tool calls, not a quality judgement)', rendered)
        self.assertIn('rework rate', rendered)
        self.assertIn('usage per passing check', rendered)
        self.assertIn('model mix:', rendered)

    def test_findings_flag_rework_and_unverified_edits(self):
        report = summarize([
            assistant('t1', [tool_use('e1', 'Write', file_path='/repo/a.py')]),
            result('e1', is_error=False),
            assistant('t2', [tool_use('c1', 'Bash', command='pytest'),
                             tool_use('c2', 'Bash', command='npm test')]),
            result('c1', is_error=True),
            result('c2', is_error=True),
        ])
        text = ' '.join(report['findings'])
        self.assertIn('of counted checks failed', text)
        self.assertIn('editing sessions ran a passing check', text)


class CompareTests(unittest.TestCase):
    def test_compare_includes_work_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(transcript(root), [
                assistant('old-turn', [tool_use('c1', 'Bash', command='pytest')],
                          counts=usage(100), at=stamp(delta_minutes=60 * 24 * 10)),
                result('c1', is_error=False),
                assistant('new-turn', [tool_use('c2', 'Bash', command='pytest')], at=stamp()),
                result('c2', is_error=False),
            ])
            args = SimpleNamespace(since='7d', project=None, path=[root], top=10, json=True, compare=True)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(audit.run(args), 0)
            compare = json.loads(output.getvalue())['compare']

        for key in audit.WORK_COMPARE_KEYS:
            self.assertIn(key, compare['current'])
            self.assertIn(key, compare['previous'])

    def test_too_few_checks_reports_not_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(transcript(root), [
                assistant('new-turn', [tool_use('c1', 'Bash', command='pytest')], at=stamp()),
                result('c1', is_error=False),
            ])
            args = SimpleNamespace(since='7d', project=None, path=[root], top=10, json=True, compare=True)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                audit.run(args)
            compare = json.loads(output.getvalue())['compare']

            args.json = False
            text = io.StringIO()
            with contextlib.redirect_stdout(text):
                audit.run(args)

        self.assertIsNone(compare['current']['usage_per_passing_check'])
        self.assertIsNone(compare['current']['rework_rate'])
        self.assertIn('n/a (too few checks)', text.getvalue())

    def test_compare_prints_named_work_rows_and_directions(self):
        base = {key: 1 for key, _ in audit.COMPARE_METRICS}
        data = {
            'current': {**base, 'api_turns': 10, 'usage_per_passing_check': 1000, 'rework_rate': 0.1,
                        'verified_edit_share': 0.8, 'premium_share': 0.5},
            'previous': {**base, 'api_turns': 10, 'usage_per_passing_check': 2000, 'rework_rate': 0.2,
                         'verified_edit_share': 0.6, 'premium_share': 0.4},
            'delta': {**{key: 0 for key, _ in audit.COMPARE_METRICS}, 'api_turns': 0,
                      'usage_per_passing_check': -1000, 'rework_rate': -0.1,
                      'verified_edit_share': 0.2, 'premium_share': 0.1},
        }
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            audit.print_comparison(data)
        rendered = output.getvalue()

        self.assertIn('Usage / passing check: 1.0k current · 2.0k previous · delta -1.0k (-50%) · better', rendered)
        self.assertIn('Rework rate: 10% current · 20% previous · delta -10 pp (-50%) · better', rendered)
        self.assertIn('Verified-edit share: 80% current · 60% previous · delta +20 pp (+33%) · better', rendered)
        self.assertIn('Premium share: 50% current · 40% previous', rendered)


if __name__ == '__main__':
    unittest.main()
