# type_hint: str to TypeExpr Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change `NewObject.type_hint` and `NewArray.type_hint` from `str` to `TypeExpr`, so type information flows from frontends through the IR as structured types rather than strings.

**Architecture:** Bridge-first approach. Commit 1 wraps all frontend call sites with `scalar()` while the field is still `str` (no-op, no breakage). Commit 2 changes the field type and simplifies handlers/inference. Each commit passes all tests independently.

**Tech Stack:** Python 3.13+, pytest, Poetry

**Issues:** red-dragon-xb2k (this plan), red-dragon-y9dx (EnumType ADT variants), red-dragon-i1ly (parameterized types)

---

## Task 1: Wrap all frontend type_hint values with scalar()

Field stays `str`. This is a no-op preparation step: `str(scalar("dict"))` produces `"dict"`.

**Files:** All frontend files that construct `NewObject` or `NewArray` (~50 sites across ~25 files)

- [ ] **Step 1: Write failing test that verifies scalar() wrapping works with str field**

Create `tests/unit/test_type_hint_type_expr.py`:

```python
"""Tests for TypeExpr-valued type_hint on NewObject and NewArray."""

from interpreter.instructions import NewObject, NewArray
from interpreter.ir import IRInstruction, Opcode
from interpreter.register import Register
from interpreter.types.type_expr import UNKNOWN, ScalarType, TypeExpr, scalar


class TestNewObjectTypeHintScalarPrep:
    """Verify scalar() values work with the current str field via __str__."""

    def test_scalar_str_matches_plain_string(self):
        assert str(scalar("dict")) == "dict"

    def test_scalar_in_new_object_operands(self):
        inst = NewObject(result_reg=Register("%r0"), type_hint=scalar("Foo"))
        assert inst.operands == ["Foo"]

    def test_scalar_in_new_array_operands(self):
        inst = NewArray(
            result_reg=Register("%r1"),
            type_hint=scalar("list"),
            size_reg=Register("%r0"),
        )
        assert inst.operands == ["list", "%r0"]
```

- [ ] **Step 2: Run test to verify it passes** (this is a compatibility check, not TDD red)

Run: `poetry run python -m pytest tests/unit/test_type_hint_type_expr.py -v`

- [ ] **Step 3: Migrate all frontend call sites**

For every `NewObject(... type_hint=X ...)` and `NewArray(... type_hint=X ...)`:
- String literal: `type_hint="dict"` → `type_hint=scalar("dict")`
- Variable: `type_hint=type_name` → `type_hint=scalar(type_name)`
- F-string: `type_hint=f"enum:{name}"` → `type_hint=scalar(f"enum:{name}")`

Add `from interpreter.types.type_expr import scalar` to each file's imports.

Find sites with: `grep -rn 'NewObject\|NewArray' interpreter/frontends/ interpreter/cobol/ --include='*.py' | grep 'type_hint='`

Note: `interpreter/frontends/symbol_table.py` also has `type_hint=` on `FieldInfo` — this is unrelated to `NewObject`/`NewArray` and should not be changed. `interpreter/handlers/calls.py` and `interpreter/vm/builtins.py` already use `TypeExpr` values for type_hint and do not need changes.

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All tests PASS (no-op change).

- [ ] **Step 5: Verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd backup
git add interpreter/frontends/ interpreter/cobol/ tests/unit/test_type_hint_type_expr.py
git commit -m "frontends: wrap type_hint values with scalar() — preparation for TypeExpr migration"
```

---

## Task 2: Change field type to TypeExpr, update handlers and type inference

All callers already pass `scalar()` values from Task 1.

**Files:**
- Modify: `interpreter/instructions.py` — field types, operands properties, _to_typed converters
- Modify: `interpreter/handlers/objects.py` — use t.type_hint directly
- Modify: `interpreter/types/type_inference.py` — use inst.type_hint directly
- Test: `tests/unit/test_type_hint_type_expr.py` — add type-level assertions

- [ ] **Step 1: Add tests that assert TypeExpr field type**

Append to `tests/unit/test_type_hint_type_expr.py`:

```python
class TestNewObjectTypeHintIsTypeExpr:
    def test_type_hint_is_type_expr(self):
        inst = NewObject(result_reg=Register("%r0"), type_hint=scalar("Foo"))
        assert isinstance(inst.type_hint, TypeExpr)
        assert isinstance(inst.type_hint, ScalarType)

    def test_default_is_unknown(self):
        inst = NewObject(result_reg=Register("%r0"))
        assert inst.type_hint is UNKNOWN

    def test_operands_renders_string(self):
        inst = NewObject(result_reg=Register("%r0"), type_hint=scalar("dict"))
        assert inst.operands == ["dict"]
        assert isinstance(inst.operands[0], str)

    def test_operands_empty_when_unknown(self):
        inst = NewObject(result_reg=Register("%r0"), type_hint=UNKNOWN)
        assert inst.operands == []

    def test_str_format(self):
        inst = NewObject(result_reg=Register("%r0"), type_hint=scalar("Foo"))
        assert str(inst) == "%r0 = new_object Foo"

    def test_factory_wraps_string(self):
        inst = IRInstruction(opcode=Opcode.NEW_OBJECT, result_reg="%r0", operands=["Foo"])
        assert isinstance(inst.type_hint, ScalarType)
        assert inst.type_hint == scalar("Foo")

    def test_factory_empty_gives_unknown(self):
        inst = IRInstruction(opcode=Opcode.NEW_OBJECT, result_reg="%r0", operands=[])
        assert inst.type_hint is UNKNOWN


