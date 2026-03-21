# C# Pattern Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make C# switch expressions/statements use the common Pattern ADT for `declaration_pattern`, `constant_pattern`, `recursive_pattern`, and `discard`.

**Architecture:** Add `parse_csharp_pattern` mapping C# tree-sitter nodes to the Pattern ADT. Enhance `isinstance` builtin for primitive types. Refactor both `lower_switch_expr` and `lower_switch` to use `compile_pattern_test`/`compile_pattern_bindings`.

**Tech Stack:** Python 3.13+, tree-sitter, frozen dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-03-21-csharp-pattern-matching-design.md`

---

## File Map

| File | Role | Action |
|---|---|---|
| `interpreter/builtins.py` | Enhance `isinstance` for primitive types | **Modify** |
| `interpreter/frontends/csharp/patterns.py` | `parse_csharp_pattern` | **Create** |
| `interpreter/frontends/csharp/node_types.py` | Add missing pattern constants | **Modify** |
| `interpreter/frontends/csharp/control_flow.py` | Refactor `lower_switch_expr` and `lower_switch` | **Modify** |
| `tests/integration/test_csharp_pattern_matching.py` | Integration tests | **Create** |

---

### Task 1: Enhance `isinstance` for primitive types (TDD)

**Files:**
- Modify: `interpreter/builtins.py`
- Create: `tests/integration/test_csharp_pattern_matching.py` (just the isinstance test for now)

- [ ] **Step 1: Write failing test**

Create `tests/integration/test_csharp_pattern_matching.py`:

```python
"""Integration tests: C# pattern matching through VM execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_csharp(source: str, max_steps: int = 1000) -> dict:
    vm = run(source, language=Language.CSHARP, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestIsinstancePrimitive:
    def test_isinstance_int(self):
        """isinstance builtin should recognize native int values."""
        from interpreter.builtins import _builtin_isinstance
        from interpreter.typed_value import typed, TypedValue
        from interpreter.type_expr import scalar
        from interpreter.vm import VMState

        vm = VMState()
        args = [typed(42, scalar("Int")), typed("int", scalar("String"))]
        result = _builtin_isinstance(args, vm)
        assert result.value.value is True, f"expected True, got {result.value}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/integration/test_csharp_pattern_matching.py::TestIsinstancePrimitive -v`
Expected: FAIL — current `isinstance` calls `_heap_addr` on a native int which fails

- [ ] **Step 3: Enhance `isinstance` builtin**

Replace `_builtin_isinstance` in `interpreter/builtins.py` (lines 272-281):

```python
_PRIMITIVE_TYPE_MAP: dict[str, type] = {
    "int": int, "Int": int, "Integer": int,
    "string": str, "String": str,
    "float": float, "Float": float, "Double": float,
    "bool": bool, "Boolean": bool,
}


def _builtin_isinstance(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """isinstance(obj, class_name) — check type against class name.

    Works for both heap objects (checks type_hint) and native primitives
    (checks Python type against _PRIMITIVE_TYPE_MAP).
    """
    obj_val = args[0].value
    class_name = str(args[1].value)
    # Try heap object first
    addr = _heap_addr(obj_val)
    if addr and addr in vm.heap:
        from interpreter.type_expr import ScalarType
        type_hint = vm.heap[addr].type_hint
        matches = isinstance(type_hint, ScalarType) and type_hint.name == class_name
        return BuiltinResult(value=typed(matches, scalar("Boolean")))
    # Fall back to primitive type check
    py_type = _PRIMITIVE_TYPE_MAP.get(class_name)
    if py_type is not None:
        matches = isinstance(obj_val, py_type)
        return BuiltinResult(value=typed(matches, scalar("Boolean")))
    return BuiltinResult(value=typed(False, scalar("Boolean")))
```

Note: This reintroduces `addr` checking before heap access — but this is **not** defensive programming. It's a deliberate branch: heap objects go one path, primitives go another. Both are valid inputs. The old `isinstance` assumed all inputs were heap objects, which was wrong.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/integration/test_csharp_pattern_matching.py::TestIsinstancePrimitive -v`
Expected: PASS

- [ ] **Step 5: Run existing tests to verify no regression**

Run: `poetry run python -m pytest tests/integration/test_python_pattern_matching.py -v --tb=short`
Expected: All PASS — Python patterns still work (isinstance for heap objects unchanged)

- [ ] **Step 6: Commit**

```bash
poetry run python -m black .
git add interpreter/builtins.py tests/integration/test_csharp_pattern_matching.py
git commit -m "feat: enhance isinstance builtin for primitive type checking (TDD)"
```

---

### Task 2: `parse_csharp_pattern` + node types

**Files:**
- Create: `interpreter/frontends/csharp/patterns.py`
- Modify: `interpreter/frontends/csharp/node_types.py`

- [ ] **Step 1: Add missing node type constants**

Add to `interpreter/frontends/csharp/node_types.py` after `DECLARATION_PATTERN` (around line 60):

```python
    RECURSIVE_PATTERN = "recursive_pattern"
    PROPERTY_PATTERN_CLAUSE = "property_pattern_clause"
    SUBPATTERN = "subpattern"
```

- [ ] **Step 2: Create `parse_csharp_pattern`**

Create `interpreter/frontends/csharp/patterns.py`:

```python
"""Parse tree-sitter C# pattern nodes into Pattern ADT."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    AsPattern,
    CapturePattern,
    ClassPattern,
    LiteralPattern,
    Pattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.csharp.node_types import CSharpNodeType as NT


