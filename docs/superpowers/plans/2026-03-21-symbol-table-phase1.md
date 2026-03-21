# Symbol Table Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a unified `SymbolTable` data model with pre-pass hook on `BaseFrontend` and COBOL bridge — no behavioral changes.

**Architecture:** Create `SymbolTable` with `ClassInfo`/`FieldInfo`/`FunctionInfo` frozen dataclasses. Add `_extract_symbols` hook to `BaseFrontend` (default returns empty). Wire `symbol_table` onto `TreeSitterEmitContext`. Bridge COBOL's `DataLayout` via `SymbolTable.from_data_layout()`.

**Tech Stack:** Python 3.13+, frozen dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-03-21-symbol-table-phase1-design.md`

---

## File Map

| File | Role | Action |
|---|---|---|
| `interpreter/frontends/symbol_table.py` | Data model + `SymbolTable.empty()` + `from_data_layout` | **Create** |
| `interpreter/frontends/context.py` | Add `symbol_table` field to `TreeSitterEmitContext` | **Modify** (1 line) |
| `interpreter/frontends/_base.py` | Add `_extract_symbols` hook, pass to ctx | **Modify** (~5 lines) |
| `interpreter/cobol/cobol_frontend.py` | Wire `SymbolTable.from_data_layout` | **Modify** (~3 lines) |
| `tests/unit/test_symbol_table.py` | Unit tests for data model | **Create** |

---

### Task 1: `SymbolTable` data model (TDD)

**Files:**
- Create: `interpreter/frontends/symbol_table.py`
- Create: `tests/unit/test_symbol_table.py`

- [ ] **Step 1: Write unit tests**

Create `tests/unit/test_symbol_table.py`:

```python
"""Unit tests for SymbolTable data model."""

from __future__ import annotations

from interpreter.frontends.symbol_table import (
    ClassInfo,
    FieldInfo,
    FunctionInfo,
    SymbolTable,
)


class TestSymbolTableEmpty:
    def test_empty_returns_empty_dicts(self):
        st = SymbolTable.empty()
        assert st.classes == {}
        assert st.functions == {}
        assert st.constants == {}


class TestFieldInfo:
    def test_flat_field(self):
        f = FieldInfo(name="x", type_hint="int", has_initializer=False)
        assert f.name == "x"
        assert f.children == ()

    def test_hierarchical_field(self):
        child = FieldInfo(name="WS-FIRST", type_hint="X(20)", has_initializer=False)
        parent = FieldInfo(
            name="WS-NAME", type_hint="group", has_initializer=False,
            children=(child,),
        )
        assert len(parent.children) == 1
        assert parent.children[0].name == "WS-FIRST"


class TestClassInfo:
    def test_class_with_fields_and_methods(self):
        ci = ClassInfo(
            name="Circle",
            fields={"radius": FieldInfo(name="radius", type_hint="int", has_initializer=False)},
            methods={"area": FunctionInfo(name="area", params=("self",), return_type="float")},
            constants={"PI": "3.14"},
            parents=("Shape",),
        )
        assert ci.name == "Circle"
        assert "radius" in ci.fields
        assert "area" in ci.methods
        assert ci.constants["PI"] == "3.14"
        assert ci.parents == ("Shape",)
        assert ci.match_args == ()

    def test_class_with_match_args(self):
        ci = ClassInfo(
            name="Point",
            fields={},
            methods={},
            constants={},
            parents=(),
            match_args=("x", "y"),
        )
        assert ci.match_args == ("x", "y")


