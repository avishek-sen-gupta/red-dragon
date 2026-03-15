# Lua Table-Based OOP Method Dispatch — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Lua table-based OOP (dot-syntax function declarations and calls) produce concrete VM results instead of symbolic values.

**Architecture:** Two changes in the Lua frontend — (1) `function Counter.new()` emits `STORE_FIELD` on the table instead of `DECL_VAR "Counter.new"`, (2) `Counter.increment(counter)` emits `LOAD_FIELD` + `CALL_UNKNOWN` instead of `CALL_METHOD`. No VM changes.

**Tech Stack:** Python, tree-sitter (Lua grammar), pytest

**Spec:** `docs/superpowers/specs/2026-03-15-lua-table-oop-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `interpreter/frontends/lua/declarations.py` | Modify | Dotted function declarations → STORE_FIELD |
| `interpreter/frontends/lua/expressions.py` | Modify | Dotted function calls → LOAD_FIELD + CALL_UNKNOWN |
| `tests/unit/test_lua_frontend.py` | Modify | Unit tests for IR shape |
| `tests/integration/test_lua_table_oop_execution.py` | Create | Integration tests for concrete execution |
| `tests/unit/rosetta/test_rosetta_method_chaining.py` | Modify | Remove Lua from symbolic exclusion list |

---

## Chunk 1: Dotted function declarations

### Task 1: Unit test for dotted function declaration IR shape

**Files:**
- Test: `tests/unit/test_lua_frontend.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_lua_frontend.py`:

```python
class TestLuaDottedFunctionDeclaration:
    def test_dotted_function_emits_store_field(self):
        """function Counter.new() should emit STORE_FIELD on Counter, not DECL_VAR 'Counter.new'."""
        instructions = _parse_lua("""
Counter = {}
function Counter.new()
    return 1
end
""")
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        # Should have a STORE_FIELD storing the function ref onto Counter
        func_store = [
            inst for inst in store_fields
            if any("new" in str(op) for op in inst.operands)
        ]
        assert len(func_store) >= 1, f"Expected STORE_FIELD for 'new', got {store_fields}"
        # Should NOT have DECL_VAR with dotted name
        decl_vars = _find_all(instructions, Opcode.DECL_VAR)
        dotted = [inst for inst in decl_vars if "Counter.new" in str(inst.operands)]
        assert len(dotted) == 0, f"Should not DECL_VAR 'Counter.new', got {dotted}"

    def test_dotted_function_uses_method_name_only(self):
        """Function label and ref should use 'new', not 'Counter.new'."""
        instructions = _parse_lua("""
Counter = {}
function Counter.new()
    return 1
end
""")
        consts = _find_all(instructions, Opcode.CONST)
        func_refs = [
            inst for inst in consts
            if any("<function:" in str(op) for op in inst.operands)
        ]
        assert len(func_refs) >= 1
        ref_str = str(func_refs[0].operands[0])
        assert "Counter.new" not in ref_str, f"Func ref should not contain dots: {ref_str}"
        assert "<function:new@" in ref_str, f"Func ref should use method name 'new': {ref_str}"

    def test_dotted_function_with_params(self):
        """function Counter.increment(self) should have params AND STORE_FIELD."""
        instructions = _parse_lua("""
Counter = {}
function Counter.increment(self)
    return self
end
""")
        store_fields = _find_all(instructions, Opcode.STORE_FIELD)
        func_store = [
            inst for inst in store_fields
            if any("increment" in str(op) for op in inst.operands)
        ]
        assert len(func_store) >= 1
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        param_names = [
            inst.operands[0]
            for inst in symbolics
            if inst.operands and str(inst.operands[0]).startswith("param:")
        ]
        assert any("self" in p for p in param_names), f"Expected param:self, got {param_names}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_lua_frontend.py::TestLuaDottedFunctionDeclaration -v`
Expected: FAIL — currently emits `DECL_VAR "Counter.new"` not `STORE_FIELD`

- [ ] **Step 3: Implement the fix in declarations.py**

Modify `lower_lua_function_declaration` in `interpreter/frontends/lua/declarations.py`. Replace lines 114-148 with:

