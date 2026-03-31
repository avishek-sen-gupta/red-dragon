# Type Annotation Triage — Design Spec

**Date:** 2026-03-31
**Status:** Approved

## Goal

Achieve tight, correct type annotations across all of `interpreter/` and `mcp_server/` with two outputs:

1. Zero `Any` (except documented display boundaries) and `pyright standard` mode passing as a hard CI gate.
2. A filed backlog of domain-type migration and union-unification candidates discovered during annotation, linked to a single epic, each decided through async triage — not all primitives will become domain types.

Strong type signatures are the documentation. No docstrings are mandated.

## Phase Overview

### Phase 1 — Gate setup (one commit)

- Add `poetry run pyright interpreter/ mcp_server/` to the verification gate in `CLAUDE.md`
- Add `mcp_server/` to the `include` list in `pyrightconfig.json`
- Configure the `pre_triage` custom Beads status: `bd config set status.custom "pre_triage:frozen"`
- File the triage epic: `"Type annotation triage — domain type and union candidates"`
- `pyrightconfig.json` stays at `typeCheckingMode: "basic"` — per-file opt-in drives the upgrade

### Phase 2 — `Any` elimination, module by module

Work through modules in dependency order (leaf → root). Per module:

1. **Annotate** — replace every `Any`, add missing arg and return types, handle `Callable` signatures
2. **File pre_triage issues** — one per flagged primitive or union, linked to the epic, status `pre_triage`
3. **Add `# pyright: standard`** to the file header
4. **Commit** (annotation only — no logic changes)

If annotation exposes a latent bug: leave a `# type: ignore[rule]  # see <issue-id>` as a temporary bridge, file a separate Beads issue linked to the typing issue with full detail, fix in a follow-up commit under normal TDD workflow.

Module order:

```
interpreter/types/coercion/
interpreter/types/
interpreter/refs/
interpreter/ir.py, instructions.py, constants.py   (grouped — small files)
interpreter/handlers/_common.py
interpreter/handlers/*.py                           ← highest leverage: ctx: Any → HandlerContext
interpreter/vm/vm_types.py, trace_types.py          (grouped)
interpreter/vm/vm.py
interpreter/vm/builtins.py
interpreter/vm/executor.py
interpreter/frontends/*.py                          ← parallelizable (15 frontends)
interpreter/cobol/                                  ← ANTLR boundary gets # type: ignore[...] with comment
interpreter/llm/                                    ← fix existing # type: ignore[misc] at root cause
interpreter/project/
interpreter/run.py
mcp_server/                                         ← fold in here (7 files, 1 Any)
```

Commit granularity: one commit per file for large modules (`executor.py`, `vm.py`, `run.py`, large frontends); small files grouped into one commit.

### Phase 3 — Gate upgrade (one commit)

Once all files carry `# pyright: standard`:

- Change `pyrightconfig.json` to `typeCheckingMode: "standard"`
- Remove all per-file `# pyright: standard` comments (now redundant)
- Fix any remaining errors surfaced by the full-codebase pass
- The gate permanently enforces `standard` from this point

## `Any` Categorization

Every `Any` is resolved to one of five outcomes:

| Category | Action |
|---|---|
| Concrete type not written | Replace with the concrete type directly |
| Primitive (may or may not need a domain type) | Annotate with the primitive (`str`, `int`, etc.); file `pre_triage` Beads issue |
| Union / heterogeneous | Annotate with explicit `Union[A, B, ...]` as a signal; file `pre_triage` Beads issue |
| Callable with unknown signature | Replace with concrete `Callable[[ArgType], RetType]`; no new Protocol classes expected |
| True display boundary | Keep `Any`; add `# Any: display boundary` comment |

`pre_triage` issues are not automatically acted on. Each is triaged asynchronously: `bd list --status pre_triage` is the queue. An issue is promoted to `open` only when action is agreed; closed with `--reason "no action needed"` otherwise.

## Triage Epic

Before the annotation pass begins, one Beads epic is filed:

> **"Type annotation triage — domain type and union candidates"**

All `pre_triage` issues are linked to this epic. `strict` mode (Phase B) is not scheduled; it will be revisited after the triage epic is substantially resolved.

## Highest-Leverage Change

`ctx: Any → HandlerContext` in `interpreter/handlers/` (33 occurrences). `HandlerContext` already exists at `interpreter/vm/executor.py:84` — no new infrastructure required. This single substitution is expected to resolve the majority of the 742 `reportArgumentType` pyright errors.

## Constraints

- **`# type: ignore`**: permitted only at third-party library boundaries lacking stubs (e.g., ANTLR parse tree, `litellm`). Must include a comment explaining why. Never on internal code — fix the root cause instead.
- **`from __future__ import annotations`**: add only where a forward reference or circular import actually requires it. Not added speculatively.
- **Bug fixes**: never mixed into an annotation commit. Separate commit, separate Beads issue linked to the typing issue that exposed the bug, TDD workflow applies.
- **`tests/`**: excluded from the pyright gate. `pyrightconfig.json` includes only `interpreter/` and `mcp_server/`.
- **No new Protocol classes**: existing strategy Protocols are correct; `Callable[[A], B]` suffices for all remaining cases.
- **`strict` mode**: no timeline. Revisit after triage epic is mostly resolved.

## Per-file Pragma Mechanism

`pyrightconfig.json` stays at `basic` throughout Phase 2. Each file gets `# pyright: standard` added at the top when its module pass is complete. This is the measurable signal of progress:

```bash
grep -rn "# pyright: standard" interpreter/ mcp_server/ | wc -l
```

Phase 3 upgrades `pyrightconfig.json` to `standard` and strips all per-file comments.

## Testing Approach

The 13,235-test suite is the correctness safety net. No new pytest tests are required for annotation-only changes.

The primary test is the pyright gate: `poetry run pyright interpreter/ mcp_server/` must pass on every commit.

If `Any` elimination exposes a latent bug, that gets a test under normal TDD workflow — it is a bug fix, not an annotation change.

## Current State (baseline)

- Pyright mode: `basic`
- Pyright errors: 1,042 (`reportArgumentType`: 742, `reportAttributeAccessIssue`: 105, `reportUndefinedVariable`: 104, `reportReturnType`: 59, other: 32)
- Functions total: 2,473
- Missing return annotations: 262 (10%)
- Missing argument annotations: 1,109 (44%)
- `Any` usages: 283 (highest concentration: `handlers/` 38, `cobol/` 34, `vm/` 15)
- `ctx: Any` occurrences: 33
- Existing `# type: ignore`: 1 (`llm_frontend.py:432` — internal control flow, must be fixed)
- `mcp_server/`: 7 files, 1 `Any`
