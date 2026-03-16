# LOAD_INDIRECT / STORE_INDIRECT Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the magic `"*"` field convention in LOAD_FIELD/STORE_FIELD with dedicated LOAD_INDIRECT/STORE_INDIRECT opcodes for pointer dereference.

**Architecture:** Add two new opcodes and VM handlers, migrate 3 frontends (C, Rust, C#) and their tests, then remove the `"*"` special cases from LOAD_FIELD/STORE_FIELD. Clean break — no backward-compatible fallback.

**Tech Stack:** Python 3.13+, pytest

**Spec:** `docs/superpowers/specs/2026-03-16-load-store-indirect-design.md`

---

## File Structure

| File | Responsibility | Change |
|------|---------------|--------|
| `interpreter/ir.py` | IR opcode definitions | Add `LOAD_INDIRECT`, `STORE_INDIRECT` |
| `interpreter/executor.py` | VM instruction execution | Add handlers, remove `"*"` from LOAD_FIELD/STORE_FIELD |
| `interpreter/type_inference.py` | Static type inference | Add dispatch entries |
| `interpreter/dataflow.py` | Def-use analysis | Add to value-producers and use extraction |
| `interpreter/frontends/c/expressions.py` | C pointer dereference | Migrate 2 sites |
| `interpreter/frontends/rust/expressions.py` | Rust dereference | Migrate 2 sites |
| `interpreter/frontends/csharp/expressions.py` | C# byref params | Migrate 2 sites |
| `tests/unit/test_pointer_aliasing.py` | VM pointer tests | Migrate IR construction |
| `tests/unit/test_heap_writes_typed.py` | VM heap write tests | Migrate IR construction |
| `tests/unit/test_c_frontend.py` | C frontend IR tests | Update assertions |
| `tests/unit/test_rust_frontend.py` | Rust frontend IR tests | Update assertions |
| `tests/unit/test_csharp_frontend.py` | C# frontend IR tests | Update assertions |
| `docs/ir-reference.md` | IR documentation | Document new opcodes |
| `docs/frontend-design/c.md` | C frontend docs | Update references |
| `docs/frontend-design/cpp.md` | C++ frontend docs | Update reference |
| `docs/notes-on-vm-design.md` | VM design notes | Update references |

---

## Chunk 1: Opcodes, VM Handlers, and Infrastructure

### Task 1: Add opcodes and VM handlers

**Files:**
- Modify: `interpreter/ir.py:44-45`
- Modify: `interpreter/executor.py`

- [ ] **Step 1: Add opcodes to the enum**

In `interpreter/ir.py`, add after `ADDRESS_OF = "ADDRESS_OF"` (line 45):

```python
    LOAD_INDIRECT = "LOAD_INDIRECT"
    STORE_INDIRECT = "STORE_INDIRECT"
```

- [ ] **Step 2: Add `_handle_load_indirect` to executor.py**

Add after the `_handle_address_of` function (around line 311):

```python
def _handle_load_indirect(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    """LOAD_INDIRECT %ptr: read through a Pointer (dereference)."""
    obj_val = _resolve_reg(vm, inst.operands[0])
    # Pointer dereference: read from heap[base].fields[offset]
    if isinstance(obj_val, Pointer) and obj_val.base in vm.heap:
        heap_obj = vm.heap[obj_val.base]
        tv = heap_obj.fields.get(str(obj_val.offset))
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: tv},
                reasoning=f"load *{obj_val} = {tv!r}",
            )
        )
    if isinstance(obj_val, Pointer) and obj_val.base not in vm.heap:
        sym = vm.fresh_symbolic(hint=f"*{obj_val}")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"load *{obj_val} (not on heap) → {sym.name}",
            )
        )
    # Function pointer dereference is identity: (*fp)(args) == fp(args)
    if isinstance(obj_val, BoundFuncRef):
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: typed_from_runtime(obj_val)},
                reasoning=f"deref {obj_val} → {obj_val} (function pointer identity)",
            )
        )
    # Fallback: symbolic
    sym = vm.fresh_symbolic(hint=f"*{_symbolic_name(obj_val)}")
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: typed(sym, UNKNOWN)},
            reasoning=f"load_indirect on non-pointer {obj_val!r} → {sym.name}",
        )
    )
```

- [ ] **Step 3: Add `_handle_store_indirect` to executor.py**

Add after `_handle_load_indirect`:

```python
def _handle_store_indirect(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    """STORE_INDIRECT %ptr %val: write through a Pointer (dereference)."""
    obj_val = _resolve_reg(vm, inst.operands[0])
    val = _resolve_reg(vm, inst.operands[1])
    if isinstance(obj_val, Pointer):
        target_field = str(obj_val.offset)
        return ExecutionResult.success(
            StateUpdate(
                heap_writes=[
                    HeapWrite(
                        obj_addr=obj_val.base,
                        field=target_field,
                        value=typed_from_runtime(val),
                    )
                ],
                reasoning=f"store *{obj_val} = {val!r}",
            )
        )
    obj_desc = _symbolic_name(obj_val)
    logger.debug("store_indirect on non-pointer %s", obj_desc)
    return ExecutionResult.success(
        StateUpdate(
            reasoning=f"store_indirect on {obj_desc} = {val!r} (non-pointer, no-op)",
        )
    )
```

- [ ] **Step 4: Register handlers in the dispatch dict**

In `executor.py`, in the `_HANDLERS` dict (around line 1500), add:

```python
        Opcode.LOAD_INDIRECT: _handle_load_indirect,
        Opcode.STORE_INDIRECT: _handle_store_indirect,
```

- [ ] **Step 5: Run existing tests to verify no regression**

Run: `poetry run python -m pytest tests/unit/test_pointer_aliasing.py tests/unit/test_heap_writes_typed.py -v --tb=short -q`
Expected: All existing tests PASS (new opcodes exist but aren't used yet)

- [ ] **Step 6: Commit**

```bash
git add interpreter/ir.py interpreter/executor.py
git commit -m "Add LOAD_INDIRECT/STORE_INDIRECT opcodes and VM handlers"
```

---

### Task 2: Update type_inference.py and dataflow.py

**Files:**
- Modify: `interpreter/type_inference.py:864-865`
- Modify: `interpreter/dataflow.py:17-32, 134-137`

- [ ] **Step 1: Add type inference dispatch entries**

In `interpreter/type_inference.py`, add a `_infer_load_indirect` function:

```python
def _infer_load_indirect(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    """LOAD_INDIRECT produces UNKNOWN — no field-type lookup for dereferences."""
    if inst.result_reg:
        ctx.register_types[inst.result_reg] = UNKNOWN
```

Add a `_infer_store_indirect` function:

```python
def _infer_store_indirect(
    inst: IRInstruction,
    ctx: _InferenceContext,
    type_resolver: TypeResolver,
) -> None:
    """STORE_INDIRECT — no type inference side effects."""
    pass
```

Add to the `_INFERENCE_HANDLERS` dict:

```python
    Opcode.LOAD_INDIRECT: _infer_load_indirect,
    Opcode.STORE_INDIRECT: _infer_store_indirect,
```

- [ ] **Step 2: Add LOAD_INDIRECT to dataflow value producers**

In `interpreter/dataflow.py`, add `Opcode.LOAD_INDIRECT` to `_VALUE_PRODUCERS` (after `Opcode.LOAD_FIELD`):

```python
        Opcode.LOAD_INDIRECT,
```

- [ ] **Step 3: Add def/use extraction for both opcodes**

In `interpreter/dataflow.py`, in the `_extract_uses` function (around line 134), add after the `STORE_FIELD` entry:

```python
    if op == Opcode.LOAD_INDIRECT and len(operands) >= 1:
        return [operands[0]]
    if op == Opcode.STORE_INDIRECT and len(operands) >= 2:
        return [operands[0], operands[1]]
```

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/unit/test_type_inference.py tests/unit/test_dataflow.py -v --tb=short -q`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/type_inference.py interpreter/dataflow.py
git commit -m "Add LOAD_INDIRECT/STORE_INDIRECT to type inference and dataflow"
```

---

### Task 3: Migrate test_pointer_aliasing.py and test_heap_writes_typed.py

**Files:**
- Modify: `tests/unit/test_pointer_aliasing.py`
- Modify: `tests/unit/test_heap_writes_typed.py`

- [ ] **Step 1: Update test_pointer_aliasing.py**

Replace all IR construction sites that use `LOAD_FIELD ... "*"` / `STORE_FIELD ... "*"` with `LOAD_INDIRECT` / `STORE_INDIRECT`:

- Line 189: `_make_inst(Opcode.STORE_FIELD, operands=["%ptr", "*", "%99"])` → `_make_inst(Opcode.STORE_INDIRECT, operands=["%ptr", "%99"])`
- Line 217: `_make_inst(Opcode.LOAD_FIELD, result_reg="%val", operands=["%ptr", "*"])` → `_make_inst(Opcode.LOAD_INDIRECT, result_reg="%val", operands=["%ptr"])`
- Line 230: `_make_inst(Opcode.STORE_FIELD, operands=["%ptr", "*", "%99"])` → `_make_inst(Opcode.STORE_INDIRECT, operands=["%ptr", "%99"])`
- Line 318: `Opcode.LOAD_FIELD, result_reg="%val", operands=["%ptr1", "*"]` → `Opcode.LOAD_INDIRECT, result_reg="%val", operands=["%ptr1"]`
- Line 430: `Opcode.LOAD_FIELD, result_reg="%inner", operands=["%pp", "*"]` → `Opcode.LOAD_INDIRECT, result_reg="%inner", operands=["%pp"]`
- Line 438: `Opcode.LOAD_FIELD, result_reg="%val", operands=["%inner", "*"]` → `Opcode.LOAD_INDIRECT, result_reg="%val", operands=["%inner"]`

Update comments at lines 7, 186, 201 to reference LOAD_INDIRECT/STORE_INDIRECT instead of `LOAD_FIELD/STORE_FIELD with "*"`.

- [ ] **Step 2: Update test_heap_writes_typed.py**

- Line 59: `IRInstruction(opcode=Opcode.STORE_FIELD, operands=["%0", "*", "%1"])` → `IRInstruction(opcode=Opcode.STORE_INDIRECT, operands=["%0", "%1"])`

- [ ] **Step 3: Run tests**

Run: `poetry run python -m pytest tests/unit/test_pointer_aliasing.py tests/unit/test_heap_writes_typed.py -v --tb=short`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_pointer_aliasing.py tests/unit/test_heap_writes_typed.py
git commit -m "Migrate pointer aliasing and heap write tests to LOAD_INDIRECT/STORE_INDIRECT"
```

---

## Chunk 2: Frontend Migration and Cleanup

### Task 4: Migrate C frontend

**Files:**
- Modify: `interpreter/frontends/c/expressions.py`
- Modify: `tests/unit/test_c_frontend.py`

- [ ] **Step 1: Migrate C dereference read**

In `interpreter/frontends/c/expressions.py`, in `lower_pointer_expr` (around line 163-171), replace:

```python
    # Dereference: *ptr -> LOAD_FIELD ptr, "*"
    inner_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[inner_reg, "*"],
        node=node,
    )
    return reg
```

With:

```python
    # Dereference: *ptr -> LOAD_INDIRECT ptr
    inner_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_INDIRECT,
        result_reg=reg,
        operands=[inner_reg],
        node=node,
    )
    return reg
