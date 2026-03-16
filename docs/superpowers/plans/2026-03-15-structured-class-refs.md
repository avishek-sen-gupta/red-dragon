# Structured Class References Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace regex-based stringly-typed class references with a symbol table and structured `ClassRef` dataclass, eliminating `CLASS_REF_PATTERN` regex parsing from the pipeline.

**Architecture:** Frontends register class references in a symbol table (`dict[str, ClassRef]`) on `TreeSitterEmitContext` and emit plain label strings in IR. The symbol table flows through the pipeline to registry, type inference, and executor. Consumer sites use `isinstance` checks or symbol table lookups instead of regex parsing. A `NO_CLASS_REF` null object sentinel eliminates `None` checks. No runtime binding equivalent (unlike `BoundFuncRef` for closures) — class references are purely compile-time.

**Tech Stack:** Python 3.13+, pytest, dataclasses

**Spec:** `docs/superpowers/specs/2026-03-15-structured-class-refs-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `interpreter/class_ref.py` | Create | `ClassRef` frozen dataclass + `NO_CLASS_REF` sentinel |
| `interpreter/frontends/context.py` | Modify | Add `class_symbol_table` field and `emit_class_ref()` method |
| `interpreter/frontends/_base.py` | Modify | Add `_class_symbol_table`, `_emit_class_ref()`, `class_symbol_table` property |
| `interpreter/frontend.py` | Modify | Add `class_symbol_table` property to `Frontend` ABC |
| `interpreter/frontends/common/declarations.py` | Modify | Replace `make_class_ref()` with `ctx.emit_class_ref()` in `lower_class_def` |
| `interpreter/frontends/` (15 frontend files, 33 sites) | Modify | Replace `make_class_ref()`/`CLASS_REF_TEMPLATE.format(...)` with `ctx.emit_class_ref(...)` |
| `interpreter/constants.py` | Modify | Delete `CLASS_REF_PATTERN`, `CLASS_REF_TEMPLATE`, `CLASS_REF_WITH_PARENTS_TEMPLATE` |
| `interpreter/registry.py` | Modify | Delete `_parse_class_ref()`, `RefPatterns`, `RefParseResult`; accept class symbol table |
| `interpreter/type_inference.py` | Modify | Delete `_CLASS_REF_PATTERN`; accept class symbol table |
| `interpreter/executor.py` | Modify | `isinstance(val, ClassRef)` at 2 sites; delete `_parse_class_ref` import |
| `interpreter/run.py` | Modify | Thread class symbol table through pipeline |
| `interpreter/llm_frontend.py` | Modify | Parse `<class:...>` strings into symbol table entries |
| `interpreter/chunked_llm_frontend.py` | Modify | Convert after reassembly |
| `interpreter/api.py` | Modify | Pass class symbol table to `infer_types` |
| `tests/unit/rosetta/conftest.py` | Modify | Pass class symbol table to `build_registry` and `execute_cfg` |
| `tests/unit/test_class_ref.py` | Create | Unit tests for `ClassRef`, `NO_CLASS_REF` |
| `tests/unit/test_emit_class_ref.py` | Create | Unit tests for `emit_class_ref()` |
| `tests/unit/test_class_inheritance.py` | Modify | Delete `TestParseClassRef` (4 tests); update IR shape assertions |
| `tests/unit/test_registry.py` | Modify | Update IR shape assertions |
| `tests/unit/test_type_inference.py` | Modify | Update IR shape assertions |
| `tests/unit/` (various frontend tests) | Modify | Update `<class:...>` assertions to plain labels |

---

## Chunk 1: Core Infrastructure

### Task 1: ClassRef dataclass and NO_CLASS_REF sentinel

**Files:**
- Create: `interpreter/class_ref.py`
- Create: `tests/unit/test_class_ref.py`

- [ ] **Step 1: Write tests for ClassRef and NO_CLASS_REF**

```python
# tests/unit/test_class_ref.py
"""Unit tests for ClassRef dataclass and NO_CLASS_REF sentinel."""

from __future__ import annotations

import pytest

from interpreter.class_ref import ClassRef, NO_CLASS_REF


class TestClassRef:
    def test_construction_no_parents(self):
        ref = ClassRef(name="Dog", label="class_Dog_0", parents=())
        assert ref.name == "Dog"
        assert ref.label == "class_Dog_0"
        assert ref.parents == ()

    def test_construction_with_parents(self):
        ref = ClassRef(name="Dog", label="class_Dog_0", parents=("Animal",))
        assert ref.parents == ("Animal",)

    def test_multiple_parents(self):
        ref = ClassRef(name="C", label="class_C_0", parents=("A", "B"))
        assert ref.parents == ("A", "B")

    def test_frozen(self):
        ref = ClassRef(name="Dog", label="class_Dog_0", parents=())
        with pytest.raises(AttributeError):
            ref.name = "Cat"

    def test_equality(self):
        a = ClassRef(name="Dog", label="class_Dog_0", parents=("Animal",))
        b = ClassRef(name="Dog", label="class_Dog_0", parents=("Animal",))
        assert a == b

    def test_different_labels_not_equal(self):
        a = ClassRef(name="Dog", label="class_Dog_0", parents=())
        b = ClassRef(name="Dog", label="class_Dog_1", parents=())
        assert a != b

    def test_hashable(self):
        """Frozen dataclasses should be usable as dict keys."""
        ref = ClassRef(name="Dog", label="class_Dog_0", parents=())
        d = {ref: True}
        assert d[ref] is True

    def test_parents_is_tuple(self):
        """Parents must be a tuple, not a list, for immutability."""
        ref = ClassRef(name="Dog", label="class_Dog_0", parents=("Animal",))
        assert isinstance(ref.parents, tuple)


