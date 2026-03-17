# Pascal defProc Qualified Method Bodies Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire out-of-class Pascal method implementations (`procedure TFoo.SetName(...)`) to their class so the VM dispatches them as class methods with `this`/`self` injection.

**Architecture:** Detect `genericDot` node in `lower_pascal_proc`, extract class name and method name, inject `this`+`self` params, and set `_current_class_name` context. The registry already picks up methods emitted after `end_class` labels, so no VM/registry changes needed.

**Tech Stack:** Python, tree-sitter, pytest

**Spec:** `docs/superpowers/specs/2026-03-17-pascal-defproc-qualified-methods-design.md`

---

## File Structure

- Modify: `interpreter/frontends/pascal/node_types.py` — add `GENERIC_DOT` constant
- Modify: `interpreter/frontends/pascal/declarations.py:210-260` — modify `lower_pascal_proc` to handle `genericDot`
- Modify: `tests/unit/test_pascal_frontend.py` — add unit test for qualified defProc IR emission
- Modify: `tests/integration/test_pascal_frontend_execution.py:63-65` — remove `xfail` marker

---

### Task 1: Node type constant + qualified method lowering

This task adds the `GENERIC_DOT` constant and modifies `lower_pascal_proc` to detect qualified names, inject `this`/`self`, and set class context.

**Files:**
- Modify: `interpreter/frontends/pascal/node_types.py:99` — add `GENERIC_DOT` after `DECL_FIELD`
- Modify: `interpreter/frontends/pascal/declarations.py:210-260` — modify `lower_pascal_proc`
- Test: `tests/unit/test_pascal_frontend.py`

**Context for implementer:**

The tree-sitter parse of `procedure TFoo.SetName(const AValue: string);` produces:

```
defProc
  declProc
    kProcedure
    genericDot              ← qualified name (NOT a plain identifier)
      identifier "TFoo"    ← class name
      kDot
      identifier "SetName" ← method name
    declArgs ...
  block ...
```

Currently `lower_pascal_proc` (line 221-222) looks for a plain `identifier` child on `search_node`. When the name is a `genericDot`, no `identifier` is found at the top level, so `func_name` falls back to `"__anon"`. The body gets lowered without `this` injection.

The registry's `_scan_classes` (in `interpreter/registry.py:67-103`) keeps `in_class` set after `end_class_X` labels. Any `CONST <func_label>` emitted after the class body but before the next class is still registered as a method. So the correctly-named function will automatically overwrite the empty stub.

- [ ] **Step 1: Write the failing unit test**

Add to `tests/unit/test_pascal_frontend.py` at the end of the file:

```python
class TestPascalQualifiedDefProc:
    """Tests for defProc with qualified name (procedure TFoo.MethodName)."""

    def test_qualified_defproc_emits_this_and_self_params(self):
        """procedure TFoo.SetName(...) should inject this+self and use correct name."""
        source = """\
program M;
type
  TFoo = class
  private
    FName: string;
    procedure SetName(const AValue: string);
  end;

procedure TFoo.SetName(const AValue: string);
begin
  self.FName := AValue;
end;
begin
end."""
        instructions = _parse_pascal(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        # Find the SYMBOLIC param:this that belongs to the defProc body (not the stub)
        # The defProc body also has param:AValue after param:this
        this_params = [s for s in symbolics if s.operands == ["param:this"]]
        # There should be at least 2: one from the stub, one from the defProc body
        assert len(this_params) >= 2, (
            f"Expected at least 2 SYMBOLIC param:this (stub + body), got {len(this_params)}"
        )
        # The defProc should emit func_ref with name "SetName", not "__anon"
        func_consts = _find_all(instructions, Opcode.CONST)
        func_labels = [c for c in func_consts if "func_SetName" in str(c.operands[0])]
        # At least 2: one from stub inside class, one from defProc body
        assert len(func_labels) >= 2, (
            f"Expected at least 2 func_SetName refs (stub + body), got {func_labels}"
        )
        # self alias: DECL_VAR self should appear in the defProc body
        decl_vars = _find_all(instructions, Opcode.DECL_VAR)
        self_decls = [d for d in decl_vars if d.operands[0] == "self"]
        assert len(self_decls) >= 1, "Expected DECL_VAR self alias in qualified defProc"

    def test_unqualified_defproc_unchanged(self):
        """Plain procedure (no dot) should NOT inject this/self."""
        source = """\
program M;
procedure Greet;
begin
end;
begin
end."""
        instructions = _parse_pascal(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        this_params = [s for s in symbolics if s.operands == ["param:this"]]
        assert len(this_params) == 0, "Plain procedure should not have param:this"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalQualifiedDefProc -v`
Expected: `test_qualified_defproc_emits_this_and_self_params` FAILS (only 1 `param:this` from stub, func name is `__anon`). `test_unqualified_defproc_unchanged` PASSES (no regression).

- [ ] **Step 3: Add GENERIC_DOT constant**

In `interpreter/frontends/pascal/node_types.py`, add after line 99 (`DECL_FIELD = "declField"`):

