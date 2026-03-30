# Layered CLAUDE.md with Hook-Based Invariant Injection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split CLAUDE.md into always-on core (~7KB) and conditional invariants (~11KB), injected via hooks based on prompt classification.

**Architecture:** CLAUDE.md imports only core files. A SessionStart hook re-injects core after compaction. A UserPromptSubmit hook classifies prompts by keywords and injects only relevant conditional files.

**Tech Stack:** POSIX shell, Claude Code hooks (settings.json), markdown

**Spec:** `docs/superpowers/specs/2026-03-30-layered-claude-md-hooks-design.md`

---

### Task 1: Split tools.md into search and skills files

**Files:**
- Create: `.claude/core/tools-search.md`
- Create: `.claude/conditional/tools-skills.md`
- Delete: `.claude/tools.md` (after moving content)

- [ ] **Step 1: Create `.claude/core/` and `.claude/conditional/` directories**

```bash
mkdir -p .claude/core .claude/conditional
```

- [ ] **Step 2: Create `.claude/core/tools-search.md`**

Write the ast-grep and code-review-graph sections (lines 1-27 of current `.claude/tools.md`):

```markdown
## Code Search and Analysis Tools

### ast-grep (structural code search)

Use the `/ast-grep` skill for structural code searches instead of regex grep. ast-grep matches AST patterns and handles multi-line constructs, indentation variations, and nested expressions that regex misses.

**When to use ast-grep:**
- Searching for constructor/function call patterns (e.g., `FuncRef(name=$X)`, `DeclVar(name=$N, value_reg=$R)`)
- Finding all call sites of a specific function with certain argument shapes
- Migrating field types: finding all constructions that pass a specific field
- Any search where the pattern spans multiple lines or has variable whitespace

**When plain grep is sufficient:**
- Simple keyword/string searches (`SELF_PARAM_NAMES`, `def _handle_const`)
- Import statements
- Constant definitions

### code-review-graph (knowledge graph)

Use the code-review-graph MCP tools before scanning files manually for codebase understanding:

- `semantic_search_nodes_tool` — find classes, functions, or types by name or keyword
- `query_graph_tool` — explore relationships: `callers_of`, `callees_of`, `imports_of`, `children_of`, `tests_for`, `inheritors_of`, `file_summary`
- `get_impact_radius_tool` — understand blast radius before making changes
- `get_review_context_tool` — token-efficient review context for PRs

These save significant tokens by avoiding full codebase scans. Fall back to grep/glob/read only when the graph doesn't cover what you need.
```

- [ ] **Step 3: Create `.claude/conditional/tools-skills.md`**

Write the workflow skills/agents table (lines 29-42 of current `.claude/tools.md`):

```markdown
## Workflow Skills and Agents

Use these installed skills and agents at the right points in the workflow:

| Skill / Agent | Trigger | When to use |
|---|---|---|
| `/tdd` | Starting a feature or bug fix | Enforces red-green-refactor discipline with structured test-first loop |
| `/audit-asserts` | Periodic test quality sweeps | Scans test files for assertion-vs-name mismatches (custom skill in `.claude/skills/audit-asserts/`) |
| `/simplify` | After completing implementation | Reviews changed code for reuse, quality, and efficiency opportunities |
| `migration-planner` skill | During brainstorming for type migrations | Auto-triggers when replacing primitives with domain types; injects migration strategies |
| `claude-mem:smart-explore` | Understanding code structure | Token-optimized tree-sitter AST exploration; use instead of reading full files when you only need function signatures or class outlines |
| `claude-mem:mem-search` | Continuing work from prior sessions | Searches persistent cross-session memory for "how did we do X last time?" |
| `debugger` agent | Test failures or unexpected behavior | Systematic debugging with persistent state; use proactively before proposing fixes |
| `code-review` agents | After completing major features | Specialized reviewers: `security-auditor`, `contracts-reviewer`, `bug-hunter`, `test-coverage-reviewer` — dispatch via the Agent tool |
```

- [ ] **Step 4: Verify content equivalence**

```bash
cat .claude/core/tools-search.md .claude/conditional/tools-skills.md | wc -l
wc -l .claude/tools.md
# Line counts should be close (±1 for the split point)
```

- [ ] **Step 5: Commit**

```bash
git add .claude/core/tools-search.md .claude/conditional/tools-skills.md
git commit -m "Split tools.md into core/tools-search.md and conditional/tools-skills.md"
```

---

### Task 2: Move existing files into core/ and conditional/

**Files:**
- Move: `.claude/project-context.md` → `.claude/core/project-context.md`
- Move: `.claude/workflow.md` → `.claude/core/workflow.md`
- Move: `.claude/implementation.md` → `.claude/core/implementation.md`
- Move: `.claude/design-principles.md` → `.claude/conditional/design-principles.md`
- Move: `.claude/testing-patterns.md` → `.claude/conditional/testing-patterns.md`
- Move: `.claude/code-review.md` → `.claude/conditional/code-review.md`
- Move: `.claude/refactoring.md` → `.claude/conditional/refactoring.md`
- Delete: `.claude/tools.md` (split in Task 1)

- [ ] **Step 1: Move core files**

```bash
mv .claude/project-context.md .claude/core/project-context.md
mv .claude/workflow.md .claude/core/workflow.md
mv .claude/implementation.md .claude/core/implementation.md
```

- [ ] **Step 2: Move conditional files**