class TestNoClassRef:
    def test_sentinel_fields(self):
        assert NO_CLASS_REF.name == ""
        assert NO_CLASS_REF.label == ""
        assert NO_CLASS_REF.parents == ()

    def test_name_is_falsy(self):
        """Consumer sites check ref.name truthiness for failed lookups."""
        assert not NO_CLASS_REF.name

    def test_is_class_ref_instance(self):
        assert isinstance(NO_CLASS_REF, ClassRef)

    def test_lookup_pattern(self):
        """Verify the .get(label, NO_CLASS_REF) pattern works."""
        table: dict[str, ClassRef] = {
            "class_Dog_0": ClassRef(name="Dog", label="class_Dog_0", parents=())
        }
        found = table.get("class_Dog_0", NO_CLASS_REF)
        assert found.name == "Dog"

        missing = table.get("class_Cat_0", NO_CLASS_REF)
        assert not missing.name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_class_ref.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'interpreter.class_ref'`

- [ ] **Step 3: Implement ClassRef and NO_CLASS_REF**

```python
# interpreter/class_ref.py
"""Structured class references — replaces stringly-typed CLASS_REF_PATTERN."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassRef:
    """Compile-time class reference. Lives in the symbol table.

    Unlike FuncRef/BoundFuncRef, class references have no runtime binding
    equivalent — they are purely compile-time records.
    """

    name: str                  # "Dog", "Counter", "__anon_class_0"
    label: str                 # "class_Dog_0"
    parents: tuple[str, ...]   # ("Animal",) or () for no parents


NO_CLASS_REF = ClassRef(name="", label="", parents=())
"""Null object sentinel for failed symbol table lookups.

Consumer sites use ``table.get(label, NO_CLASS_REF)`` and check
``ref.name`` truthiness — no ``None`` checks anywhere.
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_class_ref.py -v`
Expected: PASS (all 12 tests)

- [ ] **Step 5: Commit**

```bash
git add interpreter/class_ref.py tests/unit/test_class_ref.py
git commit -m "feat: add ClassRef dataclass and NO_CLASS_REF sentinel (red-dragon-wgb)"
```

---

### Task 2: Symbol table on TreeSitterEmitContext + emit_class_ref()

**Files:**
- Modify: `interpreter/frontends/context.py:132` (add field after `func_symbol_table`)
- Modify: `interpreter/frontends/context.py:177` (add method after `emit_func_ref`)
- Modify: `interpreter/frontend.py` (add `class_symbol_table` property to ABC)
- Modify: `interpreter/frontends/_base.py` (add `_class_symbol_table`, `_emit_class_ref()`, property)
- Create: `tests/unit/test_emit_class_ref.py`

- [ ] **Step 1: Write tests for emit_class_ref**

```python
# tests/unit/test_emit_class_ref.py
"""Unit tests for TreeSitterEmitContext.emit_class_ref() and class_symbol_table."""

from __future__ import annotations

from interpreter.frontends.context import TreeSitterEmitContext, GrammarConstants
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.constants import Language
from interpreter.class_ref import ClassRef
from interpreter.ir import Opcode


def _make_ctx(lang: Language = Language.PYTHON) -> TreeSitterEmitContext:
    return TreeSitterEmitContext(
        source=b"",
        language=lang,
        observer=NullFrontendObserver(),
        constants=GrammarConstants(),
    )


class TestEmitClassRef:
    def test_registers_in_symbol_table_no_parents(self):
        ctx = _make_ctx()
        ctx.emit_class_ref("Dog", "class_Dog_0", [], result_reg="%0")
        assert "class_Dog_0" in ctx.class_symbol_table
        ref = ctx.class_symbol_table["class_Dog_0"]
        assert ref == ClassRef(name="Dog", label="class_Dog_0", parents=())

    def test_registers_in_symbol_table_with_parents(self):
        ctx = _make_ctx()
        ctx.emit_class_ref("Dog", "class_Dog_0", ["Animal"], result_reg="%0")
        ref = ctx.class_symbol_table["class_Dog_0"]
        assert ref.parents == ("Animal",)

    def test_emits_const_with_plain_label(self):
        ctx = _make_ctx()
        ctx.emit_class_ref("Dog", "class_Dog_0", [], result_reg="%0")
        const_insts = [i for i in ctx.instructions if i.opcode == Opcode.CONST]
        assert len(const_insts) == 1
        assert const_insts[0].operands == ["class_Dog_0"]
        assert const_insts[0].result_reg == "%0"

    def test_no_angle_brackets_in_operand(self):
        ctx = _make_ctx()
        ctx.emit_class_ref("Dog", "class_Dog_0", ["Animal"], result_reg="%1")
        const_inst = [i for i in ctx.instructions if i.opcode == Opcode.CONST][0]
        operand = str(const_inst.operands[0])
        assert "<" not in operand
        assert ">" not in operand

    def test_multiple_registrations(self):
        ctx = _make_ctx()
        ctx.emit_class_ref("Dog", "class_Dog_0", ["Animal"], result_reg="%0")
        ctx.emit_class_ref("Cat", "class_Cat_0", [], result_reg="%1")
        assert len(ctx.class_symbol_table) == 2
        assert ctx.class_symbol_table["class_Dog_0"].name == "Dog"
        assert ctx.class_symbol_table["class_Cat_0"].name == "Cat"

    def test_parents_converted_to_tuple(self):
        """Parents are passed as a list but stored as a tuple."""
        ctx = _make_ctx()
        ctx.emit_class_ref("C", "class_C_0", ["A", "B"], result_reg="%0")
        ref = ctx.class_symbol_table["class_C_0"]
        assert isinstance(ref.parents, tuple)
        assert ref.parents == ("A", "B")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_emit_class_ref.py -v`
Expected: FAIL with `AttributeError: 'TreeSitterEmitContext' object has no attribute 'emit_class_ref'`

- [ ] **Step 3: Add class_symbol_table and emit_class_ref to TreeSitterEmitContext**

In `interpreter/frontends/context.py`:

Add import:
```python
from interpreter.class_ref import ClassRef
```

Add field after `func_symbol_table` (line 132):
```python
    # Class reference symbol table: class_label -> ClassRef
    class_symbol_table: dict[str, ClassRef] = field(default_factory=dict)
