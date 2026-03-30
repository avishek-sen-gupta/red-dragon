#!/bin/sh
# classify-prompt.sh — Classify user prompt and inject relevant CLAUDE.md fragments.
# Called by UserPromptSubmit hook. Reads JSON from stdin, extracts prompt field,
# matches keywords case-insensitively, cats matching conditional files.
# Exit 0 always — classification miss just means fewer instructions.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COND_DIR="$SCRIPT_DIR/conditional"

# Extract prompt from JSON stdin (lightweight — no jq dependency)
PROMPT=$(cat | sed -n 's/.*"prompt" *: *"\(.*\)"/\1/p' | head -1)

# Lowercase for matching
LOWER=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')

# Track which files to inject (avoid duplicates)
DESIGN=0
TESTING=0
REVIEW=0
REFACTORING=0
SKILLS=0

# --- implement ---
if printf '%s' "$LOWER" | grep -qiw \
  'implement\|add\|build\|create\|fix\|feature\|bug\|write\|emit\|lower\|migrate\|introduce\|wire\|hook\|support\|handle\|extend\|port\|close'; then
  DESIGN=1; TESTING=1; REFACTORING=1; SKILLS=1
fi

# --- test ---
if printf '%s' "$LOWER" | grep -qiw \
  'test\|tdd\|assert\|coverage\|xfail\|failing\|passes\|red-green\|fixture'; then
  TESTING=1
fi
if printf '%s' "$LOWER" | grep -qi 'integration test\|unit test'; then
  TESTING=1
fi

# --- refactor ---
if printf '%s' "$LOWER" | grep -qiw \
  'refactor\|rename\|extract\|move\|split\|merge\|simplify\|clean\|reorganize\|restructure\|consolidate\|decompose\|inline\|deduplicate'; then
  DESIGN=1; REFACTORING=1; SKILLS=1
fi

# --- review ---
if printf '%s' "$LOWER" | grep -qiw \
  'review\|pr\|diff\|check\|feedback\|critique\|approve'; then
  REVIEW=1
fi

# --- verify ---
if printf '%s' "$LOWER" | grep -qiw \
  'verify\|audit\|scan\|lint\|sweep\|audit-asserts\|validate\|ensure\|confirm\|gate\|black\|lint-imports'; then
  TESTING=1; SKILLS=1
fi

# Output matching files
[ "$DESIGN" = 1 ] && [ -f "$COND_DIR/design-principles.md" ] && cat "$COND_DIR/design-principles.md"
[ "$TESTING" = 1 ] && [ -f "$COND_DIR/testing-patterns.md" ] && cat "$COND_DIR/testing-patterns.md"
[ "$REVIEW" = 1 ] && [ -f "$COND_DIR/code-review.md" ] && cat "$COND_DIR/code-review.md"
[ "$REFACTORING" = 1 ] && [ -f "$COND_DIR/refactoring.md" ] && cat "$COND_DIR/refactoring.md"
[ "$SKILLS" = 1 ] && [ -f "$COND_DIR/tools-skills.md" ] && cat "$COND_DIR/tools-skills.md"

exit 0
