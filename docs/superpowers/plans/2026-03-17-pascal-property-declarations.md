# Pascal Property Declarations Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support Delphi/Object Pascal property declarations so that `obj.Name` routes through the correct getter/setter, reusing the common property-accessor infrastructure from Kotlin.

**Architecture:** Expand `lower_pascal_decl_type` to traverse class bodies (fields, methods, properties). For each `declProp`, emit synthetic `__get_<prop>__`/`__set_<prop>__` methods. Wire `lower_pascal_dot` and `lower_pascal_assignment` to intercept property access via `_pascal_var_types` tracking.

**Tech Stack:** Python, tree-sitter Pascal grammar, existing `common/property_accessors.py` helpers.

**Spec:** `docs/superpowers/specs/2026-03-17-pascal-property-declarations-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `interpreter/frontends/pascal/node_types.py` | Modify | Add 10 new node type constants |
| `interpreter/frontends/pascal/frontend.py` | Modify | Init `_pascal_var_types` via `_emit_prelude` override |
| `interpreter/frontends/pascal/declarations.py` | Modify | Class body traversal, synthetic init, method lowering, property parsing, `_resolve_object_class` helper |
| `interpreter/frontends/pascal/expressions.py` | Modify | Getter interception in `lower_pascal_dot` |
| `tests/unit/test_pascal_frontend.py` | Modify | Unit tests for IR emission |
| `tests/integration/test_pascal_frontend_execution.py` | Create | Integration tests for property execution (new file) |

**Note:** `_build_context` in `PascalFrontend` is dead code — `BaseFrontend._lower_with_context` constructs the context directly and never calls `_build_context`. Use `_emit_prelude` (called at line 276 of `_base.py`) for Pascal-specific context initialization instead.

**Note:** `_resolve_object_class` is needed by both `expressions.py` (dot access) and `declarations.py` (assignment). Define it in `declarations.py` and import from there into `expressions.py` to avoid circular imports (since `declarations.py` does not import from `expressions.py`).

---

## Chunk 1: Foundation + Class Body Traversal

### Task 1: Node type constants + synthetic `__init__` from fields

**Files:**
- Modify: `interpreter/frontends/pascal/node_types.py:79-88`
- Modify: `interpreter/frontends/pascal/declarations.py:344-372`
- Test: `tests/unit/test_pascal_frontend.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_pascal_frontend.py`:

```python
class TestPascalClassBodyTraversal:
    """Tests for class body traversal: fields -> synthetic __init__, methods."""

    def test_class_with_field_emits_synthetic_init(self):
        """declField inside declClass should produce a synthetic __init__ with STORE_FIELD."""
        source = """\
program M;
type
  TFoo = class
  private
    FName: string;
  end;
begin
end."""
        instructions = _parse_pascal(source)
        # Synthetic __init__ should exist with STORE_FIELD for FName
        labels = _labels_in_order(instructions)
        assert any("__init__" in lbl for lbl in labels), (
            f"Expected __init__ label, got {labels}"
        )
        stores = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("FName" in inst.operands for inst in stores), (
            f"Expected STORE_FIELD for FName, got {[s.operands for s in stores]}"
        )

    def test_class_with_multiple_fields_emits_store_field_per_field(self):
        source = """\
program M;
type
  TPoint = class
  private
    FX: Integer;
    FY: Integer;
  end;
begin
end."""
        instructions = _parse_pascal(source)
        stores = _find_all(instructions, Opcode.STORE_FIELD)
        field_names = [s.operands[1] for s in stores]
        assert "FX" in field_names
        assert "FY" in field_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalClassBodyTraversal -v`
Expected: FAIL — current `lower_pascal_decl_type` does not traverse class body.

- [ ] **Step 3: Add node type constants**

In `interpreter/frontends/pascal/node_types.py`, add after the `K_ELSE` line (line 87):

```python
    K_CLASS = "kClass"

    # -- Property declaration nodes ----------------------------------------
    DECL_PROP = "declProp"
    K_PROPERTY = "kProperty"
    K_READ = "kRead"
    K_WRITE = "kWrite"
    DECL_SECTION = "declSection"
    K_PRIVATE = "kPrivate"
    K_PUBLIC = "kPublic"
    K_PROTECTED = "kProtected"
    DECL_FIELD = "declField"
