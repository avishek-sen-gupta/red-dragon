# Layered CLAUDE.md with Hook-Based Invariant Injection

**Date:** 2026-03-30
**Status:** Approved

## Problem

CLAUDE.md instructions suffer from two issues:
1. **Compaction amnesia** — long sessions lose instructions when context is compressed
2. **Irrelevant noise** — all ~20KB of instructions load into every interaction, even for simple questions that need none of the TDD, refactoring, or review rules

## Decision

Three-layer system separating always-on context from conditional invariants, enforced via hooks.

## Architecture

### Layer 1 — CLAUDE.md (always loaded)

Root `CLAUDE.md` imports only the always-on core files (~7KB). These provide project context, workflow rules, and search tool guidance that are relevant regardless of task type.

### Layer 2 — SessionStart hook (compaction resilience)

A `SessionStart` hook with `compact` matcher re-injects the core files after context compaction, ensuring critical instructions survive long sessions.

### Layer 3 — UserPromptSubmit hook (contextual injection)

A shell script classifier reads the user prompt from stdin, matches keywords case-insensitively, and outputs only the relevant conditional instruction files. Questions get nothing extra. Implementation prompts get design principles + TDD + refactoring rules. Multiple categories can fire per prompt.

## File Layout

```
CLAUDE.md                          # title + #import of always-on core only
.claude/
├── core/                          # always-on (~7KB)
│   ├── project-context.md         # project setup, task tracking, dependencies (~1.7KB)
│   ├── workflow.md                # phases, verification gate, commits, docs (~3.8KB)
│   ├── implementation.md          # guidelines, interaction style, introspection, talisman (~1.8KB)
│   └── tools-search.md           # ast-grep guidance, code-review-graph tools (~1.5KB)
├── conditional/                   # injected by classifier (~11KB total, only relevant subset per prompt)
│   ├── design-principles.md      # design principles, programming patterns (~2.8KB)
│   ├── testing-patterns.md       # TDD, assertions, xfail, integration tests (~1.9KB)
│   ├── code-review.md            # self-review checklist, review rubric (~1.6KB)
│   ├── refactoring.md            # type propagation migration principles (~3.7KB)
│   └── tools-skills.md           # workflow skills/agents table (~1.4KB)
├── classify-prompt.sh             # keyword classifier (POSIX shell, reads stdin)
└── settings.json                  # hooks config (committed, repo-level)
```

## CLAUDE.md Content

```markdown
# RedDragon — Agent Instructions

#import .claude/core/project-context.md
#import .claude/core/workflow.md
#import .claude/core/implementation.md
#import .claude/core/tools-search.md
```

## Hook Configuration (.claude/settings.json)

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "compact",
        "command": "cat .claude/core/*.md"
      }
    ],
    "UserPromptSubmit": [
      {
        "command": ".claude/classify-prompt.sh"
      }
    ]
  }
}
```

## Classifier Categories

The classifier reads the user prompt from stdin and pattern-matches keywords (case-insensitive, word boundaries). Multiple categories can match per prompt. If nothing matches, no output.

| Category | Trigger keywords | Files injected |
|---|---|---|
| **implement** | `implement`, `add`, `build`, `create`, `fix`, `feature`, `bug`, `write`, `emit`, `lower`, `migrate`, `introduce`, `wire`, `hook`, `support`, `handle`, `extend`, `port`, `close` | design-principles, testing-patterns, refactoring, tools-skills |
| **test** | `test`, `tdd`, `assert`, `coverage`, `xfail`, `failing`, `passes`, `red-green`, `fixture`, `integration test`, `unit test` | testing-patterns |
| **refactor** | `refactor`, `rename`, `extract`, `move`, `split`, `merge`, `simplify`, `clean`, `reorganize`, `restructure`, `consolidate`, `decompose`, `inline`, `deduplicate` | design-principles, refactoring, tools-skills |
| **review** | `review`, `pr`, `diff`, `check`, `feedback`, `critique`, `approve` | code-review |
| **verify** | `verify`, `audit`, `scan`, `lint`, `sweep`, `audit-asserts`, `validate`, `ensure`, `confirm`, `gate`, `black`, `lint-imports` | testing-patterns, tools-skills |

## File Content Split

### Always-on core files

**core/project-context.md** — current `.claude/project-context.md` content (project setup, task tracking with Beads, external dependencies).

**core/workflow.md** — current `.claude/workflow.md` content (phases, complexity classification, verification gate, commits and state, documentation rules).

**core/implementation.md** — current `.claude/implementation.md` content (implementation guidelines, interaction style, python introspection, talisman).

**core/tools-search.md** — ast-grep guidance (when to use, when plain grep is sufficient) and code-review-graph MCP tools (semantic_search, query_graph, get_impact_radius, get_review_context). Extracted from current `.claude/tools.md`.

### Conditional files

**conditional/design-principles.md** — current `.claude/design-principles.md` content (design principles + programming patterns: code style, types and values, architecture).

**conditional/testing-patterns.md** — current `.claude/testing-patterns.md` content (TDD, assertion review, unit vs integration, fixtures, no mocking, xfail, both test types).

**conditional/code-review.md** — current `.claude/code-review.md` content (self-review checklist, requested review rubric with severity levels).

**conditional/refactoring.md** — current `.claude/refactoring.md` content (type propagation migration principles).

**conditional/tools-skills.md** — workflow skills/agents table extracted from current `.claude/tools.md` (`/tdd`, `/audit-asserts`, `/simplify`, `migration-planner`, `claude-mem:smart-explore`, `claude-mem:mem-search`, `debugger`, `code-review` agents).

## Classifier Script Design

`.claude/classify-prompt.sh` is a POSIX shell script:

1. Read prompt from stdin into a variable
2. Lowercase the text
3. Match keyword patterns (grep -qiw or case statement)
4. Track which categories matched (avoiding duplicate file output)
5. Cat the unique set of matching conditional files to stdout
6. Exit 0 always (hook failures block the prompt)

The script must be fast (no subprocess spawning beyond grep), deterministic, and never fail — a classification miss just means fewer instructions injected, which is strictly better than the current "everything always" approach.

## Migration Path

1. Split current `.claude/tools.md` into `core/tools-search.md` and `conditional/tools-skills.md`
2. Move existing `.claude/*.md` files into `core/` and `conditional/` subdirectories
3. Write `classify-prompt.sh`
4. Write `.claude/settings.json` with hook config
5. Update root `CLAUDE.md` to import only core files
6. Update `.gitignore` to track the new paths
7. Test each category by sending representative prompts and verifying injection
