# Structured Function References Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace regex-based stringly-typed function references with a symbol table and structured `FuncRef`/`BoundFuncRef` dataclasses, eliminating `FUNC_REF_PATTERN` regex parsing from the pipeline.

**Architecture:** Frontends register function references in a symbol table (`dict[str, FuncRef]`) on `TreeSitterEmitContext` and emit plain label strings in IR. The symbol table flows through the pipeline to registry, type inference, and executor. At runtime, `_handle_const` creates `BoundFuncRef` instances stored in registers. All consumer sites use `isinstance` checks instead of regex parsing.

**Tech Stack:** Python 3.13+, pytest, dataclasses

**Spec:** `docs/superpowers/specs/2026-03-15-structured-func-refs-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `interpreter/func_ref.py` | Create | `FuncRef` and `BoundFuncRef` frozen dataclasses |
| `interpreter/frontends/context.py` | Modify | Add `func_symbol_table` field and `emit_func_ref()` method |
| `interpreter/frontend.py` | Modify | Add `func_symbol_table` property to `Frontend` ABC |
| `interpreter/constants.py` | Modify | Delete `FUNC_REF_PATTERN`, `FUNC_REF_TEMPLATE` |
| `interpreter/registry.py` | Modify | Delete `_parse_func_ref`, `RefPatterns.FUNC_RE`; accept symbol table |
| `interpreter/type_inference.py` | Modify | Delete `_FUNC_REF_PATTERN`, `_FUNC_REF_EXTRACT`; accept symbol table |
| `interpreter/executor.py` | Modify | 7 call sites: `isinstance(val, BoundFuncRef)` instead of `_parse_func_ref()` |
| `interpreter/run.py` | Modify | Thread symbol table through pipeline; `_format_val` for `BoundFuncRef` |
| `interpreter/frontends/` (15 langs) | Modify | Replace `FUNC_REF_TEMPLATE.format(...)` with `ctx.emit_func_ref(...)` |
| `interpreter/llm_frontend.py` | Modify | Parse `<function:...>` strings into symbol table entries |
| `interpreter/chunked_llm_frontend.py` | Modify | Convert after reassembly |
| `tests/unit/test_func_ref.py` | Create | Unit tests for `FuncRef`, `BoundFuncRef`, symbol table |
| `tests/unit/test_*_frontend.py` | Modify | Update IR shape assertions from `<function:...>` to plain labels |

---

## Task 1: FuncRef and BoundFuncRef dataclasses

**Files:**
- Create: `interpreter/func_ref.py`
- Create: `tests/unit/test_func_ref.py`

- [ ] **Step 1: Write tests for FuncRef and BoundFuncRef**

```python
# tests/unit/test_func_ref.py
"""Unit tests for FuncRef and BoundFuncRef dataclasses."""

from __future__ import annotations

from interpreter.func_ref import FuncRef, BoundFuncRef


class TestFuncRef:
    def test_construction(self):
        ref = FuncRef(name="add", label="func_add_0")
        assert ref.name == "add"
        assert ref.label == "func_add_0"

    def test_frozen(self):
        ref = FuncRef(name="add", label="func_add_0")
        import pytest
        with pytest.raises(AttributeError):
            ref.name = "other"

    def test_equality(self):
        a = FuncRef(name="add", label="func_add_0")
        b = FuncRef(name="add", label="func_add_0")
        assert a == b

    def test_different_labels_not_equal(self):
        a = FuncRef(name="add", label="func_add_0")
        b = FuncRef(name="add", label="func_add_1")
        assert a != b

    def test_dotted_name(self):
        """Dotted names like Counter.new are valid — the whole point of this refactor."""
        ref = FuncRef(name="Counter.new", label="func_new_0")
        assert ref.name == "Counter.new"