```

Add method after `emit_func_ref` (after line 195):
```python
    def emit_class_ref(
        self,
        class_name: str,
        class_label: str,
        parents: list[str],
        result_reg: str,
        node=None,
    ) -> IRInstruction:
        """Register a class reference in the symbol table and emit CONST.

        Emits the plain class_label as the CONST operand.  The symbol table
        maps class_label -> ClassRef(name, label, parents) for downstream consumers.
        """
        self.class_symbol_table[class_label] = ClassRef(
            name=class_name, label=class_label, parents=tuple(parents)
        )
        return self.emit(
            Opcode.CONST,
            result_reg=result_reg,
            operands=[class_label],
            node=node,
        )
```

- [ ] **Step 4: Add class_symbol_table property to Frontend ABC**

In `interpreter/frontend.py`, add import:
```python
from interpreter.class_ref import ClassRef
```

Add property (after the existing `func_symbol_table` property):
```python
    @property
    def class_symbol_table(self) -> dict[str, ClassRef]:
        """Class reference symbol table accumulated during lowering.

        Override in frontends that populate class refs during lowering.
        Returns an empty dict by default.
        """
        return {}
```

- [ ] **Step 5: Add class_symbol_table to BaseFrontend**

In `interpreter/frontends/_base.py`:

Add import:
```python
from interpreter.class_ref import ClassRef
```

**Context mode** — after the line `self._func_symbol_table = ctx.func_symbol_table` in the `lower()` method, add:
```python
self._class_symbol_table = ctx.class_symbol_table
```

**Legacy mode** — add a `_class_symbol_table` field initialization (alongside `_func_symbol_table`) and a `_emit_class_ref` method:
```python
self._class_symbol_table: dict[str, ClassRef] = {}

def _emit_class_ref(
    self,
    class_name: str,
    class_label: str,
    parents: list[str],
    result_reg: str,
    node=None,
) -> IRInstruction:
    """Legacy-mode equivalent of ctx.emit_class_ref()."""
    self._class_symbol_table[class_label] = ClassRef(
        name=class_name, label=class_label, parents=tuple(parents)
    )
    return self._emit(Opcode.CONST, result_reg=result_reg, operands=[class_label], node=node)
```

Override the `class_symbol_table` property (following the `func_symbol_table` pattern):
```python
@property
def class_symbol_table(self) -> dict[str, ClassRef]:
    return self._class_symbol_table
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_emit_class_ref.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 7: Run full test suite to verify no regressions**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass (no changes to existing behavior yet)

- [ ] **Step 8: Commit**

```bash
git add interpreter/class_ref.py interpreter/frontends/context.py interpreter/frontend.py interpreter/frontends/_base.py tests/unit/test_emit_class_ref.py
git commit -m "feat: add class_symbol_table and emit_class_ref() to TreeSitterEmitContext"
```

---

### Task 3: Convert all frontends to use emit_class_ref

**Files:**
- Modify: `interpreter/frontends/common/declarations.py` — delete `make_class_ref()`, update `lower_class_def()`
- Modify: 14 frontend files (33 sites) — replace `make_class_ref()`/`CLASS_REF_TEMPLATE.format(...)` with `ctx.emit_class_ref(...)`
- Modify: `interpreter/frontends/_base.py:959-967` — use `self._emit_class_ref()`
- Modify: test files — update IR shape assertions

This is a mechanical replacement. Every site that does:
```python
ctx.emit(
    Opcode.CONST,
    result_reg=cls_reg,
    operands=[make_class_ref(class_name, class_label, parents)],
)
```
or:
```python
ctx.emit(
    Opcode.CONST,
    result_reg=cls_reg,
    operands=[constants.CLASS_REF_TEMPLATE.format(name=class_name, label=class_label)],
)
```
becomes:
```python
ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)
```

For sites using `CLASS_REF_TEMPLATE.format()` (no parents), pass `[]` as parents:
```python
ctx.emit_class_ref(class_name, class_label, [], result_reg=cls_reg)
```

- [ ] **Step 1: Update common/declarations.py**

In `interpreter/frontends/common/declarations.py`:

**Delete** `make_class_ref()` function (lines 113-122).

**Replace** the class ref emission in `lower_class_def()` (lines 204-210):

Old:
```python
    cls_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CONST,
        result_reg=cls_reg,
        operands=[make_class_ref(class_name, class_label, parents)],
    )
    ctx.emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])
```

New:
```python
    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])
```