def parse_csharp_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
    """Convert a C# tree-sitter pattern node into a Pattern ADT."""
    node_type = node.type

    # Discard: _
    if node_type == NT.DISCARD:
        return WildcardPattern()

    # Constant pattern: null, 0, "hello", etc.
    if node_type == NT.CONSTANT_PATTERN:
        inner = next((c for c in node.children if c.is_named), node)
        return _parse_constant(ctx, inner)

    # Declaration pattern: int i, string s, var x
    if node_type == NT.DECLARATION_PATTERN:
        named = [c for c in node.children if c.is_named]
        type_node = named[0] if named else node
        name_node = named[1] if len(named) >= 2 else named[0]
        var_name = ctx.node_text(name_node)
        # var x (implicit_type) → just capture, no type check
        if type_node.type == "implicit_type":
            return CapturePattern(name=var_name)
        # Explicit type → type check + binding
        type_name = ctx.node_text(type_node)
        return AsPattern(
            pattern=ClassPattern(class_name=type_name, positional=(), keyword=()),
            name=var_name,
        )

    # Recursive pattern: Circle { Radius: 0 }
    if node_type == NT.RECURSIVE_PATTERN:
        type_node = next(
            (c for c in node.children if c.type in ("identifier", "predefined_type", "generic_name")),
            None,
        )
        class_name = ctx.node_text(type_node) if type_node else "Object"
        # Extract property pattern clause
        prop_clause = next(
            (c for c in node.children if c.type == NT.PROPERTY_PATTERN_CLAUSE),
            None,
        )
        keyword: list[tuple[str, Pattern]] = []
        if prop_clause:
            subpatterns = [c for c in prop_clause.children if c.type == NT.SUBPATTERN]
            for sub in subpatterns:
                sub_named = [c for c in sub.children if c.is_named]
                if len(sub_named) >= 2:
                    prop_name = ctx.node_text(sub_named[0])
                    prop_pattern = parse_csharp_pattern(ctx, sub_named[1])
                    keyword.append((prop_name, prop_pattern))
        return ClassPattern(class_name=class_name, positional=(), keyword=tuple(keyword))

    # Identifier used as a pattern (e.g., enum member or type name)
    if node_type == "identifier":
        text = ctx.node_text(node)
        if text == "_":
            return WildcardPattern()
        return CapturePattern(name=text)

    # Fallback: treat as literal
    return _parse_constant(ctx, node)


def _parse_constant(ctx: TreeSitterEmitContext, node) -> LiteralPattern:
    """Parse a constant value node into a LiteralPattern."""
    text = ctx.node_text(node)
    match node.type:
        case "null_literal":
            return LiteralPattern(value=None)
        case "integer_literal":
            return LiteralPattern(value=int(text))
        case "real_literal":
            return LiteralPattern(value=float(text))
        case "string_literal":
            return LiteralPattern(value=text.strip('"'))
        case "character_literal":
            return LiteralPattern(value=text.strip("'"))
        case "boolean_literal":
            return LiteralPattern(value=text == "true")
        case _:
            return LiteralPattern(value=text)