```

- [ ] **Step 4: Implement class body traversal with field collection and synthetic `__init__`**

In `interpreter/frontends/pascal/declarations.py`, add this import at the top:

```python
from interpreter.frontends.common.property_accessors import (
    register_property_accessor,
    emit_field_store_or_setter,
)
```

Replace `lower_pascal_decl_type` (lines 344-372) with:

```python
def lower_pascal_decl_type(ctx: TreeSitterEmitContext, node) -> None:
    """Lower declType -- emit CLASS_REF for class/record types with body traversal."""
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    class_node = next(
        (c for c in node.children if c.type == PascalNodeType.DECL_CLASS), None
    )

    if id_node is None or class_node is None:
        return

    type_name = ctx.node_text(id_node)
    record_types: set[str] = getattr(ctx, "_pascal_record_types", set())
    record_types.add(type_name)
    ctx._pascal_record_types = record_types
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{type_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{type_name}")

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=class_label)

    prev_class_name = getattr(ctx, "_current_class_name", "")
    ctx._current_class_name = type_name

    # First pass: collect all field names across all declSection children
    field_names = _collect_class_field_names(ctx, class_node)

    # Second pass: emit synthetic __init__, methods, and properties
    _emit_synthetic_init_for_fields(ctx, field_names)

    for section in class_node.children:
        if section.type == PascalNodeType.DECL_SECTION:
            _lower_pascal_class_section(ctx, section, type_name, field_names)

    ctx._current_class_name = prev_class_name

    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(type_name, class_label, [], result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[type_name, cls_reg])


def _collect_class_field_names(ctx: TreeSitterEmitContext, class_node) -> list[str]:
    """Collect all field names from declField nodes across all declSection children."""
    return [
        ctx.node_text(id_node)
        for section in class_node.children
        if section.type == PascalNodeType.DECL_SECTION
        for child in section.children
        if child.type == PascalNodeType.DECL_FIELD
        for id_node in child.children
        if id_node.type == PascalNodeType.IDENTIFIER
    ]


def _emit_synthetic_init_for_fields(
    ctx: TreeSitterEmitContext, field_names: list[str]
) -> None:
    """Emit a synthetic __init__ that stores None for each field."""
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}__init__")
    end_label = ctx.fresh_label("end___init__")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    sym_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=sym_reg,
        operands=[f"{constants.PARAM_PREFIX}this"],
    )
    ctx.emit(Opcode.DECL_VAR, operands=["this", f"%{ctx.reg_counter - 1}"])

    for fname in field_names:
        val_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=val_reg, operands=[ctx.constants.none_literal])
        this_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
        ctx.emit(Opcode.STORE_FIELD, operands=[this_reg, fname, val_reg])

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref("__init__", func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=["__init__", func_reg])


def _lower_pascal_class_section(
    ctx: TreeSitterEmitContext,
    section,
    class_name: str,
    field_names: list[str],
) -> None:
    """Lower children of a declSection (declField, declProc, declProp)."""
    for child in section.children:
        if child.type == PascalNodeType.DECL_PROC:
            _lower_pascal_method(ctx, child)
        elif child.type == PascalNodeType.DECL_PROP:
            _lower_pascal_property(ctx, child, class_name, field_names)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalClassBodyTraversal -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass (no regression from class body traversal changes).

- [ ] **Step 7: Commit**

```bash
git add interpreter/frontends/pascal/node_types.py interpreter/frontends/pascal/declarations.py tests/unit/test_pascal_frontend.py
git commit -m "feat(pascal): add node type constants, traverse class body, emit synthetic __init__"
```

### Task 2: Method lowering with `this` injection

**Files:**
- Modify: `interpreter/frontends/pascal/declarations.py`
- Test: `tests/unit/test_pascal_frontend.py`

- [ ] **Step 1: Write the failing test**

Add to `TestPascalClassBodyTraversal`:

```python
    def test_method_inside_class_has_this_param(self):
        """declProc inside declClass should emit SYMBOLIC param:this."""
        source = """\
program M;
type
  TFoo = class
  public
    procedure DoSomething;
  end;
begin
end."""
        instructions = _parse_pascal(source)
        symbolics = _find_all(instructions, Opcode.SYMBOLIC)
        # Should have param:this from the method (and from __init__)
        this_params = [
            s for s in symbolics if "param:this" in str(s.operands)
        ]
        # At least 2: one from __init__, one from DoSomething
        assert len(this_params) >= 2, (
            f"Expected >= 2 param:this (init + method), got {len(this_params)}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalClassBodyTraversal::test_method_inside_class_has_this_param -v`
Expected: FAIL — `_lower_pascal_method` not yet defined.

- [ ] **Step 3: Implement `_lower_pascal_method`**

Add to `interpreter/frontends/pascal/declarations.py`:

```python
def _lower_pascal_method(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a declProc inside a class -- forward declaration with `this` injected."""
    id_node = next(
        (c for c in node.children if c.type == PascalNodeType.IDENTIFIER), None
    )
    args_node = next(
        (c for c in node.children if c.type == PascalNodeType.DECL_ARGS), None
    )

    func_name = ctx.node_text(id_node) if id_node else "__anon_method"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")

    return_hint = extract_pascal_return_type(ctx, node)

    ctx.emit(Opcode.BRANCH, label=end_label, node=node)
    ctx.emit(Opcode.LABEL, label=func_label)
    ctx.seed_func_return_type(func_label, return_hint)

    # Inject `this` as first parameter
    sym_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=sym_reg,
        operands=[f"{constants.PARAM_PREFIX}this"],
        node=node,
    )
    ctx.emit(Opcode.DECL_VAR, operands=["this", f"%{ctx.reg_counter - 1}"])

    if args_node:
        _lower_pascal_params(ctx, args_node)

    # Forward declarations have no body -- emit default return
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

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalClassBodyTraversal::test_method_inside_class_has_this_param -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add interpreter/frontends/pascal/declarations.py tests/unit/test_pascal_frontend.py
git commit -m "feat(pascal): lower class methods with this parameter injection"
```

### Task 3: Property parsing and synthetic getter/setter emission

**Files:**
- Modify: `interpreter/frontends/pascal/declarations.py`
- Test: `tests/unit/test_pascal_frontend.py`

- [ ] **Step 1: Write the failing test for field-targeted read accessor**

```python
class TestPascalPropertyAccessors:
    """Tests for declProp -> synthetic __get_<prop>__/__set_<prop>__ methods."""

    def test_field_read_accessor_emits_getter_with_load_field(self):
        """property Name: string read FName -> __get_Name__ with LOAD_FIELD this FName."""
        source = """\
program M;
type
  TFoo = class
  private
    FName: string;
  public
    property Name: string read FName;
  end;
begin
end."""
        instructions = _parse_pascal(source)
        labels = _labels_in_order(instructions)
        assert any("__get_Name__" in lbl for lbl in labels), (
            f"Expected __get_Name__ label, got {labels}"
        )
        # Inside __get_Name__, should LOAD_FIELD this "FName"
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert any("FName" in inst.operands for inst in loads), (
            f"Expected LOAD_FIELD with FName, got {[l.operands for l in loads]}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalPropertyAccessors::test_field_read_accessor_emits_getter_with_load_field -v`
Expected: FAIL — `_lower_pascal_property` not yet defined.

- [ ] **Step 3: Implement `_lower_pascal_property`, `_emit_property_getter`, `_emit_property_setter`**

Add to `interpreter/frontends/pascal/declarations.py`:

