#!/bin/bash
set -euo pipefail
if [[ "$(uname -s)" != "Darwin" ]]; then echo 'macOS required' >&2; exit 1; fi
repo="$(cd "$(dirname "$0")/.." && pwd)"
script="$repo/scripts/reset_watcher.py"
config="$HOME/.config/tokenmaxxing/reset-watcher.json"
if [[ ! -f "$config" ]]; then echo "Create $config from config/reset-watcher.example.json first" >&2; exit 1; fi
command -v python3 >/dev/null || { echo 'python3 required' >&2; exit 1; }
python3 "$script" status >/dev/null
agentdir="$HOME/Library/LaunchAgents"
plist="$agentdir/com.agentkindlabs.tokenmaxxing.reset-watcher.plist"
if [[ -e "$plist" ]]; then echo "Already exists: $plist (remove/unload deliberately before reinstalling)" >&2; exit 1; fi
mkdir -p "$agentdir" "$HOME/Library/Logs"
export RESET_SCRIPT="$script" RESET_CONFIG="$config"
python3 - "$plist" <<'PY'
import os,plistlib,sys
p=sys.argv[1]
data={'Label':'com.agentkindlabs.tokenmaxxing.reset-watcher',
      'ProgramArguments':['/usr/bin/env','python3',os.environ['RESET_SCRIPT'],'check','--config',os.environ['RESET_CONFIG']],
      'StartInterval':60,'RunAtLoad':True,
      'StandardOutPath':os.path.expanduser('~/Library/Logs/tokenmaxxing-reset.log'),
      'StandardErrorPath':os.path.expanduser('~/Library/Logs/tokenmaxxing-reset-error.log')}
with open(p,'wb') as f:plistlib.dump(data,f)
PY
launchctl bootstrap "gui/$(id -u)" "$plist"
echo "Installed notification-only LaunchAgent: $plist"
echo "Disable: launchctl bootout gui/$(id -u) '$plist' ; then remove the file"
