# Kotlin Property Getters/Setters Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support Kotlin custom property accessors (`get()/set()`) by emitting synthetic getter/setter methods and intercepting `this.x` access to call them.

**Architecture:** Common property-accessor infrastructure (registration + emit helpers) in `common/property_accessors.py`. Kotlin frontend parses `getter`/`setter` sibling nodes, emits synthetic methods, handles `field` keyword, and wires navigation expressions to use emit helpers. No VM changes.

**Tech Stack:** Python 3.13+, tree-sitter, pytest

**Spec:** `docs/superpowers/specs/2026-03-16-kotlin-property-accessors-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `interpreter/frontends/common/property_accessors.py` | Create | Registration + emit helpers for property accessors |
| `interpreter/frontends/context.py` | Modify | Add `property_accessors` dict field |
| `interpreter/frontends/kotlin/node_types.py` | Modify | Add `PARAMETER_WITH_OPTIONAL_TYPE` constant |
| `interpreter/frontends/kotlin/declarations.py` | Modify | Parse getter/setter siblings, emit synthetic methods, handle `field` |
| `interpreter/frontends/kotlin/expressions.py` | Modify | Wire `lower_navigation_expr` and `lower_kotlin_store_target` to use emit helpers |
| `interpreter/frontends/kotlin/frontend.py` | Modify | Remove getter/setter no-op dispatch (handled in class body) |
| `tests/unit/test_kotlin_frontend.py` | Modify | Unit tests for IR emission |
| `tests/integration/test_kotlin_frontend_execution.py` | Modify | Integration tests for accessor behavior |

---

## Chunk 1: Common Infrastructure + Context

### Task 1: Add `property_accessors` to `TreeSitterEmitContext`

**Files:**
- Modify: `interpreter/frontends/context.py:139` (after `byref_params`)

- [ ] **Step 1: Add the field**

In `interpreter/frontends/context.py`, add after line 139 (`byref_params: set[str] = field(default_factory=set)`):

```python
    # Property accessor tracking: class_name -> {prop_name -> {"get", "set"}}
    property_accessors: dict[str, dict[str, set[str]]] = field(default_factory=dict)

    # Temporary: backing field name for `field` keyword in getter/setter bodies
    _accessor_backing_field: str = ""
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `poetry run python -m pytest tests/unit/test_kotlin_frontend.py -x -q`
Expected: All pass (no behavioral change)

- [ ] **Step 3: Commit**

```bash
git add interpreter/frontends/context.py
git commit -m "feat: add property_accessors dict to TreeSitterEmitContext"
```

---

### Task 2: Create common property accessor helpers

**Files:**
- Create: `interpreter/frontends/common/property_accessors.py`
- Test: `tests/unit/test_property_accessors.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_property_accessors.py`:

