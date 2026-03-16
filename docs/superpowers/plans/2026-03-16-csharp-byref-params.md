# C# out/ref/in Pass-by-Reference Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support C# `out`, `ref`, and `in` parameter modifiers with true pass-by-reference semantics, so callee assignments propagate back to the caller.

**Architecture:** Frontend-emitted dereferences mirroring CLR IL. The C# frontend emits `ADDRESS_OF` at call sites and `LOAD_FIELD "*"` / `STORE_FIELD "*"` for reads/writes of byref params in callee bodies. Zero VM changes — reuses existing ADR-099 pointer aliasing infrastructure.

**Tech Stack:** Python 3.13+, tree-sitter-c-sharp, pytest

**Spec:** `docs/superpowers/specs/2026-03-16-csharp-byref-params-design.md`

---

## File Structure

| File | Responsibility | Change |
|------|---------------|--------|
| `interpreter/frontends/context.py` | Emit context shared state | Add `byref_params: set[str]` field |
| `interpreter/frontends/csharp/expressions.py` | C# expression lowerers | Add `emit_byref_load`, `emit_byref_store`, `lower_csharp_identifier`, `extract_csharp_call_args`; modify `lower_declaration_expression`, `lower_csharp_store_target` |
| `interpreter/frontends/csharp/frontend.py` | C# dispatch tables | Register `lower_csharp_identifier`, switch call sites to `extract_csharp_call_args` |
| `tests/unit/test_csharp_frontend.py` | Unit tests for IR output | Add byref IR tests |
| `tests/integration/test_csharp_frontend_execution.py` | Integration tests | Remove xfail, add ref/in/edge-case tests |

---

## Chunk 1: Infrastructure and Call Site

### Task 1: Add `byref_params` to TreeSitterEmitContext

**Files:**
- Modify: `interpreter/frontends/context.py:136` (after `class_symbol_table`)

- [ ] **Step 1: Add the field**

In `interpreter/frontends/context.py`, add after line 136 (`class_symbol_table`):

```python
    # Byref parameter tracking (C# out/ref/in)
    byref_params: set[str] = field(default_factory=set)
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py -v --tb=short -q`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add interpreter/frontends/context.py
git commit -m "Add byref_params set to TreeSitterEmitContext for C# out/ref/in tracking"
```

---

### Task 2: Add `emit_byref_load` and `emit_byref_store` helpers

**Files:**
- Modify: `interpreter/frontends/csharp/expressions.py`

- [ ] **Step 1: Write unit tests for the helpers**

In `tests/unit/test_csharp_frontend.py`, add:

```python
class TestCSharpByrefParamIR:
    """Unit tests for out/ref/in byref parameter IR emission."""

    def test_out_param_write_emits_store_field_deref(self):
        """Assignment to out param should emit LOAD_VAR + STORE_FIELD '*'."""
        ir = _parse_and_lower("""\
class C {
    void Fill(out int result) {
        result = 42;
    }
}""")
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any("*" in inst.operands for inst in store_fields)

    def test_ref_param_read_emits_load_field_deref(self):
        """Reading a ref param should emit LOAD_VAR + LOAD_FIELD '*'."""
        ir = _parse_and_lower("""\
class C {
    int Read(ref int x) {
        return x;
    }
}""")
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any("*" in inst.operands for inst in load_fields)

    def test_in_param_read_emits_load_field_deref(self):
        """Reading an in param should emit LOAD_VAR + LOAD_FIELD '*'."""
        ir = _parse_and_lower("""\
class C {
    int Read(in int x) {
        return x;
    }
}""")
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any("*" in inst.operands for inst in load_fields)

    def test_regular_param_no_deref(self):
        """Regular param should NOT emit LOAD_FIELD '*'."""
        ir = _parse_and_lower("""\
class C {
    int Read(int x) {
        return x;
    }
}""")
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert not any("*" in inst.operands for inst in load_fields)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py::TestCSharpByrefParamIR -v`
Expected: FAIL (no byref logic yet)

- [ ] **Step 3: Implement `emit_byref_load` and `emit_byref_store`**

In `interpreter/frontends/csharp/expressions.py`, add after the `lower_declaration_expression` function:

```python
def emit_byref_load(ctx: TreeSitterEmitContext, name: str, *, node=None) -> str:
    """Load a variable, dereferencing if it's a byref (out/ref/in) param."""
    reg = ctx.fresh_reg()
    resolved = ctx.resolve_var(name)
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[resolved], node=node)
    if name in ctx.byref_params:
        deref_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_FIELD, result_reg=deref_reg, operands=[reg, "*"], node=node)
        return deref_reg
    return reg


