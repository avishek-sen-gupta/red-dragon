# Context Injector Plugin Design

**Date:** 2026-04-01
**Status:** Approved

## Summary

A reusable Claude Code plugin that provides a stateful context injection toggle. When on, every prompt automatically receives core context plus classified conditional invariants injected into the conversation. Toggled on/off via the `/ctx` slash command.

Replaces the project-local `classify-prompt.sh` + `@@wf` sentinel mechanism.

---

## Plugin Structure

```
~/.claude/plugins/context-injector/
  hooks/
    user-prompt-submit.sh     ← UserPromptSubmit hook: inject context when mode is on
```

`/ctx` is a global command at `~/.claude/commands/ctx.md` (available in all projects, no per-project wiring).

---

## State

A lockfile at `$PWD/.claude/ctx.lock` represents mode state:
- **Present** → context injection on
- **Absent** → context injection off

The lockfile is project-scoped (via `$PWD`) so each project has independent state.

---

## Behaviour

### `/ctx` command (toggle)

- Lockfile absent → `touch $PWD/.claude/ctx.lock`, report `[ctx: on]`
- Lockfile present → `rm $PWD/.claude/ctx.lock`, report `[ctx: off]`

### `user-prompt-submit.sh` hook

- Lockfile absent → exit 0, no injection
- Lockfile present →
  1. Cat `$PWD/.claude/core/*.md` if directory exists (always injected when mode is on)
  2. Classify prompt via keyword matching, cat matching `$PWD/.claude/conditional/*.md` files
  3. Emit `[invariants injected: ...]` summary header

Missing directories (`core/`, `conditional/`) are skipped cleanly — no error.

### Classification logic (unchanged from classify-prompt.sh)

| Keywords matched | Invariants injected |
|---|---|
| implement, add, build, create, fix, feature, bug, write, emit, lower, migrate, introduce, wire, hook, support, handle, extend, port, close | design-principles, testing-patterns, refactoring, tools-skills |
| test, tdd, assert, coverage, xfail, failing, passes, red-green, fixture | testing-patterns |
| integration test, unit test | testing-patterns |
| refactor, rename, extract, move, split, merge, simplify, clean, reorganize, restructure, consolidate, decompose, inline, deduplicate | design-principles, refactoring, tools-skills |
| review, pr, diff, check, feedback, critique, approve | code-review |
| verify, audit, scan, lint, sweep, validate, ensure, confirm, gate, black, lint-imports | testing-patterns, tools-skills |

---

## Project Convention

Each project that uses this plugin provides:

```
.claude/
  core/           ← always injected when ctx is on (e.g. project-context.md, workflow.md)
  conditional/    ← injected based on keyword classification
    design-principles.md
    testing-patterns.md
    code-review.md
    refactoring.md
    tools-skills.md
  ctx.lock        ← created/deleted by /ctx command (gitignored)
```

`ctx.lock` should be added to `.gitignore`.

---

## Wiring (per-project, manual)

Add to `.claude/settings.json`:

```json
"UserPromptSubmit": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh"
      }
    ]
  }
]
```

The `/ctx` command requires no per-project wiring — it is globally available via `~/.claude/commands/ctx.md`.

---

## red-dragon Migration

1. In `.claude/settings.json`, replace `".claude/classify-prompt.sh"` with `"~/.claude/plugins/context-injector/hooks/user-prompt-submit.sh"` in the `UserPromptSubmit` hook
2. Delete `.claude/classify-prompt.sh`
3. Add `.claude/ctx.lock` to `.gitignore`
4. `conditional/` and `core/` directories stay untouched

---

## What Is Removed

- `@@wf` sentinel — gone entirely. No per-prompt opt-in; use `/ctx` to toggle mode instead.
- Per-prompt injection without mode-on — not supported. Mode on/off is the only control.