```

- [ ] **Step 2: Migrate C dereference write**

In `lower_c_store_target` (around line 91-101), replace:

```python
    elif target.type == CNodeType.POINTER_EXPRESSION:
        # *ptr = val -> lower_expr(ptr_operand) -> STORE_FIELD ptr_reg, "*", val_reg
        operand_node = target.child_by_field_name("argument")
        if operand_node is None:
            operand_node = next((c for c in target.children if c.is_named), None)
        ptr_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
        ctx.emit(
            Opcode.STORE_FIELD,
            operands=[ptr_reg, "*", val_reg],
            node=parent_node,
        )
```

With:

```python
    elif target.type == CNodeType.POINTER_EXPRESSION:
        # *ptr = val -> lower_expr(ptr_operand) -> STORE_INDIRECT ptr_reg, val_reg
        operand_node = target.child_by_field_name("argument")
        if operand_node is None:
            operand_node = next((c for c in target.children if c.is_named), None)
        ptr_reg = ctx.lower_expr(operand_node) if operand_node else ctx.fresh_reg()
        ctx.emit(
            Opcode.STORE_INDIRECT,
            operands=[ptr_reg, val_reg],
            node=parent_node,
        )
```

- [ ] **Step 3: Update test_c_frontend.py assertions**

- Line 311: `assert any("*" in inst.operands for inst in loads)` — change `loads` filter from `Opcode.LOAD_FIELD` to `Opcode.LOAD_INDIRECT` and remove the `"*"` check: `load_indirects = _find_all(ir, Opcode.LOAD_INDIRECT)` then `assert len(load_indirects) >= 1`
- Line 327: same pattern for `STORE_FIELD` → `STORE_INDIRECT`
- Line 417-420: same pattern for LOAD_FIELD → LOAD_INDIRECT

- [ ] **Step 4: Run C tests**

Run: `poetry run python -m pytest tests/unit/test_c_frontend.py tests/integration/test_c_frontend_execution.py -v --tb=short -q`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/c/expressions.py tests/unit/test_c_frontend.py
git commit -m "Migrate C frontend pointer dereference to LOAD_INDIRECT/STORE_INDIRECT"
```

