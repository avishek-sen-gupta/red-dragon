# Rust Box<T> and Option<T> Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Rust linked list traversal with Box/Option produce concrete results (answer=6) instead of SymbolicValue.

**Architecture:** Emit Box and Option as prelude IR classes in the Rust frontend. Intercept `Box::new(x)` and `Some(x)` calls to emit `CALL_FUNCTION Box[T]` / `Option[T]` with resolved type parameters. Migrate `HeapObject.type_hint` from `str | None` to `TypeExpr` so runtime objects carry parameterized type info. Add base-name extraction in the VM so `CALL_FUNCTION "Box[Node]"` looks up `"Box"` in scope.

**Tech Stack:** Python 3.13+, pytest, tree-sitter

**Spec:** `docs/superpowers/specs/2026-03-14-rust-box-option-types-design.md`

---

## Chunk 1: VM Infrastructure

### Task 1: Migrate HeapObject.type_hint from `str | None` to `TypeExpr`

**Files:**
- Modify: `interpreter/vm_types.py:46-54`
- Modify: `interpreter/vm.py:228`
- Test: `tests/unit/test_heap_type_hint_migration.py` (create)

This task changes `HeapObject.type_hint` from `str | None` to `TypeExpr` (default `UNKNOWN`). The `TypeExpr.__eq__` string compatibility ensures existing code like `type_hint == "Node"` keeps working.

- [ ] **Step 1: Write failing tests for HeapObject with TypeExpr type_hint**

Create `tests/unit/test_heap_type_hint_migration.py`:

```python
"""Tests for HeapObject.type_hint migration from str to TypeExpr."""

from interpreter.type_expr import (
    ScalarType,
    ParameterizedType,
    UNKNOWN,
    scalar,
    parse_type,
)
from interpreter.vm_types import HeapObject


class TestHeapObjectTypeHint:
    def test_default_type_hint_is_unknown(self):
        obj = HeapObject()
        assert obj.type_hint == UNKNOWN
        assert not obj.type_hint  # UNKNOWN is falsy

    def test_scalar_type_hint(self):
        obj = HeapObject(type_hint=scalar("Node"))
        assert obj.type_hint == "Node"  # string compatibility
        assert isinstance(obj.type_hint, ScalarType)

    def test_parameterized_type_hint(self):
        box_node = ParameterizedType("Box", (ScalarType("Node"),))
        obj = HeapObject(type_hint=box_node)
        assert obj.type_hint == "Box[Node]"  # string compatibility
        assert isinstance(obj.type_hint, ParameterizedType)
        assert obj.type_hint.constructor == "Box"
        assert obj.type_hint.arguments == (ScalarType("Node"),)

    def test_nested_parameterized_type_hint(self):
        opt_box_node = ParameterizedType(
            "Option",
            (ParameterizedType("Box", (ScalarType("Node"),)),),
        )
        obj = HeapObject(type_hint=opt_box_node)
        assert obj.type_hint == "Option[Box[Node]]"

    def test_to_dict_with_type_expr(self):
        obj = HeapObject(type_hint=scalar("Node"))
        d = obj.to_dict()
        assert d["type_hint"] == "Node"

    def test_to_dict_with_unknown(self):
        obj = HeapObject()
        d = obj.to_dict()
        assert d["type_hint"] is None  # preserve JSON shape

    def test_to_dict_with_parameterized(self):
        obj = HeapObject(
            type_hint=ParameterizedType("Box", (ScalarType("Node"),))
        )
        d = obj.to_dict()
        assert d["type_hint"] == "Box[Node]"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_heap_type_hint_migration.py -v`
Expected: FAIL — `HeapObject(type_hint=scalar("Node"))` will fail because type_hint is `str | None`.

- [ ] **Step 3: Implement HeapObject.type_hint migration**

In `interpreter/vm_types.py`, change:

```python
# OLD (line 46-54):
@dataclass
class HeapObject:
    type_hint: str | None = None
    fields: dict[str, TypedValue] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type_hint": self.type_hint,
            "fields": {k: _serialize_value(v) for k, v in self.fields.items()},
        }
```

to:

```python
# NEW:
@dataclass
class HeapObject:
    type_hint: TypeExpr = UNKNOWN
    fields: dict[str, TypedValue] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type_hint": str(self.type_hint) or None,
            "fields": {k: _serialize_value(v) for k, v in self.fields.items()},
        }
```

Add import at top of `vm_types.py`:

```python
from interpreter.type_expr import TypeExpr, UNKNOWN
```

Note: `UNKNOWN` is already imported via `from interpreter.type_expr import scalar` — check existing imports and add `TypeExpr, UNKNOWN` if not present.

- [ ] **Step 4: Fix ALL callers that pass string type_hint to HeapObject**

**Production code — `interpreter/executor.py`:**

There are 5 call sites. The first 4 use `_symbolic_type_hint()` which returns `str`.
Change `_symbolic_type_hint` itself (line 67) to return `TypeExpr`:

```python
# OLD (line 67-73):
def _symbolic_type_hint(val: Any) -> str:
    """Extract a type hint from a symbolic value (SymbolicValue or dict)."""
    if isinstance(val, SymbolicValue):
        return val.type_hint or ""
    if isinstance(val, dict) and val.get("__symbolic__"):
        return val.get("type_hint", "")
    return ""

# NEW:
def _symbolic_type_hint(val: Any) -> TypeExpr:
    """Extract a type hint from a symbolic value (SymbolicValue or dict)."""
    if isinstance(val, SymbolicValue):
        return scalar(val.type_hint) if val.type_hint else UNKNOWN
    if isinstance(val, dict) and val.get("__symbolic__"):
        hint = val.get("type_hint", "")
        return scalar(hint) if hint else UNKNOWN
    return UNKNOWN
```

