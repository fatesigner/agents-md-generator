#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

for candidate in "$HOME/.python-tools/.runtime/.venv/bin/python" /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$candidate" ] && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    exec "$candidate" "$SCRIPT_DIR/scripts/sync_codex_assets.py" "$@"
  fi
done

printf 'sync_codex_assets: Python 3.11 or later runtime not found\n' >&2
exit 1