```python
    GENERIC_DOT = "genericDot"
```

- [ ] **Step 4: Modify `lower_pascal_proc` to handle qualified names**

In `interpreter/frontends/pascal/declarations.py`, replace lines 220-240 of `lower_pascal_proc`. The current code is:

```python
    search_node = decl_node if decl_node else node
    id_node = next(
        (c for c in search_node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    args_node = next(
        (c for c in search_node.children if c.type == PascalNodeType.DECL_ARGS), None
    )
    body_node = next((c for c in node.children if c.type == PascalNodeType.BLOCK), None)

    func_name = ctx.node_text(id_node) if id_node else "__anon"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    return_hint = extract_pascal_return_type(ctx, search_node)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    if args_node:
        _lower_pascal_params(ctx, args_node)
```

Replace with:

```python
    search_node = decl_node if decl_node else node

    # Detect qualified name (genericDot): procedure TFoo.SetName(...)
    generic_dot = next(
        (c for c in search_node.children if c.type == PascalNodeType.GENERIC_DOT), None
    )
    if generic_dot:
        dot_ids = [c for c in generic_dot.children if c.type == PascalNodeType.IDENTIFIER]
        class_name = ctx.node_text(dot_ids[0])
        func_name = ctx.node_text(dot_ids[1])
    else:
        class_name = ""
        id_node = next(
            (c for c in search_node.children if c.type == PascalNodeType.IDENTIFIER),
            None,
        )
        func_name = ctx.node_text(id_node) if id_node else "__anon"

    args_node = next(
        (c for c in search_node.children if c.type == PascalNodeType.DECL_ARGS), None
    )
    body_node = next((c for c in node.children if c.type == PascalNodeType.BLOCK), None)

    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    return_hint = extract_pascal_return_type(ctx, search_node)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    # Inject this + self for qualified methods
    if class_name:
        sym_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=sym_reg,
            operands=[f"{constants.PARAM_PREFIX}this"],
            node=node,
        )
        ctx.emit(Opcode.DECL_VAR, operands=["this", f"%{ctx.reg_counter - 1}"])
        ctx.emit(Opcode.DECL_VAR, operands=["self", f"%{ctx.reg_counter - 1}"])

    if args_node:
        _lower_pascal_params(ctx, args_node)
```

Also wrap the body lowering section (lines 242-249) with class context save/restore. The current code:

```python
    prev_func_name = getattr(ctx, "_pascal_current_function_name", "")
    ctx._pascal_current_function_name = func_name
    for child in node.children:
        if child.type == PascalNodeType.DEF_PROC:
            lower_pascal_proc(ctx, child)
    if body_node:
        lower_pascal_block(ctx, body_node)
    ctx._pascal_current_function_name = prev_func_name
```

Replace with:

```python
    prev_func_name = getattr(ctx, "_pascal_current_function_name", "")
    ctx._pascal_current_function_name = func_name
    prev_class_name = getattr(ctx, "_current_class_name", "")
    if class_name:
        ctx._current_class_name = class_name
    for child in node.children:
        if child.type == PascalNodeType.DEF_PROC:
            lower_pascal_proc(ctx, child)
    if body_node:
        lower_pascal_block(ctx, body_node)
    ctx._pascal_current_function_name = prev_func_name
    if class_name:
        ctx._current_class_name = prev_class_name
```

- [ ] **Step 5: Run unit tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalQualifiedDefProc -v`
Expected: Both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add interpreter/frontends/pascal/node_types.py interpreter/frontends/pascal/declarations.py tests/unit/test_pascal_frontend.py
git commit -m "feat(pascal): wire defProc qualified method bodies to class (red-dragon-0b1)"
```

---

### Task 2: Integration test + cleanup

Remove the `xfail` marker from the existing integration test and verify the full pipeline works.

**Files:**
- Modify: `tests/integration/test_pascal_frontend_execution.py:63-65` — remove `xfail`

- [ ] **Step 1: Remove the xfail marker**

In `tests/integration/test_pascal_frontend_execution.py`, remove lines 63-65:

```python
    @pytest.mark.xfail(
        reason="defProc qualified name (TFoo.SetName) body not wired back to class method stub"
    )
```

- [ ] **Step 2: Run the integration test**

Run: `poetry run python -m pytest tests/integration/test_pascal_frontend_execution.py::TestPascalPropertyAccessorExecution::test_method_write_property_calls_setter_procedure -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass, xfail count drops from 27 to 26.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_pascal_frontend_execution.py
git commit -m "test(pascal): remove xfail for defProc qualified method bodies"
```

---

### Task 3: Format, update README, push, close issue

- [ ] **Step 1: Run Black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 3: Commit any formatting changes**

```bash
git add -A
git commit -m "style: black formatting"
```

(Skip if no changes.)

- [ ] **Step 4: Push to main**

```bash
git push origin main
```

- [ ] **Step 5: Close issue**

```bash
bd update red-dragon-0b1 --status closed
```