```python
def lower_lua_function_declaration(ctx: TreeSitterEmitContext, node) -> None:
    """Lower function_declaration with name, parameters, body fields.

    For dotted names (``function Counter.new()``), the function is stored
    as a field on the table object via STORE_FIELD rather than as a
    top-level variable.  The function name used in labels and func refs
    is just the method name (``new``), not the dotted path.
    """
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    params_node = node.child_by_field_name(ctx.constants.func_params_field)
    body_node = node.child_by_field_name(ctx.constants.func_body_field)

    # Extract table name and method name for dotted declarations
    is_dotted = name_node is not None and name_node.type == LuaNodeType.DOT_INDEX_EXPRESSION
    if is_dotted:
        table_node = name_node.child_by_field_name("table")
        field_node = name_node.child_by_field_name("field")
        table_name = ctx.node_text(table_node) if table_node else ""
        func_name = ctx.node_text(field_node) if field_node else "__anon"
    else:
        func_name = ctx.node_text(name_node) if name_node else "__anon"

    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)

    if params_node:
        lower_params(ctx, params_node)

    if body_node:
        ctx.lower_block(body_node)

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=func_reg,
        operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
    )

    if is_dotted and table_name:
        obj_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=obj_reg, operands=[table_name])
        ctx.emit(
            Opcode.STORE_FIELD,
            operands=[obj_reg, func_name, func_reg],
            node=node,
        )
    else:
        ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_lua_frontend.py::TestLuaDottedFunctionDeclaration -v`
Expected: PASS

- [ ] **Step 5: Run all Lua frontend tests to check for regressions**

Run: `poetry run python -m pytest tests/unit/test_lua_frontend.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Format and commit**

```bash
poetry run python -m black .
git add interpreter/frontends/lua/declarations.py tests/unit/test_lua_frontend.py
git commit -m "feat(lua): emit STORE_FIELD for dotted function declarations"
```

---

## Chunk 2: Dotted function calls

### Task 2: Unit test for dotted function call IR shape

**Files:**
- Modify: `interpreter/frontends/lua/expressions.py:57-71`
- Test: `tests/unit/test_lua_frontend.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_lua_frontend.py`:

```python
class TestLuaDottedFunctionCall:
    def test_dotted_call_emits_load_field_and_call_unknown(self):
        """Counter.increment(x) should emit LOAD_FIELD + CALL_UNKNOWN, not CALL_METHOD."""
        instructions = _parse_lua("Counter.increment(x)")
        # Should have LOAD_FIELD for "increment"
        load_fields = _find_all(instructions, Opcode.LOAD_FIELD)
        field_loads = [
            inst for inst in load_fields
            if "increment" in str(inst.operands)
        ]
        assert len(field_loads) >= 1, f"Expected LOAD_FIELD 'increment', got {load_fields}"
        # Should have CALL_UNKNOWN (not CALL_METHOD)
        call_unknowns = _find_all(instructions, Opcode.CALL_UNKNOWN)
        assert len(call_unknowns) >= 1, f"Expected CALL_UNKNOWN, got none"
        call_methods = _find_all(instructions, Opcode.CALL_METHOD)
        dotted_methods = [
            inst for inst in call_methods
            if "increment" in str(inst.operands)
        ]
        assert len(dotted_methods) == 0, f"Should not emit CALL_METHOD for dot call: {dotted_methods}"

    def test_dotted_call_with_multiple_args(self):
        """Counter.add(a, b) should pass both args to CALL_UNKNOWN."""
        instructions = _parse_lua("Counter.add(a, b)")
        call_unknowns = _find_all(instructions, Opcode.CALL_UNKNOWN)
        assert len(call_unknowns) >= 1
        # CALL_UNKNOWN operands: [func_reg, arg1_reg, arg2_reg]
        assert len(call_unknowns[0].operands) >= 3, "Should have func + 2 args"

    def test_colon_call_still_emits_call_method(self):
        """obj:method() should still use CALL_METHOD (unchanged)."""
        instructions = _parse_lua("obj:method()")
        call_methods = _find_all(instructions, Opcode.CALL_METHOD)
        assert len(call_methods) >= 1, "Colon syntax should still emit CALL_METHOD"

    def test_chained_dotted_calls(self):
        """Multiple consecutive dotted calls each produce LOAD_FIELD + CALL_UNKNOWN."""
        instructions = _parse_lua("Counter.a(x)\nCounter.b(y)")
        load_fields = _find_all(instructions, Opcode.LOAD_FIELD)
        field_names = [inst.operands[1] for inst in load_fields if len(inst.operands) >= 2]
        assert "a" in field_names, f"Expected LOAD_FIELD 'a', got {field_names}"
        assert "b" in field_names, f"Expected LOAD_FIELD 'b', got {field_names}"
        call_unknowns = _find_all(instructions, Opcode.CALL_UNKNOWN)
        assert len(call_unknowns) >= 2, f"Expected 2 CALL_UNKNOWN, got {len(call_unknowns)}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_lua_frontend.py::TestLuaDottedFunctionCall -v`
