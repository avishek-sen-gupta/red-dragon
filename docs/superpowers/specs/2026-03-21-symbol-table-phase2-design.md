# Symbol Table Phase 2: Per-Language Extractors — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Scope:** Implement `_extract_symbols` for C#, Java, C++, Python — the 4 languages with workarounds to replace in Phase 3.
**Issue:** red-dragon-xhaq

## Problem

Phase 1 added the `SymbolTable` data model and `_extract_symbols` hook, but all frontends return `SymbolTable.empty()`. The workarounds (`_class_field_names`, `_resolve_match_args`, `_resolve_class_static_field`) still exist. Phase 2 populates the symbol table; Phase 3 replaces the workarounds.

## Approach

Each of the 4 priority languages gets an `extract_<lang>_symbols(root) -> SymbolTable` function in its `declarations.py`, and a `_extract_symbols` override on its frontend class. The extraction walks the tree-sitter AST top-down, collecting class definitions with their fields, methods, constants, and parents.

## Design

### Per-Language Extraction

Each extractor walks the AST for class definitions and produces `ClassInfo` entries:

| What | C# | Java | C++ | Python |
|---|---|---|---|---|
| Class node | `class_declaration` | `class_declaration` | `class_specifier` | `class_definition` |
| Fields | `field_declaration` → `variable_declaration` → `variable_declarator` name | `field_declaration` → `variable_declarator` name | `field_declaration` → `field_identifier` | `self.x = ...` in `__init__` body |
| Static filter | `modifier` contains `static` | `modifiers` contains `static` | `storage_class_specifier` | class-body `assignment` (no `self.`) |
| Methods | `method_declaration` | `method_declaration` | `function_definition` | `function_definition` |
| Constructor | `constructor_declaration` | `constructor_declaration` | `function_definition` matching class name | `__init__` |
| Constants | static fields with initializer | static fields with initializer | static fields with initializer | class-body `assignment` (e.g., `COUNT = 0`) |
| `match_args` | N/A | N/A | N/A | `__match_args__ = ("x", "y")` |
| Parents | `base_list` | `superclass` / `interfaces` | `base_class_clause` | `argument_list` in class def |

### File Layout

Per language:
- `interpreter/frontends/<lang>/declarations.py` — add `extract_<lang>_symbols(root) -> SymbolTable`
- `interpreter/frontends/<lang>/frontend.py` — override `_extract_symbols` to call it

### What Each Extractor Produces

```python
SymbolTable(
    classes={
        "Circle": ClassInfo(
            name="Circle",
            fields={"radius": FieldInfo(name="radius", type_hint="int", has_initializer=False)},
            methods={"area": FunctionInfo(name="area", params=("self",), return_type="int")},
            constants={"COUNT": "0"},
            parents=("Shape",),
            match_args=("radius",),  # Python only
        ),
    },
    functions={...},  # module-level functions
    constants={...},  # module-level constants
)
```

### Files Changed

**Modified (per language):**
- `interpreter/frontends/csharp/declarations.py` + `frontend.py`
- `interpreter/frontends/java/declarations.py` + `frontend.py`
- `interpreter/frontends/cpp/declarations.py` + `frontend.py`
- `interpreter/frontends/python/declarations.py` + `frontend.py`

### What Phase 2 does NOT do

- Does not consume the symbol table (Phase 3)
- Does not remove workarounds (Phase 3)
- Does not add extractors for the other 11 languages (future work)
- No behavioral changes — all existing code continues to work

## Testing

Per language, one unit test class that:
- Parses a program with classes, fields, methods, constants, inheritance
- Calls `_extract_symbols` on the frontend
- Asserts `SymbolTable` has correct `ClassInfo` entries with right fields/methods/constants/parents
- Python: also asserts `match_args` extraction
