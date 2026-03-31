#!/bin/sh
# inject-for-code-review.sh — Inject code-review and design-principles context
# when the Agent tool is invoked with a code-review subagent type.
# Called by PreToolUse hook. Reads tool call JSON from stdin.
# Exit 0 always — miss just means no injection.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COND_DIR="$SCRIPT_DIR/conditional"

INPUT=$(cat)

TOOL=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_name" *: *"\([^"]*\)".*/\1/p' | head -1)
SUBAGENT=$(printf '%s' "$INPUT" | sed -n 's/.*"subagent_type" *: *"\([^"]*\)".*/\1/p' | head -1)

if [ "$TOOL" = "Agent" ] && printf '%s' "$SUBAGENT" | grep -qi "code-review"; then
  echo "[invariants injected: code-review design-principles (code-review agent activated)]"
  echo ""
  [ -f "$COND_DIR/code-review.md" ] && cat "$COND_DIR/code-review.md"
  [ -f "$COND_DIR/design-principles.md" ] && cat "$COND_DIR/design-principles.md"
fi

exit 0
