#!/usr/bin/env bash
# Install a user-scoped, opt-in 60-second quota check. Requires macOS + Python 3.9+.
set -euo pipefail
if [[ "$(uname -s)" != "Darwin" ]]; then echo 'macOS required' >&2; exit 2; fi
repo="$(cd "$(dirname "$0")/.." && pwd)"
python="$(command -v python3 || true)"
if [[ -z "$python" ]]; then echo 'Python3 required' >&2; exit 2; fi
config="$HOME/.config/tokenmaxxing/quota-windows.json"
if [[ ! -f "$config" ]]; then echo 'Run python3 tokenmaxxing.py quota setup, edit the config, and try again' >&2; exit 2; fi
"$python" "$repo/scripts/quota_engine.py" status --config "$config" > /dev/null
allow=0
if [[ "${1:-}" == '--enable-activation' ]]; then
  allow=1
  echo 'CAUTION: command mode can send paid/quota-consuming provider CLI requests.'
  echo 'You must verify each account, its cheapest subscription model and CLI adapter.'
  echo 'If unsure, install without --enable-activation for notifications only.'
fi
agent_dir="$HOME/Library/LaunchAgents"
plist="$agent_dir/com.agentkindlabs.tokenmaxxing.quota.plist"
if [[ -e "$plist" ]]; then echo "Already installed: $plist. Uninstall before reinstalling." >&2; exit 2; fi
mkdir -p "$agent_dir" "$HOME/Library/Logs"
export QUOTA_PYTHON="$python" QUOTA_SCRIPT="$repo/scripts/quota_engine.py" QUOTA_CONFIG="$config" QUOTA_ENABLE="$allow"
python3 - "$plist" <<'PY'
import os, plistlib, sys
p=sys.argv[1]
args=[os.environ['QUOTA_PYTHON'],os.environ['QUOTA_SCRIPT'],'check','--config',os.environ['QUOTA_CONFIG']]
if os.environ['QUOTA_ENABLE']=='1':args+=['--allow-dispatch']
payload={'Label':'com.agentkindlabs.tokenmaxxing.quota', 'ProgramArguments':args,
         'RunAtLoad':True,'StartInterval':60,
         'StandardOutPath':os.path.expanduser('~/Library/Logs/tokenmaxxing-quota.log'),
         'StandardErrorPath':os.path.expanduser('~/Library/Logs/tokenmaxxing-quota-error.log')}
with open(p,'wb') as f:plistlib.dump(payload,f)
PY
launchctl bootstrap "gui/$(id -u)" "$plist"
echo "Installed: $plist (automatic provider requests: $([[ "$allow" == 1 ]] && echo 'opt-in' || echo 'disabled'))"
echo "Uninstall: launchctl bootout gui/$(id -u) '$plist' && rm '$plist'"