Remove the `constants` import if no longer needed (it's still used for `CLASS_LABEL_PREFIX`, `END_CLASS_LABEL_PREFIX`, `FUNC_LABEL_PREFIX`, `PARAM_PREFIX`).

- [ ] **Step 2: Convert all 14 frontend files (33 sites)**

Complete file list — every file that uses `make_class_ref()` or `CLASS_REF_TEMPLATE.format()`:

| # | File | Sites | Pattern |
|---|------|-------|---------|
| 1 | `_base.py:959-967` | 1 | `CLASS_REF_TEMPLATE.format` → `self._emit_class_ref(class_name, class_label, [], result_reg=cls_reg)` |
| 2 | `javascript/declarations.py:225,264` | 2 | `make_class_ref` → `ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)` |
| 3 | `ruby/declarations.py:142` | 1 | `make_class_ref` → `ctx.emit_class_ref(class_name, class_label, parents, ...)` |
| 4 | `ruby/declarations.py:227` | 1 | `CLASS_REF_TEMPLATE.format` → `ctx.emit_class_ref(module_name, class_label, [], ...)` |
| 5 | `csharp/declarations.py:247,390` | 2 | `make_class_ref` → `ctx.emit_class_ref(...)` |
| 6 | `java/declarations.py:239,423` | 2 | `make_class_ref` → `ctx.emit_class_ref(...)` |
| 7 | `java/declarations.py:293` | 1 | `CLASS_REF_TEMPLATE.format` (record) → `ctx.emit_class_ref(record_name, class_label, [], ...)` |
| 8 | `rust/declarations.py:253,282,311,564,631` | 5 | `CLASS_REF_TEMPLATE.format` → `ctx.emit_class_ref(name, class_label, [], ...)` |
| 9 | `cpp/declarations.py:249,549` | 2 | `make_class_ref` → `ctx.emit_class_ref(...)` |
| 10 | `typescript.py:188,382` | 2 | `make_class_ref` → `ctx.emit_class_ref(...)` |
| 11 | `go/declarations.py:232` | 1 | `CLASS_REF_TEMPLATE.format` → `ctx.emit_class_ref(type_name, class_label, [], ...)` |
| 12 | `go/declarations.py:258` | 1 | `make_class_ref` → `ctx.emit_class_ref(type_name, class_label, [], ...)` |
| 13 | `pascal/declarations.py:375` | 1 | `CLASS_REF_TEMPLATE.format` → `ctx.emit_class_ref(type_name, class_label, [], ...)` |
| 14 | `c/declarations.py:408,529` | 2 | `CLASS_REF_TEMPLATE.format` → `ctx.emit_class_ref(name, class_label, [], ...)` |
| 15 | `php/declarations.py:321` | 1 | `make_class_ref` → `ctx.emit_class_ref(...)` |
| 16 | `php/declarations.py:348,376,431` | 3 | `CLASS_REF_TEMPLATE.format` → `ctx.emit_class_ref(name, class_label, [], ...)` |
| 17 | `scala/declarations.py:376,435` | 2 | `make_class_ref` → `ctx.emit_class_ref(...)` |
| 18 | `scala/declarations.py:406` | 1 | `CLASS_REF_TEMPLATE.format` (object) → `ctx.emit_class_ref(obj_name, class_label, [], ...)` |
| 19 | `kotlin/declarations.py:469` | 1 | `make_class_ref` → `ctx.emit_class_ref(...)` |

**Important patterns:**

For `make_class_ref` sites, the 3-argument pattern `make_class_ref(class_name, class_label, parents)` maps directly:
```python
ctx.emit_class_ref(class_name, class_label, parents, result_reg=cls_reg)
```

For `CLASS_REF_TEMPLATE.format` sites (no parents), always pass `[]`:
```python
ctx.emit_class_ref(name, class_label, [], result_reg=cls_reg)
```

For `_base.py` (legacy mode), use:
```python
self._emit_class_ref(class_name, class_label, [], result_reg=cls_reg)
```
And remove the old 4-line `self._emit(Opcode.CONST, ...)` block.

- [ ] **Step 3: Remove make_class_ref imports**

After converting all sites, remove `from interpreter.frontends.common.declarations import make_class_ref` from:
- `javascript/declarations.py`
- `ruby/declarations.py`
- `csharp/declarations.py`
- `java/declarations.py`
- `cpp/declarations.py`
- `typescript.py`
- `go/declarations.py`
- `php/declarations.py`
- `scala/declarations.py`
- `kotlin/declarations.py`

Also remove unused `constants.CLASS_REF_TEMPLATE` / `constants.CLASS_REF_WITH_PARENTS_TEMPLATE` references from any files that imported `constants` only for these.

- [ ] **Step 4: Update unit test IR shape assertions**

Find all test assertions that reference `<class:` strings:

Run: `grep -rn '"<class:\|<class:.*@' tests/unit/ | grep -v ".pyc"`

For each test file, replace assertions like:
```python
assert inst.operands[0] == "<class:Foo@class_Foo_0>"
# or
assert any("<class:" in str(c.operands) and "Foo" in str(c.operands) for c in consts)
```
with:
```python
assert inst.operands[0] == "class_Foo_0"
# or
assert any("class_Foo" in str(c.operands) for c in consts)
```

**Key test files to update:**

| File | Sites | Notes |
|------|-------|-------|
| `test_class_inheritance.py` | 5 | Lines 94, 103, 119, 124, 129 — change to plain labels |
| `test_registry.py` | 4 | Lines 17, 29, 45, 62 — update test data CONST operands |
| `test_type_inference.py` | 2+ | Line 100 and _make_inst calls |
| `test_java_frontend.py` | 3 | Lines 240, 343, 990 — change `"<class:" in str(c.operands)` to check for `"class_"` prefix |
| `test_typescript_frontend.py` | 5 | Lines 74, 83, 247, 384, 635 — similar pattern |
| `test_go_frontend.py` | 3 | Lines 205, 318, 1095 |
| `test_kotlin_frontend.py` | varies | Similar substring matching |
| `test_csharp_frontend.py` | varies | Similar substring matching |
| `test_chunked_llm_frontend.py` | 2 | Exact format assertion |

**Frontend test assertion pattern:** Most frontend tests use substring matching like:
```python
assert any("<class:" in str(c.operands) and "Foo" in str(c.operands) for c in consts)
```
These check for the class name inside the operand string. With plain labels (`class_Foo_0`), the class name is still present as a substring, so many assertions may not need changes. However, the `"<class:"` prefix check must be replaced with a `"class_"` prefix check or similar.

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL tests pass.

- [ ] **Step 6: Commit**

```bash
git add interpreter/frontends/ tests/unit/
git commit -m "refactor: convert all 15 frontends to emit_class_ref (plain labels in IR)"
```

---

## Chunk 2: Consumer Migration

### Task 4: Registry accepts class symbol table instead of regex

**Files:**
- Modify: `interpreter/registry.py:34-45` — delete `_parse_class_ref()`
- Modify: `interpreter/registry.py:17-31` — delete `RefParseResult`, `RefPatterns`
- Modify: `interpreter/registry.py:80-141` — `_scan_classes()` uses symbol table
- Modify: `interpreter/run.py:609` — thread class symbol table to `build_registry`
- Modify: `tests/unit/rosetta/conftest.py:163` — pass class symbol table

- [ ] **Step 1: Understand current registry scanning**

Read `interpreter/registry.py` function `_scan_classes()` (lines 80-141). The first pass (lines 95-103) loops through all instructions and calls `_parse_class_ref(str(inst.operands[0]))` on CONST operands to discover class names, labels, and parent chains.

- [ ] **Step 2: Add class_symbol_table parameter to build_registry and _scan_classes**

Change signatures:

```python
from interpreter.class_ref import ClassRef

def build_registry(
    instructions: list[IRInstruction],
    cfg: CFG,
    func_symbol_table: dict[str, FuncRef] = {},
    class_symbol_table: dict[str, ClassRef] = {},
) -> FunctionRegistry:
```

Pass `class_symbol_table` through to `_scan_classes`.

- [ ] **Step 3: Replace _parse_class_ref in _scan_classes first pass**

In the first pass (lines 95-103), replace:
```python
cr = _parse_class_ref(str(inst.operands[0]))
if cr.matched:
    classes[cr.name] = cr.label
    if cr.parents:
        class_parents[cr.name] = cr.parents
```
with:
```python
operand = str(inst.operands[0])
if operand in class_symbol_table:
    ref = class_symbol_table[operand]
    classes[ref.name] = ref.label
    if ref.parents:
        class_parents[ref.name] = list(ref.parents)
```

- [ ] **Step 4: Delete _parse_class_ref, RefPatterns, RefParseResult**

Remove:
- `RefParseResult` class (lines 17-25)
- `RefPatterns` class (lines 28-31)
- `_parse_class_ref()` function (lines 34-45)
- `import re` (line 5) — if no longer needed
- `from interpreter import constants` — if only used for `CLASS_REF_PATTERN`

- [ ] **Step 5: Thread class symbol table in run.py**

In `interpreter/run.py`, update the `build_registry` call (line 609):
```python
registry = build_registry(
    instructions,
    cfg,
    func_symbol_table=frontend.func_symbol_table,
    class_symbol_table=frontend.class_symbol_table,
)
```

- [ ] **Step 6: Thread class symbol table in conftest.py**

In `tests/unit/rosetta/conftest.py`, update the `build_registry` call (line 163):
```python
registry = build_registry(
    instructions,
    cfg,
    func_symbol_table=func_symbol_table,
    class_symbol_table=frontend.class_symbol_table,
)
```

- [ ] **Step 7: Thread class symbol table in api.py**

In `interpreter/api.py`, if `build_registry` is called there, add `class_symbol_table=frontend.class_symbol_table`.

- [ ] **Step 8: Update test_registry.py test data**

The registry tests construct `IRInstruction` objects with `<class:Foo@class_Foo_0>` operands. These now need to use plain labels AND provide a `class_symbol_table` argument to `build_registry`. Update each test:

```python
# Old:
IRInstruction(opcode=Opcode.CONST, operands=["<class:Foo@class_Foo_0>"])

# New:
IRInstruction(opcode=Opcode.CONST, operands=["class_Foo_0"])
# And pass class_symbol_table={"class_Foo_0": ClassRef(name="Foo", label="class_Foo_0", parents=())}
```

- [ ] **Step 9: Delete TestParseClassRef tests**

In `tests/unit/test_class_inheritance.py`, delete:
- Import: `_parse_class_ref` (line 14)
- Entire `TestParseClassRef` class (lines 23-46, 4 tests)

- [ ] **Step 10: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL tests pass.

- [ ] **Step 11: Commit**

```bash
git add interpreter/registry.py interpreter/run.py interpreter/api.py tests/
git commit -m "refactor: registry uses class_symbol_table instead of _parse_class_ref"
```

---

### Task 5: Type inference accepts class symbol table instead of regex

**Files:**
- Modify: `interpreter/type_inference.py:137` — delete `_CLASS_REF_PATTERN`
- Modify: `interpreter/type_inference.py:879` — use symbol table lookup
- Modify: `interpreter/run.py:619-624` — thread class symbol table to `infer_types`
- Modify: `interpreter/api.py` — thread class symbol table to `infer_types`

- [ ] **Step 1: Add class_symbol_table to _InferenceContext and infer_types**

In `interpreter/type_inference.py`, add import:
```python
from interpreter.class_ref import ClassRef
```

Add `class_symbol_table: dict[str, ClassRef] = {}` to `_InferenceContext` dataclass fields.

Add `class_symbol_table: dict[str, ClassRef] = {}` parameter to `infer_types()` signature and thread it into `_InferenceContext`.

- [ ] **Step 2: Replace _CLASS_REF_PATTERN usage**

`_infer_const_type` is a standalone function (line 871) with signature `def _infer_const_type(raw: str, func_symbol_table: dict[str, FuncRef] = {}) -> TypeExpr:`. Add `class_symbol_table` as an explicit parameter:

```python
def _infer_const_type(
    raw: str,
    func_symbol_table: dict[str, FuncRef] = {},
    class_symbol_table: dict[str, ClassRef] = {},
) -> TypeExpr:
```

At line 879, replace:
```python
if _CLASS_REF_PATTERN.search(str(raw)):
    return UNKNOWN
```
with:
```python
if str(raw) in class_symbol_table:
    return UNKNOWN
```

Update the call site (around line 530) to pass `class_symbol_table=ctx.class_symbol_table`.

- [ ] **Step 3: Delete _CLASS_REF_PATTERN**

Remove line 137:
```python
_CLASS_REF_PATTERN = re.compile(r"<class:")
```

Check if `re` import is still needed for other patterns.

- [ ] **Step 4: Thread class symbol table in run.py**

Update the `infer_types` call (line 619):
```python
type_env = infer_types(
    instructions,
    type_resolver,
    type_env_builder=frontend.type_env_builder,
    func_symbol_table=frontend.func_symbol_table,
    class_symbol_table=frontend.class_symbol_table,
)
```

- [ ] **Step 5: Thread class symbol table in api.py**

In `interpreter/api.py`, update the `infer_types` call:
```python
env = infer_types(
    instructions,
    resolver,
    type_env_builder=frontend.type_env_builder,
    func_symbol_table=frontend.func_symbol_table,
    class_symbol_table=frontend.class_symbol_table,
)
```

- [ ] **Step 6: Update test_type_inference.py**

Update tests that construct CONST instructions with `<class:...>` strings. These now use plain labels AND need a `class_symbol_table` in the inference context:

```python
# Old:
_infer_const_type("<class:Dog@class_Dog_0>")

# New — depends on how _infer_const_type accesses the symbol table.
# If it's passed through context, the test needs to supply a context with class_symbol_table.
```

- [ ] **Step 7: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL tests pass.

- [ ] **Step 8: Commit**

```bash
git add interpreter/type_inference.py interpreter/run.py interpreter/api.py tests/unit/test_type_inference.py
git commit -m "refactor: type inference uses class_symbol_table instead of regex"
```

---

### Task 6: Executor uses ClassRef instead of _parse_class_ref

**Files:**
- Modify: `interpreter/executor.py:32` — change import
- Modify: `interpreter/executor.py:81-126` — `_handle_const` stores `ClassRef` in register
- Modify: `interpreter/executor.py:319-340` — `_handle_new_object` uses `isinstance(raw, ClassRef)`
- Modify: `interpreter/executor.py:1016-1079` — `_try_class_constructor_call` uses `isinstance(func_val, ClassRef)`
- Modify: `interpreter/executor.py:1505-1537` — `_try_execute_locally` accepts `class_symbol_table`
- Modify: `interpreter/run.py:234-288` — `execute_cfg` accepts and threads `class_symbol_table`
- Modify: `interpreter/run.py:358-437` — `execute_cfg_traced` accepts and threads `class_symbol_table`
- Modify: `interpreter/run.py:645-655` — `run()` passes `class_symbol_table`
- Modify: `interpreter/run.py:673` — add `ClassRef` branch to `_format_val`
- Modify: `interpreter/api.py:225-265` — `execute_traced` retains frontend for symbol tables

- [ ] **Step 1: Thread class symbol table through executor infrastructure**

This requires changes at 4 levels, mirroring how `func_symbol_table` is threaded:

**1a. `_try_execute_locally` in `interpreter/executor.py` (line 1505):** Add `class_symbol_table` parameter:
```python
def _try_execute_locally(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str = "",
    ip: int = 0,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    binop_coercion: BinopCoercionStrategy = _DEFAULT_BINOP_COERCION,
    unop_coercion: UnopCoercionStrategy = _DEFAULT_UNOP_COERCION,
    func_symbol_table: dict[str, FuncRef] = {},
    class_symbol_table: dict[str, ClassRef] = {},
) -> ExecutionResult:
```

And pass it through to `LocalExecutor.execute`:
```python
    return LocalExecutor.execute(
        ...,
        func_symbol_table=func_symbol_table,
        class_symbol_table=class_symbol_table,
    )
```

Import `ClassRef`:
```python
from interpreter.class_ref import ClassRef
```

**1b. `execute_cfg` in `interpreter/run.py` (line 234):** Add `class_symbol_table` parameter to signature and pass to both `_try_execute_locally` calls (lines 275 and 424):
```python
def execute_cfg(
    ...,
    func_symbol_table: dict[str, FuncRef] = {},
    class_symbol_table: dict[str, ClassRef] = {},
) -> tuple[VMState, ExecutionStats]:
```

At lines 275-288 and 424-437, add `class_symbol_table=class_symbol_table` to each `_try_execute_locally` call.

Import `ClassRef`:
```python
from interpreter.class_ref import ClassRef
```

**1c. `execute_cfg_traced` in `interpreter/run.py` (line 358):** Same change — add `class_symbol_table` parameter and pass to both `_try_execute_locally` calls:
```python
def execute_cfg_traced(
    ...,
    func_symbol_table: dict[str, FuncRef] = {},
    class_symbol_table: dict[str, ClassRef] = {},
) -> tuple[VMState, ExecutionTrace]:
```

**1d. Callers in `run.py` and `api.py`:**

In `run()` (line 645):
```python
vm, exec_stats = execute_cfg(
    ...,
    func_symbol_table=frontend.func_symbol_table,
    class_symbol_table=frontend.class_symbol_table,
)
```

In `api.py:execute_traced()` (line 258-264): Refactor to retain the frontend so symbol tables are available. Change `lower_source()` call to `get_frontend()` + `frontend.lower()` directly:
```python
def execute_traced(...) -> ExecutionTrace:
    lang = Language(language)
    frontend = get_frontend(lang, frontend_type=frontend_type, llm_provider=backend)
    instructions = frontend.lower(source.encode("utf-8"))
    cfg = build_cfg_from_source(source, language, frontend_type, backend, function_name=function_name)
    registry = build_registry(
        instructions, cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    config = VMConfig(backend=backend, max_steps=max_steps)
    _vm, trace = execute_cfg_traced(
        cfg, entry_point, registry, config,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    return trace
```

- [ ] **Step 2: Update _handle_const for class refs**

In `_handle_const` (line 81), after the `func_symbol_table` lookup block, add a class symbol table lookup. When a CONST label matches the class symbol table, store the `ClassRef` object directly in the register (instead of the plain string):

```python
def _handle_const(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    func_symbol_table = kwargs.get("func_symbol_table", {})
    class_symbol_table = kwargs.get("class_symbol_table", {})
    raw = inst.operands[0] if inst.operands else "None"
    val = _parse_const(raw)

    # Function symbol table lookup (existing code — unchanged)
    func_ref_entry = None
    if isinstance(val, str) and val in func_symbol_table:
        func_ref_entry = func_symbol_table[val]
    if func_ref_entry is not None:
        # ... existing closure logic ...
        val = BoundFuncRef(func_ref=func_ref_entry, closure_id=closure_id)

    # Class symbol table lookup: store ClassRef directly in register
    elif isinstance(val, str) and val in class_symbol_table:
        val = class_symbol_table[val]

    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: typed_from_runtime(val)},
            reasoning=f"const {raw!r} → {inst.result_reg}",
        )
    )
```

- [ ] **Step 3: Rewrite _handle_new_object (site 1)**

In `_handle_new_object` (lines 319-340), replace:
```python
    for frame in reversed(vm.call_stack):
        if type_hint in frame.local_vars:
            raw = frame.local_vars[type_hint].value
            cr = _parse_class_ref(str(raw))
            if cr.matched:
                type_hint = cr.name
            break
```
with:
```python
    for frame in reversed(vm.call_stack):
        if type_hint in frame.local_vars:
            raw = frame.local_vars[type_hint].value
            if isinstance(raw, ClassRef):
                type_hint = raw.name
            break
```

Import `ClassRef`:
```python
from interpreter.class_ref import ClassRef
```

- [ ] **Step 4: Rewrite _try_class_constructor_call (site 2)**

In `_try_class_constructor_call` (lines 1016-1079), replace:
```python
    cr = _parse_class_ref(func_val)
    if not cr.matched:
        return ExecutionResult.not_handled()
    class_name, class_label = cr.name, cr.label
```
with:
```python
    if not isinstance(func_val, ClassRef):
        return ExecutionResult.not_handled()
    class_name, class_label = func_val.name, func_val.label
```

- [ ] **Step 5: Delete _parse_class_ref import**

Change line 32 from:
```python
from interpreter.registry import FunctionRegistry, _parse_class_ref
```
to:
```python
from interpreter.registry import FunctionRegistry
```

- [ ] **Step 6: Add ClassRef branch to _format_val in run.py**

In `interpreter/run.py`, add import:
```python
from interpreter.class_ref import ClassRef
```

In `_format_val` (line 673), add a branch before the final `repr(v)`:
```python
if isinstance(v, ClassRef):
    if v.parents:
        return f"<class:{v.name}@{v.label}:{','.join(v.parents)}>"
    return f"<class:{v.name}@{v.label}>"
```

- [ ] **Step 7: Thread class symbol table in conftest.py**

In `tests/unit/rosetta/conftest.py`, update the `execute_cfg` call (line 165):
```python
class_symbol_table = frontend.class_symbol_table
# ...
vm, stats = execute_cfg(
    cfg, "entry", registry, config,
    func_symbol_table=func_symbol_table,
    class_symbol_table=class_symbol_table,
)
```

Also update the `build_registry` call (line 163) if not done in Task 4:
```python
registry = build_registry(
    instructions, cfg,
    func_symbol_table=func_symbol_table,
    class_symbol_table=class_symbol_table,
)
```

- [ ] **Step 8: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL tests pass.

- [ ] **Step 9: Commit**

```bash
git add interpreter/executor.py interpreter/run.py tests/unit/rosetta/conftest.py
git commit -m "refactor: executor uses ClassRef instead of _parse_class_ref regex"
```

---

## Chunk 3: Cleanup and LLM Boundary

### Task 7: Delete dead code and LLM frontend boundary conversion

**Files:**
- Modify: `interpreter/constants.py` — delete `CLASS_REF_PATTERN`, `CLASS_REF_TEMPLATE`, `CLASS_REF_WITH_PARENTS_TEMPLATE`
- Modify: `interpreter/llm_frontend.py` — add `_convert_llm_class_refs()`
- Modify: `interpreter/chunked_llm_frontend.py` — add class ref conversion after reassembly

- [ ] **Step 1: Delete class ref constants**

Remove from `interpreter/constants.py` (lines 36-39):
```python
CLASS_REF_PATTERN = r"<class:(\w+)@(\w+)(?::([^>]+))?>"
CLASS_REF_TEMPLATE = "<class:{name}@{label}>"
CLASS_REF_WITH_PARENTS_TEMPLATE = "<class:{name}@{label}:{parents}>"
```

- [ ] **Step 2: Add _convert_llm_class_refs to llm_frontend.py**

Following the pattern of `_convert_llm_func_refs` (lines 284-301), add:

```python
_LLM_CLASS_REF_RE = re.compile(r"<class:(\w+)@(\w+)(?::([^>]+))?>")


def _convert_llm_class_refs(
    instructions: list[IRInstruction],
    class_symbol_table: dict[str, ClassRef],
) -> None:
    """Convert LLM-emitted <class:name@label> strings to plain labels.

    Mutates instructions in place: replaces operands and populates the symbol table.
    This is the ONLY place regex is used for class references — at the LLM boundary.
    """
    for inst in instructions:
        if inst.opcode == Opcode.CONST and inst.operands:
            operand = str(inst.operands[0])
            m = _LLM_CLASS_REF_RE.search(operand)
            if m:
                name, label = m.group(1), m.group(2)
                parents_str = m.group(3) or ""
                parents = tuple(p for p in parents_str.split(",") if p)
                class_symbol_table[label] = ClassRef(
                    name=name, label=label, parents=parents
                )
                inst.operands[0] = label
```

Import `ClassRef`:
```python
from interpreter.class_ref import ClassRef
```

Call `_convert_llm_class_refs` in the `lower()` method, after `_convert_llm_func_refs`:
```python
_convert_llm_class_refs(instructions, self._class_symbol_table)
```

Add `_class_symbol_table` field and `class_symbol_table` property (following the func ref pattern):
```python
self._class_symbol_table: dict[str, ClassRef] = {}

@property
def class_symbol_table(self) -> dict[str, ClassRef]:
    return self._class_symbol_table
```

- [ ] **Step 3: Add class ref conversion to chunked_llm_frontend.py**

Same pattern: add `_class_symbol_table` field, `class_symbol_table` property, and call `_convert_llm_class_refs` after reassembly (alongside the existing `_convert_llm_func_refs` call).

Import `ClassRef` and `_convert_llm_class_refs` from llm_frontend (or define locally).

- [ ] **Step 4: Verify no remaining references to deleted code**

Run: `grep -rn "CLASS_REF_PATTERN\|CLASS_REF_TEMPLATE\|CLASS_REF_WITH_PARENTS_TEMPLATE\|_parse_class_ref\|RefPatterns\|RefParseResult\|make_class_ref" interpreter/ tests/`

Expected: No matches except in `llm_frontend.py` (local regex `_LLM_CLASS_REF_RE`).

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL tests pass.

- [ ] **Step 6: Commit**

```bash
git add interpreter/constants.py interpreter/llm_frontend.py interpreter/chunked_llm_frontend.py
git commit -m "refactor: delete CLASS_REF constants, add LLM boundary class ref conversion"
```

---

### Task 8: ADR, README, cleanup

**Files:**
- Modify: `docs/architectural-design-decisions.md`
- Modify: `README.md`

- [ ] **Step 1: Add ADR-106**

Add to `docs/architectural-design-decisions.md`:

```markdown
### ADR-106: Structured class references via symbol table (2026-03-15)

**Context:** Class references were stringly-typed — frontends emitted `CONST "<class:name@label>"` or `CONST "<class:name@label:Parent1,Parent2>"` and every consumer (registry, type inference, executor) regex-parsed this string back. This was the same fragility that `FUNC_REF_PATTERN` had (fixed in ADR-105).

**Decision:** Replace with a symbol table (`dict[str, ClassRef]`) on `TreeSitterEmitContext`. Frontends call `ctx.emit_class_ref(name, label, parents)` which registers a `ClassRef(name, label, parents)` and emits `CONST label` (plain string). Unlike function references, class references have no runtime binding equivalent (`BoundFuncRef` for closures) — `ClassRef` objects are stored directly in registers. Consumer sites use `isinstance(val, ClassRef)` (executor) or `label in class_symbol_table` (registry, type inference). A `NO_CLASS_REF` null object sentinel eliminates None checks. The LLM frontend boundary retains a local regex for parsing LLM-emitted strings. With this change, all stringly-typed reference patterns are eliminated from the pipeline.

**Deletions:** `CLASS_REF_PATTERN`, `CLASS_REF_TEMPLATE`, `CLASS_REF_WITH_PARENTS_TEMPLATE` (constants.py), `RefPatterns`, `RefParseResult`, `_parse_class_ref()` (registry.py), `_CLASS_REF_PATTERN` (type_inference.py), `make_class_ref()` (common/declarations.py).

**Files:** `interpreter/class_ref.py`, `interpreter/frontends/context.py`, `interpreter/executor.py`, `interpreter/registry.py`, `interpreter/type_inference.py`, `interpreter/run.py`, all 15 frontend dirs.
```

- [ ] **Step 2: Update README if needed**

Check if README mentions `CLASS_REF_PATTERN`, `make_class_ref`, or the string format. Update any references.

- [ ] **Step 3: Close beads issue**

Run: `bd update red-dragon-wgb --status closed`

- [ ] **Step 4: Run formatter and full test suite**

```bash
poetry run python -m black .
poetry run python -m pytest --tb=short -q
```
Expected: ALL tests pass, formatting clean.

- [ ] **Step 5: Commit and push**

```bash
git add docs/architectural-design-decisions.md README.md .beads/
git commit -m "docs: ADR-106 structured class references, close red-dragon-wgb"
git push origin main
```
