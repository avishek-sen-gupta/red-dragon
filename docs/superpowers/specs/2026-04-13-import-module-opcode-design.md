# IMPORT_MODULE Opcode & Demand-Driven Linker

**Date:** 2026-04-13
**Status:** Design
**Issue:** red-dragon-orji (Linker: demand-driven symbol resolution with scope isolation)

## Problem

The linker uses `_is_import_call()` to detect CALL_FUNCTION instructions with magic names ("import", "require") as import stubs. This is:

- **Brittle**: string matching on function names that could appear in user code.
- **Language-specific**: the linker must understand that "require" means CJS import, "import" means Python import, etc.
- **Incomplete**: no structured way to carry resolution metadata (resolved path, module exports) through the IR.

The linker should be language-agnostic. Import semantics belong in frontends.

## Solution

A dedicated `IMPORT_MODULE` IR opcode emitted by frontends for all import statements. The linker expands it into existing opcodes (NEW_OBJECT, CONST, STORE_FIELD, LOAD_VAR) using the dependency module's ExportTable.

## Architecture

### Two-Pass Compilation

```
Pass 1 (cheap):  source bytes ──> extract_imports() ──> resolve() ──> import graph
Pass 2 (full):   source bytes ──> frontend.lower(resolved_imports) ──> IR with IMPORT_MODULE
```

`extract_imports()` already operates on raw source bytes via a separate tree-sitter parse, independent of IR lowering. The restructure moves it to an earlier pass so resolution results are available during lowering.

### IMPORT_MODULE Instruction

```python
@dataclass(frozen=True)
class ImportModule(InstructionBase):
    result_reg: Register       # register receiving the namespace object
    module_path: str           # source-level path as written ("./utils", "os")
    resolved_path: PathName    # resolved path from compilation pass 1 (NO_PATH_NAME if unresolvable)
```

### Frontend Emission

All imports emit IMPORT_MODULE. Named imports desugar:

```
# Python: import os
IMPORT_MODULE  r0, "os", <resolved>

# Python: from os import path
IMPORT_MODULE  r0, "os", <resolved>
LOAD_FIELD     r1, r0, "path"
DECL_VAR       "path", r1

# TypeScript: import utils = require('./utils')
IMPORT_MODULE  r0, "./utils", <resolved>
STORE_VAR      "utils", r0
```

Resolved imports are passed into `TreeSitterEmitContext` as `resolved_imports: dict[str, PathName]` (source path to resolved PathName).

### Linker Expansion

For each IMPORT_MODULE with a resolved path, the linker expands into:

```
NEW_OBJECT     r_ns                           # create namespace object
CONST          r_tmp1, "add"                  # load BoundFuncRef via symbol table
STORE_FIELD    r_ns, "add", r_tmp1            # attach to namespace
CONST          r_tmp2, "Greeter"              # load ClassRef via symbol table
STORE_FIELD    r_ns, "Greeter", r_tmp2        # attach to namespace
LOAD_VAR       r_tmp3, "MAX_SIZE"             # load exported variable
STORE_FIELD    r_ns, "MAX_SIZE", r_tmp3       # attach to namespace
STORE_VAR      <result_reg>, r_ns             # original IMPORT_MODULE destination
```

This uses only existing opcodes. CONST already produces BoundFuncRef/ClassRef via symbol table lookup (confirmed in `interpreter/handlers/variables.py`).

### Register Allocation for Synthetic IR

Synthetic registers (r_ns, r_tmp1, etc.) start from the high-water mark computed after all module register offsets are applied. The linker already computes per-module register offsets during `_transform_module()`.

### Demand-Driven Module Filtering

At link time, walk the import graph from the entry module. Only transitively reachable modules are included in merged IR. Unreachable modules are excluded entirely.

### Topological Ordering

Dependency module IR appears before importer module IR in the merged output. This ensures dependency code has run (populating registry/symbol tables) before the linker's expansion of IMPORT_MODULE references their CodeLabels.

## PathName Wrapper Type

New file: `interpreter/path_name.py`

Frozen dataclass with `value: str`, following the VarName/FuncName pattern:
- `__post_init__()` type validation
- `is_present()` protocol
- Null object: `NoPathName` / `NO_PATH_NAME` singleton
- `__str__`, `__hash__`, `__eq__`, `__lt__`

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Circular import | `CyclicImportError` during resolution pass (existing, no change) |
| Unresolvable import (system library) | IMPORT_MODULE emitted with `NO_PATH_NAME`; linker skips expansion |
| IMPORT_MODULE reaches VM | Returns SYMBOLIC via `ExecutionResult.not_handled()` (graceful degradation) |
| Unresolved imports | Collected in `LinkedProgram.unresolved_imports` for diagnostics |

## Scope

### In Scope

- `IMPORT_MODULE` opcode + `ImportModule` instruction class
- `PathName` wrapper type
- Python frontend: `lower_import()`, `lower_import_from()` emit IMPORT_MODULE
- TypeScript frontend: `_lower_import_require_clause()` emits IMPORT_MODULE
- `compile_directory()` restructured for two-pass compilation
- Linker: IMPORT_MODULE expansion using ExportTable
- Linker: demand-driven module filtering
- Remove `_is_import_call()` heuristic

### Out of Scope (Follow-up Issues)

- Scope isolation (preventing cross-module variable leakage)
- Multi-file test coverage for frontends beyond Python/TypeScript (Go, Java, Rust, C, C++, C#, Kotlin, Scala, Ruby, PHP, Lua, Pascal, COBOL)
- Re-exports (module A re-exporting from module B)

## Files Modified

| File | Change |
|------|--------|
| `interpreter/path_name.py` | NEW: PathName wrapper type |
| `interpreter/ir.py` | Add IMPORT_MODULE to Opcode enum |
| `interpreter/instructions.py` | Add ImportModule instruction class |
| `interpreter/frontends/context.py` | Add `resolved_imports` to TreeSitterEmitContext |
| `interpreter/frontends/python/control_flow.py` | Emit IMPORT_MODULE in `lower_import()`, `lower_import_from()` |
| `interpreter/frontends/typescript.py` | Emit IMPORT_MODULE in `_lower_import_require_clause()` |
| `interpreter/project/compiler.py` | Two-pass compilation in `compile_directory()` |
| `interpreter/project/linker.py` | IMPORT_MODULE expansion, demand filtering, remove `_is_import_call()` |

## Testing

### Unit Tests
- PathName wrapper construction, equality, hashing, null object
- ImportModule instruction operands and opcode property
- Linker IMPORT_MODULE expansion given a mock ExportTable

### Frontend Tests
- Python `import os` produces IMPORT_MODULE IR
- Python `from os import path` produces IMPORT_MODULE + LOAD_FIELD + DECL_VAR
- TypeScript `import x = require('./y')` produces IMPORT_MODULE + STORE_VAR

### Integration Tests
- Two-file Python project: import function across modules, call it, verify concrete result
- Two-file TypeScript project: require class, instantiate, call method, verify result
- Unresolvable system import: graceful SYMBOLIC degradation
- Circular import: CyclicImportError raised during resolution