Expected: FAIL — first two tests fail (currently emits CALL_METHOD), third passes

- [ ] **Step 3: Implement the fix in expressions.py**

Modify the dot-indexed call branch in `lower_lua_call` (`interpreter/frontends/lua/expressions.py` lines 57-71). Replace:

```python
    # Dot-indexed call: obj.method(args)
    if name_node.type == LuaNodeType.DOT_INDEX_EXPRESSION:
        table_node = name_node.child_by_field_name("table")
        field_node = name_node.child_by_field_name("field")
        if table_node and field_node:
            obj_reg = ctx.lower_expr(table_node)
            method_name = ctx.node_text(field_node)
            reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_METHOD,
                result_reg=reg,
                operands=[obj_reg, method_name] + arg_regs,
                node=node,
            )
            return reg
```

With:

```python
    # Dot-indexed call: obj.field(args) — field access + function call
    if name_node.type == LuaNodeType.DOT_INDEX_EXPRESSION:
        table_node = name_node.child_by_field_name("table")
        field_node = name_node.child_by_field_name("field")
        if table_node and field_node:
            obj_reg = ctx.lower_expr(table_node)
            field_name = ctx.node_text(field_node)
            func_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.LOAD_FIELD,
                result_reg=func_reg,
                operands=[obj_reg, field_name],
                node=node,
            )
            reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_UNKNOWN,
                result_reg=reg,
                operands=[func_reg] + arg_regs,
                node=node,
            )
            return reg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_lua_frontend.py::TestLuaDottedFunctionCall -v`
Expected: PASS

- [ ] **Step 5: Run all Lua frontend tests to check for regressions**

Run: `poetry run python -m pytest tests/unit/test_lua_frontend.py -v`
Expected: All tests PASS. Note: `test_method_call` (line 155) tests colon syntax (`obj:method()`), which is unchanged. The dot-access tests in `TestLuaTableAccess` test `obj.field` as an expression (not a call), which is also unchanged.

- [ ] **Step 6: Format and commit**

```bash
poetry run python -m black .
git add interpreter/frontends/lua/expressions.py tests/unit/test_lua_frontend.py
git commit -m "feat(lua): emit LOAD_FIELD + CALL_UNKNOWN for dotted function calls"
```

---

## Chunk 3: Integration tests and Rosetta update

### Task 3: Integration test for table-based OOP execution

**Files:**
- Create: `tests/integration/test_lua_table_oop_execution.py`

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_lua_table_oop_execution.py`:

```python
"""Integration tests: Lua table-based OOP produces concrete results."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_lua(source: str, max_steps: int = 500):
    vm = run(source, language=Language.LUA, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestLuaTableMethodDispatch:
    def test_table_method_returns_concrete(self):
        """Counter.new() should return a concrete table, not symbolic."""
        result = _run_lua("""
Counter = {}

function Counter.new()
    local self = {count = 0}
    return self
end

counter = Counter.new()
""")
        counter = result["counter"]
        assert isinstance(counter, str) and counter.startswith("obj_"), \
            f"counter should be a heap address, got {counter!r}"

    def test_method_chaining_produces_answer(self):
        """Full method chaining should produce answer = 6."""
        result = _run_lua("""
Counter = {}

function Counter.new()
    local self = {count = 0}
    return self
end

function Counter.increment(self)
    self.count = self.count + 1
    return self
end

function Counter.get_value(self)
    return self.count
end

counter = Counter.new()
Counter.increment(counter)
Counter.increment(counter)
Counter.increment(counter)
Counter.increment(counter)
Counter.increment(counter)
Counter.increment(counter)
answer = Counter.get_value(counter)
""")
        assert result["answer"] == 6

    def test_method_modifies_table_field(self):
        """Calling a method that modifies self.count should persist the change."""
        result = _run_lua("""
Box = {}

function Box.new(val)
    local self = {value = val}
    return self
end

function Box.get(self)
    return self.value
end

