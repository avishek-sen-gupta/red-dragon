# Linker & Multi-File Project Execution Design

**Date:** 2026-03-22  
**Status:** Implemented  
**Code:** `interpreter/project/`

---

## 1. Overview

RedDragon's multi-file project support extends the single-file pipeline to real-world codebases where source spans multiple files connected by import/include/require/use relationships. The system compiles each file independently, then a **linker** merges them into a single program that the existing VM and analysis infrastructure consume without modification.

The design follows a principle of **zero downstream changes** — the linker produces the same data structures (`CFG`, `FunctionRegistry`, `list[IRInstruction]`) that the single-file pipeline produces. Everything downstream (`execute_cfg()`, `analyze_interprocedural()`, the TUI, the MCP server) works unmodified.

---

## 2. End-to-End Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        compile_project()                               │
│                                                                        │
│   ┌─────────────┐    ┌──────────────┐    ┌──────────────┐             │
│   │ Phase 1      │    │ Phase 2       │    │ Phase 3       │            │
│   │ Import       │───▶│ Topological   │───▶│ Per-Module    │            │
│   │ Discovery    │    │ Sort          │    │ Compilation   │            │
│   │ (BFS)        │    │ (Kahn's)      │    │               │            │
│   └─────────────┘    └──────────────┘    └──────┬───────┘            │
│                                                   │                    │
│                                          list[ModuleUnit]              │
│                                                   │                    │
│                                           ┌───────▼───────┐           │
│                                           │ Phase 4        │           │
│                                           │ Linking         │           │
│                                           │                 │           │
│                                           │ ┌─────────────┐│           │
│                                           │ │ Namespace    ││           │
│                                           │ │ labels       ││           │
│                                           │ ├─────────────┤│           │
│                                           │ │ Rebase       ││           │
│                                           │ │ registers    ││           │
│                                           │ ├─────────────┤│           │
│                                           │ │ Rewrite      ││           │
│                                           │ │ cross-module ││           │
│                                           │ │ references   ││           │
│                                           │ ├─────────────┤│           │
│                                           │ │ Merge IR +   ││           │
│                                           │ │ build CFG +  ││           │
│                                           │ │ registry     ││           │
│                                           │ └─────────────┘│           │
│                                           └───────┬───────┘           │
│                                                   │                    │
│                                           LinkedProgram                │
└───────────────────────────────────────────────┬─────────────────────────┘
                                                │
                          ┌─────────────────────┼─────────────────────┐
                          │                     │                     │
                    execute_cfg()    analyze_interprocedural()    MCP/API
                    (no changes)        (no changes)           (no changes)
```

### Entry points

| Function | Module | Purpose |
|----------|--------|---------|
| `compile_project(entry_file, language, project_root?)` | `compiler.py` | Full pipeline orchestrator |
| `analyze_project(entry_file, language, project_root?)` | `api.py` | Compile + interprocedural analysis |
| `run_project(entry_file, language, project_root?, max_steps?)` | `api.py` | Compile + VM execution |
| `handle_load_project(entry_file, language)` | `mcp_server/tools.py` | MCP tool wrapper |

---

## 3. Phase 1: Import Discovery

**Module:** `interpreter/project/imports.py`  
**Input:** entry file path + language  
**Output:** per-file list of `ImportRef` objects

### 3.1 How it works

Import discovery uses tree-sitter to parse each file and walk its top-level AST nodes, extracting import statements into uniform `ImportRef` objects. This is intentionally separate from the full `lower()` pipeline — it only walks the root's children, never emits IR, and is much cheaper.

A BFS starting from the entry file drives recursive discovery:

```python
queue = [entry_file]
while queue:
    file = queue.pop(0)
    if already_discovered(file):
        continue
    refs = extract_imports(file.read_bytes(), file, language)
    for ref in refs:
        resolved = resolver.resolve(ref, project_root)
        if resolved.resolved_path is not None:
            import_graph[file].append(resolved.resolved_path)
            queue.append(resolved.resolved_path)
```

### 3.2 ImportRef — the universal import representation

Every language's import syntax is normalized into the same `ImportRef` dataclass:

```python
@dataclass(frozen=True)
class ImportRef:
    source_file: Path       # file containing this import
    module_path: str         # "os.path", "./utils", "crate::utils"
    names: tuple[str, ...]   # ("join",), ("*",), or () for module-level
    is_relative: bool        # ./path, from . import, crate::
    relative_level: int      # from .. is 2, from . is 1
    is_system: bool          # stdlib/third-party (skip resolution)
    kind: str                # "import"|"include"|"use"|"require"|"mod"|"using"
    alias: str | None        # import X as Y
```

### 3.3 Per-language import node mapping

Each language registers an extractor function that handles its tree-sitter AST node types:

| Language | AST Node Types | Import Kind |
|----------|---------------|-------------|
| Python | `import_statement`, `import_from_statement` | `import` |
| JavaScript/TypeScript | `import_statement`, `call_expression[require]` | `import`, `require` |
| Java | `import_declaration` | `import` |
| Go | `import_declaration` → `import_spec` | `import` |
| Rust | `use_declaration`, `mod_item` | `use`, `mod` |
| C/C++ | `preproc_include` | `include` |
| C# | `using_directive` | `using` |
| Kotlin | `import_list` → `import_header` | `import` |
| Scala | `import_declaration` | `import` |
| Ruby | `call[require/require_relative]` | `require` |
| PHP | `namespace_use_declaration`, `require_*_expression` | `use`, `require` |
| Lua | `function_call[require]` | `require` |
| Pascal | `declUses` → `moduleName` | `using` |

### 3.4 System import detection

Each language has heuristics to classify imports as system/third-party (skipped during resolution):

| Language | System Heuristic |
|----------|-----------------|
| Python | Not relative, file doesn't exist locally |
| JS/TS | Path doesn't start with `.` or `/` |
| Java | Starts with `java.`, `javax.`, `sun.`, `com.sun.` |
| Go | No dots in path (`"fmt"`, `"os"`) |
| Rust | Starts with `std::`, `core::`, `alloc::` |
| C/C++ | Angle-bracket includes (`<stdio.h>`) — detected by AST node type `system_lib_string` |
| C# | Starts with `System`, `Microsoft` |
| Kotlin | Starts with `java.`, `javax.`, `kotlin.`, `kotlinx.` |
| Scala | Starts with `scala.`, `java.`, `javax.` |
| Ruby | No `.` or `/` in path |
| Pascal | Known unit names: `SysUtils`, `Classes`, `System`, etc. |

---

## 4. Phase 2: Import Resolution

**Module:** `interpreter/project/resolver.py`  
**Input:** `ImportRef` + project root  
**Output:** `ResolvedImport` (file path or external marker)

### 4.1 Resolver protocol

Each language provides an `ImportResolver` implementation:

```python
class ImportResolver(ABC):
    @abstractmethod
    def resolve(self, ref: ImportRef, project_root: Path) -> ResolvedImport: ...

@dataclass(frozen=True)
class ResolvedImport:
    ref: ImportRef
    resolved_path: Path | None   # None = unresolvable
    is_external: bool = False    # True for system imports
```

### 4.2 Resolution strategies

**Python** — `module.path` → `module/path.py` or `module/path/__init__.py`. Relative imports go up `relative_level - 1` directories from the source file.

**JavaScript/TypeScript** — relative paths probed with extensions (`.js`, `.ts`, `.jsx`, `.tsx`, `.mjs`, `.cjs`) and `index.*` files. Bare specifiers (`react`, `express`) are classified as external.

**Java** — `com.example.Utils` → `com/example/Utils.java`. Searches `project_root/`, `src/`, `src/main/java/`.

**Go** — relative paths resolve to directories containing `.go` files. Stdlib and external module paths are external.

**Rust** — `crate::utils` → `src/utils.rs` or `src/utils/mod.rs`. `mod helpers;` → `helpers.rs` or `helpers/mod.rs` relative to the source file.

**C/C++** — `"header.h"` searched in: source directory, project root, `include/`, `src/`. System includes (`<stdio.h>`) are skipped by the extractor (marked `is_system` from the AST).

**Kotlin/Scala** — JVM package convention: `com.example.Utils` → `com/example/Utils.kt` (or `.scala`, `.java`). Searches `src/`, `src/main/kotlin/`, `src/main/scala/`.

### 4.3 Topological sort

After resolution, the import graph is topologically sorted using **Kahn's algorithm** so that dependencies are compiled before the files that import them.

The graph semantics: `graph[A] = [B, C]` means "A depends on B and C". The sort produces an order where B and C appear before A.

**Cycle detection:** If the sort can't complete (remaining nodes have nonzero in-degree), a DFS finds the actual cycle and raises `CyclicImportError` with the full cycle path (e.g., `a.py → b.py → c.py → a.py`).

### 4.4 Project root inference

When no explicit project root is provided, the system walks up from the entry file's directory looking for marker files:

```
pyproject.toml, setup.py, setup.cfg          # Python
package.json                                  # JS/TS
pom.xml, build.gradle, build.gradle.kts      # Java/Kotlin
go.mod                                        # Go
Cargo.toml                                    # Rust
Makefile, CMakeLists.txt                      # C/C++
composer.json                                 # PHP
.git                                          # universal fallback
```

Falls back to the entry file's directory if no marker is found.

---

## 5. Phase 3: Per-Module Compilation

**Module:** `interpreter/project/compiler.py`  
**Input:** file path + language  
**Output:** `ModuleUnit`

### 5.1 compile_module()

Per-module compilation is the existing single-file pipeline with one addition — export table extraction:

```
source bytes
    │
    ▼
frontend = get_frontend(language)
ir = frontend.lower(source)             # existing pipeline, unchanged
    │
    ▼
exports = build_export_table(ir, func_symbol_table, class_symbol_table)
imports = extract_imports(source, file, language)
    │
    ▼
ModuleUnit(path, language, ir, exports, imports)
```

### 5.2 Why no per-module CFG?

The `ModuleUnit` stores raw IR as an immutable tuple — no CFG, no registry. This is a deliberate design choice:

1. **Label collisions** — two modules can both have `func_helper_0`. Building per-module CFGs and then merging them would require renaming labels inside CFG blocks, successor/predecessor lists, and registry entries — a fragile multi-site rewrite.

2. **Registry merge complexity** — merging two `FunctionRegistry` objects with overlapping class names, method tables, and func_refs requires careful conflict resolution.

3. **Wasted work** — per-module CFGs are never used independently. Only the merged CFG matters for execution and analysis.

**Instead:** store raw IR per module. The linker namespaces the IR, concatenates it, and builds CFG + registry exactly once on the final merged IR. `build_cfg()` and `build_registry()` work completely unmodified.

### 5.3 Export table construction

The `ExportTable` catalogs what a module makes available to other modules:

```python
@dataclass(frozen=True)
class ExportTable:
    functions: dict[str, str]    # name → IR label ("helper" → "func_helper_0")
    classes: dict[str, str]      # name → IR label ("User" → "class_User_4")
    variables: dict[str, str]    # name → register ("PI" → "%0")
```

**Sources:**
- `functions` — from `func_symbol_table` (populated by the frontend during `lower()`)
- `classes` — from `class_symbol_table` (populated by the frontend during `lower()`)
- `variables` — from top-level `STORE_VAR`/`DECL_VAR` instructions at module scope (outside any function or class body)

**Scope tracking:** A boolean `in_scope` flag starts `True` (module level), flips to `False` when entering a `func_*` or `class_*` label, and flips back to `True` at `end_*` labels. Only `STORE_VAR`/`DECL_VAR` instructions encountered while `in_scope` is `True` are exported. Function and class names are excluded from the variables dict to avoid duplication.

---

## 6. Phase 4: Linking

**Module:** `interpreter/project/linker.py`  
**Input:** `dict[Path, ModuleUnit]`, import graph, entry module, project root, topological order  
**Output:** `LinkedProgram`

The linker is the core of the multi-file system. It transforms independently compiled modules into a single flat IR stream that looks exactly like what a single-file compilation would produce — just larger.

### 6.1 Step 1: Compute namespace prefixes

Each module gets a unique prefix derived from its file path relative to the project root:

```
/project/main.py          →  "main"
/project/utils.py         →  "utils"
/project/src/helpers.py   →  "src.helpers"
/project/pkg/models/user.py → "pkg.models.user"
```

**Rules:**
- Strip the project root prefix
- Strip the file extension
- Replace path separators (`/`, `\`) with `.`

### 6.2 Step 2: Build import tables

For each module, the linker builds a mapping from local imported names to their fully-namespaced labels in the target module.

**Example:** `main.py` has `from utils import helper`, and `utils.py` exports `{"helper": "func_helper_0"}`:

```
import_table["main.py"] = {
    "helper": "utils.func_helper_0"    # local name → namespaced label
}
```

**Wildcard imports** (`from utils import *`): every export name from the target module is added to the table.

**Aliased imports** (`import numpy as np`): the alias is used as the local name key.

**Module-level imports** (`import utils`): these don't add entries — the VM handles `utils.helper()` via `CALL_METHOD` on the module object. Only `from X import Y` style (where `names` is non-empty) populates the table.

### 6.3 Step 3: Namespace labels

Every label in each module's IR is prefixed with the module's namespace:

```
LABEL entry                →  LABEL main.entry
LABEL func_helper_0        →  LABEL utils.func_helper_0
BRANCH end_helper_1        →  BRANCH utils.end_helper_1
BRANCH_IF %0 t_2,f_3       →  BRANCH_IF %100 utils.t_2,utils.f_3
```

**Comma-separated branch targets** (used by `BRANCH_IF` and `TRY_PUSH`) are split, each target namespaced, and rejoined.

**TRY_PUSH operands** also contain label strings — these are namespaced in the operand list.

### 6.4 Step 4: Rebase registers

Registers use a simple integer offset to prevent collisions between modules. If module A uses `%0`..`%47` and module B uses `%0`..`%31`, module B's registers are shifted by 48:

```
Module A: %0, %1, ..., %47   →  %0, %1, ..., %47       (offset 0)
Module B: %0, %1, ..., %31   →  %48, %49, ..., %79     (offset 48)
Module C: %0, %1, ..., %15   →  %80, %81, ..., %95     (offset 80)
```

The offset is computed as `max_register_number(previous_module) + 1` accumulated across modules.

**Why not namespace registers as strings?** Registers appear in `result_reg`, in operand lists, inside `STORE_VAR`/`DECL_VAR`/`BINOP`/etc. Renaming `%0` to `%utils.0` would require parsing and rewriting every operand string. Integer rebasing is a clean arithmetic operation that doesn't change the string format.

### 6.5 Step 5: Rewrite cross-module references

Three kinds of operands are rewritten:

**1. Imported function calls:**
```
CALL_FUNCTION "helper" %0     →  CALL_FUNCTION "utils.func_helper_0" %48
```
When the first operand of `CALL_FUNCTION` matches a key in the import table, it's replaced with the namespaced label.

**2. Imported variable loads:**
```
LOAD_VAR "helper"              →  LOAD_VAR "utils.func_helper_0"
```
Same logic for `LOAD_VAR` — if the variable name is in the import table, rewrite it.

**3. Internal function/class label references:**
```
CONST "func_helper_0"          →  CONST "utils.func_helper_0"
```
When a `CONST` instruction's first operand starts with `func_` or `class_`, it's a self-reference to a function or class label within the same module. These are namespaced to match the namespaced labels.

### 6.6 Step 6: Merge and build

The namespaced IR from all modules is concatenated in a specific order:

```
[entry module IR]          ← first, so its "entry" label is the program entry
[dependency 1 IR]          ← in topological order (leaves first)
[dependency 2 IR]
...
```

The **entry module goes first** because `build_cfg()` sets `cfg.entry` to the first label it encounters. The entry module's namespaced entry label (e.g., `main.entry`) becomes the program's entry point.

After concatenation, standard `build_cfg()` and `build_registry()` run on the merged IR — producing the same data structures the single-file pipeline produces.

### 6.7 Step 7: Merge symbol tables

Function and class symbol tables from all modules are merged with namespaced labels:

```python
# Module utils.py: FuncRef(name="helper", label="func_helper_0")
# After merge:      FuncRef(name="utils.helper", label="utils.func_helper_0")
```

These merged tables are passed to `build_registry()` so the registry correctly indexes namespaced functions and classes.

### 6.8 Registry namespace awareness

The existing `build_registry()` scans CFG blocks for labels starting with `func_` to extract function parameters. After namespacing, labels look like `utils.func_helper_0`. To handle this, three helper functions were added to `interpreter/registry.py`:

```python
def _is_func_label(label: str) -> bool:
    """Matches: func_foo_0, utils.func_foo_0, src.utils.func_foo_0"""
    return label.startswith("func_") or ".func_" in label

def _is_class_label(label: str) -> bool:
    """Matches: class_Foo_0, utils.class_Foo_0"""
    # Also handles prelude_class_ variants
    ...

def _is_end_class_label(label: str) -> bool:
    """Matches: end_class_Foo_1, utils.end_class_Foo_1"""
    ...
```

These replace the previous `startswith(FUNC_LABEL_PREFIX)` checks, making the registry scanner work with both namespaced and non-namespaced labels. Single-file compilation is unaffected.

---

## 7. Data Model

### 7.1 ModuleUnit

```python
@dataclass(frozen=True)
class ModuleUnit:
    path: Path                          # absolute file path
    language: Language                  # source language
    ir: tuple[IRInstruction, ...]       # raw, un-namespaced IR (immutable)
    exports: ExportTable                # what this module makes available
    imports: tuple[ImportRef, ...]      # what this module imports
```

Frozen and uses tuples (not lists) to prevent accidental mutation before linking.

### 7.2 LinkedProgram

```python
@dataclass
class LinkedProgram:
    modules: dict[Path, ModuleUnit]       # all compiled modules
    merged_ir: list[IRInstruction]        # namespaced + rebased + rewritten
    merged_cfg: CFG                       # built from merged_ir
    merged_registry: FunctionRegistry     # built from merged_ir
    entry_module: Path                    # the entry point file
    import_graph: dict[Path, list[Path]]  # file → files it imports
    unresolved_imports: list[ImportRef]    # imports that couldn't be resolved
```

After linking, `merged_cfg` and `merged_registry` feed directly into `execute_cfg()` and `analyze_interprocedural()` — no adapter, no wrapper, no changes.

---

## 8. Worked Example

### Source files

**`utils.py`:**
```python
def helper(x):
    return x + 1
```

**`main.py`:**
```python
from utils import helper

result = helper(42)
```

### Phase 1: Import discovery

BFS from `main.py`:
1. Parse `main.py` → finds `ImportRef(module_path="utils", names=("helper",))`
2. Resolve `utils` → `utils.py` (file exists)
3. Parse `utils.py` → no imports
4. Import graph: `{main.py: [utils.py], utils.py: []}`

### Phase 2: Topological sort

`utils.py` has no dependencies → comes first.
Order: `[utils.py, main.py]`

### Phase 3: Per-module compilation

**`utils.py` IR:**
```
entry:
  BRANCH end_helper_1
func_helper_0:
  %0 = SYMBOLIC param:x
  DECL_VAR x %0
  %1 = LOAD_VAR x
  %2 = CONST 1
  %3 = BINOP + %1 %2
  RETURN %3
  %4 = CONST None
  RETURN %4
end_helper_1:
  %5 = CONST func_helper_0
  DECL_VAR helper %5
```

**`utils.py` exports:** `{functions: {"helper": "func_helper_0"}}`

**`main.py` IR:**
```
entry:
  %0 = CALL_FUNCTION "import" "from utils import helper"
  DECL_VAR helper %0
  %1 = CONST 42
  %2 = CALL_FUNCTION "helper" %1
  STORE_VAR result %2
```

**`main.py` imports:** `[ImportRef(module_path="utils", names=("helper",))]`

### Phase 4: Linking

**Prefixes:** `{utils.py: "utils", main.py: "main"}`

**Import table for `main.py`:**
```
{"helper": "utils.func_helper_0"}
```

**Entry module (main.py) — namespaced + rebased (offset=0) + rewritten:**
```
main.entry:
  %0 = CALL_FUNCTION "import" "from utils import helper"
  DECL_VAR helper %0
  %1 = CONST 42
  %2 = CALL_FUNCTION "utils.func_helper_0" %1    ← REWRITTEN
  STORE_VAR result %2
```

**utils.py — namespaced + rebased (offset=3):**
```
utils.entry:
  BRANCH utils.end_helper_1
utils.func_helper_0:
  %3 = SYMBOLIC param:x
  DECL_VAR x %3
  %4 = LOAD_VAR x
  %5 = CONST 1
  %6 = BINOP + %4 %5
  RETURN %6
  %7 = CONST None
  RETURN %7
utils.end_helper_1:
  %8 = CONST utils.func_helper_0                  ← NAMESPACED
  DECL_VAR helper %8
```

**Merged IR:** entry module first, then utils module. `build_cfg()` sees `main.entry` as the first label → sets it as `cfg.entry`.

**Execution:** When the VM hits `CALL_FUNCTION "utils.func_helper_0"`, it dispatches to the function body at label `utils.func_helper_0` — which contains the actual `x + 1` logic. The call resolves correctly because the merged registry maps `utils.func_helper_0` → params `["x"]`.

---

## 9. Error Handling

| Scenario | Behavior |
|----------|----------|
| Cyclic import (`a → b → a`) | `CyclicImportError` raised with the full cycle path |
| File not found during resolution | Import marked as unresolved; compilation continues without it |
| Parse error in imported file | Exception propagates from `frontend.lower()` |
| Export not found in target module | `CALL_FUNCTION "import" "from X import Y"` left unchanged (VM handles symbolically) |
| Duplicate names across modules | No collision — every module's labels are namespaced uniquely |

---

## 10. What This Does Not Include

- **No incremental caching** — every `compile_project()` call recompiles all files
- **No package manager integration** — no pip/npm/maven/cargo resolution; only local files
- **No virtual environment or node_modules scanning**
- **No macro expansion** — C preprocessor `#define` not expanded (only `#include` resolved)
- **No cross-language linking** — all files in a project must be the same language
- **No cycle-breaking** — cyclic imports abort with an error (no lazy import support)
- **No IDE integration** — project support is API/MCP only, no Language Server Protocol

---

## 11. Code Map

```
interpreter/project/
    __init__.py         Package init
    types.py            ImportRef, ExportTable, ModuleUnit, LinkedProgram, CyclicImportError
    imports.py          extract_imports() — per-language tree-sitter AST walkers (15 languages)
    resolver.py         ImportResolver protocol + 12 language-specific resolvers
                        topological_sort() — Kahn's algorithm with cycle detection
                        infer_project_root() — marker file search
    compiler.py         compile_module() — single-file compilation + export extraction
                        compile_project() — full orchestrator (discover → compile → link)
                        build_export_table() — IR + symbol tables → ExportTable
    linker.py           link_modules() — namespace + rebase + rewrite + merge
                        module_prefix() — file path → namespace string
                        namespace_label() — prefix a label
                        rebase_register() — shift %N by offset
                        max_register_number() — find highest register in IR

interpreter/registry.py
    _is_func_label()      — namespace-aware function label check
    _is_class_label()     — namespace-aware class label check
    _is_end_class_label() — namespace-aware end-class label check

interpreter/api.py
    analyze_project()     — compile + interprocedural analysis
    run_project()         — compile + VM execution

mcp_server/tools.py
    handle_load_project() — MCP tool for multi-file project loading

mcp_server/server.py
    load_project()        — MCP tool registration
```

---

## 12. Test Coverage

148 tests across unit and integration:

| Test File | Tests | Covers |
|-----------|-------|--------|
| `test_types.py` | 26 | Data model construction, immutability, defaults |
| `test_export_table.py` | 10 | Export table building from IR + symbol tables |
| `test_import_extraction.py` | 14 | Python import extraction (all forms) |
| `test_all_language_imports.py` | 33 | Import extraction across all 15 languages |
| `test_resolver.py` | 10 | Python resolver + protocol |
| `test_topo_sort.py` | 9 | Topological sort, cycles, edge cases |
| `test_linker.py` | 18 | Namespace, rebase, register helpers |
| `test_project_pipeline.py` | 14 | Full pipeline (Python, JS, Java, C) |
| `test_fixture_projects.py` | 5 | On-disk fixture projects |
| `test_api_integration.py` | 3 | API functions |
| `test_mcp_tool.py` | 5 | MCP tool |