This fixes these 4 sites automatically (no change needed at each call site):
- `executor.py:341` — `HeapObject(type_hint=_symbolic_type_hint(obj_val))`
- `executor.py:414` — `HeapObject(type_hint=_symbolic_type_hint(obj_val))`
- `executor.py:454` — `HeapObject(type_hint=_symbolic_type_hint(arr_val))`
- `executor.py:506` — `HeapObject(type_hint=_symbolic_type_hint(arr_val))`

5th site — `executor.py:1012`:

```python
# OLD:
vm.heap[addr] = HeapObject(type_hint=class_name)

# NEW:
vm.heap[addr] = HeapObject(type_hint=scalar(class_name))
```

Add `from interpreter.type_expr import scalar, UNKNOWN, TypeExpr` at top of `executor.py`.

**Production code — `interpreter/vm.py:228`:**

`NewObject.type_hint` is `str | None` (Pydantic, stays unchanged). The guard is
needed because we're crossing the `str | None` → `TypeExpr` boundary:

```python
# OLD:
vm.heap[obj.addr] = HeapObject(type_hint=obj.type_hint)

# NEW:
vm.heap[obj.addr] = HeapObject(
    type_hint=scalar(obj.type_hint) if obj.type_hint else UNKNOWN
)
```

Add `from interpreter.type_expr import scalar, UNKNOWN` at top of `vm.py`.

**Test files — 8 call sites that pass string type_hint:**

- `tests/unit/test_heap_writes_typed.py:42` — `HeapObject(type_hint="Point")` → `HeapObject(type_hint=scalar("Point"))`
- `tests/unit/test_heap_writes_typed.py:68` — `HeapObject(type_hint="Person")` → `HeapObject(type_hint=scalar("Person"))`
- `tests/unit/test_heap_writes_typed.py:84` — `HeapObject(type_hint="array", ...)` → `HeapObject(type_hint=scalar("array"), ...)`
- `tests/unit/test_heap_writes_typed.py:155` — `HeapObject(type_hint="Point")` → `HeapObject(type_hint=scalar("Point"))`
- `tests/unit/test_heap_writes_typed.py:191` — `HeapObject(type_hint="Foo")` → `HeapObject(type_hint=scalar("Foo"))`
- `tests/unit/test_heap_writes_typed.py:218` — `HeapObject(type_hint="Point", ...)` → `HeapObject(type_hint=scalar("Point"), ...)`
- `tests/unit/test_unresolved_call.py:296` — `HeapObject(type_hint="MyClass")` → `HeapObject(type_hint=scalar("MyClass"))`
- `tests/unit/test_builtin_keys.py:52` — `HeapObject(type_hint="object", ...)` → `HeapObject(type_hint=scalar("object"), ...)`

Add `from interpreter.type_expr import scalar` to the import block of each test file.

**Serialization note:** `to_dict()` uses `str(self.type_hint) or None`. This works
because `str(UNKNOWN)` returns `""`, and `"" or None` evaluates to `None`, preserving
the existing JSON shape `{"type_hint": null}` for untyped objects.

- [ ] **Step 5: Run tests to verify migration passes**

Run: `poetry run python -m pytest tests/unit/test_heap_type_hint_migration.py -v`
Expected: PASS

Run: `poetry run python -m pytest tests/ -x --tb=short -q`
Expected: All tests pass (no regressions from type_hint migration)

- [ ] **Step 6: Commit**

```bash
git add interpreter/vm_types.py interpreter/vm.py interpreter/executor.py tests/unit/test_heap_type_hint_migration.py
# Also add any test files that needed HeapObject constructor updates
git commit -m "feat: migrate HeapObject.type_hint from str to TypeExpr"
```

---

### Task 2: VM base-name extraction in _handle_call_function

**Files:**
- Modify: `interpreter/executor.py:1123-1175`
- Test: `tests/integration/test_parameterized_constructor.py` (create)

Add base-name extraction so `CALL_FUNCTION "Box[Node]"` looks up `"Box"` in scope, and pass the original operand to `_try_class_constructor_call`.

- [ ] **Step 1: Write failing integration test for parameterized CALL_FUNCTION**

Create `tests/integration/test_parameterized_constructor.py`:

```python
"""Tests for parameterized CALL_FUNCTION operand handling."""

from interpreter.type_expr import ScalarType, ParameterizedType, scalar
from interpreter.vm_types import HeapObject, VMState, StackFrame
from interpreter.typed_value import TypedValue, typed
from interpreter.ir import IRInstruction, Opcode
from interpreter.cfg import build_cfg
from interpreter.registry import build_registry
from interpreter.run import run
from interpreter.constants import Language


class TestParameterizedCallFunction:
    def test_box_node_constructor_creates_heap_object(self):
        """CALL_FUNCTION 'Box[Node]' should look up 'Box' in scope
        and create a HeapObject with ParameterizedType type_hint."""
        source = """\
struct Node { value: i32 }

let n = Node { value: 42 };
let b = Box::new(n);
"""
        vm = run(source, language=Language.RUST, max_steps=300)
        locals_ = {
            k: v.value if isinstance(v, TypedValue) else v
            for k, v in vm.call_stack[0].local_vars.items()
        }
        # b should be a heap address
        b_addr = locals_.get("b")
        assert b_addr is not None
        # The heap object should exist and have "value" field
        assert b_addr in vm.heap
        box_obj = vm.heap[b_addr]
        assert "value" in box_obj.fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/integration/test_parameterized_constructor.py -v`
