# IRInstruction Elimination — Layer 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all non-frontend consumers from `opcode==` comparisons and `IRInstruction(` construction to `isinstance` checks and typed instruction construction.

**Architecture:** Replace `inst.opcode == Opcode.X` with `isinstance(inst, X)`. Replace `IRInstruction(opcode=Opcode.X, ...)` with `X(...)`. Replace `inst.operands[N]` with typed field access. Use `map_registers()`/`map_labels()` in linker.

**Tech Stack:** Python 3.13+, pytest, Poetry

**Design doc:** `docs/design/eliminate-irinstruction-plan.md`

**Survey results:** 0 to_typed(), 6 operands[], 41 opcode==, 116 IRInstruction( across 16 files.

---

## Task 1: Layer 3a — Handlers + executor (4 sites)

**Issue:** red-dragon-ufnx
**Files:**
- Modify: `interpreter/handlers/arithmetic.py` (3 operands[] accesses)
- Modify: `interpreter/handlers/variables.py` (1 operands[] access)

The executor dispatch and most handler code are already using the typed API (0 markers in executor.py, 0 to_typed calls). Only 4 `operands[]` accesses remain.

- [ ] **Step 1: Find and fix the 4 operands[] accesses in handlers**

Read `interpreter/handlers/arithmetic.py` and `interpreter/handlers/variables.py`. For each `inst.operands[N]` access, replace with the corresponding typed field (e.g., `inst.operands[1]` on a Binop → `inst.left`). The inst should already be a typed instruction from `to_typed()`.

- [ ] **Step 2: Run handler tests**

Run: `poetry run python -m pytest tests/ -x -q`

- [ ] **Step 3: Verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd update ufnx --claim && bd backup
git add interpreter/handlers/
git commit -m "Layer 3a: remove last operands[] accesses in handlers"
bd close ufnx --reason "All handler operands[] accesses replaced with typed fields"
```

---

## Task 2: Layer 3c — CFG + dataflow + interprocedural (20 sites)

**Issue:** red-dragon-3h0y
**Files:**
- Modify: `interpreter/cfg.py` (8 opcode== comparisons)
- Modify: `interpreter/dataflow.py` (1 opcode== comparison)
- Modify: `interpreter/interprocedural/summaries.py` (8 opcode== comparisons)
- Modify: `interpreter/interprocedural/call_graph.py` (2 opcode== comparisons)
- Modify: `interpreter/interprocedural/propagation.py` (1 opcode== comparison)

- [ ] **Step 1: Replace opcode comparisons with isinstance checks**

Pattern: `inst.opcode == Opcode.LABEL` → `isinstance(inst, Label_)`
Pattern: `inst.opcode == Opcode.BRANCH` → `isinstance(inst, Branch)`
Pattern: `inst.opcode in (Opcode.X, Opcode.Y)` → `isinstance(inst, (X, Y))`

Add imports for the typed instruction classes at the top of each file.

- [ ] **Step 2: Run tests**

Run: `poetry run python -m pytest tests/ -x -q`

- [ ] **Step 3: Verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd update 3h0y --claim && bd backup
git add interpreter/cfg.py interpreter/dataflow.py interpreter/interprocedural/
git commit -m "Layer 3c: opcode== → isinstance in CFG, dataflow, interprocedural"
bd close 3h0y --reason "All opcode comparisons replaced with isinstance checks"
```

---

## Task 3: Layer 3d — Project infrastructure / linker (8 sites)

**Issue:** red-dragon-30vm
**Files:**
- Modify: `interpreter/project/linker.py` (5 opcode==, 2 IRInstruction constructions)
- Modify: `interpreter/project/compiler.py` (1 opcode==)

- [ ] **Step 1: Read linker.py and understand the register rebasing logic**

The linker currently iterates operands to rebase registers. Replace with `inst.map_registers(lambda r: r.rebase(offset))` and `inst.map_labels(lambda l: l.namespace(prefix))`.

- [ ] **Step 2: Replace opcode comparisons with isinstance checks**

- [ ] **Step 3: Replace IRInstruction constructions with typed instructions**

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/ -x -q`

- [ ] **Step 5: Verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd update 30vm --claim && bd backup
git add interpreter/project/
git commit -m "Layer 3d: linker uses map_registers/map_labels, isinstance checks"
bd close 30vm --reason "Linker migrated to map_registers/map_labels and typed instructions"
```

---

## Task 4: Layer 3e — LLM + registry + run.py (22 sites, excluding COBOL)

**Issue:** red-dragon-2la9
**Files:**
- Modify: `interpreter/llm/llm_frontend.py` (2 operands[], 3 opcode==, 2 IRInstruction)
- Modify: `interpreter/llm/chunked_llm_frontend.py` (1 opcode==, 4 IRInstruction)
- Modify: `interpreter/registry.py` (3 opcode==)
- Modify: `interpreter/run.py` (6 opcode==)
- Modify: `interpreter/cobol/emit_context.py` (2 opcode==, 1 IRInstruction)
- Modify: `interpreter/cobol/ir_encoders.py` (106 IRInstruction constructions)

The COBOL ir_encoders.py dominates this task (106 IRInstruction constructions). Each `IRInstruction(opcode=Opcode.X, ...)` becomes `X(...)` with named fields.

- [ ] **Step 1: Migrate LLM frontend files**

In `llm_frontend.py`: replace `inst.operands[0] = x` mutation with `instructions[i] = dataclasses.replace(inst, value=x)` (for Const instructions). Replace opcode comparisons with isinstance. Replace IRInstruction constructions with typed instructions.

In `chunked_llm_frontend.py`: same pattern.

- [ ] **Step 2: Migrate registry.py and run.py**

Replace opcode comparisons with isinstance checks. Add typed instruction imports.

- [ ] **Step 3: Migrate cobol/emit_context.py**

Replace 2 opcode comparisons and 1 IRInstruction construction.

- [ ] **Step 4: Migrate cobol/ir_encoders.py (106 sites)**

This is the largest sub-task. Each `IRInstruction(opcode=Opcode.X, result_reg=..., operands=[...])` becomes the corresponding typed instruction with named fields.

Pattern:
```python
# Before
IRInstruction(opcode=Opcode.CONST, result_reg=reg, operands=["42"])
# After
Const(result_reg=reg, value="42")

# Before
IRInstruction(opcode=Opcode.CALL_FUNCTION, result_reg=reg, operands=["func", arg1, arg2])
# After
CallFunction(result_reg=reg, func_name="func", args=(arg1, arg2))
```

Note: ir_encoders.py places literal ints in operands (tracked in red-dragon-pyww). For now, keep them as-is in the typed instruction fields — the types accept Any at runtime even though annotated as Register.

- [ ] **Step 5: Run tests**

Run: `poetry run python -m pytest tests/ -x -q`

- [ ] **Step 6: Verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd update 2la9 --claim && bd backup
git add interpreter/llm/ interpreter/registry.py interpreter/run.py interpreter/cobol/
git commit -m "Layer 3e: migrate LLM, registry, run, COBOL to typed instructions"
bd close 2la9 --reason "All non-frontend consumers migrated to typed instructions"
```

---

## Task 5: Layer 3b — Type inference (verify clean)

**Issue:** red-dragon-x37k

The survey found 0 markers in `interpreter/types/type_inference.py`. Verify this is genuinely clean and close the issue.

- [ ] **Step 1: Verify type_inference.py has no IRInstruction/Opcode usage**

Grep for `IRInstruction`, `Opcode`, `to_typed`, `operands[` in `interpreter/types/type_inference.py`. If clean, the migration was already done or never needed.

- [ ] **Step 2: Check for `list[IRInstruction]` type annotations that should be `list[Instruction]`**

- [ ] **Step 3: Check for `dict[str, TypeExpr]` that should be `dict[Register, TypeExpr]`**

- [ ] **Step 4: Make any needed annotation changes, run tests, commit if changes made**

```bash
bd update x37k --claim && bd backup
# If changes needed:
git add interpreter/types/type_inference.py
git commit -m "Layer 3b: type inference annotations updated"
bd close x37k --reason "Type inference already uses typed instructions"
```