```python
"""Tests for common property accessor registration and emit helpers."""

from __future__ import annotations

from interpreter.ir import IRInstruction, Opcode
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.common.property_accessors import (
    register_property_accessor,
    has_property_accessor,
    emit_field_load_or_getter,
    emit_field_store_or_setter,
)


class TestPropertyAccessorRegistration:
    def test_register_getter(self):
        """Registering a getter should be queryable."""
        ctx = _make_ctx()
        register_property_accessor(ctx, "Foo", "x", "get")
        assert has_property_accessor(ctx, "Foo", "x", "get")

    def test_register_setter(self):
        """Registering a setter should be queryable."""
        ctx = _make_ctx()
        register_property_accessor(ctx, "Foo", "x", "set")
        assert has_property_accessor(ctx, "Foo", "x", "set")

    def test_unregistered_returns_false(self):
        """Querying an unregistered accessor should return False."""
        ctx = _make_ctx()
        assert not has_property_accessor(ctx, "Foo", "x", "get")

    def test_register_both(self):
        """Can register both getter and setter for same property."""
        ctx = _make_ctx()
        register_property_accessor(ctx, "Foo", "x", "get")
        register_property_accessor(ctx, "Foo", "x", "set")
        assert has_property_accessor(ctx, "Foo", "x", "get")
        assert has_property_accessor(ctx, "Foo", "x", "set")


class TestEmitFieldLoadOrGetter:
    def test_without_getter_emits_load_field(self):
        """No registered getter should emit plain LOAD_FIELD."""
        ctx = _make_ctx()
        obj_reg = ctx.fresh_reg()
        result = emit_field_load_or_getter(ctx, obj_reg, "Foo", "x", None)
        load_fields = [i for i in ctx.instructions if i.opcode == Opcode.LOAD_FIELD]
        assert len(load_fields) == 1
        assert "x" in load_fields[0].operands

    def test_with_getter_emits_call_method(self):
        """Registered getter should emit CALL_METHOD __get_x__."""
        ctx = _make_ctx()
        register_property_accessor(ctx, "Foo", "x", "get")
        obj_reg = ctx.fresh_reg()
        result = emit_field_load_or_getter(ctx, obj_reg, "Foo", "x", None)
        call_methods = [i for i in ctx.instructions if i.opcode == Opcode.CALL_METHOD]
        assert len(call_methods) == 1
        assert "__get_x__" in call_methods[0].operands


class TestEmitFieldStoreOrSetter:
    def test_without_setter_emits_store_field(self):
        """No registered setter should emit plain STORE_FIELD."""
        ctx = _make_ctx()
        obj_reg = ctx.fresh_reg()
        val_reg = ctx.fresh_reg()
        emit_field_store_or_setter(ctx, obj_reg, "Foo", "x", val_reg, None)
        store_fields = [i for i in ctx.instructions if i.opcode == Opcode.STORE_FIELD]
        assert len(store_fields) == 1
        assert "x" in store_fields[0].operands

    def test_with_setter_emits_call_method(self):
        """Registered setter should emit CALL_METHOD __set_x__."""
        ctx = _make_ctx()
        register_property_accessor(ctx, "Foo", "x", "set")
        obj_reg = ctx.fresh_reg()
        val_reg = ctx.fresh_reg()
        emit_field_store_or_setter(ctx, obj_reg, "Foo", "x", val_reg, None)
        call_methods = [i for i in ctx.instructions if i.opcode == Opcode.CALL_METHOD]
        assert len(call_methods) == 1
        assert "__set_x__" in call_methods[0].operands


def _make_ctx() -> TreeSitterEmitContext:
    """Create a minimal TreeSitterEmitContext for testing."""
    from interpreter.frontends.context import GrammarConstants
    from interpreter.frontend_observer import FrontendObserver
    from interpreter.constants import Language

    return TreeSitterEmitContext(
        source=b"",
        language=Language.KOTLIN,
        observer=FrontendObserver(),
        constants=GrammarConstants(),
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_property_accessors.py -v`
Expected: FAIL with `ImportError` (module doesn't exist yet)

- [ ] **Step 3: Create the implementation**

Create `interpreter/frontends/common/property_accessors.py`:

```python
"""Common property accessor registration and emit helpers.

Reusable by any frontend that supports property getters/setters
(Kotlin, C#, JavaScript/TypeScript, Scala).
"""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.ir import Opcode


def register_property_accessor(
    ctx: TreeSitterEmitContext, class_name: str, prop_name: str, kind: str
) -> None:
    """Record that *prop_name* on *class_name* has a custom accessor.

    *kind* is ``"get"`` or ``"set"``.
    """
    ctx.property_accessors.setdefault(class_name, {}).setdefault(
        prop_name, set()
    ).add(kind)


def has_property_accessor(
    ctx: TreeSitterEmitContext, class_name: str, prop_name: str, kind: str
) -> bool:
    """Check whether *prop_name* on *class_name* has a custom *kind* accessor."""
    return kind in ctx.property_accessors.get(class_name, {}).get(
        prop_name, set()
    )


def emit_field_load_or_getter(
    ctx: TreeSitterEmitContext,
    obj_reg: str,
    class_name: str,
    field_name: str,
    node,
) -> str:
    """Emit CALL_METHOD for getter if registered, otherwise plain LOAD_FIELD."""
    if has_property_accessor(ctx, class_name, field_name, "get"):
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_METHOD,
            result_reg=reg,
            operands=[obj_reg, f"__get_{field_name}__"],
            node=node,
        )
        return reg
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg


def emit_field_store_or_setter(
    ctx: TreeSitterEmitContext,
    obj_reg: str,
    class_name: str,
    field_name: str,
    val_reg: str,
    node,
) -> None:
    """Emit CALL_METHOD for setter if registered, otherwise plain STORE_FIELD."""
    if has_property_accessor(ctx, class_name, field_name, "set"):
        ctx.emit(
            Opcode.CALL_METHOD,
            result_reg=ctx.fresh_reg(),
            operands=[obj_reg, f"__set_{field_name}__", val_reg],
            node=node,
        )
        return
    ctx.emit(
        Opcode.STORE_FIELD,
        operands=[obj_reg, field_name, val_reg],
        node=node,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_property_accessors.py -v`
Expected: All 4 pass

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/common/property_accessors.py tests/unit/test_property_accessors.py
git commit -m "feat: add common property accessor registration and emit helpers"
```

---

## Chunk 2: Kotlin Getter/Setter Lowering

### Task 3: Emit synthetic getter/setter methods in class body lowering

**Files:**
- Modify: `interpreter/frontends/kotlin/node_types.py:104` (add `PARAMETER_WITH_OPTIONAL_TYPE`)
- Modify: `interpreter/frontends/kotlin/declarations.py:272-307`
- Test: `tests/unit/test_kotlin_frontend.py`

This is the core task. We:
1. Add the `PARAMETER_WITH_OPTIONAL_TYPE` node type constant
2. Modify `_lower_class_body_with_companions` to track the most recent `property_declaration` name
3. When a `getter` or `setter` node follows, emit a synthetic method
4. Handle the `field` keyword inside accessor bodies
5. Register the accessor

- [ ] **Step 1: Write the failing unit tests**

Add to `tests/unit/test_kotlin_frontend.py`:

```python
class TestKotlinPropertyAccessors:
    """Tests for custom property getter/setter IR emission."""

    def test_getter_emits_synthetic_method(self):
        """Property getter should emit a __get_x__ method with LOAD_FIELD."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        get() = field + 1
}""")
        labels = _find_all(ir, Opcode.LABEL)
        getter_labels = [
            inst for inst in labels if inst.label and "__get_x__" in inst.label
        ]
        assert len(getter_labels) >= 1, "Expected a __get_x__ method label"
        # The getter body should contain LOAD_FIELD for the backing field
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any(
            "x" in inst.operands for inst in load_fields
        ), "Expected LOAD_FIELD with field 'x'"

    def test_setter_emits_synthetic_method(self):
        """Property setter should emit a __set_x__ method with STORE_FIELD."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        set(value) { field = value * 2 }
}""")
        labels = _find_all(ir, Opcode.LABEL)
        setter_labels = [
            inst for inst in labels if inst.label and "__set_x__" in inst.label
        ]
        assert len(setter_labels) >= 1, "Expected a __set_x__ method label"
        # The setter body should contain STORE_FIELD for the backing field
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any(
            "x" in inst.operands for inst in store_fields
        ), "Expected STORE_FIELD with field 'x'"

    def test_getter_setter_both_emitted(self):
        """Both getter and setter should produce synthetic methods."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        get() = field + 1
        set(value) { field = value * 2 }
}""")
        labels = _find_all(ir, Opcode.LABEL)
        label_names = [inst.label for inst in labels if inst.label]
        assert any("__get_x__" in lbl for lbl in label_names)
        assert any("__set_x__" in lbl for lbl in label_names)

    def test_property_without_accessors_unchanged(self):
        """Property without custom accessors should not emit synthetic methods."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
}""")
        labels = _find_all(ir, Opcode.LABEL)
        label_names = [inst.label for inst in labels if inst.label]
        assert not any("__get_" in lbl for lbl in label_names)
        assert not any("__set_" in lbl for lbl in label_names)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_kotlin_frontend.py::TestKotlinPropertyAccessors -v`
Expected: FAIL (no `__get_x__` labels emitted yet)

- [ ] **Step 3: Implement getter/setter lowering**

In `interpreter/frontends/kotlin/declarations.py`, add these new functions and modify `_lower_class_body_with_companions`.

First, add `PARAMETER_WITH_OPTIONAL_TYPE` to `interpreter/frontends/kotlin/node_types.py` after line 104 (`GETTER = "getter"`):

```python
    PARAMETER_WITH_OPTIONAL_TYPE = "parameter_with_optional_type"