class TestBoundFuncRef:
    def test_construction_with_closure(self):
        fr = FuncRef(name="inner", label="func_inner_0")
        bound = BoundFuncRef(func_ref=fr, closure_id="closure_42")
        assert bound.func_ref.name == "inner"
        assert bound.func_ref.label == "func_inner_0"
        assert bound.closure_id == "closure_42"

    def test_construction_without_closure(self):
        fr = FuncRef(name="add", label="func_add_0")
        bound = BoundFuncRef(func_ref=fr, closure_id="")
        assert bound.closure_id == ""

    def test_frozen(self):
        fr = FuncRef(name="add", label="func_add_0")
        bound = BoundFuncRef(func_ref=fr, closure_id="")
        import pytest
        with pytest.raises(AttributeError):
            bound.closure_id = "other"

    def test_composition_not_inheritance(self):
        """BoundFuncRef is NOT a FuncRef subclass."""
        assert not issubclass(BoundFuncRef, FuncRef)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_func_ref.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'interpreter.func_ref'`

- [ ] **Step 3: Implement FuncRef and BoundFuncRef**

```python
# interpreter/func_ref.py
"""Structured function references — replaces stringly-typed FUNC_REF_PATTERN."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FuncRef:
    """Compile-time function reference. Lives in the symbol table."""

    name: str   # "add", "new", "__lambda"
    label: str  # "func_add_0"


@dataclass(frozen=True)
class BoundFuncRef:
    """Runtime function reference with closure binding. Stored in registers."""

    func_ref: FuncRef
    closure_id: str  # "closure_42" or "" for non-closures
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_func_ref.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add interpreter/func_ref.py tests/unit/test_func_ref.py
git commit -m "feat: add FuncRef and BoundFuncRef dataclasses (red-dragon-fdc)"
```

---

## Task 2: Symbol table on TreeSitterEmitContext + emit_func_ref()

**Files:**
- Modify: `interpreter/frontends/context.py`
- Modify: `interpreter/frontend.py`
- Create: `tests/unit/test_emit_func_ref.py`

- [ ] **Step 1: Write tests for emit_func_ref**

```python
# tests/unit/test_emit_func_ref.py
"""Unit tests for TreeSitterEmitContext.emit_func_ref() and func_symbol_table."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontend_observer import FrontendObserver
from interpreter.constants import Language
from interpreter.func_ref import FuncRef
from interpreter.ir import Opcode
from interpreter.grammar_constants import GrammarConstants


def _make_ctx(lang: Language = Language.PYTHON) -> TreeSitterEmitContext:
    return TreeSitterEmitContext(
        source=b"",
        language=lang,
        observer=FrontendObserver(),
        constants=GrammarConstants.for_language(lang),
    )


class TestEmitFuncRef:
    def test_registers_in_symbol_table(self):
        ctx = _make_ctx()
        ctx.emit_func_ref("add", "func_add_0", result_reg="%0")
        assert "func_add_0" in ctx.func_symbol_table
        ref = ctx.func_symbol_table["func_add_0"]
        assert ref == FuncRef(name="add", label="func_add_0")

    def test_emits_const_with_plain_label(self):
        ctx = _make_ctx()
        ctx.emit_func_ref("add", "func_add_0", result_reg="%0")
        const_insts = [i for i in ctx.instructions if i.opcode == Opcode.CONST]
        assert len(const_insts) == 1
        assert const_insts[0].operands == ["func_add_0"]
        assert const_insts[0].result_reg == "%0"

    def test_no_angle_brackets_in_operand(self):
        ctx = _make_ctx()
        ctx.emit_func_ref("my_func", "func_my_func_0", result_reg="%1")
        const_inst = [i for i in ctx.instructions if i.opcode == Opcode.CONST][0]
        operand = str(const_inst.operands[0])
        assert "<" not in operand
        assert ">" not in operand

    def test_multiple_registrations(self):
        ctx = _make_ctx()
        ctx.emit_func_ref("foo", "func_foo_0", result_reg="%0")
        ctx.emit_func_ref("bar", "func_bar_0", result_reg="%1")
        assert len(ctx.func_symbol_table) == 2
        assert ctx.func_symbol_table["func_foo_0"].name == "foo"
        assert ctx.func_symbol_table["func_bar_0"].name == "bar"

    def test_dotted_name_works(self):
        """The original regex couldn't handle dots. Symbol table can."""
        ctx = _make_ctx()
        ctx.emit_func_ref("Counter.new", "func_new_0", result_reg="%0")
        assert ctx.func_symbol_table["func_new_0"].name == "Counter.new"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_emit_func_ref.py -v`
Expected: FAIL with `AttributeError: 'TreeSitterEmitContext' object has no attribute 'emit_func_ref'`

- [ ] **Step 3: Add func_symbol_table and emit_func_ref to TreeSitterEmitContext**

In `interpreter/frontends/context.py`, add to the imports:
```python
from interpreter.func_ref import FuncRef
```

Add to the `TreeSitterEmitContext` fields (after line 128, alongside other mutable state):
```python
    func_symbol_table: dict[str, FuncRef] = field(default_factory=dict)
