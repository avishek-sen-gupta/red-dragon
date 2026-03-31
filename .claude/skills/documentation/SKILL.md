---
name: documentation
description: Use when the user invokes /documentation or asks to update the RedDragon project docs. Updates README, ADRs, IR lowering gaps, VM/IR design docs, frontend design docs, and HTML presentations to reflect current codebase state.
---

# Documentation Update

Update all living RedDragon docs to reflect current codebase state. Do NOT modify files under `docs/superpowers/specs/` or `docs/superpowers/plans/` — those are immutable.

## Docs to Update

Work through these in order. For each: read the current doc, read the relevant source, then update only what has changed.

### 1. README.md (repo root)
- Supported languages list and count
- Feature capabilities (VM, type system, multi-file, MCP, TUI)
- Test count (run `poetry run python -m pytest tests/ --co -q 2>/dev/null | tail -3` to get current count)
- Any new frontends or major features since last update

### 2. `docs/architectural-design-decisions.md`
- Add a new timestamped ADR for any architectural change not yet recorded
- Check git log since the last ADR date for clues: `git log --oneline --since="<last ADR date>"`
- ADR format: `## YYYY-MM-DD — Title` followed by Context, Decision, Consequences

### 3. `docs/frontend-lowering-gaps.md`
- Reflects P0/P1/P2 gap counts per language
- Cross-reference open Beads issues: `bd list --priority=0,1 --status=open`
- Mark gaps as done where the corresponding issue is closed
- Add any newly discovered gaps from recent work

### 4. `docs/notes-on-vm-design.md`
- Covers VM execution model, heap layout, pointer semantics, opcode behaviour
- Update if new opcodes were added (`interpreter/ir.py`) or VM semantics changed (`interpreter/vm/`)
- Key areas: `LOAD_INDIRECT`, `ADDRESS_OF`, `NEW_ARRAY`, `CALL_METHOD`, `STORE_INDEX`

### 5. `docs/ir-reference.md`
- One entry per opcode with **domain-typed field tables** (`Register`, `VarName`, `FieldName`, `FuncName`, `BinopKind`/`UnopKind`, `CodeLabel`, `ContinuationName`)
- Add any opcodes present in `interpreter/instructions.py` that are missing
- Update descriptions where behaviour changed
- Source of truth: `interpreter/instructions.py` (dataclass field names and types)

### 6. `docs/type-system.md`
- `TypeExpr` ADT, coercion rules, overload resolution, type inference pipeline
- Also covers `TypedValue`, `TypeEnvironment`, `BinopCoercionStrategy`/`UnopCoercionStrategy`, `TypeConversionRules`
- Update if `interpreter/types/` changed — especially `type_expr.py`, `type_inference.py`, `coercion/`

### 7. `docs/linker-design.md`
- Multi-file linking, import resolution, two-phase compilation
- Update if `interpreter/project/` changed

### 8. `docs/notes-on-frontend-design.md`
- High-level frontend architecture, `BaseFrontend` contract, lowering patterns
- Update if `interpreter/frontends/base_frontend.py` or the lowering dispatch changed

### 9. `docs/frontend-design/<lang>.md` (per language)
- Only update files for languages that changed since last session
- Check: `git diff --name-only HEAD~10 | grep frontends/` to find recently touched frontends
- Each file covers: supported constructs, lowering strategy, known gaps, tree-sitter node types

### 10. `presentation/technical-presentation.html` and `presentation/overview-presentation.html`
- Update language count, feature list, architecture diagrams if major features shipped
- Keep existing structure and styling — only update content sections

## Rules

- **Read before writing.** Always read the current doc before editing.
- **Minimal diffs.** Only update sections where content is stale. Don't rewrite for style.
- **Source of truth is code.** Verify claims against `interpreter/` before writing them.
- **No new files.** Update existing docs; do not create new ones unless adding a new ADR entry.
- **Immutable:** Never touch `docs/superpowers/specs/` or `docs/superpowers/plans/`.

## Quick Source Lookup

| Doc | Source to read |
|-----|---------------|
| VM design | `interpreter/vm/vm.py`, `interpreter/vm/executor.py` |
| IR reference | `interpreter/instructions.py` (dataclass field names and types) |
| Type system | `interpreter/types/` |
| Linker | `interpreter/project/` |
| Frontend design | `interpreter/frontends/<lang>_frontend.py` |
| Lowering gaps | open Beads issues + `bd list --priority=0,1` |
| Test count | `poetry run python -m pytest tests/ --co -q 2>/dev/null \| tail -3` |