b = Box.new(42)
answer = Box.get(b)
""")
        assert result["answer"] == 42
```

- [ ] **Step 2: Run integration tests**

Run: `poetry run python -m pytest tests/integration/test_lua_table_oop_execution.py -v`
Expected: All 3 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_lua_table_oop_execution.py
git commit -m "test(lua): add integration tests for table-based OOP execution"
```

### Task 4: Update Rosetta method chaining test

**Files:**
- Modify: `tests/unit/rosetta/test_rosetta_method_chaining.py`

- [ ] **Step 1: Remove Lua from symbolic exclusion lists**

In `tests/unit/rosetta/test_rosetta_method_chaining.py`, make two changes:

1. Replace the `pytest.skip` for Lua in `test_call_present` (line 330-331) so Lua falls through to the assertion with an expanded opcode set. Change the full method body from:

```python
    def test_call_present(self, language_ir):
        """Languages with classes should have CALL_METHOD or CALL_FUNCTION."""
        lang, ir = language_ir
        if lang in {"lua"}:
            pytest.skip(f"{lang} uses table-based OOP (no class method syntax)")
        call_opcodes = {Opcode.CALL_METHOD, Opcode.CALL_FUNCTION}
        present = {inst.opcode for inst in ir}
        has_call = bool(present & call_opcodes)
        assert (
            has_call
        ), f"[{lang}] expected CALL_METHOD or CALL_FUNCTION, got opcodes: {present}"
```

To:

```python
    def test_call_present(self, language_ir):
        """Languages with classes should have CALL_METHOD, CALL_FUNCTION, or CALL_UNKNOWN."""
        lang, ir = language_ir
        call_opcodes = {Opcode.CALL_METHOD, Opcode.CALL_FUNCTION, Opcode.CALL_UNKNOWN}
        present = {inst.opcode for inst in ir}
        has_call = bool(present & call_opcodes)
        assert (
            has_call
        ), f"[{lang}] expected CALL_METHOD, CALL_FUNCTION, or CALL_UNKNOWN, got opcodes: {present}"
```

2. Remove `"lua"` from `_CHAINING_SYMBOLIC_LANGUAGES` (around line 370):

```python
_CHAINING_SYMBOLIC_LANGUAGES: frozenset[str] = frozenset({"pascal"})
```

- [ ] **Step 2: Run Rosetta method chaining tests**

Run: `poetry run python -m pytest tests/unit/rosetta/test_rosetta_method_chaining.py -v`
Expected: All PASS, including Lua

- [ ] **Step 3: Run the full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass, no regressions

- [ ] **Step 4: Run black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 5: Commit**

```bash
git add tests/unit/rosetta/test_rosetta_method_chaining.py
git commit -m "feat(lua): remove Lua from method chaining symbolic exclusion list"
```

### Task 5: ADR, README, and cleanup

- [ ] **Step 1: Add ADR entry**

Append to `docs/architectural-design-decisions.md`:

```markdown
### ADR-104: Lua dot-syntax as field access + function call, not method dispatch (2026-03-15)

**Context:** Lua has no classes. OOP is done via tables with function-valued fields. `function Counter.new()` is sugar for `Counter["new"] = function()`, and `Counter.increment(counter)` is `Counter["increment"](counter)`. The VM's class method registry only works with languages that emit CLASS_LABEL blocks.

**Decision:** Lua dot-syntax function declarations emit STORE_FIELD on the table object. Dot-syntax function calls emit LOAD_FIELD + CALL_UNKNOWN instead of CALL_METHOD. Colon syntax (`:`) with implicit self is deferred to a separate issue.

**Rationale:** This correctly models Lua semantics — dot syntax is field access, not method dispatch. No VM changes needed. When colon syntax is added later, it will use CALL_METHOD with implicit self, mirroring how Lua actually distinguishes `.` from `:`.

**Files:** `interpreter/frontends/lua/declarations.py`, `interpreter/frontends/lua/expressions.py`
```

- [ ] **Step 2: Update README if needed**

Check if Lua's entry in the language-specific features table mentions method chaining or table-based OOP. If not, add `table-based OOP (dot-syntax method declarations and calls)` to Lua's supported constructs.

- [ ] **Step 3: Create beads issue for colon syntax**

```bash
bd create "Lua: colon syntax (:) with implicit self not supported" --priority P2 --label frontend --label lua
```

- [ ] **Step 4: Close red-dragon-wxg**

```bash
bd update wxg --status closed
```

- [ ] **Step 5: Push**

```bash
git push origin main
```