class TestSymbolTable:
    def test_lookup_class(self):
        st = SymbolTable(
            classes={"Circle": ClassInfo(
                name="Circle",
                fields={"r": FieldInfo(name="r", type_hint="int", has_initializer=False)},
                methods={},
                constants={},
                parents=(),
            )},
            functions={},
            constants={},
        )
        assert "Circle" in st.classes
        assert "r" in st.classes["Circle"].fields

    def test_lookup_function(self):
        st = SymbolTable(
            classes={},
            functions={"main": FunctionInfo(name="main", params=(), return_type="void")},
            constants={},
        )
        assert "main" in st.functions

    def test_lookup_constant(self):
        st = SymbolTable(
            classes={},
            functions={},
            constants={"MAX_SIZE": "100"},
        )
        assert st.constants["MAX_SIZE"] == "100"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_symbol_table.py -v`
Expected: FAIL — `ImportError` (module doesn't exist)

- [ ] **Step 3: Create `symbol_table.py`**

Create `interpreter/frontends/symbol_table.py`:

```python
"""Unified symbol table for all frontends.

Generalizes COBOL's DataLayout pattern: extract symbols from the AST
before IR lowering begins, so the lowering pass has full knowledge of
all classes, fields, functions, and constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldInfo:
    """A class/struct/record field."""

    name: str
    type_hint: str
    has_initializer: bool
    children: tuple[FieldInfo, ...] = ()  # COBOL hierarchy, empty for flat languages


@dataclass(frozen=True)
class FunctionInfo:
    """A function/method signature."""

    name: str
    params: tuple[str, ...]
    return_type: str


@dataclass(frozen=True)
class ClassInfo:
    """A class/struct/record with its fields, methods, constants, and parents."""

    name: str
    fields: dict[str, FieldInfo]
    methods: dict[str, FunctionInfo]
    constants: dict[str, str]  # name → literal value as string
    parents: tuple[str, ...]
    match_args: tuple[str, ...] = ()  # Python __match_args__, empty for others


@dataclass
class SymbolTable:
    """Symbol catalog extracted before IR lowering.

    Produced by a pre-pass over the AST. Consumed by the lowering context
    to resolve field names, class constants, match_args, etc.
    """

    classes: dict[str, ClassInfo] = field(default_factory=dict)
    functions: dict[str, FunctionInfo] = field(default_factory=dict)
    constants: dict[str, str] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> SymbolTable:
        """Return an empty symbol table."""
        return cls()
```

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/unit/test_symbol_table.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/symbol_table.py tests/unit/test_symbol_table.py
git commit -m "feat: add SymbolTable data model (TDD)"
```

---

### Task 2: COBOL bridge — `from_data_layout` (TDD)

**Files:**
- Modify: `interpreter/frontends/symbol_table.py`
- Modify: `tests/unit/test_symbol_table.py`

- [ ] **Step 1: Write unit test**

Add to `tests/unit/test_symbol_table.py`:

```python
class TestFromDataLayout:
    def test_converts_field_layout_to_field_info(self):
        """DataLayout with one field converts to SymbolTable with one ClassInfo."""
        from interpreter.cobol.data_layout import DataLayout, FieldLayout
        from interpreter.cobol.cobol_types import CobolTypeDescriptor

        layout = DataLayout(
            fields={
                "WS-AMOUNT": FieldLayout(
                    name="WS-AMOUNT",
                    type_descriptor=CobolTypeDescriptor(
                        pic="9(5)V99", category="numeric", storage_size=7,
                    ),
                    offset=0,
                    byte_length=7,
                ),
                "WS-NAME": FieldLayout(
                    name="WS-NAME",
                    type_descriptor=CobolTypeDescriptor(
                        pic="X(20)", category="alphanumeric", storage_size=20,
                    ),
                    offset=7,
                    byte_length=20,
                ),
            },
            total_bytes=27,
        )
        st = SymbolTable.from_data_layout(layout)
        # All COBOL fields go into a single "__WORKING_STORAGE__" class
        assert "__WORKING_STORAGE__" in st.classes
        ws = st.classes["__WORKING_STORAGE__"]
        assert "WS-AMOUNT" in ws.fields
        assert "WS-NAME" in ws.fields
        assert ws.fields["WS-AMOUNT"].type_hint == "9(5)V99"
        assert ws.fields["WS-NAME"].type_hint == "X(20)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_symbol_table.py::TestFromDataLayout -v`
Expected: FAIL — `from_data_layout` doesn't exist

- [ ] **Step 3: Implement `from_data_layout`**

Add to `SymbolTable` in `interpreter/frontends/symbol_table.py`:

```python
    @classmethod
    def from_data_layout(cls, layout) -> SymbolTable:
        """Convert COBOL DataLayout to a SymbolTable.

        All COBOL fields are placed in a single '__WORKING_STORAGE__' ClassInfo
        since COBOL doesn't have classes — the data division is one flat record.
        """
        fields = {
            name: FieldInfo(
                name=name,
                type_hint=fl.type_descriptor.pic if hasattr(fl.type_descriptor, "pic") else "",
                has_initializer=bool(fl.value),
            )
            for name, fl in layout.fields.items()
        }
        ws_class = ClassInfo(
            name="__WORKING_STORAGE__",
            fields=fields,
            methods={},
            constants={},
            parents=(),
        )
        return cls(classes={"__WORKING_STORAGE__": ws_class})
```

Note: We import nothing from `interpreter.cobol` at module level — `from_data_layout` takes `layout` as a duck-typed argument (has `.fields` dict with `.type_descriptor.pic` and `.value`). This avoids circular imports.

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/unit/test_symbol_table.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/symbol_table.py tests/unit/test_symbol_table.py
git commit -m "feat: SymbolTable.from_data_layout for COBOL bridge (TDD)"
```

---

### Task 3: Wire into `TreeSitterEmitContext` + `BaseFrontend`

**Files:**
- Modify: `interpreter/frontends/context.py`
- Modify: `interpreter/frontends/_base.py`

- [ ] **Step 1: Add `symbol_table` to `TreeSitterEmitContext`**

In `interpreter/frontends/context.py`, add the import:

```python
from interpreter.frontends.symbol_table import SymbolTable
```

Add after `_class_field_names` (around line 141):

```python
    # Symbol table from pre-pass — populated before lowering begins
    symbol_table: SymbolTable = field(default_factory=SymbolTable.empty)
```

- [ ] **Step 2: Add `_extract_symbols` hook to `BaseFrontend`**

In `interpreter/frontends/_base.py`, add the import:

```python
from interpreter.frontends.symbol_table import SymbolTable
```

Add a new method (after `_emit_prelude`):

```python
    def _extract_symbols(self, root) -> SymbolTable:
        """Override in subclasses to extract symbols before lowering.

        Runs between parse and lowering. Default returns empty table.
        Language-specific implementations come in Phase 2.
        """
        return SymbolTable.empty()
```

Modify `_lower_with_context` to call it and pass to ctx. Find where `ctx = TreeSitterEmitContext(...)` is constructed (around line 265). Add before the constructor call:

```python
        symbol_table = self._extract_symbols(root)
```

Add to the `TreeSitterEmitContext(...)` constructor call:

```python
            symbol_table=symbol_table,
```

- [ ] **Step 3: Verify existing tests pass**

Run: `poetry run python -m pytest tests/unit/test_python_frontend.py tests/unit/test_csharp_frontend.py tests/unit/test_java_frontend.py --tb=short -q`
Expected: All PASS (no behavioral change)

- [ ] **Step 4: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/context.py interpreter/frontends/_base.py
git commit -m "feat: wire SymbolTable into TreeSitterEmitContext + BaseFrontend pre-pass hook"
```

---

### Task 4: Wire COBOL + full suite + push

**Files:**
- Modify: `interpreter/cobol/cobol_frontend.py`

- [ ] **Step 1: Wire `from_data_layout` into COBOL frontend**

In `interpreter/cobol/cobol_frontend.py`, add import:

```python
from interpreter.frontends.symbol_table import SymbolTable
```

In the `lower` method (around line 117), after `self._layout = layout`, add:

```python
        self._symbol_table = SymbolTable.from_data_layout(layout)
```

- [ ] **Step 2: Run Black**

Run: `poetry run python -m black .`

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest -x --tb=short`
Expected: All pass, no regressions.

- [ ] **Step 4: Commit and push**

```bash
git add interpreter/cobol/cobol_frontend.py
git commit -m "feat: wire SymbolTable.from_data_layout into CobolFrontend"
git push origin main
```