Expected: FAIL — Box::new not resolved (no Box class defined, falls to symbolic).

Note: This test will fully pass only after Tasks 2, 3, and 4 are complete. At this stage, it establishes the failing baseline.

- [ ] **Step 3: Implement base-name extraction in _handle_call_function**

In `interpreter/executor.py`, modify `_handle_call_function` (~line 1133-1174):

```python
# OLD:
def _handle_call_function(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    **kwargs: Any,
) -> ExecutionResult:
    func_name = inst.operands[0]
    arg_regs = inst.operands[1:]
    args = [_resolve_binop_operand(vm, a) for a in arg_regs]

    # ... I/O provider, builtins ...

    # 2. Look up the function/class via scope chain
    func_val = ""
    for f in reversed(vm.call_stack):
        if func_name in f.local_vars:
            func_val = f.local_vars[func_name].value
            break
```

Change to:

```python
# NEW:
def _handle_call_function(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    **kwargs: Any,
) -> ExecutionResult:
    raw_func_name = inst.operands[0]
    # Extract base name for scope lookup: "Box[Node]" → "Box"
    base_name = (
        raw_func_name.split("[")[0]
        if isinstance(raw_func_name, str) and "[" in raw_func_name
        else raw_func_name
    )
    arg_regs = inst.operands[1:]
    args = [_resolve_binop_operand(vm, a) for a in arg_regs]

    # ... I/O provider uses base_name ...
    # ... builtins use base_name ...

    # 2. Look up the function/class via scope chain
    func_val = ""
    for f in reversed(vm.call_stack):
        if base_name in f.local_vars:
            func_val = f.local_vars[base_name].value
            break
    if not func_val:
        return call_resolver.resolve_call(base_name, [a.value for a in args], inst, vm)
```

Rename all remaining `func_name` references in the function body. Here is the
complete list:

- Line 1142: `func_name.startswith("__cobol_")` → `base_name.startswith("__cobol_")`
- Line 1153: `f"{func_name}(…)"` → `f"{base_name}(…)"` (reasoning string)
- Line 1157: `f"io_provider {func_name}"` → `f"io_provider {base_name}"` (reasoning)
- Line 1162: `_try_builtin_call(func_name, ...)` → `_try_builtin_call(base_name, ...)`
- Line 1169: `if func_name in f.local_vars` → `if base_name in f.local_vars`
- Line 1174: `call_resolver.resolve_call(func_name, ...)` → `call_resolver.resolve_call(base_name, ...)`
- Line 1187/1205: reasoning strings — use `base_name`
- Line 1232: final `call_resolver.resolve_call(func_name, ...)` → `call_resolver.resolve_call(base_name, ...)`

The ONLY place `raw_func_name` is used is `type_hint_source=raw_func_name` passed
to `_try_class_constructor_call`.

Update the constructor call site (~line 1210):

```python
    # 3. Class constructor
    ctor_result = _try_class_constructor_call(
        func_val,
        args,
        inst,
        vm,
        cfg,
        registry,
        current_label,
        overload_resolver=overload_resolver,
        type_env=type_env,
        type_hint_source=raw_func_name,  # NEW parameter
    )
```

- [ ] **Step 4: Run full test suite to verify no regressions**

Run: `poetry run python -m pytest tests/ -x --tb=short -q`
Expected: All existing tests pass (base_name extraction is transparent for non-parameterized names).

- [ ] **Step 5: Commit**

```bash
git add interpreter/executor.py tests/unit/test_parameterized_constructor.py
git commit -m "feat: extract base name from parameterized CALL_FUNCTION operands"
```

---

### Task 3: Add type_hint_source parameter to _try_class_constructor_call

**Files:**
- Modify: `interpreter/executor.py:977-1056`
- Test: uses test from Task 2

Add `type_hint_source` parameter so the constructor creates HeapObject with `parse_type(type_hint_source)` as the type_hint.

- [ ] **Step 1: Write unit test for parameterized type_hint on HeapObject**

Add to `tests/unit/test_parameterized_constructor.py`:

```python
    def test_parameterized_type_hint_on_heap_object(self):
        """Box[Node] constructor should produce HeapObject with
        ParameterizedType('Box', (ScalarType('Node'),)) type_hint."""
        source = """\
struct Node { value: i32 }

let n = Node { value: 42 };
let b = Box::new(n);
"""
        vm = run(source, language=Language.RUST, max_steps=300)
        locals_ = {
            k: v.value if isinstance(v, TypedValue) else v
            for k, v in vm.call_stack[0].local_vars.items()
        }
        b_addr = locals_.get("b")
        assert b_addr in vm.heap
        box_obj = vm.heap[b_addr]
        assert isinstance(box_obj.type_hint, ParameterizedType)
        assert box_obj.type_hint.constructor == "Box"
```

- [ ] **Step 2: Implement type_hint_source in _try_class_constructor_call**

In `interpreter/executor.py`, modify `_try_class_constructor_call` signature (~line 977):

```python
# OLD:
def _try_class_constructor_call(
    func_val: Any,
    args: list[TypedValue],
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
) -> ExecutionResult:
```

Add parameter:

```python
# NEW:
def _try_class_constructor_call(
    func_val: Any,
    args: list[TypedValue],
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    type_hint_source: str = "",
) -> ExecutionResult:
```

Change the HeapObject creation (~line 1012):

Add `parse_type` to the imports at the top of `executor.py` (alongside `scalar`
and `UNKNOWN` added in Task 1):

