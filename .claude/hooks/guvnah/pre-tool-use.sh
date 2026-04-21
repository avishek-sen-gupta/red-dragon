#!/usr/bin/env bash
GUVNAH_ROOT="/Users/asgupta/code/context-injector"
export PYTHONPATH="$GUVNAH_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export GUVNAH_MACHINES="$(cd "$(dirname "$0")" && pwd)/machines"
# PreToolUse hook — evaluate tool call against governor phase.
set -euo pipefail

SESSION="$(printf '%s' "$PWD" | (md5 2>/dev/null || md5sum | cut -d' ' -f1))"

LOCK="/tmp/ctx-governor/${SESSION}/active"
[ -f "$LOCK" ] || exit 0

exec python3 -m governor_v4 evaluate --session "$SESSION"
