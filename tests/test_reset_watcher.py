import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

source=Path(__file__).resolve().parents[1]/'scripts'/'reset_watcher.py'
spec=importlib.util.spec_from_file_location('watcher',source)
w=importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

BASE=datetime(2026,10,21,12,tzinfo=timezone.utc)

def acc(sem='first_request',dispatch='notify'):
    d={'id':'a','provider':'codex','window':'session','semantics':sem,
        'next_reset_at':w.iso(BASE),'dispatch':dispatch,'grace_seconds':120,
        'window_hours':5}
    if sem=='fixed':
        d.update({'provider':'claude','window':'weekly','repeat_days':7})
        d.pop('window_hours')
    if sem=='unverified':
        d.pop('window_hours')
    if dispatch=='command':
        d['command']=['my_cli','-m','cheap','yo']
    return {'version':1,'accounts':[d]}

class Tests(unittest.TestCase):
    def test_early_no_action(self):
        self.assertFalse(w.evaluate(acc(),{},BASE-timedelta(seconds=1),quiet=True))
    def test_due_and_dedup(self):
        st={}
        self.assertEqual(w.evaluate(acc(),st,BASE,quiet=True)[0]['status'],'notification')
        self.assertFalse(w.evaluate(acc(),st,BASE+timedelta(seconds=60),quiet=True))
    def test_unverified_never_auto(self):
        st={}
        self.assertEqual(w.evaluate(acc('unverified'),st,BASE,allow_dispatch=True,quiet=True)[0]['status'],'unverified-reset-manual-confirmation')
    def test_fixed_cannot_dispatch(self):
        with self.assertRaises(ValueError):w.validate(acc('fixed','command'))
    def test_fixed_weekly_advances(self):
        st={}
        self.assertEqual(w.evaluate(acc('fixed'),st,BASE,quiet=True)[0]['status'],'fixed-reset-no-prime-needed')
        self.assertFalse(w.evaluate(acc('fixed'),st,BASE+timedelta(minutes=10),quiet=True))
        self.assertEqual(w.evaluate(acc('fixed'),st,BASE+timedelta(days=7),quiet=True)[0]['status'],'fixed-reset-no-prime-needed')
    def test_explicit_auto(self):
        class R: returncode=0
        calls=[]
        def runner(*args,**kwargs): calls.append(args);return R()
        st={}
        res=w.evaluate(acc(dispatch='command'),st,BASE,allow_dispatch=True,quiet=True,runner=runner)
        self.assertEqual(res[0]['status'],'dispatched')
        self.assertEqual(len(calls),1)
        self.assertEqual(st['accounts']['a']['next_due'],w.iso(BASE+timedelta(hours=5)))
    def test_no_auto_without_opt_in(self):
        st={}
        res=w.evaluate(acc(dispatch='command'),st,BASE,quiet=True)
        self.assertEqual(res[0]['status'],'manual-approval-required')
    def test_no_auto_if_late(self):
        st={}
        r=w.evaluate(acc(dispatch='command'),st,BASE+timedelta(hours=1),allow_dispatch=True,quiet=True)
        self.assertEqual(r[0]['status'],'missed-grace-period')
    def test_no_auto_under_dry_run(self):
        st={}
        r=w.evaluate(acc(dispatch='command'),st,BASE,allow_dispatch=True,dry_run=True,quiet=True)
        self.assertEqual(r[0]['status'],'would-dispatch')
        self.assertEqual(st,{})
    def test_tz_required(self):
        with self.assertRaises(ValueError):w.parse_time('2026-10-21T08:00:00')
    def test_state_file_private(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'state.json'
            w.save_json(f,{'accounts':{}})
            self.assertEqual(f.stat().st_mode & 0o777,0o600)
if __name__=='__main__': unittest.main()