---

### Task 5: Migrate Rust frontend

**Files:**
- Modify: `interpreter/frontends/rust/expressions.py`
- Modify: `tests/unit/test_rust_frontend.py`

- [ ] **Step 1: Migrate Rust dereference read**

In `interpreter/frontends/rust/expressions.py`, in `lower_deref_expr` (around line 131-137), replace:

```python
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[inner_reg, "*"],
        node=node,
    )
```

With:

```python
    ctx.emit(
        Opcode.LOAD_INDIRECT,
        result_reg=reg,
        operands=[inner_reg],
        node=node,
    )
```

- [ ] **Step 2: Migrate Rust dereference write**

In `lower_rust_store_target` (around line 954-958), replace:

```python
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[inner_reg, "*", val_reg],
                node=parent_node,
            )
```

With:

```python
            ctx.emit(
                Opcode.STORE_INDIRECT,
                operands=[inner_reg, val_reg],
                node=parent_node,
            )
```

- [ ] **Step 3: Update test_rust_frontend.py assertions**

- Line 182: Change from asserting `"*" in inst.operands` on `LOAD_FIELD` to asserting `len(_find_all(ir, Opcode.LOAD_INDIRECT)) >= 1`
- Line 342: Same pattern

- [ ] **Step 4: Run Rust tests**

