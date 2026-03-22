# Multi-File Project Support

**Date:** 2026-03-22
**Status:** Accepted
**Epic:** red-dragon-iz14

## Context

RedDragon's pipeline currently operates on a single source string: one file → one IR stream → one CFG → one registry → one VM execution. Real production codebases span hundreds of files with import/include/require dependencies between them. To analyze and execute such codebases, RedDragon needs multi-file support.

## Decision

Per-module compilation with two-phase linking. Each file is compiled independently into a `ModuleUnit` (preserving the existing single-file pipeline), then a linker resolves cross-module references and merges everything into a `LinkedProgram` that feeds into the existing VM and interprocedural analysis — unchanged.

No incremental caching in the initial implementation. Correctness first.

## Architecture

```
Entry file (main.py)
    │
    ▼
Import Resolver ──── extract_imports() per file
    │                 recursively discovers transitive deps
    ▼                 returns topological sort (DAG)
Dependency Graph
    │
    ▼
Per-Module Compiler ──── for each file in topo order:
    │                     frontend.lower() → build_cfg() → build_registry()
    │                     + extract export table
    ▼
list[ModuleUnit]
    │
    ▼
Linker ──── Phase 1: build import tables
    │       Phase 2: namespace labels, rewrite references
    ▼
LinkedProgram
    │
    ├──► execute_cfg() / execute_cfg_traced()  [no VM changes]
    └──► analyze_interprocedural()             [no analysis changes]
```

## Data Model

### ModuleUnit

```python
@dataclass(frozen=True)
class ImportRef:
    """A single import statement's resolved target."""
    source_module: Path           # file that contains the import
    target_module: Path           # file being imported
    names: tuple[str, ...]        # imported names ("*" for wildcard)

@dataclass(frozen=True)
class ModuleUnit:
    """A single compiled file."""
    path: Path
    ir: list[IRInstruction]
    cfg: CFG
    registry: FunctionRegistry
    exports: dict[str, str]       # exported_name → internal_label
    imports: list[ImportRef]

@dataclass(frozen=True)
class LinkedProgram:
    """Merged multi-file program ready for execution."""
    modules: dict[Path, ModuleUnit]
    merged_cfg: CFG
    merged_registry: FunctionRegistry
    entry_module: Path
    import_graph: dict[Path, list[Path]]  # adjacency list
```

### Location: `interpreter/project/`

```
interpreter/project/
    __init__.py
    types.py          — ModuleUnit, ImportRef, LinkedProgram
    compiler.py       — compile_module(): file → ModuleUnit
    resolver.py       — resolve_imports(): entry → dependency DAG
    linker.py         — link_modules(): list[ModuleUnit] → LinkedProgram
```

## Component Details

### 1. Import Resolver (`resolver.py`)

**Input:** entry file path + language
**Output:** topologically sorted list of file paths + import graph

Algorithm:
1. Parse entry file's imports via `frontend.extract_imports(source_bytes)`
2. For each imported module, resolve to a file path (language-specific resolution)
3. Recursively parse that file's imports
4. Detect cycles — error with the cycle path
5. Return topological sort (dependencies before dependents)

### 2. Per-Module Compiler (`compiler.py`)

**Input:** file path + language
**Output:** `ModuleUnit`

Wraps the existing pipeline:
1. `frontend = get_frontend(language)`
2. `ir = frontend.lower(source_bytes)`
3. `cfg = build_cfg(ir)`
4. `registry = build_registry(ir, cfg, func_symbol_table=..., class_symbol_table=...)`
5. Build export table: collect all top-level function and class names from the registry

The export table maps `"helper"` → `"func_helper_0"`, `"User"` → `"class_User_0"`. Derived from `registry.func_params` (function labels) and `registry.classes` (class labels).

### 3. Linker (`linker.py`)

**Input:** list of `ModuleUnit`s + import graph
**Output:** `LinkedProgram`