```bash
mv .claude/design-principles.md .claude/conditional/design-principles.md
mv .claude/testing-patterns.md .claude/conditional/testing-patterns.md
mv .claude/code-review.md .claude/conditional/code-review.md
mv .claude/refactoring.md .claude/conditional/refactoring.md
```

- [ ] **Step 3: Remove old tools.md**

```bash
rm .claude/tools.md
```

- [ ] **Step 4: Update CLAUDE.md to import from new paths**

```markdown
# RedDragon — Agent Instructions

#import .claude/core/project-context.md
#import .claude/core/workflow.md
#import .claude/core/implementation.md
#import .claude/core/tools-search.md
```

- [ ] **Step 5: Update .gitignore**

Replace the current `.claude/*.md` exceptions with the new paths:

```gitignore
# Claude Code
.claude/*
!.claude/skills/
!.claude/core/
!.claude/conditional/
!.claude/classify-prompt.sh
!.claude/settings.json
```

- [ ] **Step 6: Verify file structure**

```bash
find .claude/core .claude/conditional -name '*.md' | sort
# Expected:
# .claude/conditional/code-review.md
# .claude/conditional/design-principles.md
# .claude/conditional/refactoring.md
# .claude/conditional/testing-patterns.md
# .claude/conditional/tools-skills.md
# .claude/core/implementation.md
# .claude/core/project-context.md
# .claude/core/tools-search.md
# .claude/core/workflow.md
```

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md .gitignore .claude/core/ .claude/conditional/
git rm .claude/project-context.md .claude/workflow.md .claude/implementation.md .claude/design-principles.md .claude/testing-patterns.md .claude/code-review.md .claude/refactoring.md .claude/tools.md
git commit -m "Reorganize CLAUDE.md fragments into core/ and conditional/ directories"
```

---

### Task 3: Write the prompt classifier script

**Files:**
- Create: `.claude/classify-prompt.sh`

- [ ] **Step 1: Create the classifier script**

```bash
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
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x .claude/classify-prompt.sh
```

- [ ] **Step 3: Test the classifier locally**

Test with an implementation prompt:
```bash
echo '{"prompt": "implement the ContinuationName domain type"}' | .claude/classify-prompt.sh | head -3
# Expected: first lines of design-principles.md
```

Test with a question prompt:
```bash
echo '{"prompt": "what outstanding issues are there?"}' | .claude/classify-prompt.sh | wc -c
# Expected: 0 (no output)
```

Test with a review prompt:
```bash
echo '{"prompt": "review the latest PR changes"}' | .claude/classify-prompt.sh | head -3
# Expected: first lines of code-review.md
```

Test with a verify prompt:
```bash
echo '{"prompt": "run audit-asserts on the test files"}' | .claude/classify-prompt.sh | head -3
# Expected: first lines of testing-patterns.md
```

Test with a refactor prompt:
```bash
echo '{"prompt": "refactor the executor into smaller modules"}' | .claude/classify-prompt.sh | grep -c "^##"
# Expected: 3 or more (design-principles + refactoring + tools-skills headers)
```

- [ ] **Step 4: Commit**

```bash
git add .claude/classify-prompt.sh
git commit -m "Add prompt classifier script for conditional invariant injection"
```

---

### Task 4: Configure hooks in settings.json

**Files:**
- Create: `.claude/settings.json`

- [ ] **Step 1: Create settings.json with hooks**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "cat .claude/core/*.md"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/classify-prompt.sh"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Verify settings.json is valid JSON**

```bash
python3 -c "import json; json.load(open('.claude/settings.json')); print('valid')"
# Expected: valid
```

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "Add hook configuration for layered CLAUDE.md injection"
```

---

### Task 5: End-to-end verification and push

**Files:**
- None (verification only)

- [ ] **Step 1: Verify CLAUDE.md imports resolve**

```bash
cat CLAUDE.md
# Should show 4 #import lines pointing to .claude/core/*.md
```

- [ ] **Step 2: Verify core files exist and are readable**

```bash
cat .claude/core/*.md | wc -c
# Expected: ~7000 (approximate)
```

- [ ] **Step 3: Verify conditional files exist and are readable**

```bash
cat .claude/conditional/*.md | wc -c
# Expected: ~11000 (approximate)
```

- [ ] **Step 4: Verify classifier handles all categories**

```bash
echo '{"prompt": "add a new feature"}' | .claude/classify-prompt.sh | grep -c "^##"
echo '{"prompt": "write tests for the VM"}' | .claude/classify-prompt.sh | grep -c "^##"
echo '{"prompt": "refactor the registry"}' | .claude/classify-prompt.sh | grep -c "^##"
echo '{"prompt": "review this diff"}' | .claude/classify-prompt.sh | grep -c "^##"
echo '{"prompt": "run audit-asserts"}' | .claude/classify-prompt.sh | grep -c "^##"
echo '{"prompt": "what issues are open?"}' | .claude/classify-prompt.sh | wc -c
# Last one should be 0
```

- [ ] **Step 5: Verify git tracks all new files**

```bash
git status
# All new files in .claude/core/, .claude/conditional/, .claude/classify-prompt.sh,
# .claude/settings.json should be tracked. No untracked files.
```

- [ ] **Step 6: Run verification gate**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/ -x -q
```

Expected: all pass (no Python code changed, just markdown and shell).

- [ ] **Step 7: Push**

```bash
git push
```