```

Then in `interpreter/frontends/kotlin/declarations.py`, add imports at the top (after existing imports):

```python
from interpreter.frontends.common.property_accessors import register_property_accessor
```

Then add these helper functions before `_lower_class_body_with_companions`:

```python
def _emit_synthetic_getter(
    ctx: TreeSitterEmitContext, prop_name: str, getter_node
) -> None:
    """Emit a synthetic __get_<prop>__ method from a getter node."""
    func_name = f"__get_{prop_name}__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=getter_node)
    ctx.emit(Opcode.LABEL, label=func_label)
    _emit_this_param(ctx)

    # Set backing field context so 'field' resolves to LOAD_FIELD/STORE_FIELD
    prev_backing = ctx._accessor_backing_field
    ctx._accessor_backing_field = prop_name

    body_node = next(
        (c for c in getter_node.children if c.type == KNT.FUNCTION_BODY), None
    )
    expr_reg = ""
    if body_node:
        expr_reg = _lower_function_body(ctx, body_node)

    ctx._accessor_backing_field = prev_backing

    if expr_reg:
        ctx.emit(Opcode.RETURN, operands=[expr_reg])
    else:
        none_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CONST,
            result_reg=none_reg,
            operands=[ctx.constants.default_return_value],
        )
        ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])


def _emit_synthetic_setter(
    ctx: TreeSitterEmitContext, prop_name: str, setter_node
) -> None:
    """Emit a synthetic __set_<prop>__ method from a setter node."""
    func_name = f"__set_{prop_name}__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=setter_node)
    ctx.emit(Opcode.LABEL, label=func_label)
    _emit_this_param(ctx)

    # Extract setter parameter name (default: "value")
    param_name = "value"
    param_node = next(
        (c for c in setter_node.children if c.type == KNT.PARAMETER_WITH_OPTIONAL_TYPE),
        None,
    )
    if param_node:
        id_node = next(
            (c for c in param_node.children if c.type == KNT.SIMPLE_IDENTIFIER), None
        )
        if id_node:
            param_name = ctx.node_text(id_node)

    # Emit parameter
    param_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=param_reg,
        operands=[f"{constants.PARAM_PREFIX}{param_name}"],
    )
    ctx.emit(Opcode.DECL_VAR, operands=[param_name, param_reg])

    # Set backing field context
    prev_backing = ctx._accessor_backing_field
    ctx._accessor_backing_field = prop_name

    body_node = next(
        (c for c in setter_node.children if c.type == KNT.FUNCTION_BODY), None
    )
    if body_node:
        _lower_function_body(ctx, body_node)

    ctx._accessor_backing_field = prev_backing

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, func_reg])
```

Then modify `_lower_class_body_with_companions` to track the most recent property name and handle getter/setter:

```python
def _lower_class_body_with_companions(
    ctx: TreeSitterEmitContext, node, primary_ctor_params: list[str] = []
) -> None:
    """Lower class_body, handling companion_object children specially.

    Collects field initializers from property declarations and emits
    a synthetic ``__init__`` constructor when field inits are present.
    Getter/setter sibling nodes are paired with the preceding property_declaration.
    """
    named_children = [c for c in node.children if c.is_named]

    # Collect field initializers from property declarations
    field_inits: list[FieldInit] = [
        init
        for c in named_children
        if c.type == KNT.PROPERTY_DECLARATION
        for init in [_collect_kotlin_field_init(ctx, c)]
        if init is not None
    ]

    last_property_name = ""
    for child in named_children:
        if child.type == KNT.PROPERTY_DECLARATION:
            var_decl = next(
                (c for c in child.children if c.type == KNT.VARIABLE_DECLARATION), None
            )
            last_property_name = (
                _extract_property_name(ctx, var_decl) if var_decl else ""
            )
        elif child.type == KNT.GETTER and last_property_name:
            _emit_synthetic_getter(ctx, last_property_name, child)
            register_property_accessor(
                ctx, ctx._current_class_name, last_property_name, "get"
            )
            continue
        elif child.type == KNT.SETTER and last_property_name:
            _emit_synthetic_setter(ctx, last_property_name, child)
            register_property_accessor(
                ctx, ctx._current_class_name, last_property_name, "set"
            )
            continue

        if child.type == KNT.COMPANION_OBJECT:
            _lower_companion_object(ctx, child)
        elif child.type == KNT.FUNCTION_DECLARATION:
            lower_function_decl(ctx, child, inject_this=True)
        elif child.type == KNT.SECONDARY_CONSTRUCTOR:
            lower_secondary_constructor(ctx, child, primary_ctor_params, field_inits)
        elif (
            child.type == KNT.PROPERTY_DECLARATION
            and _collect_kotlin_field_init(ctx, child) is not None
        ):
            continue  # Skip — will be emitted via synthetic __init__
        else:
            ctx.lower_stmt(child)

    if field_inits:
        emit_synthetic_init(ctx, field_inits)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_kotlin_frontend.py::TestKotlinPropertyAccessors -v`
Expected: All 4 pass

- [ ] **Step 5: Run full Kotlin unit tests for regression**

Run: `poetry run python -m pytest tests/unit/test_kotlin_frontend.py -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add interpreter/frontends/kotlin/node_types.py interpreter/frontends/kotlin/declarations.py tests/unit/test_kotlin_frontend.py
git commit -m "feat: emit synthetic getter/setter methods for Kotlin property accessors"
```

---

### Task 4: Handle `field` keyword in getter/setter bodies

**Files:**
- Modify: `interpreter/frontends/kotlin/expressions.py` (identifier lowering + assignment target)
- Test: `tests/unit/test_kotlin_frontend.py`

The `field` keyword appears as a `simple_identifier` with text `"field"`. When `ctx._accessor_backing_field` is set (we're inside a getter/setter body), `field` in read position should emit `LOAD_FIELD this "<prop>"` and in write position should emit `STORE_FIELD this "<prop>" val`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_kotlin_frontend.py` inside `TestKotlinPropertyAccessors`:

```python
    def test_field_keyword_in_getter_emits_load_field(self):
        """'field' in getter body should emit LOAD_FIELD this 'x'."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        get() = field
}""")
        load_fields = _find_all(ir, Opcode.LOAD_FIELD)
        assert any(
            "x" in inst.operands and any("this" in str(op) or op == "this" for op in inst.operands)
            for inst in load_fields
        ), f"Expected LOAD_FIELD with 'this' and 'x', got: {[(inst.operands) for inst in load_fields]}"

    def test_field_keyword_in_setter_emits_store_field(self):
        """'field = value' in setter body should emit STORE_FIELD this 'x'."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        set(value) { field = value }
}""")
        store_fields = _find_all(ir, Opcode.STORE_FIELD)
        assert any(
            "x" in inst.operands
            for inst in store_fields
        ), f"Expected STORE_FIELD with field 'x', got: {[(inst.operands) for inst in store_fields]}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_kotlin_frontend.py::TestKotlinPropertyAccessors::test_field_keyword_in_getter_emits_load_field tests/unit/test_kotlin_frontend.py::TestKotlinPropertyAccessors::test_field_keyword_in_setter_emits_store_field -v`
Expected: FAIL (field is lowered as plain identifier, not LOAD_FIELD)

- [ ] **Step 3: Add field keyword handling for read position**

