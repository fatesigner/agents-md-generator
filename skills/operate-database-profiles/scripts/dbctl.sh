#!/bin/sh

set +x
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -n "${DBCTL_PYTHON:-}" ]; then
  [ -x "$DBCTL_PYTHON" ] || {
    printf 'dbctl: DBCTL_PYTHON is not executable\n' >&2
    exit 1
  }
  exec "$DBCTL_PYTHON" "$SCRIPT_DIR/dbctl.py" "$@"
fi

for candidate in "$HOME/.python-tools/.runtime/.venv/bin/python" /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$candidate" ]; then
    exec "$candidate" "$SCRIPT_DIR/dbctl.py" "$@"
  fi
done

printf 'dbctl: Python 3 runtime not found; set DBCTL_PYTHON to an approved absolute path\n' >&2
exit 1
