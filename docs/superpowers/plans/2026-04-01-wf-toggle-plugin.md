# Context Injector Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable `context-injector` plugin that auto-injects core + classified conditional context on every prompt when mode is on, toggled via `/ctx` global command.

**Architecture:** A `UserPromptSubmit` hook script checks for a per-project lockfile (`$PWD/.claude/ctx.lock`); when present it cats `core/` then classifies the prompt and cats matching `conditional/` files. A global `~/.claude/commands/ctx.md` command toggles the lockfile. red-dragon's existing `classify-prompt.sh` is deleted and `settings.json` updated to point to the plugin hook.

**Tech Stack:** POSIX sh, Claude Code hooks, Claude Code custom commands

---

## File Map

| Action | Path |
|---|---|
| Create | `~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh` |
| Create | `~/.claude/commands/ctx.md` |
| Modify | `red-dragon/.claude/settings.json` (update hook command) |
| Modify | `red-dragon/.gitignore` (add `ctx.lock`) |
| Delete | `red-dragon/.claude/classify-prompt.sh` |

---

## Task 1: Create plugin hook script

**Files:**
- Create: `~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh`

- [ ] **Step 1: Create plugin directory**

```bash
mkdir -p ~/.claude/plugins/context-injector/hooks
```

- [ ] **Step 2: Write the hook script**

Create `~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh`:

```sh
#!/bin/sh
# user-prompt-submit.sh — Context Injector plugin hook.
# Called by UserPromptSubmit. When ctx mode is on ($PWD/.claude/ctx.lock exists),
# injects core context + classified conditional invariants into the conversation.
# Exit 0 always — missing dirs or no matches are silent no-ops.

LOCK="$PWD/.claude/ctx.lock"
CORE_DIR="$PWD/.claude/core"
COND_DIR="$PWD/.claude/conditional"

# Mode off — nothing to do
[ -f "$LOCK" ] || exit 0

# Extract prompt from JSON stdin (no jq dependency)
PROMPT=$(cat | sed -n 's/.*"prompt" *: *"\(.*\)"/\1/p' | head -1)

# Lowercase for keyword matching
LOWER=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')

# --- classify ---
DESIGN=0
TESTING=0
REVIEW=0
REFACTORING=0
SKILLS=0

if printf '%s' "$LOWER" | grep -qiw \
  'implement\|add\|build\|create\|fix\|feature\|bug\|write\|emit\|lower\|migrate\|introduce\|wire\|hook\|support\|handle\|extend\|port\|close'; then
  DESIGN=1; TESTING=1; REFACTORING=1; SKILLS=1
fi

if printf '%s' "$LOWER" | grep -qiw \
  'test\|tdd\|assert\|coverage\|xfail\|failing\|passes\|red-green\|fixture'; then
  TESTING=1
fi
if printf '%s' "$LOWER" | grep -qi 'integration test\|unit test'; then
  TESTING=1
fi

if printf '%s' "$LOWER" | grep -qiw \
  'refactor\|rename\|extract\|move\|split\|merge\|simplify\|clean\|reorganize\|restructure\|consolidate\|decompose\|inline\|deduplicate'; then
  DESIGN=1; REFACTORING=1; SKILLS=1
fi

if printf '%s' "$LOWER" | grep -qiw \
  'review\|pr\|diff\|check\|feedback\|critique\|approve'; then
  REVIEW=1
fi

if printf '%s' "$LOWER" | grep -qiw \
  'verify\|audit\|scan\|lint\|sweep\|validate\|ensure\|confirm\|gate\|black\|lint-imports'; then
  TESTING=1; SKILLS=1
fi

# --- build injection summary ---
INJECTED="core"
[ "$DESIGN" = 1 ] && INJECTED="${INJECTED} design-principles"
[ "$TESTING" = 1 ] && INJECTED="${INJECTED} testing-patterns"
[ "$REVIEW" = 1 ] && INJECTED="${INJECTED} code-review"
[ "$REFACTORING" = 1 ] && INJECTED="${INJECTED} refactoring"
[ "$SKILLS" = 1 ] && INJECTED="${INJECTED} tools-skills"

echo "[invariants injected: ${INJECTED}]"
echo ""

# --- inject core (always when mode is on) ---
if [ -d "$CORE_DIR" ]; then
  for f in "$CORE_DIR"/*.md; do
    [ -f "$f" ] && cat "$f"
  done
fi

# --- inject matching conditional files ---
[ "$DESIGN" = 1 ] && [ -f "$COND_DIR/design-principles.md" ] && cat "$COND_DIR/design-principles.md"
[ "$TESTING" = 1 ] && [ -f "$COND_DIR/testing-patterns.md" ] && cat "$COND_DIR/testing-patterns.md"
[ "$REVIEW" = 1 ] && [ -f "$COND_DIR/code-review.md" ] && cat "$COND_DIR/code-review.md"
[ "$REFACTORING" = 1 ] && [ -f "$COND_DIR/refactoring.md" ] && cat "$COND_DIR/refactoring.md"
[ "$SKILLS" = 1 ] && [ -f "$COND_DIR/tools-skills.md" ] && cat "$COND_DIR/tools-skills.md"

exit 0
```

