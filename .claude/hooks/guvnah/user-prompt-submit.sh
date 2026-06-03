#!/usr/bin/env bash
GUVNAH_ROOT="/Users/asgupta/code/guvnah"
export PYTHONPATH="$GUVNAH_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export GUVNAH_MACHINES="$(cd "$(dirname "$0")" && pwd)/machines"
# UserPromptSubmit hook — parse /governor commands.
set -euo pipefail

SESSION="$(printf '%s' "$PWD" | (md5 2>/dev/null || md5sum | cut -d' ' -f1))"

# Quick check: does stdin contain a governor command?
# Matches both raw "/governor" and expanded "Governor workflow enforcer has been invoked with:"
INPUT="$(cat)"
printf '%s' "$INPUT" | grep -qE '/governor|Governor workflow enforcer has been invoked with:' || exit 0

printf '%s' "$INPUT" | exec python3 -m governor_v4 prompt --session "$SESSION"