def emit_byref_store(ctx: TreeSitterEmitContext, name: str, val_reg: str, *, node=None) -> None:
    """Store to a variable, writing through pointer if it's a byref param."""
    if name in ctx.byref_params:
        ptr_reg = ctx.fresh_reg()
        resolved = ctx.resolve_var(name)
        ctx.emit(Opcode.LOAD_VAR, result_reg=ptr_reg, operands=[resolved], node=node)
        ctx.emit(Opcode.STORE_FIELD, operands=[ptr_reg, "*", val_reg], node=node)
    else:
        ctx.emit(Opcode.STORE_VAR, operands=[ctx.resolve_var(name), val_reg], node=node)
```

- [ ] **Step 4: Implement `lower_csharp_identifier`**

In `interpreter/frontends/csharp/expressions.py`, add:

```python
def lower_csharp_identifier(ctx: TreeSitterEmitContext, node) -> str:
    """Lower identifier with byref dereference support."""
    name = ctx.node_text(node)
    return emit_byref_load(ctx, name, node=node)
```

- [ ] **Step 5: Update `lower_csharp_params` for byref detection**

In `interpreter/frontends/csharp/expressions.py`, modify `lower_csharp_params`. At the top of the function, add `ctx.byref_params.clear()`. Inside the parameter loop, after extracting `pname`, add modifier detection:

```python
def lower_csharp_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower C# formal parameters (parameter nodes)."""
    ctx.byref_params.clear()
    for child in params_node.children:
        if child.type == NT.PARAMETER:
            name_node = child.child_by_field_name("name")
            if name_node:
                pname = ctx.node_text(name_node)
                # Detect out/ref/in modifier
                modifier = next(
                    (c for c in child.children
                     if c.type == NT.MODIFIER and ctx.node_text(c) in ("out", "ref", "in")),
                    None,
                )
                if modifier:
                    ctx.byref_params.add(pname)
                type_hint = extract_normalized_type(ctx, child, "type", ctx.type_map)
                param_reg = ctx.fresh_reg()
                ctx.emit(
                    Opcode.SYMBOLIC,
                    result_reg=param_reg,
                    operands=[f"{constants.PARAM_PREFIX}{pname}"],
                    node=child,
                )
                ctx.seed_register_type(param_reg, type_hint)
                ctx.seed_param_type(pname, type_hint)
                ctx.emit(
                    Opcode.DECL_VAR,
                    operands=[pname, param_reg],
                )
                ctx.seed_var_type(pname, type_hint)
```

- [ ] **Step 6: Update `lower_csharp_store_target` for byref writes**

In `interpreter/frontends/csharp/expressions.py`, modify the `IDENTIFIER` branch of `lower_csharp_store_target` (around line 600):

Replace:
```python
    if target.type == NT.IDENTIFIER:
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
```

With:
```python
    if target.type == NT.IDENTIFIER:
        emit_byref_store(ctx, ctx.node_text(target), val_reg, node=parent_node)
```

- [ ] **Step 7: Register `lower_csharp_identifier` in frontend dispatch**

In `interpreter/frontends/csharp/frontend.py`, change the `IDENTIFIER` entry in `_build_expr_dispatch`:

Replace:
```python
            NT.IDENTIFIER: common_expr.lower_identifier,
```

With:
```python
            NT.IDENTIFIER: csharp_expr.lower_csharp_identifier,
```

- [ ] **Step 8: Run unit tests**

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py::TestCSharpByrefParamIR -v`
Expected: All 4 tests PASS