- [ ] **Step 3: Make executable**

```bash
chmod +x ~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh
```

- [ ] **Step 4: Verify hook runs cleanly with no lockfile**

```bash
echo '{"prompt": "implement something"}' | ~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh
echo "Exit code: $?"
```

Expected: no output, exit code 0.

- [ ] **Step 5: Verify hook injects when lockfile present**

```bash
mkdir -p /tmp/test-ctx/.claude/core /tmp/test-ctx/.claude/conditional
echo "# Core Context" > /tmp/test-ctx/.claude/core/project-context.md
echo "# Testing Patterns" > /tmp/test-ctx/.claude/conditional/testing-patterns.md
touch /tmp/test-ctx/.claude/ctx.lock

cd /tmp/test-ctx && echo '{"prompt": "implement a new feature"}' \
  | ~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh
```

Expected output contains `[invariants injected: core design-principles testing-patterns refactoring tools-skills]` followed by `# Core Context` and `# Testing Patterns`.

- [ ] **Step 6: Clean up temp dir**

```bash
rm -rf /tmp/test-ctx
```

- [ ] **Step 7: Commit**

```bash
git -C ~/.claude add plugins/context-injector/hooks/user-prompt-submit.sh
git -C ~/.claude commit -m "feat: add context-injector plugin hook"
```

(If `~/.claude` is not a git repo, skip the commit — the file just needs to exist.)

---

## Task 2: Create `/ctx` global command

**Files:**
- Create: `~/.claude/commands/ctx.md`

- [ ] **Step 1: Write the command file**

Create `~/.claude/commands/ctx.md`:

```markdown
Toggle Context Injector mode on or off for the current project.

Check whether `.claude/ctx.lock` exists in `$PWD`:
- If it does NOT exist: run `touch .claude/ctx.lock` and respond with exactly: `[ctx: on]`
- If it DOES exist: run `rm .claude/ctx.lock` and respond with exactly: `[ctx: off]`

Do not explain. Do not ask for confirmation. Just toggle and report.
```

- [ ] **Step 2: Verify the file is in place**

```bash
cat ~/.claude/commands/ctx.md
```

Expected: the content above.

- [ ] **Step 3: Commit**

```bash
git -C ~/.claude add commands/ctx.md
git -C ~/.claude commit -m "feat: add /ctx global Context Injector toggle command"
```

(If `~/.claude` is not a git repo, skip.)

---

## Task 3: Migrate red-dragon

**Files:**
- Modify: `.claude/settings.json`
- Modify: `.gitignore`
- Delete: `.claude/classify-prompt.sh`

- [ ] **Step 1: Update settings.json hook command**

In `.claude/settings.json`, in the `UserPromptSubmit` block, replace:

```json
"command": ".claude/classify-prompt.sh"
```

with:

```json
"command": "~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh"
```

- [ ] **Step 2: Add ctx.lock to .gitignore**

Append to `.gitignore`:

```
.claude/ctx.lock
```

- [ ] **Step 3: Delete classify-prompt.sh**

```bash
rm /Users/asgupta/code/red-dragon/.claude/classify-prompt.sh
```

- [ ] **Step 4: Verify settings.json is valid JSON**

```bash
jq . /Users/asgupta/code/red-dragon/.claude/settings.json > /dev/null && echo "valid"
```

Expected: `valid`

- [ ] **Step 5: Smoke-test the hook in red-dragon context**

```bash
cd /Users/asgupta/code/red-dragon
touch .claude/ctx.lock
echo '{"prompt": "implement a new feature"}' \
  | ~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh | head -5
rm .claude/ctx.lock
```

Expected: first line is `[invariants injected: core design-principles testing-patterns refactoring tools-skills]`

- [ ] **Step 6: Commit**

```bash
cd /Users/asgupta/code/red-dragon
git add .claude/settings.json .gitignore
git rm .claude/classify-prompt.sh
git commit -m "feat: migrate to context-injector plugin, remove classify-prompt.sh"
```
