# Symbol Table Infrastructure (Phase 1) — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Scope:** Data model + pre-pass hook + COBOL bridge. No frontend extractors, no behavioral changes.
**Issue:** red-dragon-4x78

## Problem

Tree-sitter frontends discover symbols (class fields, constants, `__match_args__`) during IR lowering, leading to ad-hoc workarounds (`_class_field_names`, `_resolve_match_args` AST walking, `_resolve_class_static_field` IR scanning). COBOL already has the right pattern: `build_data_layout()` extracts all symbols before lowering begins.

## Approach

Generalize COBOL's `DataLayout` pattern to all frontends. Define a unified `SymbolTable` data model. Add a pre-pass hook to `BaseFrontend` that runs between parse and lowering. Provide a `from_data_layout` bridge so COBOL can also produce a `SymbolTable`. Phase 1 is purely additive — no behavioral changes.

## Design

### 1. Data Model (`interpreter/frontends/symbol_table.py`)

```python
@dataclass(frozen=True)
class FieldInfo:
    name: str
    type_hint: str
    has_initializer: bool
    children: tuple[FieldInfo, ...] = ()  # COBOL hierarchy, empty for flat languages

@dataclass(frozen=True)
class FunctionInfo:
    name: str
    params: tuple[str, ...]
    return_type: str

@dataclass(frozen=True)
class ClassInfo:
    name: str
    fields: dict[str, FieldInfo]
    methods: dict[str, FunctionInfo]
    constants: dict[str, str]       # name → literal value as string
    parents: tuple[str, ...]
    match_args: tuple[str, ...] = ()  # Python-specific, empty for others

@dataclass
class SymbolTable:
    classes: dict[str, ClassInfo]
    functions: dict[str, FunctionInfo]
    constants: dict[str, str]

    @classmethod
    def empty(cls) -> SymbolTable:
        return cls(classes={}, functions={}, constants={})
```

`FieldInfo.children` supports COBOL's hierarchical level-number fields (`01 WS-RECORD` → `05 WS-NAME` → `10 WS-FIRST`). Flat languages leave it as `()`.

### 2. Pre-pass Hook on `BaseFrontend`

In `interpreter/frontends/_base.py`, modify `_lower_with_context`:

```python
def _lower_with_context(self, source, root):
    symbol_table = self._extract_symbols(root)
    ctx = TreeSitterEmitContext(
        ...
        symbol_table=symbol_table,
    )
    ...

def _extract_symbols(self, root) -> SymbolTable:
    """Override in subclasses to extract symbols before lowering. Phase 2."""
    return SymbolTable.empty()
```

### 3. Context Field

Add to `TreeSitterEmitContext` in `interpreter/frontends/context.py`:

```python
symbol_table: SymbolTable = field(default_factory=SymbolTable.empty)
```

### 4. COBOL Bridge

Add factory method on `SymbolTable`:

```python
@classmethod
def from_data_layout(cls, layout: DataLayout) -> SymbolTable:
    """Convert COBOL DataLayout to a SymbolTable."""
```

This maps `FieldLayout` entries to `FieldInfo` with `children` for group-level items. Optionally wire it into `CobolFrontend.lower()` so `EmitContext` also carries a `symbol_table`.

### 5. Files Changed

**Created:**
- `interpreter/frontends/symbol_table.py` — data model + `SymbolTable.empty()` + `from_data_layout`

**Modified:**
- `interpreter/frontends/context.py` — add `symbol_table` field
- `interpreter/frontends/_base.py` — add `_extract_symbols` hook, pass to ctx

**Optionally modified:**
- `interpreter/cobol/cobol_frontend.py` — wire `SymbolTable.from_data_layout(layout)` after `build_data_layout`

### 6. What Phase 1 does NOT do

- No per-language `_extract_symbols` implementations (Phase 2)
- No consumers of `symbol_table` (Phase 3 replaces `_class_field_names`, `_resolve_match_args`, etc.)
- No behavioral changes — all existing code continues to work unchanged
- No new capabilities — those come in Phase 4

## Testing

- Unit test: `SymbolTable.empty()` returns correct empty structure
- Unit test: `FieldInfo` with `children` for hierarchy
- Unit test: `from_data_layout` converts a sample `DataLayout` correctly
- Integration: existing tests all pass unchanged (no behavioral changes)

## Future Phases

- **Phase 2:** Per-language `_extract_symbols` implementations (15 frontends)
- **Phase 3:** Replace `_class_field_names`, `_resolve_match_args`, `_resolve_class_static_field` with `ctx.symbol_table` lookups
- **Phase 4:** Forward references, cross-class field awareness, better type inference