```

Add a new method (after `emit_decl_var` or similar convenience methods):
```python
    def emit_func_ref(
        self,
        func_name: str,
        func_label: str,
        result_reg: str,
        node=None,
    ) -> IRInstruction:
        """Register a function reference in the symbol table and emit CONST."""
        self.func_symbol_table[func_label] = FuncRef(name=func_name, label=func_label)
        return self.emit(
            Opcode.CONST,
            result_reg=result_reg,
            operands=[func_label],
            node=node,
        )
```

- [ ] **Step 4: Add func_symbol_table property to Frontend ABC**

In `interpreter/frontend.py`, add import and property:
```python
from interpreter.func_ref import FuncRef
```

Add property to the `Frontend` ABC (after `type_env_builder`):
```python
    @property
    def func_symbol_table(self) -> dict[str, FuncRef]:
        """Function reference symbol table accumulated during lowering.

        Override in frontends that populate func refs during lowering.
        Returns an empty dict by default.
        """
        return {}
```

- [ ] **Step 4b: Add func_symbol_table to BaseFrontend**

In `interpreter/frontends/_base.py`, `BaseFrontend(Frontend)` has two lowering modes:

**Context mode** (line 211-229): Uses `TreeSitterEmitContext`. After lowering, copy the symbol table — add after line 228 (`self._type_env_builder.var_scope_metadata = ...`):
```python
self._func_symbol_table = ctx.func_symbol_table
```

**Legacy mode** (line 198-206): Uses `self._emit()` directly. Add a `_func_symbol_table` field and `_emit_func_ref` method:
```python
# In __init__ or as class field:
self._func_symbol_table: dict[str, FuncRef] = {}

def _emit_func_ref(self, func_name: str, func_label: str, result_reg: str, node=None) -> IRInstruction:
    """Legacy-mode equivalent of ctx.emit_func_ref()."""
    self._func_symbol_table[func_label] = FuncRef(name=func_name, label=func_label)
    return self._emit(Opcode.CONST, result_reg=result_reg, operands=[func_label], node=node)
```

Override the `func_symbol_table` property (following the `type_env_builder` pattern at line 162-163):
```python
@property
def func_symbol_table(self) -> dict[str, FuncRef]:
    return self._func_symbol_table
```

Import `FuncRef`:
```python
from interpreter.func_ref import FuncRef
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_emit_func_ref.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `poetry run python -m pytest --tb=short -q`
Expected: 11666 passed (no changes to existing behavior yet)

- [ ] **Step 7: Commit**

```bash
git add interpreter/func_ref.py interpreter/frontends/context.py interpreter/frontend.py tests/unit/test_emit_func_ref.py
git commit -m "feat: add func_symbol_table and emit_func_ref() to TreeSitterEmitContext"
```

---

## Task 3: Convert all 15 tree-sitter frontends to use emit_func_ref

**Files:**
- Modify: all files under `interpreter/frontends/` that contain `FUNC_REF_TEMPLATE.format`

This is a mechanical replacement. Every site that does:
```python
ctx.emit(
    Opcode.CONST,
    result_reg=func_reg,
    operands=[constants.FUNC_REF_TEMPLATE.format(name=func_name, label=func_label)],
)
```
becomes:
```python
ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)
```