```python
from interpreter.type_expr import scalar, UNKNOWN, TypeExpr, parse_type
```

Then change the HeapObject creation:

```python
# OLD (after Task 1 changes):
vm.heap[addr] = HeapObject(type_hint=scalar(class_name))

# NEW:
type_hint = parse_type(type_hint_source) if type_hint_source else scalar(class_name)
vm.heap[addr] = HeapObject(type_hint=type_hint)
```

Also update the `NewObject` in the no-init early return (~line 1017) to use
`str(type_hint)` for `NewObject.type_hint` (since `NewObject` stays `str | None`):

```python
new_objects=[NewObject(addr=addr, type_hint=str(type_hint) or None)],
```

Note: There is only one `NewObject` creation site in `_try_class_constructor_call`
(the no-init early return). The main return path pushes a stack frame and does not
create a `NewObject`.

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest tests/ -x --tb=short -q`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add interpreter/executor.py tests/unit/test_parameterized_constructor.py
git commit -m "feat: add type_hint_source to _try_class_constructor_call for parameterized types"
```

---

## Chunk 2: Rust Frontend — Prelude and Lowering

### Task 4: Emit Box and Option prelude classes in Rust frontend

**Files:**
- Modify: `interpreter/frontends/rust/declarations.py`
- Modify: `interpreter/frontends/_base.py:211-228`
- Modify: `interpreter/frontends/rust/frontend.py`
- Test: `tests/unit/test_rust_prelude.py` (create)

Add an `_emit_prelude` hook to `BaseFrontend` (no-op default), override in `RustFrontend` to emit Box and Option class definitions.

- [ ] **Step 1: Write failing tests for prelude emission**

Create `tests/unit/test_rust_prelude.py`:

```python
"""Tests for Rust frontend prelude class emission (Box, Option)."""

from interpreter.frontends.rust.frontend import RustFrontend
from interpreter.ir import Opcode


def _parse_rust(source: str):
    frontend = RustFrontend()
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions, opcode):
    return [i for i in instructions if i.opcode == opcode]


def _labels(instructions):
    return [i.label for i in instructions if i.opcode == Opcode.LABEL]


class TestRustPrelude:
    def test_box_class_label_emitted(self):
        """Even an empty Rust program should emit Box class definition."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(l.startswith("class_Box") for l in labels if l)

    def test_option_class_label_emitted(self):
        """Even an empty Rust program should emit Option class definition."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(l.startswith("class_Option") for l in labels if l)

    def test_box_has_init_method(self):
        """Box prelude should define __init__ with a value parameter."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(
            l and "Box" in l and "__init__" in l for l in labels
        ), f"No Box.__init__ label found in {labels}"

    def test_option_has_init_method(self):
        """Option prelude should define __init__ with a value parameter."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(
            l and "Option" in l and "__init__" in l for l in labels
        )

    def test_option_has_unwrap_method(self):
        """Option prelude should define unwrap method."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(
            l and "Option" in l and "unwrap" in l for l in labels
        )

    def test_option_has_as_ref_method(self):
        """Option prelude should define as_ref method."""
        instructions = _parse_rust("let x: i32 = 1;")
        labels = _labels(instructions)
        assert any(
            l and "Option" in l and "as_ref" in l for l in labels
        )

    def test_box_store_var_emitted(self):
        """Box class ref should be stored in a variable."""
        instructions = _parse_rust("let x: i32 = 1;")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any(
            "Box" in inst.operands for inst in stores
        )

    def test_option_store_var_emitted(self):
        """Option class ref should be stored in a variable."""
        instructions = _parse_rust("let x: i32 = 1;")
        stores = _find_all(instructions, Opcode.STORE_VAR)
        assert any(
            "Option" in inst.operands for inst in stores
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_rust_prelude.py -v`
Expected: FAIL — no Box/Option labels emitted.

- [ ] **Step 3: Add _emit_prelude hook to BaseFrontend**

In `interpreter/frontends/_base.py`, add a no-op hook and call it in `_lower_with_context`:

```python
# In _lower_with_context (~line 224), change:
#   ctx.emit(Opcode.LABEL, label=constants.CFG_ENTRY_LABEL)
#   ctx.lower_block(root)
# to:
    ctx.emit(Opcode.LABEL, label=constants.CFG_ENTRY_LABEL)
    self._emit_prelude(ctx)
    ctx.lower_block(root)

# Add method:
def _emit_prelude(self, ctx: TreeSitterEmitContext) -> None:
    """Override in subclasses to emit prelude type definitions."""
```

- [ ] **Step 4: Implement prelude emission in Rust frontend**

Add function in `interpreter/frontends/rust/declarations.py`:

```python
def emit_prelude(ctx: TreeSitterEmitContext) -> None:
    """Emit Box and Option class definitions as IR prelude.

    Box has __init__(self, value) that stores self.value = value.
    Option has __init__(self, value), unwrap(self), and as_ref(self).
    """
    _emit_box_class(ctx)
    _emit_option_class(ctx)


def _emit_method_params(ctx: TreeSitterEmitContext, param_names: list[str]) -> None:
    """Emit SYMBOLIC param: + STORE_VAR for each parameter.

    This follows the exact pattern from lower_rust_param (declarations.py:63-91):
    build_registry._scan_func_params discovers params by finding SYMBOLIC instructions
    with 'param:' prefix inside function blocks.
    """
    for pname in param_names:
        reg = ctx.fresh_reg()
        ctx.emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"{constants.PARAM_PREFIX}{pname}"],
        )
        ctx.emit(Opcode.STORE_VAR, operands=[pname, reg])


def _emit_func_ref(ctx: TreeSitterEmitContext, func_name: str, func_label: str) -> None:
    """Emit CONST <function:name@label> + STORE_VAR.

    This follows the pattern from lower_function_def (declarations.py:130-136):
    build_registry._scan_classes discovers methods by finding CONST instructions
    with <function:...> format inside class body scope.
    """
    func_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=func_reg,
        operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[func_name, func_reg])


def _emit_box_class(ctx: TreeSitterEmitContext) -> None:
    """Emit:
    class Box:
        def __init__(self, value):
            self.value = value
    """
    class_name = "Box"
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")
    init_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{class_name}___init__")
    init_end = ctx.fresh_label(f"end_{class_name}___init__")

    # Class body — branch past it
    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=class_label)

    # __init__ function body
    ctx.emit(Opcode.BRANCH, label=init_end)
    ctx.emit(Opcode.LABEL, label=init_label)
    _emit_method_params(ctx, [constants.PARAM_SELF, "value"])
    self_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=self_reg, operands=[constants.PARAM_SELF])
    val_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=val_reg, operands=["value"])
    ctx.emit(Opcode.STORE_FIELD, operands=[self_reg, "value", val_reg])
    ctx.emit(Opcode.RETURN, operands=[self_reg])
    ctx.emit(Opcode.LABEL, label=init_end)

    # Register __init__ as method — CONST func_ref INSIDE class body
    _emit_func_ref(ctx, "__init__", init_label)

    ctx.emit(Opcode.LABEL, label=end_label)

    # Store class ref (OUTSIDE class body, after end_label)
    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[constants.CLASS_REF_TEMPLATE.format(name=class_name, label=class_label)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[class_name, cls_reg])


def _emit_option_class(ctx: TreeSitterEmitContext) -> None:
    """Emit:
    class Option:
        def __init__(self, value):
            self.value = value
        def unwrap(self):
            return self.value
        def as_ref(self):
            return self
    """
    class_name = "Option"
    class_label = ctx.fresh_label(f"{constants.CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(f"{constants.END_CLASS_LABEL_PREFIX}{class_name}")
    init_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{class_name}___init__")
    init_end = ctx.fresh_label(f"end_{class_name}___init__")
    unwrap_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{class_name}__unwrap")
    unwrap_end = ctx.fresh_label(f"end_{class_name}__unwrap")
    as_ref_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{class_name}__as_ref")
    as_ref_end = ctx.fresh_label(f"end_{class_name}__as_ref")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=class_label)

    # __init__(self, value) body
    ctx.emit(Opcode.BRANCH, label=init_end)
    ctx.emit(Opcode.LABEL, label=init_label)
    _emit_method_params(ctx, [constants.PARAM_SELF, "value"])
    self_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=self_reg, operands=[constants.PARAM_SELF])
    val_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=val_reg, operands=["value"])
    ctx.emit(Opcode.STORE_FIELD, operands=[self_reg, "value", val_reg])
    ctx.emit(Opcode.RETURN, operands=[self_reg])
    ctx.emit(Opcode.LABEL, label=init_end)

    # unwrap(self) body
    ctx.emit(Opcode.BRANCH, label=unwrap_end)
    ctx.emit(Opcode.LABEL, label=unwrap_label)
    _emit_method_params(ctx, [constants.PARAM_SELF])
    self_reg2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=self_reg2, operands=[constants.PARAM_SELF])
    val_reg2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_FIELD, result_reg=val_reg2, operands=[self_reg2, "value"])
    ctx.emit(Opcode.RETURN, operands=[val_reg2])
    ctx.emit(Opcode.LABEL, label=unwrap_end)

    # as_ref(self) body
    ctx.emit(Opcode.BRANCH, label=as_ref_end)
    ctx.emit(Opcode.LABEL, label=as_ref_label)
    _emit_method_params(ctx, [constants.PARAM_SELF])
    self_reg3 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=self_reg3, operands=[constants.PARAM_SELF])
    ctx.emit(Opcode.RETURN, operands=[self_reg3])
    ctx.emit(Opcode.LABEL, label=as_ref_end)

    # Register all 3 methods — CONST func_ref INSIDE class body
    _emit_func_ref(ctx, "__init__", init_label)
    _emit_func_ref(ctx, "unwrap", unwrap_label)
    _emit_func_ref(ctx, "as_ref", as_ref_label)

    ctx.emit(Opcode.LABEL, label=end_label)

    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[constants.CLASS_REF_TEMPLATE.format(name=class_name, label=class_label)],
    )
    ctx.emit(Opcode.STORE_VAR, operands=[class_name, cls_reg])
```

**How method registration works:** `build_registry._scan_classes` (registry.py:119-146)
discovers methods by finding `CONST "<function:name@label>"` instructions **inside**
the class label scope (between `class_label` and `end_label`). `_scan_func_params`
(registry.py:78-92) discovers parameters by finding `SYMBOLIC "param:name"` instructions
inside function blocks. The helper functions `_emit_func_ref` and `_emit_method_params`
follow the exact patterns from `lower_function_def` and `lower_rust_param`.

Override in `interpreter/frontends/rust/frontend.py`:

```python
class RustFrontend(BaseFrontend):
    # ... existing code ...

    def _emit_prelude(self, ctx: TreeSitterEmitContext) -> None:
        from interpreter.frontends.rust.declarations import emit_prelude
        emit_prelude(ctx)
```

- [ ] **Step 5: Run tests to verify prelude emission passes**

