import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_audit import assistant, stamp, write_jsonl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import fix


def tree(root):
    return {str(p.relative_to(root)): ('link', os.readlink(p)) if p.is_symlink() else ('file', p.read_bytes())
            for p in root.rglob('*') if p.is_symlink() or p.is_file()}


class TestFix(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / 'config'
        self.config.mkdir()
        self.settings = self.config / 'settings.json'
        self.settings.write_bytes(b'{ "enabledPlugins": {}, "secret": "test-only" }\n')
        self.settings_bytes = self.settings.read_bytes()
        self.home_patch = patch.object(fix.doctor, '_home', return_value=self.root)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.skill('used')
        self.skill('unused')
        self.sessions(10)

    def skill(self, dirname, name=None):
        path = self.config / 'skills' / dirname
        path.mkdir(parents=True)
        (path / 'SKILL.md').write_text('---\nname: ' + (name or dirname) + '\ndescription: Test metadata only\n---\nBody\n')
        return path

    def sessions(self, count):
        for path in (self.config / 'projects').glob('*.jsonl'):
            path.unlink()
        for n in range(count):
            events = [assistant('turn-' + str(n), stamp())]
            if n == 0:
                events.append({'type': 'user', 'timestamp': stamp(), 'message': {'content': '<command-name>/used</command-name>'}})
            write_jsonl(self.config / 'projects' / ('s' + str(n) + '.jsonl'), events)

    def run_fix(self, *flags):
        parser = argparse.ArgumentParser()
        fix.add_arguments(parser)
        args = parser.parse_args(['--config-dir', str(self.config), '--json', *flags])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = fix.run(args)
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)
        return code, json.loads(output.getvalue())

    def test_dry_run_changes_nothing(self):
        before = tree(self.config)
        code, plan = self.run_fix()
        self.assertEqual(code, 0)
        self.assertEqual(tree(self.config), before)
        self.assertEqual([a['name'] for a in plan['actions'] if a['auto']], ['unused'])
        self.assertGreater(plan['estimated_tokens_per_session'], 0)

    def test_apply_undo_roundtrip_settings_and_second_undo(self):
        before = tree(self.config)
        code, applied = self.run_fix('--apply')
        self.assertEqual(code, 0)
        run = self.config / 'tokenmaxxing-archive' / applied['run_id']
        self.assertTrue((self.config / 'skills' / 'used').is_dir())
        self.assertFalse((self.config / 'skills' / 'unused').exists())
        self.assertTrue((run / 'skills' / 'unused' / 'SKILL.md').is_file())
        manifest = json.loads((run / 'manifest.json').read_text())
        self.assertEqual(manifest['version'], '2.0.0')
        self.assertTrue(manifest['moves'][0]['done'])
        code, undone = self.run_fix('--undo')
        self.assertEqual(code, 0)
        self.assertTrue(undone['undone'])
        restored = {k: v for k, v in tree(self.config).items() if not k.startswith('tokenmaxxing-archive/')}
        self.assertEqual(restored, before)
        self.assertEqual(self.run_fix('--undo')[0], 0)

    def test_keep_by_name_and_directory(self):
        self.skill('folder', 'another-name')
        _, report = self.run_fix('--apply', '--keep', 'unused', 'another-name')
        self.assertIsNone(report['run_id'])
        self.assertTrue((self.config / 'skills' / 'unused').exists())
        self.assertTrue((self.config / 'skills' / 'folder').exists())

    def test_insufficient_sessions_skips_unused(self):
        self.sessions(9)
        _, report = self.run_fix('--apply')
        self.assertIsNone(report['run_id'])
        self.assertTrue(any('10 Claude sessions' in reason for reason in report['skipped']))

    def test_symlink_moves_link_only(self):
        target = self.root / 'shared'
        target.mkdir()
        (target / 'SKILL.md').write_text('---\nname: linked\ndescription: Shared metadata\n---\n')
        link = self.config / 'skills' / 'linked'
        link.symlink_to(target, target_is_directory=True)
        before = tree(target)
        _, applied = self.run_fix('--apply')
        archived = self.config / 'tokenmaxxing-archive' / applied['run_id'] / 'skills' / 'linked'
        self.assertTrue(archived.is_symlink())
        self.assertEqual(tree(target), before)
        self.run_fix('--undo')
        self.assertTrue(link.is_symlink())
        self.assertEqual(tree(target), before)

    def test_manifest_exists_before_each_move(self):
        original = Path.rename
        seen = []
        def rename(path, destination):
            if path.parent == self.config / 'skills':
                manifest = Path(destination).parents[1] / 'manifest.json'
                value = json.loads(manifest.read_text())
                self.assertTrue(any(m['src'] == str(path) for m in value['moves']))
                seen.append(path.name)
            return original(path, destination)
        with patch.object(Path, 'rename', rename):
            self.run_fix('--apply')
        self.assertEqual(seen, ['unused'])

    def test_undo_refuses_conflict_then_can_retry(self):
        _, applied = self.run_fix('--apply')
        self.skill('unused')
        marker = self.config / 'skills' / 'unused' / 'keep.txt'
        marker.write_text('new data')
        code, report = self.run_fix('--undo', applied['run_id'])
        self.assertEqual(code, 1)
        self.assertFalse(report['undone'])
        self.assertTrue(report['conflicts'])
        self.assertEqual(marker.read_text(), 'new data')
        (self.config / 'skills' / 'unused').rename(self.root / 'new-skill')
        self.assertEqual(self.run_fix('--undo')[0], 0)

    def test_mid_move_crash_leaves_recoverable_manifest(self):
        original = Path.rename
        def rename(path, destination):
            result = original(path, destination)
            if path.parent == self.config / 'skills':
                raise OSError('simulated crash after move')
            return result
        with patch.object(Path, 'rename', rename):
            code, report = self.run_fix('--apply')
        self.assertEqual(code, 1)
        self.assertTrue(report['errors'])
        self.assertEqual(self.run_fix('--undo')[0], 0)
        self.assertTrue((self.config / 'skills' / 'unused').is_dir())

    def test_ambiguous_duplicate_is_suggestion_only(self):
        self.skill('copy-a', 'same-name')
        self.skill('copy-b', 'same-name')
        _, report = self.run_fix('--apply')
        suggestions = [a for a in report['actions'] if a['kind'] == 'duplicate']
        self.assertTrue(suggestions)
        self.assertFalse(any(a['auto'] for a in suggestions))
        self.assertTrue((self.config / 'skills' / 'copy-a').exists())
        self.assertTrue((self.config / 'skills' / 'copy-b').exists())

    def test_instruction_sections_and_optimizer_suggestions(self):
        (self.config / 'CLAUDE.md').write_text('# Big section\n' + 'x' * 5000 + '\n## Smaller\n' + 'y' * 100)
        self.settings_bytes = b'{"enabledPlugins":{"whittle@market":true,"ponytail@market":true}}'
        self.settings.write_bytes(self.settings_bytes)
        _, report = self.run_fix()
        instructions = [a for a in report['actions'] if a['kind'] == 'instructions']
        self.assertEqual(instructions[0]['sections'][0]['heading'], 'Big section')
        commands = [c for a in report['actions'] for c in a.get('commands', [])]
        self.assertIn('/plugin disable whittle@market', commands)

    def test_list_and_invalid_run_id(self):
        self.assertEqual(self.run_fix('--list')[1]['runs'], [])
        _, applied = self.run_fix('--apply')
        self.assertEqual(self.run_fix('--list')[1]['runs'][0]['run_id'], applied['run_id'])
        self.assertEqual(self.run_fix('--undo', '../outside')[0], 1)

    def test_tampered_manifest_cannot_move_outside_skills(self):
        _, applied = self.run_fix('--apply')
        manifest = self.config / 'tokenmaxxing-archive' / applied['run_id'] / 'manifest.json'
        value = json.loads(manifest.read_text())
        value['moves'][0]['src'] = str(self.settings)
        manifest.write_text(json.dumps(value))
        self.assertEqual(self.run_fix('--undo')[0], 1)

    def test_archive_symlink_is_refused(self):
        external = self.root / 'external'
        external.mkdir()
        (self.config / 'tokenmaxxing-archive').symlink_to(external, target_is_directory=True)
        self.assertEqual(self.run_fix('--apply')[0], 1)
        self.assertEqual(list(external.iterdir()), [])
        self.assertTrue((self.config / 'skills' / 'unused').exists())


if __name__ == '__main__':
    unittest.main()
