#!/usr/bin/env python3
"""TOKENMAXXING: cautious quota-window alerts and optional provider CLI activation.

Standard library, Python >=3.9. No undocumented T3 endpoints, API requests,
provider authentication changes, or autonomous dispatch by default.
"""
import argparse
import contextlib
from datetime import datetime, timezone, timedelta
import fcntl
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

HOME = Path.home()
CONFIG = HOME / '.config/tokenmaxxing/quota-windows.json'
STATE = HOME / '.local/state/tokenmaxxing/quota-state.json'
LOG = HOME / '.local/state/tokenmaxxing/quota-events.jsonl'
PROVIDER_SET = {'codex', 'claude', 'other'}
KINDS = {'session', 'weekly', 'model', 'other'}
SEMANTICS = {'first_request', 'fixed', 'unverified'}
PROTECTED_ENV = ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_BASE_URL',
                 'ANTHROPIC_BASE_URL', 'AZURE_OPENAI_API_KEY', 'ANTHROPIC_AUTH_TOKEN',
                 'CODEX_API_KEY', 'TOKEN_HARBOR_URL')


def timestamp(s):
    if not isinstance(s, str):
        raise ValueError('Reset timestamps must be strings with an explicit timezone')
    try:
        d = datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError as e:
        raise ValueError('Invalid ISO 8601 reset timestamp') from e
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError('Reset timestamp needs timezone offset (or Z)')
    return d.astimezone(timezone.utc)


def stamp(t):
    return t.astimezone(timezone.utc).isoformat(timespec='seconds')


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        if default is None:
            raise
        return default


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, indent=2, sort_keys=True)
            f.write('\n')
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if tmp.exists():
            tmp.unlink()


def log_event(path, entry):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(json.dumps(entry, separators=(',', ':'), sort_keys=True)+'\n')


@contextlib.contextmanager
def exclusive_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path)+'.lock', os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def validate(cfg):
    if cfg.get('version') != 2 or not isinstance(cfg.get('accounts'), list):
        raise ValueError('Expected {"version":2,"accounts":[...]}')
    seen = set()
    for a in cfg['accounts']:
        if not isinstance(a, dict):
            raise ValueError('Account must be an object')
        aid = a.get('id')
        if not isinstance(aid, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,96}', aid) or aid in seen:
            raise ValueError('Account ID must be unique, nonempty and alphanumeric/dot/dash/underscore')
        seen.add(aid)
        if a.get('provider') not in PROVIDER_SET:
            raise ValueError(aid+': unsupported provider')
        if not isinstance(a.get('instance_id'), str) or not a['instance_id'].strip():
            raise ValueError(aid+': require a stable T3/provider instance_id')
        wins = a.get('windows')
        if not isinstance(wins, list) or not wins:
            raise ValueError(aid+': require windows')
        winids = set()
        for w in wins:
            wid = w.get('id')
            if not isinstance(wid, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,96}', wid) or wid in winids:
                raise ValueError(aid+': invalid or duplicate window id')
            winids.add(wid)
            if w.get('kind') not in KINDS or w.get('semantics') not in SEMANTICS:
                raise ValueError(aid+'/'+wid+': invalid kind or semantics')
            timestamp(w['next_reset_at'])
            if w.get('semantics') == 'fixed' and w.get('kind') == 'weekly':
                if w.get('repeat_days', 7) != 7:
                    raise ValueError('Fixed weekly resets repeat every 7 days')
            if w.get('semantics') == 'first_request':
                h = w.get('window_hours')
                if not isinstance(h, (int, float)) or isinstance(h, bool) or not (0 < h <= 24*14):
                    raise ValueError(aid+'/'+wid+': window_hours required for first_request')
        d = a.get('activation', {})
        if not isinstance(d, dict):
            raise ValueError(aid+': invalid activation')
        mode = d.get('mode', 'notify')
        if mode not in ('notify', 'command'):
            raise ValueError(aid+': invalid activation mode')
        if mode == 'command':
            argv = d.get('argv')
            if not isinstance(argv, list) or len(argv) < 2 or not all(isinstance(v, str) and v.strip() for v in argv):
                raise ValueError(aid+': command mode requires explicit argv')
            if any(re.search(r'(?i)(api[_-]?key|--api-key|base[_-]?url|token_harbor)', x) for x in argv):
                raise ValueError(aid+': API-key/base-URL overrides are not permitted')
            if d.get('confirmed_instance_id') != a['instance_id']:
                raise ValueError(aid+': confirmed_instance_id must match account instance_id')
            if not d.get('subscription_verified', False):
                raise ValueError(aid+': explicitly verify subscription mode before command dispatch')
        grace = d.get('grace_seconds', 90)
        if not isinstance(grace, int) or not (1 <= grace <= 3600):
            raise ValueError(aid+': grace_seconds must be between 1 and 3600')
    return cfg