Run: `poetry run python -m pytest tests/unit/test_rust_frontend.py tests/integration/test_rust_frontend_execution.py -v --tb=short -q`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/rust/expressions.py tests/unit/test_rust_frontend.py
git commit -m "Migrate Rust frontend dereference to LOAD_INDIRECT/STORE_INDIRECT"
```

---

### Task 6: Migrate C# frontend

**Files:**
- Modify: `interpreter/frontends/csharp/expressions.py`
- Modify: `tests/unit/test_csharp_frontend.py`

- [ ] **Step 1: Migrate emit_byref_load**

In `interpreter/frontends/csharp/expressions.py`, in `emit_byref_load` (around line 331-332), replace:

```python
        ctx.emit(Opcode.LOAD_FIELD, result_reg=deref_reg, operands=[reg, "*"], node=node)
```

With:

```python
        ctx.emit(Opcode.LOAD_INDIRECT, result_reg=deref_reg, operands=[reg], node=node)
```

- [ ] **Step 2: Migrate emit_byref_store**

In `emit_byref_store` (around line 345), replace:

```python
        ctx.emit(Opcode.STORE_FIELD, operands=[ptr_reg, "*", val_reg], node=node)
```

With:

```python
        ctx.emit(Opcode.STORE_INDIRECT, operands=[ptr_reg, val_reg], node=node)