- [ ] **Step 9: Run full C# unit test suite for regression**

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py -v --tb=short -q`
Expected: All existing tests PASS

- [ ] **Step 10: Commit**

```bash
git add interpreter/frontends/csharp/expressions.py interpreter/frontends/csharp/frontend.py tests/unit/test_csharp_frontend.py
git commit -m "Add byref param detection and dereference emission for C# out/ref/in"
```

---

### Task 3: Call site — `lower_declaration_expression` emits ADDRESS_OF

**Files:**
- Modify: `interpreter/frontends/csharp/expressions.py`

- [ ] **Step 1: Write unit test**

In `tests/unit/test_csharp_frontend.py`, add to `TestCSharpByrefParamIR`:

```python
    def test_out_int_call_site_emits_address_of(self):
        """out int result at call site should emit DECL_VAR + ADDRESS_OF."""
        ir = _parse_and_lower("int.TryParse(s, out int result);")
        address_ofs = _find_all(ir, Opcode.ADDRESS_OF)
        assert any("result" in inst.operands for inst in address_ofs)

    def test_out_var_call_site_emits_address_of(self):
        """out var result at call site should emit DECL_VAR + ADDRESS_OF."""
        ir = _parse_and_lower("int.TryParse(s, out var result);")
        address_ofs = _find_all(ir, Opcode.ADDRESS_OF)
        assert any("result" in inst.operands for inst in address_ofs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py::TestCSharpByrefParamIR::test_out_int_call_site_emits_address_of -v`
Expected: FAIL

- [ ] **Step 3: Modify `lower_declaration_expression` to emit ADDRESS_OF**

In `interpreter/frontends/csharp/expressions.py`, replace the current `lower_declaration_expression`:

```python
def lower_declaration_expression(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `out int x` / `out var x` declaration_expression.

    Declares the variable in the current scope with a default value (0)
    and emits ADDRESS_OF to produce a Pointer for pass-by-reference.
    """
    name_node = next(
        (c for c in node.children if c.type == NT.IDENTIFIER),
        None,
    )
    var_name = ctx.node_text(name_node) if name_node else "__out_var"
    default_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=default_reg, operands=["0"])
    ctx.emit(Opcode.DECL_VAR, operands=[var_name, default_reg], node=node)
    result_reg = ctx.fresh_reg()
    ctx.emit(Opcode.ADDRESS_OF, result_reg=result_reg, operands=[var_name])
    return result_reg
```

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py::TestCSharpByrefParamIR -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/csharp/expressions.py tests/unit/test_csharp_frontend.py
git commit -m "Emit ADDRESS_OF at call site for out declaration_expression"
```

---

### Task 4: Call site — `extract_csharp_call_args` for ref/in arguments

**Files:**
- Modify: `interpreter/frontends/csharp/expressions.py`
- Modify: `interpreter/frontends/csharp/frontend.py`

- [ ] **Step 1: Write unit test**

In `tests/unit/test_csharp_frontend.py`, add to `TestCSharpByrefParamIR`:

```python
    def test_ref_arg_call_site_emits_address_of(self):
        """ref x at call site should emit ADDRESS_OF."""
        ir = _parse_and_lower("""\
class C {
    void Swap(ref int a, ref int b) { }
    void M() {
        int x = 1;
        int y = 2;
        Swap(ref x, ref y);
    }
}""")
        address_ofs = _find_all(ir, Opcode.ADDRESS_OF)
        assert len(address_ofs) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py::TestCSharpByrefParamIR::test_ref_arg_call_site_emits_address_of -v`
Expected: FAIL

- [ ] **Step 3: Implement `extract_csharp_call_args`**

In `interpreter/frontends/csharp/expressions.py`, add:

```python
from interpreter.frontends.common.expressions import CommonNodeType


_BYREF_KEYWORDS = frozenset({"out", "ref", "in"})


def extract_csharp_call_args(ctx: TreeSitterEmitContext, args_node) -> list[str]:
    """Extract call args, emitting ADDRESS_OF for out/ref/in arguments."""
    if args_node is None:
        return []
    regs: list[str] = []
    for c in args_node.children:
        if c.type in (
            CommonNodeType.OPEN_PAREN,
            CommonNodeType.CLOSE_PAREN,
            CommonNodeType.COMMA,
        ):
            continue
        if c.type in (CommonNodeType.ARGUMENT, CommonNodeType.VALUE_ARGUMENT):
            has_byref = any(
                not gc.is_named and ctx.node_text(gc) in _BYREF_KEYWORDS
                for gc in c.children
            )
            inner = next((gc for gc in c.children if gc.is_named), None)
            if inner is None:
                continue
            if has_byref and inner.type == NT.IDENTIFIER:
                # ref x / in x / out existingVar — emit ADDRESS_OF
                reg = ctx.fresh_reg()
                ctx.emit(Opcode.ADDRESS_OF, result_reg=reg, operands=[ctx.node_text(inner)])
                regs.append(reg)
            else:
                # declaration_expression (out int x) or regular arg
                regs.append(ctx.lower_expr(inner))
        elif c.is_named:
            regs.append(ctx.lower_expr(c))
    return regs
```

- [ ] **Step 4: Switch C# call sites to `extract_csharp_call_args`**

In `interpreter/frontends/csharp/expressions.py`, modify `lower_invocation` and `lower_object_creation`. Replace all calls to `extract_call_args_unwrap(ctx, args_node)` with `extract_csharp_call_args(ctx, args_node)`.

Remove the unused import of `extract_call_args_unwrap` from the imports at the top (it's imported from `interpreter.frontends.common.expressions`). Keep the `CommonNodeType` import added in step 3.

- [ ] **Step 5: Run tests**

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py::TestCSharpByrefParamIR -v`
Expected: All 7 tests PASS

- [ ] **Step 6: Run full C# unit + integration tests for regression**

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py tests/integration/test_csharp_frontend_execution.py -v --tb=short -q`
Expected: All existing tests PASS (xfails still xfail)

- [ ] **Step 7: Commit**

```bash
git add interpreter/frontends/csharp/expressions.py tests/unit/test_csharp_frontend.py
git commit -m "Add extract_csharp_call_args with ADDRESS_OF for ref/in arguments"
```

---

## Chunk 2: Integration Tests and Existing xfail Resolution

### Task 5: Remove xfail from existing out param tests

**Files:**
- Modify: `tests/integration/test_csharp_frontend_execution.py`

- [ ] **Step 1: Remove xfail markers from all 4 tests**

In `tests/integration/test_csharp_frontend_execution.py`, remove the `@pytest.mark.xfail(reason="red-dragon-ia8: ...")` decorators from:
- `test_try_parse_pattern_out_int`
- `test_try_parse_pattern_out_var`
- `test_multiple_out_params`
- `test_out_var_used_in_if_condition`

- [ ] **Step 2: Run the previously-xfailed tests**

Run: `poetry run python -m pytest tests/integration/test_csharp_frontend_execution.py::TestCSharpOutVarExecution -v`
Expected: All 4 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_csharp_frontend_execution.py
git commit -m "Remove xfail from C# out param tests — pass-by-reference now works"
```

---

### Task 6: Add ref parameter integration tests

**Files:**
- Modify: `tests/integration/test_csharp_frontend_execution.py`

- [ ] **Step 1: Write ref parameter tests**

```python
class TestCSharpRefParamExecution:
    """C# ref parameter — callee modifies, caller sees the change."""

    def test_ref_swap(self):
        """Classic swap via ref params."""
        locals_ = _run_csharp(
            """\
class Swapper {
    int dummy;
    Swapper() { this.dummy = 0; }
    void Swap(ref int a, ref int b) {
        int temp = a;
        a = b;
        b = temp;
    }
}
Swapper s = new Swapper();
int x = 10;
int y = 20;
s.Swap(ref x, ref y);
int rx = x;
int ry = y;
""",
            max_steps=1000,
        )
        assert locals_["rx"] == 20
        assert locals_["ry"] == 10

    def test_ref_increment(self):
        """Callee increments a ref param, caller sees updated value."""
        locals_ = _run_csharp(
            """\
class Inc {
    int dummy;
    Inc() { this.dummy = 0; }
    void Increment(ref int x) {
        x = x + 1;
    }
}
Inc inc = new Inc();
int val = 5;
inc.Increment(ref val);
int answer = val;
""",
            max_steps=1000,
        )
        assert locals_["answer"] == 6

    def test_mixed_regular_and_ref_params(self):
        """Method with both regular and ref params."""
        locals_ = _run_csharp(
            """\
class Calc {
    int dummy;
    Calc() { this.dummy = 0; }
    int AddAndStore(int a, ref int result) {
        result = a + result;
        return result;
    }
}
Calc c = new Calc();
int r = 10;
int ret = c.AddAndStore(5, ref r);
int answer = r;
""",
            max_steps=1000,
        )
        assert locals_["answer"] == 15
        assert locals_["ret"] == 15
```

- [ ] **Step 2: Run tests**

Run: `poetry run python -m pytest tests/integration/test_csharp_frontend_execution.py::TestCSharpRefParamExecution -v`
Expected: All 3 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_csharp_frontend_execution.py
git commit -m "Add C# ref parameter integration tests (swap, increment, mixed)"
```

---

### Task 7: Add in parameter and edge case integration tests

**Files:**
- Modify: `tests/integration/test_csharp_frontend_execution.py`

- [ ] **Step 1: Write in parameter and edge case tests**

```python
class TestCSharpInParamExecution:
    """C# in parameter — callee reads via dereference."""

    def test_in_param_read(self):
        """in param should be readable in callee."""
        locals_ = _run_csharp(
            """\
class Reader {
    int dummy;
    Reader() { this.dummy = 0; }
    int Double(in int x) {
        return x + x;
    }
}
Reader r = new Reader();
int val = 7;
int answer = r.Double(in val);
""",
            max_steps=1000,
        )
        assert locals_["answer"] == 14


class TestCSharpByrefEdgeCases:
    """Edge cases for out/ref/in params."""

    def test_out_param_reassigned_multiple_times(self):
        """Callee assigns to out param multiple times; caller sees last value."""
        locals_ = _run_csharp(
            """\
class Multi {
    int dummy;
    Multi() { this.dummy = 0; }
    void Fill(out int result) {
        result = 1;
        result = 2;
        result = 3;
    }
}
Multi m = new Multi();
int x = 0;
m.Fill(out x);
int answer = x;
""",
            max_steps=1000,
        )
        assert locals_["answer"] == 3

    def test_byref_param_as_method_receiver(self):
        """Byref param used as method receiver should dereference first."""
        locals_ = _run_csharp(
            """\
class Box {
    int value;
    Box(int v) { this.value = v; }
    int GetValue() { return value; }
}
class Wrapper {
    int dummy;
    Wrapper() { this.dummy = 0; }
    int Extract(ref Box b) {
        return b.GetValue();
    }
}
Wrapper w = new Wrapper();
Box box = new Box(42);
int answer = w.Extract(ref box);
""",
            max_steps=1500,
        )
        assert locals_["answer"] == 42
```

- [ ] **Step 2: Run tests**

Run: `poetry run python -m pytest tests/integration/test_csharp_frontend_execution.py::TestCSharpInParamExecution tests/integration/test_csharp_frontend_execution.py::TestCSharpByrefEdgeCases -v`
Expected: All 3 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_csharp_frontend_execution.py
git commit -m "Add C# in param and byref edge case integration tests"
```

---

### Task 8: Full test suite verification and cleanup

**Files:**
- No new files

- [ ] **Step 1: Run black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q --no-header`
Expected: All tests pass, xfail count should be 25 (was 29, minus 4 removed xfails)

- [ ] **Step 3: Commit any formatting changes**

```bash
git add -A
git commit -m "Black formatting for C# byref params implementation"
```

- [ ] **Step 4: Push**

```bash
git push origin main
```

- [ ] **Step 5: Close issue**

```bash
bd update red-dragon-ia8 --status closed
```