If the call has a `node=node` argument on the original `ctx.emit`, pass it through to `emit_func_ref`.

- [ ] **Step 1: Find all 56 sites**

Run: `grep -rn "FUNC_REF_TEMPLATE.format" interpreter/frontends/`

This produces the complete list of files and line numbers to change.

- [ ] **Step 2: Convert all 28 files (56 sites)**

Complete file list — every file containing `FUNC_REF_TEMPLATE.format`:

| # | File | Sites |
|---|------|-------|
| 1 | `_base.py` | 1 (uses `self._emit` — use `self._emit_func_ref` instead) |
| 2 | `common/declarations.py` | 2 |
| 3 | `c/declarations.py` | 2 |
| 4 | `cpp/declarations.py` | 3 |
| 5 | `cpp/expressions.py` | 1 |
| 6 | `csharp/declarations.py` | 4 |
| 7 | `csharp/expressions.py` | 1 |
| 8 | `go/declarations.py` | 3 |
| 9 | `go/expressions.py` | 1 |
| 10 | `java/declarations.py` | 2 |
| 11 | `java/expressions.py` | 1 |
| 12 | `javascript/declarations.py` | 2 |
| 13 | `javascript/expressions.py` | 2 |
| 14 | `kotlin/declarations.py` | 2 |
| 15 | `kotlin/expressions.py` | 2 |
| 16 | `lua/declarations.py` | 1 |
| 17 | `lua/expressions.py` | 1 |
| 18 | `pascal/declarations.py` | 1 |
| 19 | `php/declarations.py` | 4 |
| 20 | `php/expressions.py` | 2 |
| 21 | `python/expressions.py` | 1 |
| 22 | `ruby/declarations.py` | 2 |
| 23 | `ruby/expressions.py` | 1 |
| 24 | `rust/declarations.py` | 3 |
| 25 | `rust/expressions.py` | 1 |
| 26 | `scala/declarations.py` | 3 |
| 27 | `scala/expressions.py` | 1 |
| 28 | `typescript.py` | 6 (single-file frontend, NOT `typescript/declarations.py`) |

For `_base.py` (legacy mode), use `self._emit_func_ref(func_name, func_label, result_reg=func_reg)`.
For all other files (context mode), use `ctx.emit_func_ref(func_name, func_label, result_reg=func_reg)`.

**Important patterns to watch for:**

Some sites emit a 3-line `ctx.emit(Opcode.CONST, ...)` call. Others may be on a single line. The key is: wherever `FUNC_REF_TEMPLATE.format(name=X, label=Y)` appears as an operand to a `CONST` emit, replace the entire `ctx.emit(Opcode.CONST, ...)` with `ctx.emit_func_ref(X, Y, result_reg=R)`.

Some sites also pass `node=node` — preserve this argument.

- [ ] **Step 3: Remove `FUNC_REF_TEMPLATE` imports**

After converting all sites, remove any `from interpreter import constants` or `constants.FUNC_REF_TEMPLATE` references that are no longer used. Be careful: `constants` may still be needed for other constants (`CLASS_REF_TEMPLATE`, `PARAM_PREFIX`, etc.) — only remove the import if nothing else from `constants` is used in that file.

- [ ] **Step 4: Update unit test IR shape assertions**

Find all ~81 test assertions that reference `<function:` strings:

Run: `grep -rn '"<function:\|function:.*@' tests/unit/ | grep -v ".pyc"`

For each test file, replace assertions like:
```python
assert inst.operands[0] == f"<function:add@func_add_0>"
# or
assert f"<function:{name}@{label}>" in str(inst.operands[0])
```
with:
```python
assert inst.operands[0] == "func_add_0"
# or
assert inst.operands[0] == label
```

Work through test files systematically. The exact assertion format varies — some check string containment, some check equality. Replace each with the appropriate plain label check.

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL tests pass (11666+). Tests must be green before committing.

- [ ] **Step 6: Commit**

```bash
git add interpreter/frontends/ tests/unit/
git commit -m "refactor: convert all 15 frontends to emit_func_ref (plain labels in IR)"
```

