#!/usr/bin/env python3
"""TOKENMAXXING Reset Activation Engine. No API polling or prompts by default.

Python 3.9+. A human supplies verified account-specific reset timestamps.
`dispatch: command` requires both an explicit argv and --allow-dispatch.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

DEFAULT_CONFIG = Path.home() / '.config' / 'tokenmaxxing' / 'reset-watcher.json'
DEFAULT_STATE = Path.home() / '.local' / 'state' / 'tokenmaxxing' / 'reset-watcher-state.json'


def parse_time(s):
    if not isinstance(s, str):
        raise ValueError('reset time must be ISO8601 text with timezone')
    d = datetime.fromisoformat(s.replace('Z', '+00:00'))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError('reset time must include UTC offset or Z')
    return d.astimezone(timezone.utc)


def iso(t):
    return t.astimezone(timezone.utc).isoformat(timespec='seconds')


def load_json(p, default=None):
    try:
        with p.open(encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        if default is not None:
            return default
        raise


def save_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2)
        f.write('\n')
    os.replace(str(tmp), str(p))


def validate(config):
    if config.get('version') != 1:
        raise ValueError('Unsupported config version (expected 1)')
    accounts = config.get('accounts')
    if not isinstance(accounts, list):
        raise ValueError('accounts must be a list')
    seen = set()
    for a in accounts:
        k = a.get('id')
        if not isinstance(k, str) or not k or k in seen:
            raise ValueError('account id must be unique nonempty text')
        seen.add(k)
        if a.get('provider') not in ('codex', 'claude', 'other'):
            raise ValueError(f'{k}: unsupported provider')
        if a.get('window') not in ('session', 'weekly', 'other'):
            raise ValueError(f'{k}: unsupported window')
        if a.get('semantics') not in ('first_request', 'fixed', 'unverified'):
            raise ValueError(f'{k}: invalid reset semantics')
        if a.get('dispatch', 'notify') not in ('notify', 'command'):
            raise ValueError(f'{k}: dispatch must be notify or command')
        parse_time(a['next_reset_at'])
        if a.get('semantics') == 'first_request':
            if not isinstance(a.get('window_hours'), (int, float)) or a['window_hours'] <= 0:
                raise ValueError(f'{k}: window_hours required for first_request')
        if a.get('semantics') == 'fixed' and a.get('dispatch') == 'command':
            raise ValueError(f'{k}: fixed reset cannot auto-dispatch just to start a timer')
        if a.get('semantics') == 'unverified' and a.get('dispatch') == 'command':
            raise ValueError(f'{k}: unverified reset cannot auto-dispatch')
        if a.get('dispatch') == 'command':
            argv = a.get('command')
            if not isinstance(argv, list) or len(argv) < 2 or not all(isinstance(x, str) and x for x in argv):
                raise ValueError(f'{k}: command requires explicit argv list')
            # Commands run without a shell. No provider credentials are read or modified.
        if a.get('grace_seconds', 120) < 0:
            raise ValueError(f'{k}: grace_seconds must be nonnegative')
        if a.get('semantics') == 'fixed' and a.get('window') == 'weekly' and a.get('repeat_days', 7) != 7:
            raise ValueError(f'{k}: fixed weekly windows repeat every 7 days')
    return accounts


def account_record(state, account):
    records = state.setdefault('accounts', {})
    rec = records.setdefault(account['id'], {})
    initial = iso(parse_time(account['next_reset_at']))
    if rec.get('configured_reset') != initial:
        rec.clear()
        rec.update({'configured_reset': initial, 'next_due': initial, 'processed': []})
    return rec


def due_at(account, record, now):
    due = parse_time(record['next_due'])
    if account['semantics'] == 'fixed':
        days = int(account.get('repeat_days', 7)) if account['window'] == 'weekly' else 0
        if days and now >= due + timedelta(days=days):
            intervals = (now - due) // timedelta(days=days)
            due += intervals * timedelta(days=days)
    return due


def notify(title, message, quiet=False):
    print(f'{title}: {message}')
    if quiet or platform.system() != 'Darwin':
        return
    try:
        subprocess.run(['osascript','-e','display notification ' + json.dumps(message) + ' with title ' + json.dumps(title)],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def evaluate(config, state, now, *, allow_dispatch=False, dry_run=False, quiet=False, runner=None):
    """Return list of event outcomes. Mutates state unless dry_run. Never auto-prime unknown/fixed windows."""
    runner = runner or subprocess.run
    outcomes = []
    for a in validate(config):
        rec = account_record(state, a) if not dry_run else account_record(json.loads(json.dumps(state)), a)
        due = due_at(a, rec, now)
        if now < due:
            continue
        event_id = f'{a["id"]}|{iso(due)}'
        if event_id in rec.get('processed', []):
            continue
        lag = (now - due).total_seconds()
        grace = a.get('grace_seconds', 120)
        status = 'notification'
        should_auto = (a.get('dispatch') == 'command' and a['semantics'] == 'first_request'
                       and lag <= grace and allow_dispatch)
        if a.get('dispatch') == 'command' and not allow_dispatch:
            status = 'manual-approval-required'
        elif a.get('dispatch') == 'command' and lag > grace:
            status = 'missed-grace-period'
        elif a['semantics'] == 'fixed':
            status = 'fixed-reset-no-prime-needed'
        elif a['semantics'] == 'unverified':
            status = 'unverified-reset-manual-confirmation'
        if should_auto:
            argv = a['command']
            if not dry_run:
                try:
                    result = runner(argv, shell=False, timeout=int(a.get('timeout_seconds', 60)),
                                    capture_output=True, text=True, check=False)
                    if result.returncode != 0:
                        status = 'dispatch-failed'
                    else:
                        status = 'dispatched'
                except (OSError, subprocess.TimeoutExpired):
                    status = 'dispatch-failed'
            else:
                status = 'would-dispatch'
        if not dry_run:
            notify('TOKENMAXXING reset', f'{a["id"]}: {status} ({iso(due)})', quiet)
            if status != 'dispatch-failed':
                rec.setdefault('processed', []).append(event_id)
                rec['processed'] = rec['processed'][-100:]
                if status == 'dispatched':
                    rec['next_due'] = iso(now + timedelta(hours=a['window_hours']))
                elif a['semantics'] == 'fixed' and a.get('window') == 'weekly':
                    rec['next_due'] = iso(due + timedelta(days=7))
        outcomes.append({'account': a['id'], 'reset_at': iso(due), 'status': status})
    return outcomes


def main(argv=None):
    ap = argparse.ArgumentParser(description='TOKENMAXXING provider usage-reset watcher')
    ap.add_argument('action', choices=('status','check','watch','ack'))
    ap.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    ap.add_argument('--state', type=Path, default=DEFAULT_STATE)
    ap.add_argument('--allow-dispatch', action='store_true', help='Explicitly permit configured provider CLI requests')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--quiet', action='store_true', help='Do not send macOS desktop notifications')
    ap.add_argument('--account', help='Account id for ack')
    ap.add_argument('--at', help='ISO timestamp of the first real user message, for ack')
    ap.add_argument('--poll-seconds', type=int, default=60)
    args = ap.parse_args(argv)
    if not args.config.is_file():
        ap.error(f'Create {args.config} from config/reset-watcher.example.json first')
    config = load_json(args.config)
    validate(config)
    if args.poll_seconds < 60:
        ap.error('Minimum polling interval is 60 seconds')
    state = load_json(args.state, {'accounts': {}})
    if args.action == 'ack':
        if not args.account:
            ap.error('--account is required for ack')
        match = next((a for a in config['accounts'] if a['id'] == args.account), None)
        if match is None or match['semantics'] != 'first_request':
            ap.error('ack requires a configured first_request account')
        at = parse_time(args.at) if args.at else datetime.now(timezone.utc)
        rec = account_record(state, match)
        reset = due_at(match, rec, at)
        if at < reset:
            ap.error('First message cannot precede the reset timestamp')
        rec.setdefault('processed', []).append(f'{match["id"]}|{iso(reset)}')
        rec['next_due'] = iso(at + timedelta(hours=match['window_hours']))
        if not args.dry_run:
            save_json(args.state,state)
        print(f'Acknowledged {match["id"]}; next estimated window {rec["next_due"]}')
        return 0
    if args.action == 'status':
        for a in config['accounts']:
            rec = account_record(state,a)
            due = due_at(a,rec,datetime.now(timezone.utc))
            print(f'{a["id"]}: {a["provider"]} {a["window"]}, {a["semantics"]}, next {iso(due)}, {a.get("dispatch","notify")}')
        return 0
    if args.action == 'watch' and args.dry_run:
        ap.error('watch does not support --dry-run; run check --dry-run')
    while True:
        now = datetime.now(timezone.utc)
        results = evaluate(config,state,now,allow_dispatch=args.allow_dispatch,dry_run=args.dry_run,quiet=args.quiet)
        for x in results:
            if args.dry_run:
                print(json.dumps(x))
        if not args.dry_run:
            save_json(args.state,state)
        if args.action == 'check':
            return 0
        time.sleep(args.poll_seconds)

if __name__ == '__main__':
    sys.exit(main())
