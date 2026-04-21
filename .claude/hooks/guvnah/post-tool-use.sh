#!/usr/bin/env bash
GUVNAH_ROOT="/Users/asgupta/code/context-injector"
export PYTHONPATH="$GUVNAH_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export GUVNAH_MACHINES="$(cd "$(dirname "$0")" && pwd)/machines"
# PostToolUse hook — capture tool output as evidence.
set -euo pipefail

SESSION="$(printf '%s' "$PWD" | (md5 2>/dev/null || md5sum | cut -d' ' -f1))"

LOCK="/tmp/ctx-governor/${SESSION}/active"
[ -f "$LOCK" ] || exit 0

exec python3 -m governor_v4 capture --session "$SESSION"