---

## Task 4: Registry accepts symbol table instead of regex

**Files:**
- Modify: `interpreter/registry.py`
- Modify: `interpreter/run.py` (thread symbol table to `build_registry`)

- [ ] **Step 1: Understand the current registry scanning**

Read `interpreter/registry.py` function `_scan_classes()`. Find the line that does `_parse_func_ref(str(inst.operands[0]))` to discover class methods. This is around line 149-152. It scans CONST operands inside class blocks to find method references.

- [ ] **Step 2: Add func_symbol_table parameter to build_registry**

Change the `build_registry` signature:
```python
def build_registry(
    instructions: list[IRInstruction],
    cfg: CFG,
    func_symbol_table: dict[str, FuncRef] = {},
) -> FunctionRegistry:
```

Import `FuncRef`:
```python
from interpreter.func_ref import FuncRef
```

- [ ] **Step 3: Replace _parse_func_ref with symbol table lookup in _scan_classes**

Pass `func_symbol_table` to `_scan_classes`. In the method discovery code, replace:
```python
fr = _parse_func_ref(str(inst.operands[0]))
if fr.matched:
    class_methods[in_class].setdefault(fr.name, []).append(fr.label)
```
with:
```python
operand = str(inst.operands[0])
if operand in func_symbol_table:
    ref = func_symbol_table[operand]
    class_methods[in_class].setdefault(ref.name, []).append(ref.label)
```

- [ ] **Step 4: Thread symbol table in run.py**

In `interpreter/run.py`, update the `build_registry` call (around line 604):
```python
registry = build_registry(instructions, cfg, func_symbol_table=frontend.func_symbol_table)
```

Do the same in `execute_cfg_traced` if it calls `build_registry` directly (check).

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL tests pass.

- [ ] **Step 6: Commit**

```bash
git add interpreter/registry.py interpreter/run.py
git commit -m "refactor: registry uses func_symbol_table instead of _parse_func_ref"
```

---

## Task 5: Type inference accepts symbol table instead of regex

**Files:**
- Modify: `interpreter/type_inference.py`
- Modify: `interpreter/run.py` (thread symbol table to `infer_types`)

- [ ] **Step 1: Add func_symbol_table parameter to infer_types**

Change the `infer_types` signature (around line 317):
```python
def infer_types(
    instructions: list[IRInstruction],
    type_resolver: TypeResolver,
    type_env_builder: TypeEnvironmentBuilder = TypeEnvironmentBuilder(),
    func_symbol_table: dict[str, FuncRef] = {},
) -> TypeEnvironment:
```

Import `FuncRef`:
```python
from interpreter.func_ref import FuncRef
```

- [ ] **Step 2: Replace _FUNC_REF_EXTRACT usage (line ~486)**

In the function that uses `_FUNC_REF_EXTRACT.search(raw)` to extract function name and label for `FunctionType` construction, replace with:
```python
raw = str(inst.operands[0]) if inst.operands else ""
if raw in func_symbol_table:
    ref = func_symbol_table[raw]
    func_name, func_label = ref.name, ref.label
    # ... rest of FunctionType construction stays the same
```

Thread `func_symbol_table` through the internal call chain to reach this point. Follow how `type_env_builder` is threaded as a pattern.

- [ ] **Step 3: Replace _FUNC_REF_PATTERN usage (line ~872)**

The prefix check `_FUNC_REF_PATTERN.search(str(raw))` that returns `UNKNOWN` for function refs becomes:
```python
if str(raw) in func_symbol_table:
    return UNKNOWN
```

- [ ] **Step 4: Delete the two regex patterns**

Remove these lines (around 136-137):
```python
_FUNC_REF_PATTERN = re.compile(r"<function:")
_FUNC_REF_EXTRACT = re.compile(constants.FUNC_REF_PATTERN)
```

Remove the `import re` if no longer needed. Remove `constants.FUNC_REF_PATTERN` import if no longer needed.

- [ ] **Step 5: Thread symbol table in run.py**

