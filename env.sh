#!/usr/bin/env bash
# This file is meant to be sourced in an interactive shell.
# Avoid strict-mode flags (`set -euo pipefail`) here, since they leak into
# the caller shell and can break tab-completion or interactive behavior.
# Also clear them in case an older version of this file enabled them.
set +e
set +u
set +o pipefail 2>/dev/null || true

FRIDA_DIR="$HOME/frida"
VENV_DIR="$FRIDA_DIR/.venv"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "Missing venv: $VENV_DIR" >&2
  return 1 2>/dev/null || exit 1
fi

# Activate FRIDA virtual environment
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

# Enable pytest tab-completion via this venv's argcomplete install
if [[ $- == *i* ]] && [ -x "$VENV_DIR/bin/register-python-argcomplete" ]; then
  eval "$($VENV_DIR/bin/register-python-argcomplete pytest)"
fi