```

- [ ] **Step 3: Update test_csharp_frontend.py assertions**

In `TestCSharpByrefParamIR`:

- `test_out_param_write_emits_store_field_deref`: Change from asserting `"*" in STORE_FIELD` to asserting `len(_find_all(ir, Opcode.STORE_INDIRECT)) >= 1`. Update docstring.
- `test_ref_param_read_emits_load_field_deref`: Change from asserting `"*" in LOAD_FIELD` to asserting `len(_find_all(ir, Opcode.LOAD_INDIRECT)) >= 1`. Update docstring.
- `test_in_param_read_emits_load_field_deref`: Same pattern.
- `test_regular_param_no_deref`: Change from asserting no `"*" in LOAD_FIELD` to asserting `len(_find_all(ir, Opcode.LOAD_INDIRECT)) == 0`. Update docstring.

- [ ] **Step 4: Run C# tests**

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py tests/integration/test_csharp_frontend_execution.py -v --tb=short -q`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/csharp/expressions.py tests/unit/test_csharp_frontend.py
git commit -m "Migrate C# byref params to LOAD_INDIRECT/STORE_INDIRECT"
```

---

### Task 7: Remove `"*"` special cases from LOAD_FIELD/STORE_FIELD

**Files:**
- Modify: `interpreter/executor.py`

- [ ] **Step 1: Remove `"*"` from `_handle_load_field`**

In `_handle_load_field` (line 436), remove:

1. The `if field_name == "*":` block inside the `isinstance(obj_val, Pointer)` branch (lines 445-452). Keep the `ptr->field` block (lines 454-461) and the Pointer-not-on-heap block (lines 462-469).
2. The standalone `if field_name == "*" and isinstance(obj_val, BoundFuncRef):` block (lines 471-477).

- [ ] **Step 2: Remove `"*"` from `_handle_store_field`**

In `_handle_store_field` (line 387), the `isinstance(obj_val, Pointer)` block (lines 394-408) currently uses a ternary: `target_field = str(obj_val.offset) if field_name == "*" else field_name`. Change this to always use `field_name`:

```python
    if isinstance(obj_val, Pointer):
        return ExecutionResult.success(
            StateUpdate(
                heap_writes=[
                    HeapWrite(
                        obj_addr=obj_val.base,
                        field=field_name,
                        value=typed_from_runtime(val),
                    )
                ],
                reasoning=f"store {obj_val.base}.{field_name} = {val!r} (via Pointer)",
            )
        )
```

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q --no-header`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add interpreter/executor.py
git commit -m "Remove magic '*' field special cases from LOAD_FIELD/STORE_FIELD handlers"
```

---

### Task 8: Update documentation

**Files:**
- Modify: `docs/ir-reference.md`
- Modify: `docs/frontend-design/c.md`
- Modify: `docs/frontend-design/cpp.md`
- Modify: `docs/notes-on-vm-design.md`

- [ ] **Step 1: Update ir-reference.md**

Add documentation for LOAD_INDIRECT and STORE_INDIRECT under the Pointer operations section. Remove all `"*"` dereference references from LOAD_FIELD and STORE_FIELD documentation (lines 74, 78, 282, 286). Update the pointer aliasing section (line 589) to reference the new opcodes.

- [ ] **Step 2: Update frontend-design/c.md**

Replace all `LOAD_FIELD ptr, "*"` / `STORE_FIELD ptr, "*", val` references with `LOAD_INDIRECT ptr` / `STORE_INDIRECT ptr, val` (lines 10, 100, 196, 206, 373).

- [ ] **Step 3: Update frontend-design/cpp.md**

Replace `LOAD_FIELD ptr, "*"` reference at line 101.

- [ ] **Step 4: Update notes-on-vm-design.md**

Replace pointer operations table entries (lines 855, 861, 862).

- [ ] **Step 5: Commit**

```bash
git add docs/ir-reference.md docs/frontend-design/c.md docs/frontend-design/cpp.md docs/notes-on-vm-design.md
git commit -m "Update documentation: LOAD_INDIRECT/STORE_INDIRECT replace LOAD_FIELD/STORE_FIELD '*'"
```

---

### Task 9: Full test suite verification and cleanup

- [ ] **Step 1: Run black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q --no-header`
Expected: All tests pass

- [ ] **Step 3: Commit any formatting changes**

```bash
git add -A
git commit -m "Black formatting for LOAD_INDIRECT/STORE_INDIRECT migration"
```

- [ ] **Step 4: Update README**

Add mention of LOAD_INDIRECT/STORE_INDIRECT in the pointer operations section if applicable.

- [ ] **Step 5: Push**

```bash
git push origin main
```

- [ ] **Step 6: Close issue**

```bash
bd update red-dragon-aiu --status closed
```