Update the `infer_types` call (around line 612):
```python
type_env = infer_types(
    instructions,
    type_resolver,
    type_env_builder=frontend.type_env_builder,
    func_symbol_table=frontend.func_symbol_table,
)
```

- [ ] **Step 6: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL tests pass.

- [ ] **Step 7: Commit**

```bash
git add interpreter/type_inference.py interpreter/run.py
git commit -m "refactor: type inference uses func_symbol_table instead of regex"
```

---

## Task 6: Executor uses BoundFuncRef instead of _parse_func_ref

**Files:**
- Modify: `interpreter/executor.py`
- Modify: `interpreter/run.py` (thread symbol table to `execute_cfg`)

This is the most important task — 7 call sites in executor.py switch from regex to structured types.

- [ ] **Step 1: Thread symbol table to executor**

In `interpreter/run.py`, update `execute_cfg()` and `execute_cfg_traced()` signatures to accept `func_symbol_table` and pass it through to `_try_execute_locally`. Follow how `registry` is threaded.

In `interpreter/executor.py`, add `func_symbol_table` as a parameter to `_try_execute_locally` and the internal dispatch. Thread it to `_handle_const` via `kwargs`.

Import:
```python
from interpreter.func_ref import FuncRef, BoundFuncRef
```

- [ ] **Step 2: Rewrite _handle_const (site 1 — the critical one)**

Current code (lines 80-123) regex-parses the CONST value, creates closure environments, and reconstructs the string with closure ID appended.

New logic:
```python
def _handle_const(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    func_symbol_table = kwargs.get("func_symbol_table", {})
    raw = inst.operands[0] if inst.operands else "None"
    val = _parse_const(raw)

    # Symbol table lookup: if this CONST is a function label, produce BoundFuncRef
    if isinstance(val, str) and val in func_symbol_table:
        func_ref = func_symbol_table[val]
        closure_id = ""

        # Closure capture: inner functions get linked to enclosing scope
        if len(vm.call_stack) > 1:
            enclosing = vm.current_frame
            env_id = enclosing.closure_env_id
            if env_id:
                env = vm.closures[env_id]
                for k, v in enclosing.local_vars.items():
                    if k not in env.bindings:
                        env.bindings[k] = v
            else:
                env_id = f"{constants.ENV_ID_PREFIX}{vm.symbolic_counter}"
                vm.symbolic_counter += 1
                env = ClosureEnvironment(bindings=dict(enclosing.local_vars))
                vm.closures[env_id] = env
                enclosing.closure_env_id = env_id
                enclosing.captured_var_names = frozenset(enclosing.local_vars.keys())
            closure_id = f"closure_{vm.symbolic_counter}"
            vm.symbolic_counter += 1
            vm.closures[closure_id] = env
            logger.debug(
                "Captured closure %s (env %s) for %s: %s",
                closure_id,
                env_id,
                func_ref.name,
                list(env.bindings.keys()),
            )

        val = BoundFuncRef(func_ref=func_ref, closure_id=closure_id)

    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: typed_from_runtime(val)},
            reasoning=f"const {raw!r} → {inst.result_reg}",
        )
    )
```

- [ ] **Step 3: Rewrite _try_user_function_call (site 2)**

Change the function to accept `BoundFuncRef` directly instead of parsing a string:

```python
def _try_user_function_call(
    func_val: Any,
    args: list[TypedValue],
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str,
) -> ExecutionResult:
    """Attempt to dispatch a call to a user-defined function."""
    if not isinstance(func_val, BoundFuncRef):
        return ExecutionResult.not_handled()

    fname, flabel = func_val.func_ref.name, func_val.func_ref.label
    if flabel not in cfg.blocks:
        return ExecutionResult.not_handled()

    params = registry.func_params.get(flabel, [])
    param_vars = {params[i]: arg for i, arg in enumerate(args) if i < len(params)}
    args_result = _builtin_array_of(list(args), vm)
    param_vars["arguments"] = typed(args_result.value, UNKNOWN)

    closure_env: ClosureEnvironment | None = None
    captured: dict[str, Any] = {}
    if func_val.closure_id:
        closure_env = vm.closures.get(func_val.closure_id)
        if closure_env:
            captured = closure_env.bindings

    # ... rest of function unchanged, but replace fr.name→fname, fr.label→flabel,
    # fr.closure_id→func_val.closure_id throughout
```

