#!/usr/bin/env python3
"""TOKENMAXXING bootstrap: staged, pinned upstream tools + scoped portable skill.

Standard library only. Does not change API credentials, provider routing,
Claude settings.json, shell profiles, existing subagents, or T3 configuration.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "policy" / "optimizer-registry.json"
PROFILE_NAMES = ("balanced", "deep-reasoning", "full-product", "minimal-patch", "large-repository")


def home_dir():
    return Path.home()


def installed_dir():
    return Path(os.environ.get("TOKENMAXXING_HOME", str(home_dir()/".tokenmaxxing"))).expanduser()


def registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["tools"]


def command(args, cwd=None, check=True):
    return subprocess.run(args, cwd=cwd, check=check, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def say(msg):
    print(msg, flush=True)


def validate_tool(tool):
    url = tool["source"]
    rev = tool["revision"]
    if not url.startswith("https://github.com/") or not url.endswith(".git"):
        raise ValueError("Non-GitHub source rejected")
    if len(rev) != 40 or any(c not in "0123456789abcdef" for c in rev):
        raise ValueError("Invalid pinned commit")
    if '/' in tool['id'] or tool['id'].startswith('.'):
        raise ValueError("Invalid tool name")


def stage(tool, base, *, dry_run=False):
    validate_tool(tool)
    dest = base / 'vendor' / tool['id']
    if dry_run:
        say(f"[plan] fetch {tool['upstream']} @ {tool['revision'][:12]} -> {dest}")
        return 'planned'
    if dest.exists():
        if not (dest/'.git').is_dir():
            say(f"[skip] {dest} exists without a standalone git checkout; manual review needed")
            return 'conflict'
        try:
            got = command(['git','rev-parse','HEAD'],cwd=dest).stdout.strip()
        except subprocess.CalledProcessError:
            return 'conflict'
        if got == tool['revision']:
            say(f"[ok] {tool['id']} pinned at {got[:12]}")
            return 'present'
        say(f"[skip] {tool['id']} exists at {got[:12]} (expected {tool['revision'][:12]}); not overwriting")
        return 'conflict'
    dest.parent.mkdir(parents=True,exist_ok=True)
    try:
        command(['git','clone','--quiet','--no-checkout',tool['source'],str(dest)])
        command(['git','checkout','--quiet','--detach',tool['revision']],cwd=dest)
        got = command(['git','rev-parse','HEAD'],cwd=dest).stdout.strip()
        if got != tool['revision']:
            raise RuntimeError(f"Pinned commit mismatch: {got}")
        say(f"[ok] staged {tool['id']} @ {got[:12]}")
        return 'staged'
    except (OSError,subprocess.CalledProcessError,RuntimeError) as e:
        # Only remove our own incomplete checkout, never a preexisting one.
        if dest.exists(): shutil.rmtree(dest)
        say(f"[error] stage {tool['id']}: {e}")
        return 'failed'


def install_skill(*, scope, dry_run=False, replace=False):
    source = ROOT/'skills'/'tokenmaxxing'
    if scope == 'user':
        dest=home_dir()/'.claude'/'skills'/'tokenmaxxing'
    else:
        dest=ROOT/'.claude'/'skills'/'tokenmaxxing'
    if dry_run:
        say(f"[plan] install TOKENMAXXING skill -> {dest}")
        return 'planned'
    if not source.joinpath('SKILL.md').is_file():
        raise FileNotFoundError(source/'SKILL.md')
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() or dest.is_symlink():
        if dest.is_dir() and (dest/'SKILL.md').is_file() and (dest/'SKILL.md').read_bytes()==(source/'SKILL.md').read_bytes():
            say(f"[ok] skill already installed at {dest}")
            return 'present'
        if not replace:
            say(f"[skip] existing skill at {dest}; use --replace-skill for backup and replacement")
            return 'conflict'
        backup = dest.parent/(dest.name+'.backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        dest.rename(backup)
        say(f"[backup] {backup}")
    shutil.copytree(source,dest)
    say(f"[ok] installed TOKENMAXXING skill -> {dest}")
    return 'installed'


def status():
    base=installed_dir()
    say(f"Cache: {base}")
    for t in registry():
        dest=base/'vendor'/t['id']
        if (dest/'.git').is_dir():
            try:
                head=command(['git','rev-parse','HEAD'],cwd=dest).stdout.strip()
                st='pinned' if head==t['revision'] else f"different commit {head[:12]}"
            except Exception: st='unreadable'
        else: st='not staged'
        say(f"{t['id']}: {st}")
    for scope in ('user','project'):
        path=(home_dir()/'.claude'/'skills'/'tokenmaxxing') if scope=='user' else ROOT/'.claude'/'skills'/'tokenmaxxing'
        say(f"{scope} skill: {'present' if (path/'SKILL.md').is_file() else 'missing'}")
    # This is NOT a claim about active Claude plugin settings or T3 registration.
    say('Native optimizer activation: not managed automatically. T3 Chat setup: manual policy reference.')
    cfg=reset_config_path()
    say(f'Reset Activation Engine: {"configured" if cfg.is_file() else "not configured"} ({cfg})')
    say('Reset controls: python3 tokenmaxxing.py reset --help')
    say('Usage audit: python3 tokenmaxxing.py audit --help · doctor: python3 tokenmaxxing.py doctor --help · statusline: python3 tokenmaxxing.py statusline --help')


def preview_plugin(tool):
    info=tool.get('claude_plugin')
    if not info: return f"{tool['id']}: no verified native plugin installation recipe; staged repository only"
    return f"claude plugin marketplace add {info['marketplace']}\nclaude plugin install {info['name']}@{info['marketplace_id']} --scope user"


def reset_config_path():
    return home_dir() / '.config' / 'tokenmaxxing' / 'reset-watcher.json'


def setup_reset_config(*, dest=None, dry_run=False):
    """Create a private, unconfigured example without overwriting user settings."""
    source = ROOT / 'config' / 'reset-watcher.example.json'
    dest = Path(dest) if dest is not None else reset_config_path()
    if not source.is_file():
        raise FileNotFoundError(source)
    if dest.exists():
        say(f'[ok] reset configuration already exists: {dest} (unchanged)')
        return 'present'
    if dry_run:
        say(f'[plan] copy the example reset configuration to {dest}')
        return 'planned'
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        say(f'[ok] reset configuration appeared meanwhile: {dest} (unchanged)')
        return 'present'
    with os.fdopen(fd, 'w', encoding='utf-8') as out:
        out.write(source.read_text(encoding='utf-8'))
    say(f'[ok] created private reset config at {dest}')
    say('ACTION REQUIRED: Replace every example timestamp with the verified account-specific reset time.')
    say('No messages or watcher were activated. Default dispatch is notification-only.')
    return 'created'


def run_reset_action(args):
    config = args.config or reset_config_path()
    if args.reset_action == 'setup':
        setup_reset_config(dest=config, dry_run=args.dry_run)
        return 0
    if args.reset_action == 'install-macos':
        if args.config is not None and config != reset_config_path():
            say('macOS LaunchAgent uses the default config path; omit --config for install-macos')
            return 2
        if args.dry_run:
            say(f'[plan] install minute-interval notification-only LaunchAgent via {ROOT / "scripts/install-reset-watcher-macos.sh"}')
            return 0
        if not config.is_file():
            say(f'Create the reset configuration first: python3 tokenmaxxing.py reset setup')
            return 2
        # The installer itself verifies macOS and registers a notification-only agent.
        return subprocess.call(['bash', str(ROOT/'scripts'/'install-reset-watcher-macos.sh')])
    if not config.is_file():
        say('Reset config missing. First run: python3 tokenmaxxing.py reset setup')
        return 2
    cmd = [sys.executable, str(ROOT/'scripts'/'reset_watcher.py'), args.reset_action, '--config', str(config)]
    if args.state: cmd.extend(['--state', str(args.state)])
    if args.allow_dispatch: cmd.append('--allow-dispatch')
    if args.dry_run: cmd.append('--dry-run')
    if args.quiet: cmd.append('--quiet')
    if args.account: cmd.extend(['--account', args.account])
    if args.at: cmd.extend(['--at', args.at])
    if args.poll_seconds is not None: cmd.extend(['--poll-seconds', str(args.poll_seconds)])
    # No shell, no authentication or provider-config modification.
    return subprocess.call(cmd)


def load_subcommand(name):
    script = ROOT / 'scripts' / (name + '.py')
    if not script.is_file():
        say(f"Subcommand '{name}' is unavailable: scripts/{name}.py is missing")
        return None
    script_dir = str(ROOT / 'scripts')
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        return importlib.import_module(name)
    except ImportError as e:
        say(f"Subcommand '{name}' is unavailable: could not load scripts/{name}.py ({e})")
        return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    module_names = ('audit', 'doctor', 'statusline', 'fix', 'guard')
    selected_module = None
    if argv and argv[0] in module_names:
        selected_module = load_subcommand(argv[0])
        if selected_module is None:
            return 2
    p=argparse.ArgumentParser(prog='tokenmaxxing',description='Pinned optimizer toolkit and portable token-efficient agent skill')
    p.add_argument('--version', action='version', version='tokenmaxxing 1.5.0')
    subs=p.add_subparsers(dest='action',required=True)
    install=subs.add_parser('install',help='Stage pinned upstream repos and install one reusable token-efficiency skill')
    install.add_argument('--scope',choices=('user','project'),default='user')
    install.add_argument('--profile',choices=PROFILE_NAMES,default='balanced')
    install.add_argument('--no-fetch',action='store_true',help='Only install the local skill, without git clones')
    install.add_argument('--dry-run',action='store_true',help='Print intended changes only')
    install.add_argument('--replace-skill',action='store_true',help='Back up existing skill before replacing it')
    install.add_argument('--with-reset-config',action='store_true',help='Prepare an inactive, private reset-watcher config (never sends a request)')
    subs.add_parser('status',help='Check staged git revisions and installed skill')
    for name, help_text in (
            ('audit', 'Measure token spend from local agent session logs'),
            ('doctor', 'Inspect local agent configuration and context overhead'),
            ('fix', 'Plan or apply reversible skill archives'),
            ('guard', 'Opt-in cache-cold prompt guard'),
            ('statusline', 'Show a compact live usage statusline')):
        cmd = subs.add_parser(name, help=help_text)
        if name == (argv[0] if argv else None) and selected_module is not None:
            selected_module.add_arguments(cmd)
    pp=subs.add_parser('profiles',help='List available profiles')
    plugin=subs.add_parser('plugin-commands',help='Show upstream native plugin commands; never executes them')
    plugin.add_argument('id',choices=[t['id'] for t in registry()])
    reset=subs.add_parser('reset',help='First-class reset window feature: setup, status, check, watch, ack, install-macos')
    reset.add_argument('reset_action',nargs='?',choices=('setup','status','check','watch','ack','install-macos'),default='status')
    reset.add_argument('--config',type=Path,help='Reset watcher configuration path')
    reset.add_argument('--state',type=Path,help='Reset watcher state path')
    reset.add_argument('--allow-dispatch',action='store_true',help='Explicitly allow preconfigured provider CLI request; never enabled by default')
    reset.add_argument('--dry-run',action='store_true',help='Preview actions without sending requests')
    reset.add_argument('--quiet',action='store_true',help='Suppress desktop notification')
    reset.add_argument('--account',help='Account ID for manual acknowledgment')
    reset.add_argument('--at',help='Time of first real request, ISO 8601 with zone')
    reset.add_argument('--poll-seconds',type=int,help='Polling interval, minimum 60 seconds')
    args=p.parse_args(argv)
    if args.action in module_names:
        return selected_module.run(args)
    if args.action=='reset':return run_reset_action(args)
    if args.action=='status':status();return 0
    if args.action=='profiles':
        for prof in PROFILE_NAMES: say(f"{prof}: {ROOT/'profiles'/(prof+'.md')}")
        return 0
    if args.action=='plugin-commands':
        say(preview_plugin(next(t for t in registry() if t['id']==args.id)))
        return 0
    if sys.version_info < (3,9):
        say('Python 3.9+ required');return 2
    say('TOKENMAXXING bootstrap — no credential, provider, MCP, hook, or settings modifications')
    say(f"Selected profile: {args.profile} (instructions: {ROOT/'profiles'/(args.profile+'.md')})")
    result=install_skill(scope=args.scope,dry_run=args.dry_run,replace=args.replace_skill)
    failures=1 if result=='conflict' else 0
    if args.with_reset_config:
        setup_reset_config(dry_run=args.dry_run)
    if not args.no_fetch:
        if not shutil.which('git'):
            say('Git missing: cannot stage pinned sources');return 2
        for tool in registry():
            result=stage(tool,installed_dir(),dry_run=args.dry_run)
            if result in ('failed','conflict'): failures+=1
    say('\nREVIEW BEFORE ACTIVATION: these repos may have competing hooks. No external optimizer is activated by this installer.')
    say('Read docs/optimizer-profiles.md and use `python3 tokenmaxxing.py plugin-commands <id>` for upstream plugin setup.')
    say('T3 Chat cannot be configured automatically by this CLI. See docs/t3-chat.md for portable instructions.')
    if failures: say(f"Finished with {failures} item(s) requiring attention.")
    else: say('Bootstrap completed. Tools are staged, and TOKENMAXXING skill is available where supported.')
    return 1 if failures else 0

if __name__=='__main__':sys.exit(main())