**Phase 1 — Build import tables:**
For each module's `ImportRef` list, look up the target module's export table:
```
main.py imports "helper" from utils.py
  → utils.py exports: {"helper": "func_helper_0"}
  → import table entry: "helper" → "utils__func_helper_0"
```

**Phase 2 — Namespace and merge:**
1. Prefix all labels in each module's IR/CFG with the module name: `func_helper_0` → `utils__func_helper_0`. The prefix is derived from the file path relative to the project root.
2. Rewrite IR operands: where a `CALL_FUNCTION` or `LOAD_VAR` references an imported name, replace with the qualified label from the import table.
3. Merge all CFGs: concatenate blocks (now uniquely namespaced).
4. Merge all registries: union of func_params, class_methods, etc.
5. Set the entry point to the entry module's first block.

### 4. Per-Language Import Parsing

Each frontend implements `extract_imports(source_bytes) → list[ImportRef]`. The base implementation returns an empty list. Languages are added incrementally:

**P0 (first, establishes pattern):**
- Python: `import foo`, `from foo import bar`, `from foo.bar import baz`, relative imports

**P1 (high value):**
- JavaScript/TypeScript: `import { x } from "./utils"`, `require("./utils")`
- Java: `import com.example.Utils;`
- C/C++: `#include "header.h"` (skip system includes)

**P2 (remaining):**
- Go: `import "package/name"`
- Rust: `use crate::utils;`, `mod utils;`
- C#: `using MyNamespace;`
- Ruby, PHP, Kotlin, Scala, Pascal, Lua

## Execution

`LinkedProgram.merged_cfg` and `merged_registry` feed directly into `execute_cfg()` — no VM changes. The VM dispatches function calls by label, and namespaced labels (`utils__func_helper_0`) work the same as non-namespaced ones.

## Analysis

`analyze_interprocedural(merged_cfg, merged_registry)` works unchanged — all functions from all modules are in the merged registry, so cross-file call graphs and dataflow analysis happen automatically.

## API / MCP

New entry points:
- `interpreter/api.py`: `analyze_project(entry_file, language)`, `run_project(entry_file, language)`
- MCP server: `load_project(entry_file, language)` tool

## Label Namespacing

Module prefix derived from file path: `/project/src/utils.py` with project root `/project/` → prefix `src__utils__`. Rules:
- Replace `/` and `.` with `__`
- Strip the file extension
- Strip the project root prefix

Example: `func_helper_0` in `src/utils.py` → `src__utils__func_helper_0`

## Issues

| Issue | Description | Priority |
|-------|-------------|----------|
| red-dragon-3wuj | Data model: ModuleUnit, ImportRef, LinkedProgram | P0 |
| red-dragon-g9xm | Per-module compiler | P0 |
| red-dragon-co5y | Linker | P0 |
| red-dragon-gl1q | extract_imports() base infrastructure | P0 |
| red-dragon-jpug | Import resolver (dependency graph builder) | P0 |
| red-dragon-xhda | MCP + API integration | P1 |
| red-dragon-881h | Python extract_imports | P0 |
| red-dragon-p2in | JS/TS extract_imports | P1 |
| red-dragon-xycm | Java extract_imports | P1 |
| red-dragon-p373 | C/C++ extract_imports | P1 |
| red-dragon-6eoq | Go extract_imports | P2 |
| red-dragon-v8wl | Rust extract_imports | P2 |
| red-dragon-px9t | C# extract_imports | P2 |
| red-dragon-btbr | Ruby/PHP/Kotlin/Scala/Pascal/Lua extract_imports | P2 |

## What This Does NOT Include

- No incremental caching — recompiles all files every time (optimization for later)
- No package manager integration (pip, npm, maven) — only local file resolution
- No virtual environment or node_modules scanning
- No macro expansion (C preprocessor beyond #include)
- No cross-language linking (e.g., Python calling C extensions)
- No IDE integration (language server protocol) — MCP only