```

- [ ] **Step 3: Verify import**

Run: `poetry run python -c "from interpreter.frontends.csharp.patterns import parse_csharp_pattern; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/csharp/patterns.py interpreter/frontends/csharp/node_types.py
git commit -m "feat: C# parse_csharp_pattern — tree-sitter to Pattern ADT"
```

---

### Task 3: Refactor `lower_switch_expr` and `lower_switch`

**Files:**
- Modify: `interpreter/frontends/csharp/control_flow.py`

- [ ] **Step 1: Refactor `lower_switch_expr` (lines 245-298)**

Replace with:

```python
def lower_switch_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower C# 8 switch expression: subject switch { pattern => expr, ... }."""
    from interpreter.frontends.common.patterns import (
        WildcardPattern, CapturePattern, compile_pattern_test, compile_pattern_bindings,
    )
    from interpreter.frontends.csharp.patterns import parse_csharp_pattern

    named_children = [c for c in node.children if c.is_named]
    subject_node = named_children[0] if named_children else node
    subject_reg = ctx.lower_expr(subject_node)

    result_var = f"__switch_expr_{ctx.label_counter}"
    end_label = ctx.fresh_label("switch_expr_end")

    arms = [c for c in node.children if c.type == NT.SWITCH_EXPRESSION_ARM]

    for arm in arms:
        arm_children = [c for c in arm.children if c.is_named]
        if len(arm_children) < 2:
            continue
        pattern_node = arm_children[0]
        value_node = arm_children[-1]

        pattern = parse_csharp_pattern(ctx, pattern_node)

        arm_label = ctx.fresh_label("switch_arm")
        next_label = ctx.fresh_label("switch_arm_next")

        if isinstance(pattern, (WildcardPattern, CapturePattern)):
            compile_pattern_bindings(ctx, subject_reg, pattern)
            val_reg = ctx.lower_expr(value_node)
            ctx.emit(Opcode.DECL_VAR, operands=[result_var, val_reg])
            ctx.emit(Opcode.BRANCH, label=end_label)
        else:
            test_reg = compile_pattern_test(ctx, subject_reg, pattern)
            ctx.emit(
                Opcode.BRANCH_IF,
                operands=[test_reg],
                label=f"{arm_label},{next_label}",
            )
            ctx.emit(Opcode.LABEL, label=arm_label)
            compile_pattern_bindings(ctx, subject_reg, pattern)
            val_reg = ctx.lower_expr(value_node)
            ctx.emit(Opcode.DECL_VAR, operands=[result_var, val_reg])
            ctx.emit(Opcode.BRANCH, label=end_label)
            ctx.emit(Opcode.LABEL, label=next_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg
```

- [ ] **Step 2: Refactor `lower_switch` (lines 185-242)**

Replace with:

```python
def lower_switch(ctx: TreeSitterEmitContext, node) -> None:
    """Lower switch statement with pattern matching."""
    from interpreter.frontends.common.patterns import (
        WildcardPattern, CapturePattern, compile_pattern_test, compile_pattern_bindings,
    )
    from interpreter.frontends.csharp.patterns import parse_csharp_pattern

    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")

    subject_reg = ctx.lower_expr(value_node) if value_node else ctx.fresh_reg()
    end_label = ctx.fresh_label("switch_end")

    ctx.break_target_stack.append(end_label)

    sections = (
        [c for c in body_node.children if c.type == NT.SWITCH_SECTION]
        if body_node
        else []
    )

    for section in sections:
        # Find pattern node — could be constant_pattern, declaration_pattern, recursive_pattern, or default
        pattern_node = next(
            (c for c in section.children if c.type in (
                NT.CONSTANT_PATTERN, NT.DECLARATION_PATTERN, NT.RECURSIVE_PATTERN,
            )),
            None,
        )
        is_default = any(
            c.type == "default_switch_label" or (not c.is_named and c.text == b"default")
            for c in section.children
        )
        body_stmts = [
            c for c in section.children
            if c.is_named and c.type not in (
                NT.CONSTANT_PATTERN, NT.DECLARATION_PATTERN, NT.RECURSIVE_PATTERN,
                "case_switch_label",
            )
        ]

        arm_label = ctx.fresh_label("case_arm")
        next_label = ctx.fresh_label("case_next")

        if is_default or pattern_node is None:
            ctx.emit(Opcode.BRANCH, label=arm_label)
        else:
            pattern = parse_csharp_pattern(ctx, pattern_node)
            if isinstance(pattern, (WildcardPattern, CapturePattern)):
                compile_pattern_bindings(ctx, subject_reg, pattern)
                ctx.emit(Opcode.BRANCH, label=arm_label)
            else:
                test_reg = compile_pattern_test(ctx, subject_reg, pattern)
                ctx.emit(
                    Opcode.BRANCH_IF,
                    operands=[test_reg],
                    label=f"{arm_label},{next_label}",
                )

        ctx.emit(Opcode.LABEL, label=arm_label)
        for stmt in body_stmts:
            ctx.lower_stmt(stmt)
        ctx.emit(Opcode.BRANCH, label=end_label)
        ctx.emit(Opcode.LABEL, label=next_label)

    ctx.break_target_stack.pop()
    ctx.emit(Opcode.LABEL, label=end_label)
```

- [ ] **Step 3: Run existing C# tests**

Run: `poetry run python -m pytest tests/unit/test_csharp_frontend.py tests/unit/rosetta/ -k csharp -v --tb=short`
Expected: All PASS — existing switch behavior preserved

- [ ] **Step 4: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/csharp/control_flow.py
git commit -m "refactor: C# lower_switch/lower_switch_expr use Pattern ADT"
```

---

### Task 4: Integration tests

**Files:**
- Modify: `tests/integration/test_csharp_pattern_matching.py`

- [ ] **Step 1: Add integration tests**

Add to `tests/integration/test_csharp_pattern_matching.py`:

```python
class TestCSharpSwitchExprPatterns:
    def test_switch_expr_constant_null(self):
        """constant_pattern: null => "null"."""
        local_vars = _run_csharp("""\
class M {
    static string Test(object x) {
        return x switch {
            null => "null",
            _ => "other"
        };
    }
    static string result = Test(null);
}
""", max_steps=1000)
        assert isinstance(local_vars["result"], str) and local_vars["result"] == "null"

    def test_switch_expr_discard(self):
        """discard: _ => "fallback"."""
        local_vars = _run_csharp("""\
class M {
    static string Test(int x) {
        return x switch {
            1 => "one",
            _ => "other"
        };
    }
    static string result = Test(99);
}
""", max_steps=1000)
        assert isinstance(local_vars["result"], str) and local_vars["result"] == "other"

    def test_switch_expr_declaration_pattern_int(self):
        """declaration_pattern: int i => "integer"."""
        local_vars = _run_csharp("""\
class M {
    static string Classify(object x) {
        return x switch {
            int i => "integer",
            _ => "other"
        };
    }
    static string result = Classify(42);
}
""", max_steps=1000)
        assert isinstance(local_vars["result"], str) and local_vars["result"] == "integer"

    def test_switch_expr_var_pattern(self):
        """declaration_pattern with var: var x => x."""
        local_vars = _run_csharp("""\
class M {
    static int Identity(object x) {
        return x switch {
            var v => v
        };
    }
    static int result = Identity(42);
}
""", max_steps=1000)
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 42

    def test_switch_expr_recursive_pattern(self):
        """recursive_pattern: Circle { Radius: 0 } => "point"."""
        local_vars = _run_csharp("""\
class Circle {
    public int Radius;
    public Circle(int r) { Radius = r; }
}
class M {
    static string Describe(Circle c) {
        return c switch {
            Circle { Radius: 0 } => "point",
            _ => "circle"
        };
    }
    static string result = Describe(new Circle(0));
}
""", max_steps=2000)
        assert isinstance(local_vars["result"], str) and local_vars["result"] == "point"

    def test_switch_expr_recursive_with_capture(self):
        """recursive_pattern with var capture: Circle { Radius: var r } => r."""
        local_vars = _run_csharp("""\
class Circle {
    public int Radius;
    public Circle(int r) { Radius = r; }
}
class M {
    static int GetRadius(Circle c) {
        return c switch {
            Circle { Radius: var r } => r,
            _ => -1
        };
    }
    static int result = GetRadius(new Circle(5));
}
""", max_steps=2000)
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 5


class TestCSharpSwitchStmtPatterns:
    def test_switch_stmt_declaration_pattern(self):
        """switch statement with case int i:."""
        local_vars = _run_csharp("""\
class M {
    static string Classify(object x) {
        string result = "unknown";
        switch (x) {
            case int i:
                result = "integer";
                break;
            case string s:
                result = "string";
                break;
            default:
                result = "other";
                break;
        }
        return result;
    }
    static string result = Classify(42);
}
""", max_steps=1500)
        assert isinstance(local_vars["result"], str) and local_vars["result"] == "integer"
```

- [ ] **Step 2: Run tests**

Run: `poetry run python -m pytest tests/integration/test_csharp_pattern_matching.py -v`
Expected: All PASS (some may need debugging — recursive patterns depend on field access working)

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m black . && poetry run python -m pytest -x --tb=short`
Expected: All pass, no regressions

- [ ] **Step 4: Close issue and push**

```bash
bd update red-dragon-u0gv --status closed
git add tests/integration/test_csharp_pattern_matching.py
git commit -m "test: C# pattern matching integration tests"
git push origin main
```