Run: `poetry run python -m pytest tests/unit/test_rust_prelude.py -v`
Expected: PASS

Run: `poetry run python -m pytest tests/ -x --tb=short -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add interpreter/frontends/_base.py interpreter/frontends/rust/frontend.py interpreter/frontends/rust/declarations.py tests/unit/test_rust_prelude.py
git commit -m "feat: emit Box and Option prelude classes in Rust frontend"
```

---

### Task 5: Lower Box::new and Some calls with parameterized types

**Files:**
- Modify: `interpreter/frontends/rust/expressions.py`
- Test: `tests/unit/test_rust_box_option_lowering.py` (create)

Intercept `Box::new(expr)` and `Some(expr)` in the Rust frontend to emit `CALL_FUNCTION "Box[T]"` and `CALL_FUNCTION "Option[T]"` with resolved type parameters.

- [ ] **Step 1: Write failing tests for Box::new and Some lowering**

Create `tests/unit/test_rust_box_option_lowering.py`:

```python
"""Tests for Rust frontend Box::new and Some call lowering."""

from interpreter.frontends.rust.frontend import RustFrontend
from interpreter.ir import Opcode


def _parse_rust(source: str):
    frontend = RustFrontend()
    return frontend.lower(source.encode("utf-8"))


def _find_all(instructions, opcode):
    return [i for i in instructions if i.opcode == opcode]


class TestBoxNewLowering:
    def test_box_new_emits_call_function(self):
        """Box::new(x) should emit CALL_FUNCTION, not CALL_UNKNOWN."""
        instructions = _parse_rust("""\
struct Node { value: i32 }
let n = Node { value: 42 };
let b = Box::new(n);
""")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        box_calls = [c for c in calls if isinstance(c.operands[0], str) and "Box" in c.operands[0]]
        assert len(box_calls) >= 1, f"Expected CALL_FUNCTION with Box, got {[c.operands for c in calls]}"

    def test_box_new_operand_is_not_call_unknown(self):
        """Box::new should NOT produce CALL_UNKNOWN."""
        instructions = _parse_rust("""\
struct Node { value: i32 }
let n = Node { value: 42 };
let b = Box::new(n);
""")
        unknowns = _find_all(instructions, Opcode.CALL_UNKNOWN)
        box_unknowns = [c for c in unknowns if any("Box" in str(op) for op in c.operands)]
        assert len(box_unknowns) == 0, f"Box::new should not produce CALL_UNKNOWN: {box_unknowns}"


class TestSomeLowering:
    def test_some_emits_call_function(self):
        """Some(x) should emit CALL_FUNCTION with Option."""
        instructions = _parse_rust("""\
struct Node { value: i32 }
let n = Node { value: 42 };
let opt = Some(n);
""")
        calls = _find_all(instructions, Opcode.CALL_FUNCTION)
        option_calls = [c for c in calls if isinstance(c.operands[0], str) and "Option" in c.operands[0]]
        assert len(option_calls) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_rust_box_option_lowering.py -v`
Expected: FAIL — Box::new currently produces CALL_UNKNOWN, Some produces CALL_FUNCTION "Some" (not "Option").

- [ ] **Step 3: Implement Box::new interception**

In `interpreter/frontends/rust/expressions.py`, modify `lower_scoped_identifier` or the call expression handling.

The call chain for `Box::new(n)`:
1. `call_expression` → `lower_call` (common)
2. func_node is `scoped_identifier` → `lower_scoped_identifier` emits `LOAD_VAR "Box::new"`
3. `lower_call_impl` sees non-identifier func_node → emits `CALL_UNKNOWN`

**Approach:** Override the call expression handling. In the Rust `_build_expr_dispatch`, the `CALL_EXPRESSION` maps to `common_expr.lower_call`. Create a Rust-specific `lower_call` wrapper that intercepts `Box::new(...)` and `Some(...)`:

Add to `interpreter/frontends/rust/expressions.py`:

```python
def lower_call_with_box_option(ctx: TreeSitterEmitContext, node) -> str:
    """Rust-specific call lowering that intercepts Box::new and Some."""
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)

    if func_node and func_node.type == RustNodeType.SCOPED_IDENTIFIER:
        full_name = "::".join(
            ctx.node_text(c)
            for c in func_node.children
            if c.type == RustNodeType.IDENTIFIER
        )
        if full_name == "Box::new":
            return _lower_box_new(ctx, args_node, node)

    if func_node and func_node.type == RustNodeType.IDENTIFIER:
        name = ctx.node_text(func_node)
        if name == "Some":
            return _lower_some(ctx, args_node, node)

    # Fall through to common call lowering
    from interpreter.frontends.common.expressions import lower_call_impl
    return lower_call_impl(ctx, func_node, args_node, node)


def _lower_box_new(ctx: TreeSitterEmitContext, args_node, call_node) -> str:
    """Lower Box::new(expr) → CALL_FUNCTION 'Box' with single arg."""
    from interpreter.frontends.common.expressions import extract_call_args
    arg_regs = extract_call_args(ctx, args_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["Box"] + arg_regs,
        node=call_node,
    )
    return reg


def _lower_some(ctx: TreeSitterEmitContext, args_node, call_node) -> str:
    """Lower Some(expr) → CALL_FUNCTION 'Option' with single arg."""
    from interpreter.frontends.common.expressions import extract_call_args
    arg_regs = extract_call_args(ctx, args_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["Option"] + arg_regs,
        node=call_node,
    )
    return reg
```

