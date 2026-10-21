"""Offline tests: no actual provider messages or connections."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

source=Path(__file__).resolve().parents[1]/'scripts'/'quota_engine.py'
spec=importlib.util.spec_from_file_location('quota_engine',source)
q=importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
NOW=datetime(2026,10,22,3,30,tzinfo=timezone.utc)

def cfg(mode='notify', semantics='first_request', window='session'):
    a={'id':'personal','provider':'codex','instance_id':'t3-codex-001',
       'windows':[{'id':window,'kind':window,'semantics':semantics,
                   'next_reset_at':q.stamp(NOW),'window_hours':5}],
       'activation':{'mode':mode,'grace_seconds':90}}
    if semantics!='first_request':a['windows'][0].pop('window_hours')
    if mode=='command':
        a['activation'].update({'argv':['fake-cli','--model','cheap','yo'],
            'confirmed_instance_id':'t3-codex-001','subscription_verified':True})
    return {'version':2,'accounts':[a]}

class Tests(unittest.TestCase):
    def test_timestamp_requires_zone(self):
        with self.assertRaises(ValueError):q.timestamp('2026-10-22T09:00')
    def test_unique_identity(self):
        c=cfg();c['accounts'].append(dict(c['accounts'][0]))
        with self.assertRaises(ValueError):q.validate(c)
    def test_missing_verified_provider_blocks_command(self):
        c=cfg('command');c['accounts'][0]['activation']['subscription_verified']=False
        with self.assertRaises(ValueError):q.validate(c)
    def test_early_no_send(self):
        self.assertEqual(q.check(cfg('command'),{},NOW-timedelta(seconds=1),allow_dispatch=True,quiet=True),[])
    def test_no_implicit_auto_dispatch(self):
        result=q.check(cfg('command'),{},NOW,quiet=True)
        self.assertEqual(result[0]['status'],'explicit-dispatch-required')
    def test_fixed_weekly_never_send(self):
        c=cfg('notify','fixed','weekly');state={}
        r=q.check(c,state,NOW,allow_dispatch=True,quiet=True)
        self.assertEqual(r[0]['status'],'fixed-window-no-request')
        self.assertEqual(q.check(c,state,NOW+timedelta(days=7),quiet=True)[0]['status'],'fixed-window-no-request')
    def test_unverified_never_send(self):
        r=q.check(cfg('notify','unverified'),{},NOW,allow_dispatch=True,quiet=True)
        self.assertEqual(r[0]['status'],'unverified-window-no-request')
    def test_dry_run_doesnt_mutate(self):
        state={}
        r=q.check(cfg('command'),state,NOW,allow_dispatch=True,dry_run=True,quiet=True)
        self.assertEqual(r[0]['status'],'would-dispatch')
        self.assertEqual(state,{})
    def test_late_window_no_send(self):
        r=q.check(cfg('command'),{},NOW+timedelta(seconds=91),allow_dispatch=True,quiet=True)
        self.assertEqual(r[0]['status'],'missed-activation-window')
    def test_success_requires_confirmation(self):
        class Result:returncode=0
        calls=[]
        def run(*args,**kw):calls.append((args,kw));return Result()
        with tempfile.TemporaryDirectory() as d:
            state={}; path=Path(d)/'state.json'
            r=q.check(cfg('command'),state,NOW,allow_dispatch=True,quiet=True,runner=run,state_path=path)
            self.assertEqual(r[0]['status'],'sent-pending-verification')
            self.assertEqual(len(calls),1)
            self.assertEqual(q.read_json(path)['windows'][q.key(*next(q.windows(cfg())))]['confirmation'],'pending')
            self.assertEqual(q.check(cfg('command'),state,NOW+timedelta(seconds=3),allow_dispatch=True,quiet=True),[])
            self.assertNotIn('OPENAI_API_KEY',calls[0][1]['env'])
    def test_failed_run_never_auto_retries(self):
        class Result:returncode=1
        calls=[]
        def run(*args,**kw):calls.append(1);return Result()
        st={}; c=cfg('command')
        r=q.check(c,st,NOW,allow_dispatch=True,runner=run,quiet=True)
        self.assertEqual(r[0]['status'],'request-exited-nonzero-unverified')
        self.assertEqual(q.check(c,st,NOW+timedelta(seconds=20),allow_dispatch=True,runner=run,quiet=True),[])
        self.assertEqual(len(calls),1)
    def test_snapshot_distinguishes_provider_instances(self):
        c=cfg();st={}
        sn={'version':1,'observed_at':q.stamp(NOW),'accounts':[
            {'provider':'codex','instance_id':'t3-codex-WRONG','windows':[{'id':'session','resets_at':q.stamp(NOW+timedelta(hours=5)), 'used_percent':1}]}]}
        self.assertEqual(q.apply_snapshot(c,st,sn,NOW),[])
    def test_snapshot_advances_real_window(self):
        c=cfg();st={};a,w=next(q.windows(c));q.record(st,a,w)
        sn={'version':1,'observed_at':q.stamp(NOW+timedelta(minutes=5)),
            'accounts':[{'provider':'codex','instance_id':'t3-codex-001','windows':[
            {'id':'session','resets_at':q.stamp(NOW+timedelta(hours=5)),'used_percent':1}]}]}
        self.assertEqual(q.apply_snapshot(c,st,sn,NOW+timedelta(minutes=5))[0]['next_reset_at'],q.stamp(NOW+timedelta(hours=5)))
    def test_no_provider_confirmation_from_command_exit_alone(self):
        self.assertNotEqual(q.check(cfg('notify'),{},NOW,quiet=True)[0]['status'],'confirmed-provider-window-moved')
    def test_private_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sub'/'state.json';q.atomic(p,{'foo':42})
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
    def test_separate_windows(self):
        c=cfg();c['accounts'][0]['windows'].append({'id':'weekly','kind':'weekly','semantics':'unverified','next_reset_at':q.stamp(NOW)})
        r=q.check(c,{},NOW,quiet=True)
        self.assertEqual({x['window']:x['status'] for x in r},{'session':'notification','weekly':'unverified-window-no-request'})

if __name__=='__main__':unittest.main()

class ExtraTests(unittest.TestCase):
    def test_handled_survives_edit_same_reset(self):
        c=cfg('notify');st={}
        q.check(c,st,NOW,quiet=True)
        c['accounts'][0]['windows'][0]['next_reset_at']=q.stamp(NOW+timedelta(hours=1))
        q.record(st,*next(q.windows(c)))
        c['accounts'][0]['windows'][0]['next_reset_at']=q.stamp(NOW)
        self.assertEqual(q.check(c,st,NOW,quiet=True),[])

    def test_shared_group_never_sends_two_prompts_for_same_reset(self):
        c=cfg('command');c['accounts'][0]['windows'].append({
            'id':'weekly','kind':'weekly','semantics':'first_request',
            'next_reset_at':q.stamp(NOW),'window_hours':168})
        class Result:returncode=0
        calls=[]
        def runner(*a,**k):calls.append(1);return Result()
        st={}
        r=q.check(c,st,NOW,allow_dispatch=True,runner=runner,quiet=True)
        self.assertEqual(len(calls),1)
        self.assertEqual({x['status'] for x in r}, {'sent-pending-verification','shared-activation-already-sent'})