In `interpreter/frontends/kotlin/expressions.py`, create a new function that wraps `lower_identifier` for Kotlin:

```python
def lower_kotlin_identifier(ctx: TreeSitterEmitContext, node) -> str:
    """Lower identifier, intercepting 'field' inside property accessor bodies."""
    text = ctx.node_text(node)
    if text == "field" and ctx._accessor_backing_field:
        this_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_FIELD,
            result_reg=reg,
            operands=[this_reg, ctx._accessor_backing_field],
            node=node,
        )
        return reg
    return lower_identifier(ctx, node)
```

Then in `interpreter/frontends/kotlin/frontend.py`, change the `SIMPLE_IDENTIFIER` dispatch:

```python
# Change from:
KNT.SIMPLE_IDENTIFIER: common_expr.lower_identifier,
# Change to:
KNT.SIMPLE_IDENTIFIER: kotlin_expr.lower_kotlin_identifier,
```

- [ ] **Step 4: Add field keyword handling for write position (assignment target)**

In `interpreter/frontends/kotlin/expressions.py`, modify `lower_kotlin_store_target` (line 917). Add a check at the top of the `SIMPLE_IDENTIFIER` branch:

```python
def lower_kotlin_store_target(
    ctx: TreeSitterEmitContext, target, val_reg: str, parent_node
) -> None:
    if target.type == KNT.SIMPLE_IDENTIFIER:
        text = ctx.node_text(target)
        if text == "field" and ctx._accessor_backing_field:
            this_reg = ctx.fresh_reg()
            ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[this_reg, ctx._accessor_backing_field, val_reg],
                node=parent_node,
            )
            return
        ctx.emit(
            Opcode.STORE_VAR,
            operands=[ctx.node_text(target), val_reg],
            node=parent_node,
        )
    elif target.type == KNT.NAVIGATION_EXPRESSION:
        # ... rest unchanged
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_kotlin_frontend.py::TestKotlinPropertyAccessors -v`
Expected: All 6 pass

