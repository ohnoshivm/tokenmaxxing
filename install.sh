#!/usr/bin/env bash
    set -euo pipefail
    cd "$(dirname "$0")"
    if ! command -v python3 >/dev/null 2>&1; then
      printf '%s\n' 'TOKENMAXXING requires Python 3.9+.' >&2; exit 1
    fi
    exec python3 tokenmaxxing.py install "$@"