def windows(cfg):
    for a in cfg['accounts']:
        for w in a['windows']:
            yield a, w


def key(a, w):
    return a['provider']+'|'+a['instance_id']+'|'+a['id']+'|'+w['id']


def record(state, a, w):
    k = key(a,w)
    rec = state.setdefault('windows',{}).setdefault(k,{})
    configured = stamp(timestamp(w['next_reset_at']))
    if rec.get('configured') != configured:
        # Keep handled event IDs across config edits: never replay an old dispatch.
        rec.update(configured=configured, next_reset_at=configured, confirmation='unconfirmed')
        rec.setdefault('handled', [])
    return rec


def effective_due(rec, w, now):
    due = timestamp(rec['next_reset_at'])
    if w['semantics']=='fixed' and w['kind']=='weekly' and now >= due + timedelta(days=7):
        n = int((now-due)//timedelta(days=7))
        due += timedelta(days=7*n)
    return due


def notify(msg, quiet=False):
    print(msg)
    if quiet or platform.system() != 'Darwin':
        return
    try:
        subprocess.run(['osascript','-e','display notification '+json.dumps(msg)+' with title "TOKENMAXXING quotas"'],
                       capture_output=True, timeout=4, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def apply_snapshot(cfg,state,snapshot,now):
    """Import a user-supplied normalized T3/CLI usage export, never read private T3 files."""
    if not isinstance(snapshot,dict) or snapshot.get('version') != 1:
        raise ValueError('Snapshot must have version=1')
    observed = timestamp(snapshot['observed_at'])
    if observed > now + timedelta(minutes=2) or observed < now-timedelta(days=2):
        raise ValueError('Snapshot is future-dated or more than 48 hours old')
    matches=[]
    entries = snapshot.get('accounts',[])
    if not isinstance(entries,list):
        raise ValueError('accounts must be a list')
    by_id={(a['provider'],a['instance_id']):a for a in cfg['accounts']}
    for entry in entries:
        pair=(entry.get('provider'),entry.get('instance_id'))
        a=by_id.get(pair)
        if a is None:
            continue  # Don't combine different T3 accounts or homes.
        lookup={w['id']:w for w in a['windows']}
        for s in entry.get('windows',[]):
            w=lookup.get(s.get('id'))
            if w is None:
                continue
            new_due=timestamp(s['resets_at'])
            if new_due <= observed-timedelta(hours=24):
                continue
            pct=s.get('used_percent')
            if pct is not None and (not isinstance(pct,(float,int)) or isinstance(pct,bool) or not 0<=pct<=100):
                raise ValueError('used_percent must be between 0 and 100')
            rec=record(state,a,w)
            old_due=timestamp(rec['next_reset_at'])
            rec['observed_at']=stamp(observed)
            rec['used_percent']=pct
            rec['source']='manual-normalized-provider-export'
            if new_due>old_due:
                rec['next_reset_at']=stamp(new_due)
                sent=rec.get('last_dispatch_at')
                if (rec.get('confirmation')=='pending' and pct is not None and pct>0
                        and sent is not None and observed>=timestamp(sent)):
                    rec['confirmation']='confirmed-provider-window-moved'
            matches.append({'account':a['id'],'window':w['id'],'next_reset_at':rec['next_reset_at'],
                            'confirmation':rec['confirmation']})
    return matches


def check(cfg,state,now,*,allow_dispatch=False,dry_run=False,quiet=False,runner=None,log_path=None,state_path=None):
    """At-most-once send. Exit 0 is only 'pending', never a confirmed reset."""
    runner=runner or subprocess.run
    outcomes=[]
    # Dry runs operate on an isolated copy: zero changes, no notifications, no commands.
    if dry_run:
        state=json.loads(json.dumps(state))
    for a,w in windows(validate(cfg)):
        rec=record(state,a,w)
        due=effective_due(rec,w,now)
        if now<due:
            continue
        token=stamp(due)
        if token in rec.get('handled',[]):
            continue
        mode=a.get('activation',{}).get('mode','notify')
        status='notification'
        if w['semantics']=='fixed':
            status='fixed-window-no-request'
        elif w['semantics']=='unverified':
            status='unverified-window-no-request'
        elif mode=='command':
            lag=(now-due).total_seconds()
            if not allow_dispatch:
                status='explicit-dispatch-required'
            elif lag>a['activation'].get('grace_seconds',90):
                status='missed-activation-window'
            else:
                group=w.get('activation_group', 'shared' if w['kind'] in ('session','weekly') else w['id'])
                gk=key(a, {'id':'group-'+group})
                previous=state.get('group_dispatch',{}).get(gk)
                if previous and abs((now-timestamp(previous)).total_seconds())<120:
                    status='shared-activation-already-sent'
                else:
                    status='dispatch-reserved' if not dry_run else 'would-dispatch'
        if not dry_run and status=='dispatch-reserved':
            # Persist a reservation BEFORE sending. Crash or timeout cannot replay a second request.
            rec['handled'].append(token)
            rec['handled']=rec['handled'][-150:]
            rec['confirmation']='pending'
            rec['last_dispatch_at']=stamp(now)
            # Reserve shared pool too before invoking provider (crash-safe across windows).
            state.setdefault('group_dispatch',{})[gk]=stamp(now)
            if state_path is not None:
                atomic(state_path,state)
            env=os.environ.copy()
            for env_key in PROTECTED_ENV:
                env.pop(env_key,None)
            try:
                cmd=a['activation']['argv']
                ret=runner(cmd,check=False,capture_output=True,text=True,shell=False,
                           timeout=min(int(a['activation'].get('timeout_seconds',30)),120),env=env)
                status='sent-pending-verification' if ret.returncode==0 else 'request-exited-nonzero-unverified'
            except (OSError, subprocess.TimeoutExpired):
                status='request-failed-or-timeout-unverified'
            rec['last_dispatch_status']=status
        elif not dry_run:
            rec['handled'].append(token)
            rec['handled']=rec['handled'][-150:]
        if not dry_run and w['semantics']=='fixed' and w['kind']=='weekly':
            rec['next_reset_at']=stamp(due+timedelta(days=7))
        event={'at':stamp(now),'account':a['id'],'instance_id':a['instance_id'],'window':w['id'],
               'reset_at':token,'status':status}
        outcomes.append(event)
        if not dry_run:
            if log_path is not None:
                log_event(log_path,event)
            notify(a['id']+'/'+w['id']+': '+status,quiet)
    return outcomes


def status(cfg,state,now):
    for a,w in windows(validate(cfg)):
        rec=record(state,a,w)
        due=effective_due(rec,w,now)
        print(f"{a['id']} [{a['provider']}/{a['instance_id']}] {w['id']} ({w['kind']}, {w['semantics']}): "
              f"{stamp(due)}, verification={rec.get('confirmation','none')}, "
              f"used={rec.get('used_percent','unknown')}%")


def main(argv=None):
    ap=argparse.ArgumentParser(description='TOKENMAXXING quota windows: notifications by default')
    ap.add_argument('action',choices=('setup','status','check','watch','sync','confirm'))
    ap.add_argument('--config',type=Path,default=CONFIG)
    ap.add_argument('--state',type=Path,default=STATE)
    ap.add_argument('--log',type=Path,default=LOG)
    ap.add_argument('--snapshot',type=Path,help='Sanitized JSON export manually supplied from provider/T3 UI')
    ap.add_argument('--allow-dispatch',action='store_true',help='Explicit extra opt-in for verified subscription-backed CLI')
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--quiet',action='store_true')
    ap.add_argument('--account')
    ap.add_argument('--window')
    ap.add_argument('--next-reset',help='Verified provider next reset timestamp, not an estimate')
    ap.add_argument('--poll-seconds',type=int,default=60)
    args=ap.parse_args(argv)
    if args.action=='setup':
        path=Path(args.config)
        if path.exists():
            print('Existing quota configuration kept unchanged:',path)
            return 0
        template=Path(__file__).resolve().parents[1]/'config/quota-windows.example.json'
        if args.dry_run:
            print('Would create:',path);return 0
        fd=os.open(str(path),os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600) if path.parent.exists() else None
        if fd is None:
            path.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(str(path),os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            f.write(template.read_text(encoding='utf-8'))
        print('Created private quota config:',path)
        print('Replace sample timestamps, instance IDs and provider settings with VERIFIED values before activation.')
        return 0
    if args.poll_seconds<60:
        ap.error('Minimum polling interval is 60 seconds')
    try:
        cfg=validate(read_json(args.config))
    except (ValueError,FileNotFoundError,KeyError) as e:
        ap.error('Invalid/missing quota configuration: '+str(e))
    if args.action=='watch' and args.dry_run:
        ap.error('Use check --dry-run instead of watch --dry-run')
    while True:
        now=datetime.now(timezone.utc)
        with exclusive_lock(args.state):
            state=read_json(args.state,{'windows':{}})
            if args.action=='status':
                status(cfg,state,now)
                return 0
            elif args.action=='sync':
                if not args.snapshot:
                    ap.error('sync requires --snapshot')
                results=apply_snapshot(cfg,state,read_json(args.snapshot),now)
                if not args.dry_run:
                    atomic(args.state,state)
                print(json.dumps(results,indent=2))
                return 0
            elif args.action=='confirm':
                if not (args.account and args.window and args.next_reset):
                    ap.error('confirm needs --account, --window and --next-reset')
                target=next(((a,w) for a,w in windows(cfg) if a['id']==args.account and w['id']==args.window),None)
                if target is None:
                    ap.error('Unknown account/window')
                a,w=target
                rec=record(state,a,w)
                nextdue=timestamp(args.next_reset)
                if nextdue<=timestamp(rec['next_reset_at']):
                    ap.error('Confirmed reset must be later than previously known reset')
                rec['next_reset_at']=stamp(nextdue)
                rec['confirmation']='user-confirmed-from-provider-ui'
                if not args.dry_run:
                    atomic(args.state,state)
                print('Verified next reset recorded:',rec['next_reset_at'])
                return 0
            else:
                results=check(cfg,state,now,allow_dispatch=args.allow_dispatch,dry_run=args.dry_run,
                              quiet=args.quiet,log_path=args.log,state_path=args.state)
                if not args.dry_run:
                    atomic(args.state,state)
                else:
                    for item in results:
                        print(json.dumps(item))
                if args.action=='check':
                    return 0
        time.sleep(args.poll_seconds)

if __name__=='__main__':
    sys.exit(main())