**Note on type parameter encoding:** The spec says `CALL_FUNCTION "Box[Node]"` with the resolved type parameter. However, at lowering time the frontend may not know the concrete type of the argument (it's a register). For the initial implementation, emit `"Box"` and `"Option"` without type parameters. The HeapObject will get `scalar("Box")` as type_hint, which is correct for basic functionality. Type parameter resolution can be added incrementally once the basic flow works.

Update the dispatch table in `interpreter/frontends/rust/frontend.py`:

```python
# In _build_expr_dispatch, change:
#   RustNodeType.CALL_EXPRESSION: common_expr.lower_call,
# to:
    RustNodeType.CALL_EXPRESSION: rust_expr.lower_call_with_box_option,
```

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/unit/test_rust_box_option_lowering.py -v`
Expected: PASS

Run: `poetry run python -m pytest tests/ -x --tb=short -q`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/rust/expressions.py interpreter/frontends/rust/frontend.py tests/unit/test_rust_box_option_lowering.py
git commit -m "feat: lower Box::new and Some calls to CALL_FUNCTION in Rust frontend"
```

---

### Task 6: Lower dereference (*expr) to LOAD_FIELD "value" for Box types

**Files:**
- Modify: `interpreter/frontends/rust/expressions.py`
- Test: `tests/unit/test_rust_box_option_lowering.py` (append)

When the Rust frontend encounters `*box_expr` (dereference), it should emit `LOAD_FIELD "value"` since Box wraps its content in a `value` field.

- [ ] **Step 1: Check existing deref lowering**

Read `lower_deref_expr` and `lower_unary_or_deref` in `interpreter/frontends/rust/expressions.py` to understand the current deref handling.

- [ ] **Step 2: Write failing test**

Add to `tests/unit/test_rust_box_option_lowering.py`:

```python
class TestDerefLowering:
    def test_deref_emits_load_field_value(self):
        """*box_val should emit LOAD_FIELD with 'value' field name."""
        instructions = _parse_rust("""\
struct Node { value: i32 }
let n = Node { value: 42 };
let b = Box::new(n);
let inner = *b;
""")
        # The deref should produce a LOAD_FIELD with "value"
        fields = _find_all(instructions, Opcode.LOAD_FIELD)
        value_fields = [f for f in fields if "value" in f.operands]
        assert len(value_fields) >= 1
```

- [ ] **Step 3: Verify existing behavior**

Run: `poetry run python -m pytest tests/unit/test_rust_box_option_lowering.py::TestDerefLowering -v`

Check what the existing deref lowering produces. If it already emits `LOAD_FIELD "value"` (unlikely — it probably emits pointer dereference logic), implement the change.

- [ ] **Step 4: Implement if needed**

The existing `lower_deref_expr` likely emits some form of pointer dereference. For Box types, `*box_val` should produce `LOAD_FIELD box_reg "value"`. Since we don't have type information at lowering time to distinguish Box deref from raw pointer deref, and the existing Rosetta test uses `.unwrap()` (not `*`), this step may be deferred. Check whether the Rosetta test actually uses `*` on Box — looking at the test program:

```rust
return node.value + sum_list(node.next_node.as_ref().unwrap(), count - 1);
```

It uses `.as_ref().unwrap()`, not `*`. So deref lowering is NOT needed for the Rosetta test. **Skip this task if the Rosetta test doesn't use deref on Box.** Add an xfail test and move on.

- [ ] **Step 5: Commit if changes were made**

```bash
git add interpreter/frontends/rust/expressions.py tests/unit/test_rust_box_option_lowering.py
git commit -m "test: add deref lowering test for Box (xfail — not needed for Rosetta)"
```

---

## Chunk 3: Integration and Rosetta

### Task 7: Integration tests for Box and Option execution

**Files:**
- Modify: `tests/integration/test_rust_frontend_execution.py`
- Test: same file

- [ ] **Step 1: Write integration tests**

Add to `tests/integration/test_rust_frontend_execution.py`:

```python
class TestRustBoxExecution:
    def test_box_value_field_access(self):
        """Box wraps its argument in a 'value' field."""
        vm, local_vars = _run_rust("""\
struct Node { value: i32 }
let n = Node { value: 42 };
let b = Box::new(n);
""", max_steps=300)
        b_addr = local_vars.get("b")
        assert b_addr is not None
        assert b_addr in vm.heap
        assert "value" in vm.heap[b_addr].fields


class TestRustOptionExecution:
    def test_some_creates_option_with_value(self):
        """Some(42) should create an Option object with value field = 42."""
        vm, local_vars = _run_rust("let opt = Some(42);", max_steps=300)
        opt_addr = local_vars.get("opt")
        assert opt_addr is not None
        assert opt_addr in vm.heap
        assert "value" in vm.heap[opt_addr].fields
        # fields store TypedValue wrappers (TypedValue.value holds the raw value)
        from interpreter.typed_value import TypedValue
        tv = vm.heap[opt_addr].fields["value"]
        assert isinstance(tv, TypedValue)
        assert tv.value == 42

    def test_option_unwrap_returns_inner(self):
        """Some(42).unwrap() should return 42."""
        _, local_vars = _run_rust("""\
let opt = Some(42);
let val = opt.unwrap();
""", max_steps=300)
        assert local_vars["val"] == 42

    def test_option_as_ref_identity(self):
        """opt.as_ref() should return the same object."""
        _, local_vars = _run_rust("""\
let opt = Some(42);
let ref_opt = opt.as_ref();
let val = ref_opt.unwrap();
""", max_steps=400)
        assert local_vars["val"] == 42

    def test_nested_box_in_option(self):
        """Some(Box::new(42)) should create nested wrapper."""
        _, local_vars = _run_rust("""\
let opt = Some(Box::new(42));
let inner_box = opt.unwrap();
""", max_steps=400)
        # inner_box should be a heap address pointing to the Box
        assert local_vars.get("inner_box") is not None

    def test_as_ref_unwrap_chain(self):
        """opt.as_ref().unwrap() — the actual Rosetta pattern."""
        _, local_vars = _run_rust("""\
struct Node { value: i32 }
let n = Node { value: 42 };
let opt = Some(Box::new(n));
let inner = opt.as_ref().unwrap();
""", max_steps=500)
        assert local_vars.get("inner") is not None
```

- [ ] **Step 2: Run tests**

Run: `poetry run python -m pytest tests/integration/test_rust_frontend_execution.py::TestRustBoxExecution -v`
Run: `poetry run python -m pytest tests/integration/test_rust_frontend_execution.py::TestRustOptionExecution -v`
Expected: PASS (if Tasks 1-5 are complete)

If tests fail, debug and fix. Common issues:
- Method dispatch for `unwrap`/`as_ref` — check `build_registry` picks up prelude methods
- `self` vs `this` parameter naming — Rust uses Python-style `self`
- Constructor argument binding — check `_try_class_constructor_call` param mapping

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest tests/ -x --tb=short -q`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_rust_frontend_execution.py
git commit -m "test: add integration tests for Rust Box and Option execution"
```

---

### Task 8: Update Rosetta linked list test — move Rust to concrete tier

**Files:**
- Modify: `tests/unit/rosetta/test_rosetta_linked_list.py:436-457`

- [ ] **Step 1: Verify Rosetta Rust test produces concrete answer**

Run the Rosetta linked list test for Rust only:

```bash
poetry run python -m pytest tests/unit/rosetta/test_rosetta_linked_list.py -k "rust" -v
```

If `TestLinkedListSymbolicExecution` passes for Rust (answer exists, 0 LLM calls) AND the answer is actually 6, then Rust can move to the concrete tier.

If the answer is still SymbolicValue, debug:
1. Check prelude classes are emitted and registered
2. Check `Box::new` and `Some` lower to `CALL_FUNCTION`
3. Check `.as_ref().unwrap()` chain resolves through method dispatch
4. Check field access on Box/Option objects returns concrete values
5. Run with verbose logging to trace execution

- [ ] **Step 2: Move Rust from SYMBOLIC to CONCRETE**

In `tests/unit/rosetta/test_rosetta_linked_list.py`, move `"rust"` from `SYMBOLIC_LANGUAGES` to `CONCRETE_LANGUAGES`:

```python
# OLD (~line 436):
CONCRETE_LANGUAGES: frozenset[str] = frozenset(
    {
        "python", "javascript", "typescript", "java", "ruby",
        "csharp", "php", "go", "lua", "c", "cpp", "kotlin", "scala",
    }
)

SYMBOLIC_LANGUAGES: frozenset[str] = frozenset({"rust", "pascal"})

# NEW:
CONCRETE_LANGUAGES: frozenset[str] = frozenset(
    {
        "python", "javascript", "typescript", "java", "ruby",
        "csharp", "php", "go", "lua", "c", "cpp", "kotlin", "scala",
        "rust",
    }
)

SYMBOLIC_LANGUAGES: frozenset[str] = frozenset({"pascal"})
```

Update the module docstring (~lines 10-11) to reflect 14 concrete / 1 symbolic.

- [ ] **Step 3: Run Rosetta tests**

Run: `poetry run python -m pytest tests/unit/rosetta/test_rosetta_linked_list.py -v`
Expected: All pass, including `TestLinkedListConcreteExecution[rust]` with answer=6.

- [ ] **Step 4: Run full test suite and format**

Run: `poetry run python -m black .`
Run: `poetry run python -m pytest tests/ -x --tb=short -q`
Expected: All tests pass.

- [ ] **Step 5: Update README**

Update `README.md` with:
- Rust Box and Option prelude types
- 14/15 languages concrete for Rosetta linked list (only Pascal symbolic)

- [ ] **Step 6: Commit**

```bash
git add tests/unit/rosetta/test_rosetta_linked_list.py README.md
git commit -m "feat: Rust linked list concrete — Box/Option prelude types resolve to answer=6"
```

---

## Implementation Notes

### Method Registration Pattern

The prelude emission (Task 4) needs to register methods so `build_registry` discovers them. Study how `lower_impl_item` in `rust/declarations.py` registers methods:

1. It emits function labels **inside** the class body (between `class_label` and `end_label`)
2. `build_registry` scans for `FUNC_LABEL_PREFIX` labels within class label ranges
3. It may also use `ctx.register_method()` or similar — check the context API

If `TreeSitterEmitContext` doesn't have a `register_class_method` helper, the method labels must be emitted within the class body range, and parameter metadata must be emitted as the registry builder expects.

### Existing Test Fixtures

- Unit tests: `_parse_rust()` helper returns `list[IRInstruction]`
- Integration tests: `_run_rust()` helper in `test_rust_frontend_execution.py` returns `(VMState, dict)`
- Rosetta tests: `execute_for_language("rust", source)` returns `(VMState, ExecutionStats)`

### Type Parameter Resolution (Future)

The initial implementation uses plain class names (`"Box"`, `"Option"`) in `CALL_FUNCTION` operands. Full type parameter resolution (`"Box[Node]"`) requires knowing the argument type at lowering time, which needs frontend type tracking. This is deferred — the basic functionality works without it, and the VM infrastructure (Task 2-3) is ready when type parameter resolution is added.
