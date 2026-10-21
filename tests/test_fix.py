import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('tokenmaxxing_fix', SCRIPTS / 'fix.py')
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)


def session(skills=(), plugin_skills=(), agent='claude', subagent=False):
    return SimpleNamespace(agent=agent, subagent=subagent,
                           skills=list(skills), plugin_skills=list(plugin_skills))


def make_skill(root, name, description='does a thing', tokens_text=''):
    directory = root / 'skills' / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'SKILL.md').write_text(
        f'---\nname: {name}\ndescription: {description}\n---\n\n{tokens_text}\n', encoding='utf-8')
    return directory


def snapshot(root):
    """Every path and file hash under root, so 'nothing changed' is provable."""
    out = {}
    for path in sorted(root.rglob('*')):
        rel = str(path.relative_to(root))
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'dir'
    return out


def args_for(config_dir, project_dir, **overrides):
    values = {'since': '30d', 'config_dir': config_dir, 'project_dir': project_dir,
              'keep': [], 'apply': False, 'undo': None, 'list': False, 'json': False}
    values.update(overrides)
    return SimpleNamespace(**values)


@contextlib.contextmanager
def environment(tmp, sessions):
    home = tmp / 'home'
    with patch.object(fix.audit, 'collect', return_value=sessions), \
            patch.object(fix.doctor, '_home', return_value=home):
        yield


def cli(args):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = fix.run(args)
    return code, buffer.getvalue()


class FixTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config = self.tmp / 'claude'
        self.project = self.tmp / 'project'
        self.config.mkdir()
        self.project.mkdir()
        self.addCleanup(lambda: __import__('shutil').rmtree(self.tmp, ignore_errors=True))

    def sessions(self, count=12, used=()):
        return [session(skills=used if index == 0 else ())
                for index in range(count)]

    def test_dry_run_changes_nothing(self):
        make_skill(self.config, 'unused')
        make_skill(self.config, 'used')
        before = snapshot(self.tmp)
        with environment(self.tmp, self.sessions(used=('used',))):
            code, output = cli(args_for(self.config, self.project))
        self.assertEqual(code, 0)
        self.assertIn('dry run', output)
        self.assertIn('unused', output)
        self.assertEqual(snapshot(self.tmp), before)
        self.assertFalse((self.config / fix.ARCHIVE_DIR).exists())

    def test_apply_moves_only_unused_skills(self):
        make_skill(self.config, 'unused')
        make_skill(self.config, 'used')
        with environment(self.tmp, self.sessions(used=('used',))):
            code, _ = cli(args_for(self.config, self.project, apply=True))
        self.assertEqual(code, 0)
        self.assertFalse((self.config / 'skills' / 'unused').exists())
        self.assertTrue((self.config / 'skills' / 'used' / 'SKILL.md').is_file())
        runs = sorted((self.config / fix.ARCHIVE_DIR).glob('*/manifest.json'))
        self.assertEqual(len(runs), 1)
        manifest = json.loads(runs[0].read_text())
        self.assertEqual([move['name'] for move in manifest['moves']], ['unused'])
        self.assertTrue(manifest['moves'][0]['done'])
        moved = Path(manifest['moves'][0]['dst'])
        self.assertTrue((moved / 'SKILL.md').is_file())
        self.assertEqual(manifest['version'], '2.0.0')

    def test_keep_is_honoured(self):
        make_skill(self.config, 'unused')
        with environment(self.tmp, self.sessions()):
            code, output = cli(args_for(self.config, self.project, keep=['unused'], apply=True))
        self.assertEqual(code, 0)
        self.assertIn('kept by --keep', output)
        self.assertTrue((self.config / 'skills' / 'unused' / 'SKILL.md').is_file())
        self.assertFalse((self.config / fix.ARCHIVE_DIR).exists())

    def test_small_window_skips_skills(self):
        make_skill(self.config, 'unused')
        with environment(self.tmp, self.sessions(count=3)):
            code, output = cli(args_for(self.config, self.project, apply=True))
        self.assertEqual(code, 0)
        self.assertIn('needs 10', output)
        self.assertTrue((self.config / 'skills' / 'unused' / 'SKILL.md').is_file())

    def test_plugin_skill_counts_as_used(self):
        make_skill(self.config, 'shared')
        with environment(self.tmp, self.sessions(used=())):
            with patch.object(fix.audit, 'collect',
                              return_value=[session(plugin_skills=('pack:shared',))] * 12):
                cli(args_for(self.config, self.project, apply=True))
        self.assertTrue((self.config / 'skills' / 'shared' / 'SKILL.md').is_file())

    def test_symlink_is_moved_as_a_link(self):
        target = self.tmp / 'elsewhere'
        target.mkdir()
        (target / 'SKILL.md').write_text('---\nname: linked\ndescription: d\n---\n', encoding='utf-8')
        (self.config / 'skills').mkdir()
        os.symlink(target, self.config / 'skills' / 'linked')
        with environment(self.tmp, self.sessions()):
            cli(args_for(self.config, self.project, apply=True))
        archived = list((self.config / fix.ARCHIVE_DIR).glob('*/skills/linked'))[0]
        self.assertTrue(archived.is_symlink())
        self.assertEqual(archived.resolve(), target.resolve())
        self.assertTrue((target / 'SKILL.md').is_file())

    def test_manifest_is_written_before_the_first_move(self):
        make_skill(self.config, 'unused')
        seen = []
        real_rename = os.rename

        def spy(source, target):
            manifests = list((self.config / fix.ARCHIVE_DIR).glob('*/manifest.json'))
            seen.append(json.loads(manifests[0].read_text()) if manifests else None)
            return real_rename(source, target)

        with environment(self.tmp, self.sessions()):
            with patch.object(fix.os, 'rename', side_effect=spy):
                cli(args_for(self.config, self.project, apply=True))
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0]['moves'][0]['done'])

    def test_undo_restores_and_second_undo_is_a_noop(self):
        make_skill(self.config, 'unused', tokens_text='body')
        with environment(self.tmp, self.sessions()):
            cli(args_for(self.config, self.project, apply=True))
            code, output = cli(args_for(self.config, self.project, undo=''))
        self.assertEqual(code, 0)
        self.assertIn('Restored 1 path', output)
        self.assertTrue((self.config / 'skills' / 'unused' / 'SKILL.md').is_file())
        with environment(self.tmp, self.sessions()):
            code, output = cli(args_for(self.config, self.project, undo=''))
        self.assertEqual(code, 0)
        self.assertIn('already undone', output)

    def test_undo_refuses_to_overwrite_a_new_directory(self):
        make_skill(self.config, 'unused')
        with environment(self.tmp, self.sessions()):
            cli(args_for(self.config, self.project, apply=True))
            make_skill(self.config, 'unused', description='new copy')
            code, output = cli(args_for(self.config, self.project, undo=''))
        self.assertEqual(code, 0)
        self.assertIn('not restored', output)
        self.assertEqual((self.config / 'skills' / 'unused' / 'SKILL.md')
                         .read_text(encoding='utf-8').count('new copy'), 1)
        manifests = list((self.config / fix.ARCHIVE_DIR).glob('*/manifest.json'))
        self.assertNotIn('undone_at', json.loads(manifests[0].read_text()))

    def test_apply_then_undo_restores_an_identical_skills_tree(self):
        first = make_skill(self.config, 'unused', tokens_text='keep me')
        (first / 'reference.md').write_text('extra file\n', encoding='utf-8')
        make_skill(self.config, 'used')
        before = snapshot(self.config / 'skills')
        with environment(self.tmp, self.sessions(used=('used',))):
            cli(args_for(self.config, self.project, apply=True))
            self.assertNotEqual(snapshot(self.config / 'skills'), before)
            cli(args_for(self.config, self.project, undo=''))
        self.assertEqual(snapshot(self.config / 'skills'), before)
        # The run record stays behind on purpose, so the archive is auditable.
        self.assertEqual(len(list((self.config / fix.ARCHIVE_DIR).glob('*/manifest.json'))), 1)

    def test_undo_without_runs_reports_an_error(self):
        with environment(self.tmp, self.sessions()):
            code, output = cli(args_for(self.config, self.project, undo=''))
        self.assertEqual(code, 2)
        self.assertIn('no fix runs found', output)

    def test_list_shows_runs(self):
        make_skill(self.config, 'unused')
        with environment(self.tmp, self.sessions()):
            cli(args_for(self.config, self.project, apply=True))
            code, output = cli(args_for(self.config, self.project, list=True))
        self.assertEqual(code, 0)
        self.assertIn('1 moved', output)

    def test_settings_json_is_never_touched(self):
        settings = self.config / 'settings.json'
        original = b'{"model": "opus", "hooks": {"SessionStart": []}}\n'
        settings.write_bytes(original)
        make_skill(self.config, 'unused')
        with environment(self.tmp, self.sessions()):
            cli(args_for(self.config, self.project, apply=True))
            cli(args_for(self.config, self.project, undo=''))
        self.assertEqual(settings.read_bytes(), original)

    def test_json_output_shape(self):
        make_skill(self.config, 'unused')
        with environment(self.tmp, self.sessions()):
            code, output = cli(args_for(self.config, self.project, json=True))
        payload = json.loads(output)
        self.assertEqual(code, 0)
        self.assertTrue(payload['dry_run'])
        self.assertEqual(payload['config_dir'], str(self.config.resolve()))
        self.assertEqual([item['kind'] for item in payload['actions']], ['skill'])
        self.assertNotIn('dir', payload['actions'][0])
        self.assertGreater(payload['estimated_tokens_per_session'], 0)


if __name__ == '__main__':
    unittest.main()