```python
def _lower_pascal_property(
    ctx: TreeSitterEmitContext,
    node,
    class_name: str,
    field_names: list[str],
) -> None:
    """Lower declProp -- emit synthetic __get_<prop>__ and/or __set_<prop>__ methods."""
    children = node.children
    prop_name = ""
    read_target = ""
    write_target = ""

    # First identifier after kProperty is the property name
    saw_property = False
    saw_read = False
    saw_write = False
    for child in children:
        if child.type == PascalNodeType.K_PROPERTY:
            saw_property = True
        elif child.type == PascalNodeType.K_READ:
            saw_read = True
        elif child.type == PascalNodeType.K_WRITE:
            saw_write = True
        elif child.type == PascalNodeType.IDENTIFIER:
            text = ctx.node_text(child)
            if saw_write:
                write_target = text
                saw_write = False
            elif saw_read:
                read_target = text
                saw_read = False
            elif saw_property and not prop_name:
                prop_name = text

    if not prop_name:
        return

    field_name_set = set(field_names)

    if read_target:
        _emit_property_getter(ctx, class_name, prop_name, read_target, field_name_set)

    if write_target:
        _emit_property_setter(ctx, class_name, prop_name, write_target, field_name_set)


def _emit_property_getter(
    ctx: TreeSitterEmitContext,
    class_name: str,
    prop_name: str,
    target: str,
    field_names: set[str],
) -> None:
    """Emit synthetic __get_<prop>__ method."""
    getter_name = f"__get_{prop_name}__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{getter_name}")
    end_label = ctx.fresh_label(f"end_{getter_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    sym_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=sym_reg,
        operands=[f"{constants.PARAM_PREFIX}this"],
    )
    ctx.emit(Opcode.DECL_VAR, operands=["this", f"%{ctx.reg_counter - 1}"])

    this_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])

    if target in field_names:
        # Field-targeted: LOAD_FIELD this "<target>"
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.LOAD_FIELD,
            result_reg=result_reg,
            operands=[this_reg, target],
        )
    else:
        # Method-targeted: CALL_METHOD this "<target>"
        result_reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.CALL_METHOD,
            result_reg=result_reg,
            operands=[this_reg, target],
        )

    ctx.emit(Opcode.RETURN, operands=[result_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(getter_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[getter_name, func_reg])

    register_property_accessor(ctx, class_name, prop_name, "get")


def _emit_property_setter(
    ctx: TreeSitterEmitContext,
    class_name: str,
    prop_name: str,
    target: str,
    field_names: set[str],
) -> None:
    """Emit synthetic __set_<prop>__ method."""
    setter_name = f"__set_{prop_name}__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{setter_name}")
    end_label = ctx.fresh_label(f"end_{setter_name}")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    sym_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=sym_reg,
        operands=[f"{constants.PARAM_PREFIX}this"],
    )
    ctx.emit(Opcode.DECL_VAR, operands=["this", f"%{ctx.reg_counter - 1}"])

    val_sym = ctx.fresh_reg()
    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=val_sym,
        operands=[f"{constants.PARAM_PREFIX}value"],
    )
    ctx.emit(Opcode.DECL_VAR, operands=["value", f"%{ctx.reg_counter - 1}"])

    this_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
    val_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=val_reg, operands=["value"])

    if target in field_names:
        # Field-targeted: STORE_FIELD this "<target>" value
        ctx.emit(Opcode.STORE_FIELD, operands=[this_reg, target, val_reg])
    else:
        # Method-targeted: CALL_METHOD this "<target>" value
        ctx.emit(
            Opcode.CALL_METHOD,
            result_reg=ctx.fresh_reg(),
            operands=[this_reg, target, val_reg],
        )

    none_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=none_reg,
        operands=[ctx.constants.default_return_value],
    )
    ctx.emit(Opcode.RETURN, operands=[none_reg])
    ctx.emit(Opcode.LABEL, label=end_label)

    func_reg = ctx.fresh_reg()
    ctx.emit_func_ref(setter_name, func_label, result_reg=func_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[setter_name, func_reg])

    register_property_accessor(ctx, class_name, prop_name, "set")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalPropertyAccessors::test_field_read_accessor_emits_getter_with_load_field -v`
Expected: PASS

- [ ] **Step 5: Write additional property tests**

Add to `TestPascalPropertyAccessors`:

```python
    def test_method_write_accessor_emits_setter_with_call_method(self):
        """property Name: string write SetName -> __set_Name__ with CALL_METHOD this SetName."""
        source = """\
program M;
type
  TFoo = class
  private
    FName: string;
    procedure SetName(const AValue: string);
  public
    property Name: string read FName write SetName;
  end;
begin
end."""
        instructions = _parse_pascal(source)
        labels = _labels_in_order(instructions)
        assert any("__set_Name__" in lbl for lbl in labels), (
            f"Expected __set_Name__ label, got {labels}"
        )
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("SetName" in inst.operands for inst in calls), (
            f"Expected CALL_METHOD with SetName, got {[c.operands for c in calls]}"
        )

    def test_read_only_property_no_setter(self):
        """property Name: string read FName (no write) -> only getter, no setter."""
        source = """\
program M;
type
  TFoo = class
  private
    FName: string;
  public
    property Name: string read FName;
  end;
begin
end."""
        instructions = _parse_pascal(source)
        labels = _labels_in_order(instructions)
        assert any("__get_Name__" in lbl for lbl in labels)
        assert not any("__set_Name__" in lbl for lbl in labels), (
            f"Read-only property should not emit setter, got labels {labels}"
        )

    def test_field_write_accessor_emits_store_field(self):
        """property Name: string write FName -> __set_Name__ with STORE_FIELD this FName."""
        source = """\
program M;
type
  TFoo = class
  private
    FName: string;
  public
    property Name: string read FName write FName;
  end;
begin
end."""
        instructions = _parse_pascal(source)
        labels = _labels_in_order(instructions)
        assert any("__set_Name__" in lbl for lbl in labels)
        # The setter body should have STORE_FIELD with FName (from __init__ AND setter)
        stores = _find_all(instructions, Opcode.STORE_FIELD)
        fname_stores = [s for s in stores if "FName" in s.operands]
        # At least 2: one from __init__ (None default) and one from __set_Name__
        assert len(fname_stores) >= 2, (
            f"Expected >= 2 STORE_FIELD for FName, got {len(fname_stores)}"
        )

    def test_method_read_accessor_emits_call_method(self):
        """property Name: string read GetName -> __get_Name__ with CALL_METHOD this GetName."""
        source = """\
program M;
type
  TFoo = class
  private
    FName: string;
    function GetName: string;
  public
    property Name: string read GetName;
  end;
begin
end."""
        instructions = _parse_pascal(source)
        labels = _labels_in_order(instructions)
        assert any("__get_Name__" in lbl for lbl in labels)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        assert any("GetName" in inst.operands for inst in calls), (
            f"Expected CALL_METHOD with GetName, got {[c.operands for c in calls]}"
        )
```

