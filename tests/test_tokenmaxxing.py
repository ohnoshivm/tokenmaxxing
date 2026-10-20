import importlib.util
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE=Path(__file__).resolve().parents[1]/'tokenmaxxing.py'
spec=importlib.util.spec_from_file_location('tokenmaxxing', MODULE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestInstall(unittest.TestCase):
    def test_plugin_marketplace_manifest(self):
        root=MODULE.parent
        market=json.loads((root/'.claude-plugin/marketplace.json').read_text())
        plugin=json.loads((root/'plugins/tokenmaxxing/.claude-plugin/plugin.json').read_text())
        self.assertEqual(market['plugins'][0]['name'],plugin['name'])
        self.assertEqual((root/'plugins/tokenmaxxing/skills/tokenmaxxing/SKILL.md').read_bytes(),(root/'skills/tokenmaxxing/SKILL.md').read_bytes())

    def test_registry_pins(self):
        tools=m.registry()
        self.assertEqual(len(tools),8)
        for tool in tools:
            m.validate_tool(tool)
            self.assertEqual(len(tool['revision']),40)

    def test_skill_installs_and_skips_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(m,'home_dir',return_value=Path(tmp)):
                self.assertEqual(m.install_skill(scope='user'),'installed')
                self.assertEqual(m.install_skill(scope='user'),'present')
                dest=Path(tmp)/'.claude/skills/tokenmaxxing/SKILL.md'
                self.assertTrue(dest.is_file())
                dest.write_text('user customization')
                self.assertEqual(m.install_skill(scope='user'),'conflict')
                self.assertEqual(dest.read_text(),'user customization')
                self.assertEqual(m.install_skill(scope='user',replace=True),'installed')
                backups=list(dest.parent.parent.glob('tokenmaxxing.backup-*'))
                self.assertEqual(len(backups),1)

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(m,'home_dir',return_value=Path(tmp)):
                self.assertEqual(m.install_skill(scope='user',dry_run=True),'planned')
                self.assertFalse((Path(tmp)/'.claude').exists())
                self.assertEqual(m.stage(m.registry()[0],Path(tmp),dry_run=True),'planned')
                self.assertFalse((Path(tmp)/'vendor').exists())

    def test_plugin_commands_never_execute(self):
        p=m.preview_plugin(next(x for x in m.registry() if x['id']=='occam'))
        self.assertIn('claude plugin marketplace add',p)
        self.assertIn('claude plugin install',p)

if __name__=='__main__': unittest.main()