- [ ] **Step 4: Update _handle_address_of identity (site 3, line ~239)**

Replace:
```python
if isinstance(current_val, str) and _parse_func_ref(current_val).matched:
```
with:
```python
if isinstance(current_val, BoundFuncRef):
```

- [ ] **Step 5: Update _handle_load_field pointer deref (site 4, line ~440)**

Replace:
```python
if (
    field_name == "*"
    and isinstance(obj_val, str)
    and _parse_func_ref(obj_val).matched
):
```
with:
```python
if field_name == "*" and isinstance(obj_val, BoundFuncRef):
```

- [ ] **Step 6: Update _handle_unop & address-of (site 5, line ~788)**

Replace:
```python
if addr and (_parse_func_ref(operand).matched or addr in vm.heap):
```
with:
```python
if addr and (isinstance(operand, BoundFuncRef) or addr in vm.heap):
```

Note: check what `_heap_addr` returns for a `BoundFuncRef` — it may need adjustment since it likely expects a string. If `_heap_addr` returns `None` for non-strings, the `addr and ...` guard already handles it. Verify.

- [ ] **Step 7: Update _handle_call_method .call()/.apply() (site 6, line ~1308)**

Replace:
```python
func_ref = _parse_func_ref(obj_val.value)
if func_ref.matched:
    return _try_user_function_call(
```
with:
```python
if isinstance(obj_val.value, BoundFuncRef):
    return _try_user_function_call(
```

- [ ] **Step 8: Delete _parse_func_ref import (site 7)**

Remove from the import line (~line 32):
```python
from interpreter.registry import FunctionRegistry, _parse_func_ref, _parse_class_ref
```
Change to:
```python
from interpreter.registry import FunctionRegistry, _parse_class_ref
```

- [ ] **Step 9: Add _format_val BoundFuncRef branch in run.py**

In `interpreter/run.py`, update `_format_val` (around line 662):
```python
from interpreter.func_ref import BoundFuncRef
```

Add a branch before the final `repr(v)`:
```python
if isinstance(v, BoundFuncRef):
    if v.closure_id:
        return f"<function:{v.func_ref.name}@{v.func_ref.label}#{v.closure_id}>"
    return f"<function:{v.func_ref.name}@{v.func_ref.label}>"
```

- [ ] **Step 10: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL tests pass. Unit test IR shape assertions were already updated in Task 3.

- [ ] **Step 11: Commit**

```bash
git add interpreter/executor.py interpreter/run.py
git commit -m "refactor: executor uses BoundFuncRef instead of _parse_func_ref regex"
```

---

## Task 7: Delete dead code and LLM frontend boundary conversion

**Files:**
- Modify: `interpreter/constants.py` — delete `FUNC_REF_PATTERN`, `FUNC_REF_TEMPLATE`
- Modify: `interpreter/registry.py` — delete `_parse_func_ref()`, `RefPatterns.FUNC_RE`
- Modify: `interpreter/llm_frontend.py` — parse `<function:...>` into symbol table entries
- Modify: `interpreter/chunked_llm_frontend.py` — convert after reassembly

- [ ] **Step 1: Delete FUNC_REF_PATTERN and FUNC_REF_TEMPLATE from constants.py**

Remove from `interpreter/constants.py` (lines 36, 39):
```python
FUNC_REF_PATTERN = r"<function:(\w+)@(\w+)(?:#(\w+))?>"
FUNC_REF_TEMPLATE = "<function:{name}@{label}>"
```

- [ ] **Step 2: Delete _parse_func_ref and RefPatterns.FUNC_RE from registry.py**

Remove the `_parse_func_ref` function (lines 34-46) and `RefPatterns.FUNC_RE` (line 30). Keep `_parse_class_ref` and `RefPatterns.CLASS_RE` — those are out of scope (red-dragon-wgb).