- [ ] **Step 6: Run all property tests**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalPropertyAccessors -v`
Expected: All PASS.

- [ ] **Step 7: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add interpreter/frontends/pascal/declarations.py tests/unit/test_pascal_frontend.py
git commit -m "feat(pascal): parse declProp, emit synthetic getter/setter methods"
```

---

## Chunk 2: Var Type Tracking + Interception + Integration Tests

### Task 4: Variable-to-class type tracking

**Files:**
- Modify: `interpreter/frontends/pascal/frontend.py:51-56`
- Modify: `interpreter/frontends/pascal/declarations.py` (in `lower_pascal_decl_var` and `_lower_pascal_single_param`)
- Test: `tests/unit/test_pascal_frontend.py`

- [ ] **Step 1: Write the failing test**

This test checks that `_pascal_var_types` is populated by examining IR side effects. Since `_build_context` is dead code, we verify type tracking by checking that getter interception works end-to-end (dot access on a typed var emits CALL_METHOD). This test will initially fail because neither var type tracking nor dot interception are wired yet.

```python
class TestPascalVarTypeTracking:
    """Tests for _pascal_var_types population -- verified via getter interception."""

    def test_var_declaration_of_class_type_enables_getter_interception(self):
        """var foo: TFoo should enable foo.Name to route through __get_Name__."""
        source = """\
program M;
type
  TFoo = class
  private
    FName: string;
  public
    property Name: string read FName;
  end;
var
  foo: TFoo;
begin
  foo := TFoo;
  WriteLn(foo.Name);
end."""
        instructions = _parse_pascal(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        getter_calls = [c for c in calls if "__get_Name__" in c.operands]
        assert len(getter_calls) >= 1, (
            f"Expected CALL_METHOD __get_Name__ (var type tracking + getter), "
            f"got {[c.operands for c in calls]}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalVarTypeTracking::test_var_declaration_of_class_type_enables_getter_interception -v`
Expected: FAIL — neither var type tracking nor dot interception implemented yet.

- [ ] **Step 3: Initialize `_pascal_var_types` via `_emit_prelude`**

In `interpreter/frontends/pascal/frontend.py`, replace `_build_context` with `_emit_prelude`:

```python
    def _build_context(self, source: bytes) -> TreeSitterEmitContext:
        ctx = super()._build_context(source)
        # Pascal-specific mutable state stored on the context
        ctx._pascal_current_function_name = ""
        ctx._pascal_record_types = set()
        ctx._pascal_var_types = {}
        return ctx

    def _emit_prelude(self, ctx) -> None:
        """Initialize Pascal-specific mutable state on the context."""
        ctx._pascal_current_function_name = ""
        ctx._pascal_record_types = set()
        ctx._pascal_var_types = {}
```