class TestNewArrayTypeHintIsTypeExpr:
    def test_type_hint_is_type_expr(self):
        inst = NewArray(result_reg=Register("%r1"), type_hint=scalar("list"), size_reg=Register("%r0"))
        assert isinstance(inst.type_hint, TypeExpr)

    def test_default_is_unknown(self):
        inst = NewArray(result_reg=Register("%r1"), size_reg=Register("%r0"))
        assert inst.type_hint is UNKNOWN

    def test_str_format(self):
        inst = NewArray(result_reg=Register("%r1"), type_hint=scalar("list"), size_reg=Register("%r0"))
        assert str(inst) == "%r1 = new_array list %r0"

    def test_factory_wraps_string(self):
        inst = IRInstruction(opcode=Opcode.NEW_ARRAY, result_reg="%r1", operands=["list", "%r0"])
        assert isinstance(inst.type_hint, ScalarType)
```

- [ ] **Step 2: Run tests — expect failures** (field is still str)

Run: `poetry run python -m pytest tests/unit/test_type_hint_type_expr.py -v`
Expected: `isinstance` assertions FAIL.

- [ ] **Step 3: Change field types in instructions.py**

```python
# NewObject
type_hint: TypeExpr = UNKNOWN  # was: str = ""

# NewArray
type_hint: TypeExpr = UNKNOWN  # was: str = ""
```

Update `operands` properties to `str()` the TypeExpr:
```python
# NewObject
return [str(self.type_hint)] if self.type_hint else []

# NewArray
return [str(self.type_hint), str(self.size_reg)]
```

Update `_new_object` and `_new_array` converters to wrap with `scalar()`:
```python
def _new_object(inst):
    raw = str(inst.operands[0]) if inst.operands else ""
    return NewObject(
        result_reg=inst.result_reg,
        type_hint=scalar(raw) if raw else UNKNOWN,
        source_location=inst.source_location,
    )

def _new_array(inst):
    ops = inst.operands
    raw = str(ops[0]) if len(ops) >= 1 else ""
    return NewArray(
        result_reg=inst.result_reg,
        type_hint=scalar(raw) if raw else UNKNOWN,
        size_reg=Register(str(ops[1])) if len(ops) >= 2 else NO_REGISTER,
        source_location=inst.source_location,
    )
```

Add import: `from interpreter.types.type_expr import UNKNOWN, TypeExpr, scalar`

- [ ] **Step 4: Update handler — use type_hint directly**

In `interpreter/handlers/objects.py`, replace both handlers with explicit TypeExpr handling.

`_handle_new_object`: Use `t.type_hint` directly. The ClassRef dereference branch MUST assign `scalar(raw.name)` (not `raw.name`) to keep the variable as TypeExpr:

```python
obj_type = t.type_hint
hint_name = str(obj_type)
for frame in reversed(vm.call_stack):
    if hint_name in frame.local_vars:
        raw = frame.local_vars[hint_name].value
        if isinstance(raw, ClassRef):
            obj_type = scalar(raw.name)  # TypeExpr, not str
        break
if not obj_type:
    obj_type = scalar("Object")
```

`_handle_new_array`: Use `t.type_hint` directly:

```python
arr_type = t.type_hint if t.type_hint else scalar("Array")
```

- [ ] **Step 5: Update type inference — use type_hint directly**

In `interpreter/types/type_inference.py`:

`_infer_new_object`: Replace `class_name = str(inst.type_hint); scalar(class_name)` with `inst.type_hint` directly.

`_infer_new_array`: The tuple check `str(inst.type_hint) == "tuple"` can become `inst.type_hint == scalar(TypeName.TUPLE)`. The non-tuple branch can use `inst.type_hint` directly instead of `scalar(TypeName.ARRAY)`.

- [ ] **Step 6: Run tests — expect pass**

Run: `poetry run python -m pytest tests/unit/test_type_hint_type_expr.py -v`
Expected: All PASS.

- [ ] **Step 7: Run full test suite**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All ~12,944 tests PASS.

- [ ] **Step 8: Verification gate and commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
bd update xb2k --claim && bd backup
git add interpreter/instructions.py interpreter/handlers/objects.py interpreter/types/type_inference.py tests/unit/test_type_hint_type_expr.py
git commit -m "type_hint: str → TypeExpr on NewObject/NewArray — handlers and inference use TypeExpr directly"
bd close xb2k --reason "type_hint is TypeExpr; frontends emit scalar(), handlers consume directly"
```