If `RefPatterns` only has `CLASS_RE` left, consider whether it's worth keeping the class or inlining.

- [ ] **Step 3: Handle LLM frontend boundary**

Read `interpreter/llm_frontend.py` to understand how it parses LLM-emitted IR. Find where it processes `CONST` instructions with `<function:...>` operands.

Add a conversion step: after the LLM frontend parses IR instructions, scan for CONST operands matching the `<function:name@label>` pattern, create `FuncRef` entries in a symbol table, and replace the operand with the plain label.

Use a local regex here — this is the ONLY place regex is allowed, at the LLM boundary:
```python
import re
_LLM_FUNC_REF_RE = re.compile(r"<function:(\w+)@(\w+)(?:#(\w+))?>")

def _convert_llm_func_refs(instructions, func_symbol_table):
    for inst in instructions:
        if inst.opcode == Opcode.CONST and inst.operands:
            m = _LLM_FUNC_REF_RE.search(str(inst.operands[0]))
            if m:
                name, label = m.group(1), m.group(2)
                func_symbol_table[label] = FuncRef(name=name, label=label)
                inst.operands[0] = label
```

Do the same for `chunked_llm_frontend.py` after reassembly.

Make sure the LLM frontend's `func_symbol_table` property returns this table.

- [ ] **Step 4: Verify no remaining references to deleted code**

Run: `grep -rn "FUNC_REF_PATTERN\|FUNC_REF_TEMPLATE\|_parse_func_ref\|FUNC_RE" interpreter/ tests/`

Expected: No matches except in `llm_frontend.py` (local regex) and possibly test files for the LLM frontend.

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL tests pass

- [ ] **Step 6: Commit**

```bash
git add interpreter/constants.py interpreter/registry.py interpreter/llm_frontend.py interpreter/chunked_llm_frontend.py
git commit -m "refactor: delete FUNC_REF_PATTERN/TEMPLATE, add LLM boundary conversion"
```

---

## Task 8: ADR, README, cleanup

**Files:**
- Modify: `docs/architectural-design-decisions.md`
- Modify: `README.md`

- [ ] **Step 1: Add ADR-105**

Add to `docs/architectural-design-decisions.md`:

```markdown
### ADR-105: Structured function references via symbol table (2026-03-15)

**Context:** Function references were stringly-typed — frontends emitted `CONST "<function:name@label>"` and every consumer (registry, type inference, executor) regex-parsed this string back. This was fragile (dotted names broke `\w+` matching) and violated the principle of passing decisions through data.

**Decision:** Replace with a symbol table (`dict[str, FuncRef]`) on `TreeSitterEmitContext`. Frontends call `ctx.emit_func_ref(name, label)` which registers a `FuncRef(name, label)` and emits `CONST label` (plain string). At runtime, `_handle_const` looks up the label in the symbol table and creates a `BoundFuncRef(func_ref, closure_id)` stored in the register. All consumer sites use `isinstance(val, BoundFuncRef)` instead of regex. The LLM frontend boundary retains a local regex for parsing LLM-emitted strings, converting to structured refs before pipeline entry.

**Files:** `interpreter/func_ref.py`, `interpreter/frontends/context.py`, `interpreter/executor.py`, `interpreter/registry.py`, `interpreter/type_inference.py`, `interpreter/run.py`, all 15 frontend dirs.
```

- [ ] **Step 2: Update README if needed**

Check if README mentions `FUNC_REF_PATTERN` or the string format. Update any references.

- [ ] **Step 3: Close beads issue**

Run: `bd update red-dragon-fdc --status closed`

- [ ] **Step 4: Run formatter and full test suite**

```bash
poetry run python -m black .
poetry run python -m pytest --tb=short -q
```
Expected: ALL tests pass, formatting clean.

- [ ] **Step 5: Commit and push**

```bash
git add docs/architectural-design-decisions.md README.md .beads/
git commit -m "docs: ADR-105 structured function references, close red-dragon-fdc"
git push origin main
```