Note: Keep `_build_context` as-is for now (it's dead but harmless). Add `_emit_prelude` which IS called by `BaseFrontend._lower_with_context`.

- [ ] **Step 4: Populate `_pascal_var_types` in `lower_pascal_decl_var`**

In `interpreter/frontends/pascal/declarations.py`, in `lower_pascal_decl_var`, after the existing `ctx.seed_var_type(var_name, type_hint)` line (line 144), add inside the `else` branch (non-array path):

```python
        pascal_var_types: dict = getattr(ctx, "_pascal_var_types", {})
        if type_name in record_types:
            pascal_var_types[var_name] = type_name
            ctx._pascal_var_types = pascal_var_types
```

Note: `record_types` and `type_name` are already in scope in the `else` branch.

- [ ] **Step 5: Populate `_pascal_var_types` in `_lower_pascal_single_param`**

In `interpreter/frontends/pascal/declarations.py`, in `_lower_pascal_single_param`, after the `ctx.seed_var_type(pname, type_hint)` line (line 285), add:

```python
        record_types: set[str] = getattr(ctx, "_pascal_record_types", set())
        pascal_var_types: dict = getattr(ctx, "_pascal_var_types", {})
        if type_name in record_types:
            pascal_var_types[pname] = type_name
            ctx._pascal_var_types = pascal_var_types
```

Note: `type_name` is already computed at line 264.

- [ ] **Step 6: Note — test still fails**

The test requires both var type tracking AND dot interception (Task 5). It will pass after Task 5. For now, verify no regressions in the full test suite.

Run: `poetry run python -m pytest --tb=short -q --ignore=tests/unit/test_pascal_frontend.py::TestPascalVarTypeTracking`
Expected: All other tests pass.

- [ ] **Step 7: Commit**

```bash
git add interpreter/frontends/pascal/frontend.py interpreter/frontends/pascal/declarations.py tests/unit/test_pascal_frontend.py
git commit -m "feat(pascal): add _pascal_var_types tracking for class-typed variables and params"
```

### Task 5: Getter interception in `lower_pascal_dot` + `_resolve_object_class`

**Files:**
- Modify: `interpreter/frontends/pascal/declarations.py` (add `_resolve_object_class`)
- Modify: `interpreter/frontends/pascal/expressions.py:112-130`
- Test: `tests/unit/test_pascal_frontend.py`

- [ ] **Step 1: Add `_resolve_object_class` to `declarations.py`**

Define `_resolve_object_class` in `declarations.py` (not `expressions.py`) so both modules can use it without circular imports:

```python
def _resolve_object_class(ctx: TreeSitterEmitContext, obj_node) -> str:
    """Resolve the class name of an object node, if known.

    Checks _pascal_var_types for variable identifiers, and
    _current_class_name for 'self' references.
    """
    if obj_node.type == PascalNodeType.IDENTIFIER:
        obj_name = ctx.node_text(obj_node)
        if obj_name == "self":
            return getattr(ctx, "_current_class_name", "")
        pascal_var_types: dict = getattr(ctx, "_pascal_var_types", {})
        return pascal_var_types.get(obj_name, "")
    return ""
```

- [ ] **Step 2: Modify `lower_pascal_dot` for getter interception**

In `interpreter/frontends/pascal/expressions.py`, add imports at top:

```python
from interpreter.frontends.common.property_accessors import emit_field_load_or_getter
from interpreter.frontends.pascal.declarations import _resolve_object_class
```

Replace `lower_pascal_dot` (lines 112-130) with:

```python
def lower_pascal_dot(ctx: TreeSitterEmitContext, node) -> str:
    """Lower exprDot -- first child = object, last child = field name.

    If the object is a class-typed variable with a registered property getter,
    emit CALL_METHOD __get_<field>__ instead of plain LOAD_FIELD.
    """
    named_children = [
        c for c in node.children if c.is_named and c.type not in KEYWORD_NOISE
    ]
    if len(named_children) < 2:
        return lower_const_literal(ctx, node)
    obj_node = named_children[0]
    field_node = named_children[-1]
    obj_reg = ctx.lower_expr(obj_node)
    field_name = ctx.node_text(field_node)

    # Check if obj is a class-typed variable for property interception
    obj_class = _resolve_object_class(ctx, obj_node)
    if obj_class:
        return emit_field_load_or_getter(ctx, obj_reg, obj_class, field_name, node)

    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[obj_reg, field_name],
        node=node,
    )
    return reg
```

- [ ] **Step 3: Run the var type tracking test (should now pass)**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalVarTypeTracking::test_var_declaration_of_class_type_enables_getter_interception -v`
Expected: PASS (var type tracking + getter interception now both wired).

- [ ] **Step 4: Write test for untyped variable (no interception)**

Add to `TestPascalVarTypeTracking`:

```python
    def test_dot_access_on_untyped_var_emits_plain_load_field(self):
        """rec.field on unknown-type variable -> plain LOAD_FIELD (no interception)."""
        instructions = _parse_pascal("program M; begin x := rec.field; end.")
        loads = _find_all(instructions, Opcode.LOAD_FIELD)
        assert len(loads) >= 1
        assert "field" in loads[0].operands
        # Should NOT have CALL_METHOD for getter
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        getter_calls = [c for c in calls if "__get_" in str(c.operands)]
        assert len(getter_calls) == 0

    def test_param_of_class_type_enables_getter_interception(self):
        """procedure Foo(bar: TBar) -> bar.X should use getter if registered."""
        source = """\
program M;
type
  TBar = class
  private
    FX: Integer;
  public
    property X: Integer read FX;
  end;
procedure DoWork(bar: TBar);
begin
  WriteLn(bar.X);
end;
begin
end."""
        instructions = _parse_pascal(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        getter_calls = [c for c in calls if "__get_X__" in c.operands]
        assert len(getter_calls) >= 1, (
            f"Expected CALL_METHOD __get_X__ from param type tracking, "
            f"got {[c.operands for c in calls]}"
        )
```

- [ ] **Step 5: Run all tests**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalVarTypeTracking -v`
Expected: All PASS.

- [ ] **Step 6: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add interpreter/frontends/pascal/declarations.py interpreter/frontends/pascal/expressions.py tests/unit/test_pascal_frontend.py
git commit -m "feat(pascal): intercept dot access on class-typed vars for property getters"
```

### Task 6: Setter interception in `lower_pascal_assignment`

**Files:**
- Modify: `interpreter/frontends/pascal/declarations.py:66-76` (EXPR_DOT branch of `lower_pascal_assignment`)
- Test: `tests/unit/test_pascal_frontend.py`

- [ ] **Step 1: Write the failing test**

```python
class TestPascalAssignmentInterception:
    """Tests for property setter interception in lower_pascal_assignment."""

    def test_dot_assign_on_typed_var_with_setter_emits_call_method(self):
        """foo.Name := 'x' on class-typed var with setter -> CALL_METHOD __set_Name__."""
        source = """\
program M;
type
  TFoo = class
  private
    FName: string;
    procedure SetName(const AValue: string);
  public
    property Name: string read FName write SetName;
  end;
var
  foo: TFoo;
begin
  foo := TFoo;
  foo.Name := 'hello';
end."""
        instructions = _parse_pascal(source)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        setter_calls = [c for c in calls if "__set_Name__" in c.operands]
        assert len(setter_calls) >= 1, (
            f"Expected CALL_METHOD __set_Name__, got {[c.operands for c in calls]}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalAssignmentInterception::test_dot_assign_on_typed_var_with_setter_emits_call_method -v`
Expected: FAIL — assignment still emits plain STORE_FIELD.

- [ ] **Step 3: Modify `lower_pascal_assignment` EXPR_DOT branch**

In `interpreter/frontends/pascal/declarations.py`, the `emit_field_store_or_setter` import was already added in Task 1. Also ensure `_resolve_object_class` is available (defined in same file).

Replace the EXPR_DOT branch in `lower_pascal_assignment` (lines 66-76) with:

```python
    elif target.type == PascalNodeType.EXPR_DOT:
        dot_named = [
            c for c in target.children if c.is_named and c.type not in KEYWORD_NOISE
        ]
        obj_node = dot_named[0]
        obj_reg = ctx.lower_expr(obj_node)
        field_name = ctx.node_text(dot_named[-1])

        obj_class = _resolve_object_class(ctx, obj_node)
        if obj_class:
            emit_field_store_or_setter(
                ctx, obj_reg, obj_class, field_name, val_reg, node
            )
        else:
            ctx.emit(
                Opcode.STORE_FIELD,
                operands=[obj_reg, field_name, val_reg],
                node=node,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalAssignmentInterception::test_dot_assign_on_typed_var_with_setter_emits_call_method -v`
Expected: PASS

- [ ] **Step 5: Write test for untyped variable (no interception)**

```python
    def test_dot_assign_on_untyped_var_emits_plain_store_field(self):
        """rec.field := 10 on unknown-type variable -> plain STORE_FIELD."""
        instructions = _parse_pascal("program M; begin rec.field := 10; end.")
        stores = _find_all(instructions, Opcode.STORE_FIELD)
        assert any("field" in inst.operands for inst in stores)
        calls = _find_all(instructions, Opcode.CALL_METHOD)
        setter_calls = [c for c in calls if "__set_" in str(c.operands)]
        assert len(setter_calls) == 0
```

- [ ] **Step 6: Run tests and verify**

Run: `poetry run python -m pytest tests/unit/test_pascal_frontend.py::TestPascalAssignmentInterception -v`
Expected: All PASS.

- [ ] **Step 7: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add interpreter/frontends/pascal/declarations.py tests/unit/test_pascal_frontend.py
git commit -m "feat(pascal): intercept dot assignment on class-typed vars for property setters"
```

### Task 7: Integration tests

**Files:**
- Create: `tests/integration/test_pascal_frontend_execution.py`
- Test: `tests/integration/test_pascal_frontend_execution.py`

- [ ] **Step 1: Create integration test file**

Create `tests/integration/test_pascal_frontend_execution.py`:

```python
"""Integration tests for Pascal property declarations -- end-to-end VM execution."""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_pascal(source: str, max_steps: int = 500) -> tuple:
    """Run a Pascal program and return (vm, unwrapped local vars)."""
    vm = run(source, language=Language.PASCAL, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestPascalPropertyAccessorExecution:
    """End-to-end property accessor tests via VM execution."""

    def test_field_read_property_returns_backing_field_value(self):
        """foo.Name should return the backing field FName's value via getter."""
        _, vars_ = _run_pascal("""\
program M;
type
  TFoo = class
  private
    FName: string;
  public
    property Name: string read FName;
  end;
var
  foo: TFoo;
  answer: string;
begin
  foo := TFoo();
  foo.FName := 'Alice';
  answer := foo.Name;
end.""")
        assert vars_["answer"] == "Alice"

    def test_field_write_property_stores_to_backing_field(self):
        """foo.Name := 'x' with field-targeted write should store to FName."""
        _, vars_ = _run_pascal("""\
program M;
type
  TFoo = class
  private
    FName: string;
  public
    property Name: string read FName write FName;
  end;
var
  foo: TFoo;
  answer: string;
begin
  foo := TFoo();
  foo.Name := 'Bob';
  answer := foo.FName;
end.""")
        assert vars_["answer"] == "Bob"

    def test_method_write_property_calls_setter_procedure(self):
        """foo.Name := 'x' should call SetName which stores to self.FName."""
        _, vars_ = _run_pascal("""\
program M;
type
  TFoo = class
  private
    FName: string;
    procedure SetName(const AValue: string);
  public
    property Name: string read FName write SetName;
  end;

procedure TFoo.SetName(const AValue: string);
begin
  self.FName := AValue;
end;

var
  foo: TFoo;
  answer: string;
begin
  foo := TFoo();
  foo.Name := 'Charlie';
  answer := foo.Name;
end.""", max_steps=1000)
        assert vars_["answer"] == "Charlie"

    def test_read_only_property_returns_value(self):
        """Read-only property (no write accessor) returns backing field value."""
        _, vars_ = _run_pascal("""\
program M;
type
  TFoo = class
  private
    FValue: Integer;
  public
    property Value: Integer read FValue;
  end;
var
  foo: TFoo;
  answer: Integer;
begin
  foo := TFoo();
  foo.FValue := 42;
  answer := foo.Value;
end.""")
        assert vars_["answer"] == 42

    def test_class_without_properties_regression(self):
        """Class without properties should still work (regression guard)."""
        _, vars_ = _run_pascal("""\
program M;
type
  TPoint = class
  public
    X: Integer;
    Y: Integer;
  end;
var
  p: TPoint;
  answer: Integer;
begin
  p := TPoint();
  p.X := 10;
  p.Y := 20;
  answer := p.X + p.Y;
end.""")
        assert vars_["answer"] == 30
```

- [ ] **Step 2: Run integration tests**

Run: `poetry run python -m pytest tests/integration/test_pascal_frontend_execution.py -v`
Expected: Tests pass (or xfail-mark any that hit known VM limitations — see Step 3).

- [ ] **Step 3: Debug and fix any failures**

If integration tests fail due to VM execution issues:
- If `TFoo()` doesn't invoke `__init__`, check how the VM handles `CALL_FUNCTION` for class types.
- If `foo.FName := 'Alice'` fails because `foo` is class-typed and `FName` is not a property (so it should NOT be intercepted), verify that `emit_field_store_or_setter` falls through to plain `STORE_FIELD` when no setter is registered for `FName`.
- If `self.FName` inside `TFoo.SetName` fails, note that `self` should resolve via `_current_class_name` in `_resolve_object_class`. However, the method body is in a `defProc` (outside the class), not inside the class body traversal, so `_current_class_name` may not be set. This may require additional wiring in `lower_pascal_proc` for `defProc` nodes with qualified names (e.g., `TFoo.SetName`). If this test hits this limitation, mark it `@pytest.mark.xfail(reason="defProc qualified name class context not yet wired")` and file a beads issue.
- If any test hits a genuine VM limitation not in scope, mark it `@pytest.mark.xfail(reason="...")` and file a beads issue.

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_pascal_frontend_execution.py
git commit -m "test(pascal): add integration tests for property accessor execution"
```

### Task 8: Format, update README, push, close issue

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run Black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 3: Update README**

Add Pascal property declarations to the relevant feature list in README.md.

- [ ] **Step 4: Commit and push**

```bash
git add -A
git commit -m "chore: format, update README for Pascal property declarations"
git push origin main
```

- [ ] **Step 5: Close issue**

```bash
bd update red-dragon-93w --status closed
```
