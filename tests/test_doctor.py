import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('tokenmaxxing_doctor', SCRIPTS / 'doctor.py')
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return path


def skill(path, name, description):
    return write(path, f'---\nname: {name}\ndescription: >-\n  {description}\n---\nbody is not always loaded\n')


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.home = self.base / 'home'
        self.config = self.base / 'claude-config'
        self.project = self.base / 'workspace' / 'app'
        self.home.mkdir()
        self.project.mkdir(parents=True)
        self.old_env = os.environ.copy()
        os.environ['HOME'] = str(self.home)
        os.environ['CLAUDE_CONFIG_DIR'] = str(self.config)
        self._make_config()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        self.tmp.cleanup()

    def _make_config(self, enabled=None):
        enabled = enabled or {'occam@official': True, 'whittle@official': True}
        self.global_instruction = write(
            self.config / 'CLAUDE.md',
            '@~/global-extra.md\n@relative-extra.md\n' + ('G' * 80),
        )
        self.global_import = write(self.home / 'global-extra.md', 'I' * 44)
        self.relative_import = write(self.config / 'relative-extra.md', 'R' * 20)
        self.project_instruction = write(
            self.project / 'CLAUDE.md',
            '@./project-extra.md\n' + ('P' * 48),
        )
        self.project_import = write(self.project / 'project-extra.md', 'J' * 32)
        write(self.project.parent / 'CLAUDE.local.md', 'L' * 28)
        write(self.project / '.claude' / 'CLAUDE.md', 'C' * 36)
        write(self.project / 'AGENTS.md', 'A' * 40)

        skill(self.config / 'skills' / 'alpha' / 'SKILL.md', 'shared-skill', 'a' * 40)
        skill(self.project / '.claude' / 'skills' / 'beta' / 'SKILL.md', 'shared-skill', 'b' * 80)
        write(self.config / 'agents' / 'helper.md', '---\nname: helper\ndescription: ' + ('h' * 52) + '\n---\n')
        write(self.project / '.claude' / 'agents' / 'local.md', '---\ndescription: ' + ('p' * 36) + '\n---\n')

        occam = self.config / 'plugins' / 'occam-install'
        whittle = self.config / 'plugins' / 'whittle-install'
        skill(occam / 'skills' / 'one' / 'SKILL.md', 'plugin-one', 'x' * 64)
        skill(occam / 'skills' / 'two' / 'SKILL.md', 'plugin-two', 'y' * 32)
        write(occam / 'agents' / 'helper.md', '---\nname: plugin-agent\ndescription: unused\n---\n')
        write(occam / 'commands' / 'one.md', 'command one')
        write(occam / 'commands' / 'two.md', 'command two')
        write(occam / 'hooks' / 'hooks.json', json.dumps({
            'hooks': {
                'SessionStart': [{'hooks': [{'type': 'command', 'command': 'hidden'}]}],
                'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': 'hidden'}]}],
            },
        }))
        write(whittle / 'hooks' / 'hooks.json', json.dumps({'hooks': {'PostToolUse': []}}))

        write(self.config / 'settings.json', json.dumps({
            'enabledPlugins': enabled,
            'hooks': {'SessionStart': [{'matcher': '', 'hooks': [{'type': 'command'}]}]},
        }))
        write(self.config / 'plugins' / 'installed_plugins.json', json.dumps({
            'version': 2,
            'plugins': {
                'occam@official': [{'installPath': str(occam)}],
                'whittle@official': [{'installPath': str(whittle)}],
            },
        }))

        write(self.home / '.claude.json', json.dumps({
            'mcpServers': {
                'private-local': {
                    'command': 'private-command',
                    'env': {'API_KEY': 'TOP_SECRET_MCP_VALUE'},
                    'headers': {'Authorization': 'Bearer TOP_SECRET_HEADER'},
                },
            },
            'projects': {
                str(self.project.resolve()): {
                    'mcpServers': {'project-http': {'type': 'http', 'url': 'https://not-to-print'}},
                },
            },
        }))
        write(self.project / '.mcp.json', json.dumps({
            'mcpServers': {'project-stdio': {'command': 'private-project-command'}},
        }))

        self.registry = self.base / 'optimizer-registry.json'
        write(self.registry, json.dumps({'tools': [
            {'id': 'occam', 'claude_plugin': {'name': 'occam'}},
            {'id': 'whittle', 'claude_plugin': {'name': 'whittle'}},
            {'id': 'ponytail', 'claude_plugin': {'name': 'ponytail'}},
        ]}))

    def _environment(self):
        return patch.object(doctor.Path, 'home', return_value=self.home), patch.object(doctor, 'REGISTRY_PATH', self.registry)

    def test_estimates_imports_plugins_skills_hooks_and_safe_mcp(self):
        home_patch, registry_patch = self._environment()
        with home_patch, registry_patch:
            report = doctor.collect_report(self.project, measure=False)

        claude_files = [item for item in report['instructions']['files'] if item['loaded_by'] == 'claude']
        expected_instruction_tokens = sum(len(Path(item['path']).read_text(encoding='utf-8')) // 4 for item in claude_files)
        self.assertEqual(report['instructions']['claude_tokens'], expected_instruction_tokens)
        self.assertIn(str(self.global_import.resolve()), {item['path'] for item in claude_files})
        self.assertIn(str(self.relative_import.resolve()), {item['path'] for item in claude_files})
        self.assertIn(str(self.project_import.resolve()), {item['path'] for item in claude_files})
        self.assertEqual(report['instructions']['codex_agents_tokens'], 10)

        self.assertEqual(report['skills']['count'], 4)
        self.assertEqual(report['skills']['tokens'], 64)
        self.assertEqual(len(report['skills']['duplicates']), 1)
        self.assertEqual(report['skills']['duplicates'][0]['name'], 'shared-skill')
        self.assertEqual(report['skills']['duplicates'][0]['count'], 2)
        self.assertEqual(len(report['skills']['longest_descriptions']), 4)

        occam = next(item for item in report['plugins'] if item['name'] == 'occam@official')
        self.assertEqual((occam['skills'], occam['agents'], occam['commands'], occam['hooks']), (2, 1, 2, 2))
        self.assertIn('SessionStart', occam['hook_events'])
        self.assertEqual(report['subagents']['count'], 2)
        self.assertEqual(report['subagents']['tokens'], (52 + 36) // 4)
        self.assertEqual(report['estimated_always_loaded_tokens'],
                         report['instructions']['claude_tokens'] + 64 + (52 + 36) // 4)

        self.assertEqual(report['mcp']['count'], 3)
        self.assertEqual({(server['name'], server['transport']) for server in report['mcp']['servers']}, {
            ('private-local', 'stdio'), ('project-http', 'http'), ('project-stdio', 'stdio'),
        })
        self.assertTrue(report['optimizers']['stacked'])
        self.assertEqual({item['id'] for item in report['optimizers']['active']}, {'occam', 'whittle'})
        self.assertIn('2 coding-behavior optimizers', report['findings'][0]['text'])
        self.assertGreater(report['estimated_always_loaded_tokens'], report['instructions']['claude_tokens'])

    def test_one_optimizer_is_not_reported_as_stacking(self):
        self._make_config({'occam@official': True, 'whittle@official': False})
        home_patch, registry_patch = self._environment()
        with home_patch, registry_patch:
            report = doctor.collect_report(self.project, measure=False)
        self.assertEqual([item['id'] for item in report['optimizers']['active']], ['occam'])
        self.assertFalse(report['optimizers']['stacked'])
        self.assertFalse(any('coding-behavior optimizers' in item['text'] for item in report['findings']))

    def test_cli_total_includes_all_sections_from_each_cwd_and_config_path(self):
        (self.home / '.claude').symlink_to(self.config, target_is_directory=True)
        expected = doctor.collect_report(self.project, measure=False)
        for cwd in (self.project, self.home):
            for configured in (None, str(self.config), '~/.claude', os.path.relpath(self.config, cwd)):
                env = os.environ.copy()
                if configured is None:
                    env.pop('CLAUDE_CONFIG_DIR', None)
                else:
                    env['CLAUDE_CONFIG_DIR'] = configured
                for entry, command in ((ROOT / 'tokenmaxxing.py', ['doctor']), (SCRIPTS / 'doctor.py', [])):
                    with self.subTest(cwd=cwd, config=configured, entry=entry):
                        result = subprocess.run(
                            [sys.executable, str(entry), *command, '--project-dir', str(self.project),
                             '--no-measure', '--json'], cwd=cwd, env=env, text=True, capture_output=True,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        report = json.loads(result.stdout)
                        sections = (report['instructions']['claude_tokens'], report['skills']['tokens'],
                                    report['subagents']['tokens'])
                        self.assertTrue(all(value > 0 for value in sections))
                        self.assertEqual(report['estimated_always_loaded_tokens'], sum(sections))
                        self.assertEqual(report['estimated_always_loaded_tokens'],
                                         expected['estimated_always_loaded_tokens'])
                        self.assertIsNone(report['measured'])

    def test_reports_config_dir_and_source_in_text_and_json(self):
        (self.home / '.claude').symlink_to(self.config, target_is_directory=True)
        os.environ.pop('CLAUDE_CONFIG_DIR')
        home_patch, registry_patch = self._environment()
        with home_patch, registry_patch:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = doctor.main(['--project-dir', str(self.project), '--no-measure'])
            self.assertEqual(code, 0)
            text = output.getvalue().splitlines()[0]
            self.assertEqual(text, f"Config dir: {self.config.resolve()} (from default)")

            os.environ['CLAUDE_CONFIG_DIR'] = str(self.config)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                doctor.main(['--project-dir', str(self.project), '--no-measure'])
            self.assertEqual(output.getvalue().splitlines()[0],
                             f"Config dir: {self.config.resolve()} (from CLAUDE_CONFIG_DIR)")

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                doctor.main(['--project-dir', str(self.project), '--no-measure', '--json'])
        self.assertEqual(json.loads(output.getvalue())['config_dir'], str(self.config.resolve()))

    def test_config_dir_flag_overrides_env_for_both_entrypoints(self):
        other = self.base / 'other-config'
        write(other / 'CLAUDE.md', 'O' * 400)
        env = os.environ.copy()
        env['CLAUDE_CONFIG_DIR'] = str(self.config)
        for entry, command in ((ROOT / 'tokenmaxxing.py', ['doctor']), (SCRIPTS / 'doctor.py', [])):
            for argv, parse in ((('--no-measure',), False), (('--no-measure', '--json'), True)):
                result = subprocess.run(
                    [sys.executable, str(entry), *command, '--project-dir', str(self.project),
                     '--config-dir', str(other), *argv],
                    cwd=self.project, env=env, text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                if parse:
                    report = json.loads(result.stdout)
                    self.assertEqual(report['config_dir'], str(other.resolve()))
                    self.assertEqual(report['config_dir_source'], '--config-dir')
                    paths = {item['path'] for item in report['instructions']['files']}
                    self.assertIn(str((other / 'CLAUDE.md').resolve()), paths)
                else:
                    self.assertEqual(result.stdout.splitlines()[0],
                                     f"Config dir: {other.resolve()} (from --config-dir)")

    def test_flags_second_config_only_when_env_points_elsewhere(self):
        other = self.home / '.claude'
        write(other / 'CLAUDE.md', 'D' * 44)
        home_patch, registry_patch = self._environment()
        with home_patch, registry_patch:
            report = doctor.collect_report(self.project, measure=False)
        self.assertEqual(report['config_dir_source'], 'CLAUDE_CONFIG_DIR')
        self.assertIn('Another Claude config exists at ~/.claude; run `doctor --config-dir ~/.claude` to audit it too.',
                      [item['text'] for item in report['findings'] if item['priority'] == 'LOW'])

        os.environ['CLAUDE_CONFIG_DIR'] = str(other)
        with home_patch, registry_patch:
            report = doctor.collect_report(self.project, measure=False)
        self.assertFalse(any('Another Claude config' in item['text'] for item in report['findings']))

        os.environ['CLAUDE_CONFIG_DIR'] = str(self.config)
        (other / 'CLAUDE.md').unlink()
        with home_patch, registry_patch:
            report = doctor.collect_report(self.project, measure=False)
        self.assertFalse(any('Another Claude config' in item['text'] for item in report['findings']))

    def test_measured_baseline_uses_audit_summary(self):
        sessions = [object()]
        summary = {'claude': {'sessions': 1, 'starting_context': {'median': 12_000, 'p90': 16_000}}}
        home_patch, registry_patch = self._environment()
        with home_patch, registry_patch, \
                patch.object(doctor.audit, 'collect', return_value=sessions) as collect, \
                patch.object(doctor.audit, 'summarize', return_value=summary):
            report = doctor.collect_report(self.project, measure=True)
        self.assertEqual(report['measured'], {'sessions': 1, 'median': 12_000, 'p90': 16_000})
        since = collect.call_args.kwargs['since']
        self.assertAlmostEqual((doctor.datetime.now(doctor.timezone.utc) - since).total_seconds(), 30 * 24 * 60 * 60, delta=2)

    def test_json_and_text_never_print_mcp_secrets_and_no_measure_skips_logs(self):
        home_patch, registry_patch = self._environment()
        with home_patch, registry_patch, patch.object(doctor.audit, 'collect') as collect:
            for argv in (
                ['--project-dir', str(self.project), '--no-measure'],
                ['--project-dir', str(self.project), '--no-measure', '--json'],
            ):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = doctor.main(argv)
                self.assertEqual(result, 0)
                rendered = output.getvalue()
                self.assertNotIn('TOP_SECRET_MCP_VALUE', rendered)
                self.assertNotIn('TOP_SECRET_HEADER', rendered)
                self.assertNotIn('private-command', rendered)
                self.assertNotIn('not-to-print', rendered)
                if '--json' in argv:
                    parsed = json.loads(rendered)
                    self.assertEqual(parsed['measured'], None)
                    self.assertEqual(parsed['mcp']['servers'][0].keys(), {'name', 'transport'})
                else:
                    self.assertIn('skipped (--no-measure)', rendered)
            collect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
