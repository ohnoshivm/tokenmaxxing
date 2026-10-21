"""CLI integration smoke tests using isolated config paths and no network/provider calls."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'tokenmaxxing.py'

class QuotaCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), 'quota', *map(str,args)],
                              cwd=str(ROOT),capture_output=True,text=True,timeout=12)

    def test_help_exposes_quota_commands(self):
        proc=self.run_cli('--help')
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn('install-macos',proc.stdout)
        self.assertIn('sync',proc.stdout)

    def test_setup_is_private_and_status_lists_pools(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf=Path(tmp)/'windows.json'
            p=self.run_cli('setup','--config',conf)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(conf.stat().st_mode & 0o777,0o600)
            p=self.run_cli('status','--config',conf,'--state',Path(tmp)/'state.json')
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertIn('session',p.stdout)
            self.assertIn('weekly',p.stdout)

    def test_checks_cannot_dispatch_in_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf=Path(tmp)/'windows.json';state=Path(tmp)/'state.json'
            self.assertEqual(self.run_cli('setup','--config',conf).returncode,0)
            p=self.run_cli('check','--config',conf,'--state',state,'--dry-run','--allow-dispatch')
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertFalse(state.exists())

    def test_macos_install_dry_run_makes_no_changes(self):
        p=self.run_cli('install-macos','--dry-run')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('plan',p.stdout.lower())

if __name__=='__main__':unittest.main()
