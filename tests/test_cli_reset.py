import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tokenmaxxing_cli', ROOT/'tokenmaxxing.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ResetCliTests(unittest.TestCase):
    def test_setup_is_private_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'reset.json'
            self.assertEqual(m.setup_reset_config(dest=p), 'created')
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            p.write_text('custom configuration')
            self.assertEqual(m.setup_reset_config(dest=p), 'present')
            self.assertEqual(p.read_text(), 'custom configuration')

    def test_dry_run_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'reset.json'
            self.assertEqual(m.setup_reset_config(dest=p, dry_run=True), 'planned')
            self.assertFalse(p.exists())

    def test_reset_status_forwards_correct_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp)/'reset.json'
            m.setup_reset_config(dest=conf)
            r = subprocess.run([sys.executable,str(ROOT/'tokenmaxxing.py'),'reset','status','--config',str(conf)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('codex-main-session',r.stdout)

    def test_reset_dry_run_preserves_watcher_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp)/'reset.json'
            state = Path(tmp)/'state.json'
            m.setup_reset_config(dest=conf)
            r = subprocess.run([sys.executable,str(ROOT/'tokenmaxxing.py'),'reset','check','--config',str(conf),'--state',str(state),'--dry-run','--quiet'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertFalse(state.exists())

    def test_optin_is_not_added_unless_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf=Path(tmp)/'reset.json';m.setup_reset_config(dest=conf)
            args = SimpleNamespace(reset_action='check',config=conf,state=None,allow_dispatch=False,dry_run=True,quiet=True,account=None,at=None,poll_seconds=None)
            calls=[]
            with patch.object(m.subprocess,'call',side_effect=lambda cmd:calls.append(cmd) or 0):
                self.assertEqual(m.run_reset_action(args),0)
            self.assertNotIn('--allow-dispatch',calls[0])
            self.assertIn('--dry-run',calls[0])

    def test_macos_install_requires_config(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m,'home_dir',return_value=Path(tmp)):
            args=SimpleNamespace(reset_action='install-macos',config=None,dry_run=False)
            self.assertEqual(m.run_reset_action(args),2)

    def test_missing_config_has_actionable_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=SimpleNamespace(reset_action='status',config=Path(tmp)/'not-present',dry_run=False)
            self.assertEqual(m.run_reset_action(args),2)

if __name__=='__main__':unittest.main()