- [ ] **Step 6: Commit**

```bash
git add interpreter/frontends/kotlin/expressions.py interpreter/frontends/kotlin/frontend.py tests/unit/test_kotlin_frontend.py
git commit -m "feat: handle 'field' keyword in Kotlin property accessor bodies"
```

---

## Chunk 3: Navigation Expression Interception + Integration Tests

### Task 5: Wire `lower_navigation_expr` to use emit helpers

**Files:**
- Modify: `interpreter/frontends/kotlin/expressions.py:150-163`
- Test: `tests/unit/test_kotlin_frontend.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_kotlin_frontend.py` inside `TestKotlinPropertyAccessors`:

```python
    def test_this_dot_x_with_getter_emits_call_method(self):
        """this.x with custom getter should emit CALL_METHOD __get_x__."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        get() = field + 1
    fun bar(): Int {
        return this.x
    }
}""")
        call_methods = _find_all(ir, Opcode.CALL_METHOD)
        assert any(
            "__get_x__" in inst.operands for inst in call_methods
        ), f"Expected CALL_METHOD with __get_x__, got: {[(inst.operands) for inst in call_methods]}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_kotlin_frontend.py::TestKotlinPropertyAccessors::test_this_dot_x_with_getter_emits_call_method -v`
Expected: FAIL (emits LOAD_FIELD instead of CALL_METHOD)

- [ ] **Step 3: Modify `lower_navigation_expr`**

In `interpreter/frontends/kotlin/expressions.py`, modify `lower_navigation_expr` (line 150):

```python
def lower_navigation_expr(ctx: TreeSitterEmitContext, node) -> str:
    from interpreter.frontends.common.property_accessors import (
        emit_field_load_or_getter,
    )

    named_children = [c for c in node.children if c.is_named]
    if len(named_children) < 2:
        return lower_const_literal(ctx, node)
    obj_node = named_children[0]
    obj_reg = ctx.lower_expr(obj_node)
    field_name = _extract_nav_field_name(ctx, named_children[-1])

    # Intercept this.x when a custom getter is registered
    if obj_node.type == KNT.THIS_EXPRESSION and ctx._current_class_name:
        return emit_field_load_or_getter(
            ctx, obj_reg, ctx._current_class_name, field_name, node
        )

    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_kotlin_frontend.py::TestKotlinPropertyAccessors::test_this_dot_x_with_getter_emits_call_method -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/kotlin/expressions.py tests/unit/test_kotlin_frontend.py
git commit -m "feat: intercept this.x reads with custom getter in navigation_expr"
```

---

### Task 6: Wire `lower_kotlin_store_target` for setter interception

**Files:**
- Modify: `interpreter/frontends/kotlin/expressions.py:926-938`
- Test: `tests/unit/test_kotlin_frontend.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_kotlin_frontend.py` inside `TestKotlinPropertyAccessors`:

```python
    def test_this_dot_x_assign_with_setter_emits_call_method(self):
        """this.x = val with custom setter should emit CALL_METHOD __set_x__."""
        ir = _parse_kotlin("""\
class Foo {
    var x: Int = 0
        set(value) { field = value * 2 }
    fun bar() {
        this.x = 5
    }
}""")
        call_methods = _find_all(ir, Opcode.CALL_METHOD)
        assert any(
            "__set_x__" in inst.operands for inst in call_methods
        ), f"Expected CALL_METHOD with __set_x__, got: {[(inst.operands) for inst in call_methods]}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_kotlin_frontend.py::TestKotlinPropertyAccessors::test_this_dot_x_assign_with_setter_emits_call_method -v`
Expected: FAIL (emits STORE_FIELD instead of CALL_METHOD)

- [ ] **Step 3: Modify `lower_kotlin_store_target` for navigation expression branch**

In `interpreter/frontends/kotlin/expressions.py`, modify the `NAVIGATION_EXPRESSION` branch of `lower_kotlin_store_target` (line 926):

```python
    elif target.type == KNT.NAVIGATION_EXPRESSION:
        from interpreter.frontends.common.property_accessors import (
            emit_field_store_or_setter,
        )

        named_children = [c for c in target.children if c.is_named]
        if len(named_children) >= 2:
            obj_node = named_children[0]
            obj_reg = ctx.lower_expr(obj_node)
            field_name = _extract_nav_field_name(ctx, named_children[-1])

            # Intercept this.x = val when a custom setter is registered
            if obj_node.type == KNT.THIS_EXPRESSION and ctx._current_class_name:
                emit_field_store_or_setter(
                    ctx,
                    obj_reg,
                    ctx._current_class_name,
                    field_name,
                    val_reg,
                    parent_node,
                )
                return

            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, field_name, val_reg],
                node=parent_node,
            )
        else:
            ctx.emit(
                Opcode.STORE_VAR,
                operands=[ctx.node_text(target), val_reg],
                node=parent_node,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_kotlin_frontend.py::TestKotlinPropertyAccessors::test_this_dot_x_assign_with_setter_emits_call_method -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/kotlin/expressions.py tests/unit/test_kotlin_frontend.py
git commit -m "feat: intercept this.x = val writes with custom setter"
```

---

### Task 7: Remove no-op getter/setter dispatch from frontend.py

**Files:**
- Modify: `interpreter/frontends/kotlin/frontend.py:116-117`

The getter/setter nodes are now handled in `_lower_class_body_with_companions`. The no-op dispatch entries should remain to prevent them from being lowered as unknown statements outside of class bodies (they'd fall through to `lower_expr` → `SYMBOLIC`). However, since getter/setter can only appear inside class bodies, and we handle them there, the no-ops are still correct as a safety net. **Keep them as-is.**

- [ ] **Step 1: Verify no change needed — run existing setter tests**

Run: `poetry run python -m pytest tests/unit/test_kotlin_frontend.py::TestKotlinSetter -v`
Expected: All pass (no-ops still prevent SYMBOLIC emission)

- [ ] **Step 2: No commit needed (no changes)**

---

### Task 8: Integration tests

**Files:**
- Modify: `tests/integration/test_kotlin_frontend_execution.py`

- [ ] **Step 1: Write integration tests**

Add to `tests/integration/test_kotlin_frontend_execution.py`:

```python
class TestKotlinPropertyAccessorExecution:
    """Integration tests for custom property getter/setter execution."""

    def test_getter_transforms_read(self):
        """Custom getter should transform the read value."""
        vars_ = _run_kotlin(
            """\
class Foo {
    var x: Int = 10
        get() = field + 1
    fun getX(): Int {
        return this.x
    }
}
val foo = Foo()
val result = foo.getX()""",
            max_steps=1000,
        )
        assert vars_["result"] == 11

    def test_setter_transforms_write(self):
        """Custom setter should transform the written value."""
        vars_ = _run_kotlin(
            """\
class Foo {
    var x: Int = 0
        set(value) { field = value * 2 }
    fun setX(v: Int) {
        this.x = v
    }
    fun getX(): Int {
        return this.x
    }
}
val foo = Foo()
foo.setX(5)
val result = foo.getX()""",
            max_steps=1500,
        )
        assert vars_["result"] == 10

    def test_getter_and_setter_together(self):
        """Both getter and setter should apply their transformations."""
        vars_ = _run_kotlin(
            """\
class Foo {
    var x: Int = 0
        get() = field + 1
        set(value) { field = value * 2 }
    fun setX(v: Int) {
        this.x = v
    }
    fun getX(): Int {
        return this.x
    }
}
val foo = Foo()
foo.setX(5)
val result = foo.getX()""",
            max_steps=1500,
        )
        # setter stores 5 * 2 = 10, getter returns 10 + 1 = 11
        assert vars_["result"] == 11

    def test_property_without_accessors_regression(self):
        """Property without custom accessors should still work as plain field."""
        vars_ = _run_kotlin(
            """\
class Foo {
    var x: Int = 42
    fun getX(): Int {
        return this.x
    }
}
val foo = Foo()
val result = foo.getX()""",
            max_steps=1000,
        )
        assert vars_["result"] == 42
```

- [ ] **Step 2: Run integration tests**

Run: `poetry run python -m pytest tests/integration/test_kotlin_frontend_execution.py::TestKotlinPropertyAccessorExecution -v`
Expected: All 4 pass

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All pass (11775+ tests), no regressions

- [ ] **Step 4: Format with Black**

Run: `poetry run python -m black .`

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_kotlin_frontend_execution.py
git commit -m "feat: add integration tests for Kotlin property accessor execution"
```

---

### Task 9: Final push

- [ ] **Step 1: Push to main**

```bash
git push origin main
```

- [ ] **Step 2: Close issue**

```bash
bd update red-dragon-3l0 --status closed
```
