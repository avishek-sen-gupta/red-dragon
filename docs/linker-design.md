# Linker & Multi-File Project Execution Design

**Date:** 2026-03-22 (revised 2026-03-23)  
**Status:** Implemented  
**Code:** `interpreter/project/`

---

## 1. Overview

RedDragon's multi-file project support extends the single-file pipeline to real-world codebases. Given an entry file, it recursively discovers imports, compiles each file independently, then a **linker** merges them into a single IR stream that looks exactly like what the single-file pipeline would produce if all source files were concatenated in dependency order.

**Design principle:** The linker's output is indistinguishable from single-file compilation. The VM, CFG builder, registry, and interprocedural analysis run completely unmodified.

**Supported:** All 15 tree-sitter frontends + COBOL (16 languages total).

---

## 2. Pipeline

```
Entry file
    │
    ▼
Phase 1: Import Discovery (BFS)
    │  extract_imports() per file — tree-sitter AST or regex (COBOL)
    │  ImportResolver maps ImportRef → file path
    ▼
Dependency graph + topological sort
    │
    ▼
Phase 1.5: Namespace Pre-Scan (Java only)
    │  java_pre_scan() per file → (package, class_names, imports)
    │  build_java_namespace_tree(scan_results, stdlib_registry)
    │  → JavaNamespaceResolver injected into Phase 2
    ▼
Phase 2: Per-Module Compilation
    │  frontend.lower(source, namespace_resolver) → IR
    │  build_export_table() → ExportTable
    ▼
list[ModuleUnit]
    │
    ▼
Phase 3: Linking
    │  Strip per-module entry: labels
    │  Namespace all labels + rebase registers
    │  Drop resolved import stubs
    │  Concatenate: deps first, entry module last
    │  Prepend single entry: label
    │  build_cfg() + build_registry()
    ▼
LinkedProgram
    │
    ├──► execute_cfg()              (no changes)
    └──► analyze_interprocedural()  (no changes)
```

### Entry points

| Function | Module | Purpose |
|----------|--------|---------|
| `compile_project(entry_file, language, project_root?)` | `compiler.py` | Full pipeline: discover → compile → link |
| `analyze_project(entry_file, language, project_root?)` | `api.py` | compile_project + interprocedural analysis |
| `run_project(entry_file, language, project_root?, ...)` | `api.py` | compile_project + VM execution |
| `handle_load_project(entry_file, language)` | `mcp_server/tools.py` | MCP tool wrapper |

---

## 3. Phase 1: Import Discovery

**Module:** `interpreter/project/imports.py`

### 3.1 ImportRef

Every language's import syntax is normalized into the same frozen dataclass:

```python
@dataclass(frozen=True)
class ImportRef:
    source_file: Path       # file containing this import
    module_path: str         # "os.path", "./utils", "crate::utils"
    names: tuple[str, ...]   # ("join",), ("*",), or () for module-level
    is_relative: bool        # ./path, from . import, crate::
    relative_level: int      # from .. is 2, from . is 1
    is_system: bool          # stdlib/third-party
    kind: str                # "import"|"include"|"use"|"require"|"mod"|"using"
    alias: str | None        # import X as Y
```

### 3.2 Per-language extraction

| Language | AST Node Types | Kind | Notes |
|----------|---------------|------|-------|
| Python | `import_statement`, `import_from_statement` | `import` | Relative imports, aliases, wildcards |
| JS/TS | `import_statement`, `call_expression[require]` | `import`, `require` | ESM + CJS |
| Java | `import_declaration` | `import` | Static, wildcard |
| Go | `import_declaration` → `import_spec` | `import` | Grouped, aliased |
| Rust | `use_declaration`, `mod_item` | `use`, `mod` | Scoped, lists |
| C/C++ | `preproc_include` | `include` | System vs local by AST node type |
| C# | `using_directive` | `using` | Static, alias |
| Kotlin | `import_list` → `import_header` | `import` | |
| Scala | `import_declaration` | `import` | Namespace selectors, wildcard |
| Ruby | `call[require/require_relative]` | `require` | |
| PHP | `namespace_use_declaration`, `require_*` | `use`, `require` | |
| Lua | `function_call[require]` | `require` | |
| Pascal | `declUses` → `moduleName` | `using` | |
| COBOL | regex: `COPY name`, `CALL 'name'` | `include`, `require` | No tree-sitter |

### 3.3 Import resolution

**Module:** `interpreter/project/resolver.py`

Each language has an `ImportResolver` that maps `ImportRef → file path`:

| Resolver | Languages | Strategy |
|----------|-----------|----------|
| `PythonImportResolver` | Python | `mod.path` → `mod/path.py` or `mod/path/__init__.py` |
| `JavaScriptImportResolver` | JS, TS | Extension probing (`.js/.ts/.jsx/.tsx`) + `index.*` |
| `JavaImportResolver` | Java | Package path + source root probing |
| `GoImportResolver` | Go | Relative paths → directories with `.go` files |
| `RustImportResolver` | Rust | `crate::`/`self::`/`super::` + `.rs`/`mod.rs` |
| `CIncludeResolver` | C, C++ | Source dir → project root → `include/` |
| `CSharpImportResolver` | C# | Dotted name → `.cs` file |
| `JvmImportResolver` | Kotlin, Scala | Package path + `.kt`/`.scala`/`.java` |
| `RubyImportResolver` | Ruby | `lib/` dir probing + `.rb` extension |
| `PhpImportResolver` | PHP | `use` namespace → dir, `require` → direct path |
| `LuaImportResolver` | Lua | Dot-to-slash conversion + `.lua` extension |
| `PascalImportResolver` | Pascal | `name.pas` in source dir or project root |
| `CobolImportResolver` | COBOL | `.cpy`/`.cbl` in source dir, project root, `copylib/` |

System imports (stdlib, npm packages, etc.) are skipped — the resolver returns `resolved_path=None` and the file is not compiled.

### 3.4 Dependency graph

BFS from the entry file discovers all reachable files. **Kahn's algorithm** produces a topological sort (dependencies before dependents). Cycles raise `CyclicImportError` with the full cycle path.

---

## 4. Phase 2: Per-Module Compilation

**Module:** `interpreter/project/compiler.py`

Each file is compiled independently using the existing single-file pipeline:

```python
frontend = get_frontend(language)
ir = frontend.lower(source, namespace_resolver=namespace_resolver)
exports = build_export_table(ir, func_symbol_table, class_symbol_table)
→ ModuleUnit(path, language, ir, exports, imports)
```

No CFG or registry is built per module. Only the raw IR (as an immutable tuple) and an export table.

### Namespace Pre-Scan (Java)

For Java, `compile_directory()` runs a pre-scan phase before per-module compilation:

1. **`java_pre_scan(source)`** — fast tree-sitter walk extracting package name, top-level type names (class, interface, enum, record), and imports. No expression lowering.
2. **`build_java_namespace_tree(scan_results, stdlib_registry)`** — builds a `NamespaceTree` (trie). Stdlib stubs are registered first, then project classes override at the same path. Types without a package are not registered.
3. A `JavaNamespaceResolver` wrapping the tree is passed to each `compile_module()` call. During lowering, `lower_field_access` calls `resolver.try_resolve_field_access()` which collapses `java.util.Arrays` into `LoadVar("Arrays")` instead of cascading `LOAD_VAR "java"` → `LOAD_FIELD "util"` → `LOAD_FIELD "Arrays"`.

Non-Java languages receive the null-object `NamespaceResolver` base class (no-op). Code: `interpreter/frontends/java/namespace.py`, `interpreter/namespace.py`.

### ExportTable

```python
@dataclass(frozen=True)
class ExportTable:
    functions: dict[str, str]    # name → label ("helper" → "func_helper_0")
    classes: dict[str, str]      # name → label ("User" → "class_User_4")
    variables: dict[str, str]    # name → register ("PI" → "%0")
```

Functions and classes come from the frontend's symbol tables. Variables come from top-level `STORE_VAR`/`DECL_VAR` instructions (outside function/class bodies).

---

## 5. Phase 3: Linking

**Module:** `interpreter/project/linker.py`

The linker's job: produce a single IR stream that looks exactly like single-file compilation. The entire logic:

### 5.1 Strip per-module `entry:` labels

Each module's IR starts with `LABEL entry`. The linker removes these — there's only one entry point in the merged program.

### 5.2 Namespace labels + rebase registers

Labels get a module prefix derived from the file path: `func_helper_0` → `utils.func_helper_0`. Registers get an integer offset to avoid collisions: module A uses `%0–%47`, module B starts at `%48`.

`CONST` operands referencing function/class labels (`CONST "func_helper_0"`) are also namespaced. This is how the VM's `_handle_const` handler finds the label in the `func_symbol_table` and creates a `BoundFuncRef`.

### 5.3 Drop resolved import stubs

Python emits import statements as:
```
%0 = CALL_FUNCTION "import" "from utils import helper"
DECL_VAR helper %0
```

For names that a dependency module already provides (functions, classes, variables), this pair is dropped. The dependency module's top-level code runs first and sets those names in scope — exactly like single-file.

Other languages (JS, Java, Go, etc.) emit no import IR at all — their import statements are no-ops during lowering. Ruby/PHP/Lua emit `CALL_FUNCTION require/require_once` which produce harmless symbolic values that don't overwrite the dependency's declarations.

### 5.4 Concatenate in dependency order

```
entry:                           ← single entry label
  [dep1 top-level code]          ← STORE_VAR, CONST+DECL_VAR for funcs/classes
  [dep2 top-level code]
  [entry module top-level code]  ← uses imported names (already in scope)
  [dep1 function/class bodies]   ← jumped over by BRANCH-end patterns
  [dep2 function/class bodies]
  [entry function/class bodies]
```

Dependencies run first, so by the time the entry module's code executes, all imported names are available in the scope chain.

### 5.5 Build CFG + registry

`build_cfg()` and `build_registry()` run on the merged IR exactly as they do for single-file compilation. No modifications needed.

### 5.6 Symbol table merging

Function and class symbol tables from all modules are merged. Labels are namespaced (unique in merged CFG). **Names are kept bare** — the VM uses bare names for method dispatch (`__init__`, `area`), constructor dispatch, and class_methods lookup.

---

## 6. Worked Example

### Source

**utils.py:**
```python
def add(a, b):
    return a + b
```

**main.py:**
```python
from utils import add
result = add(10, 20)
```

### Phase 1: Discovery

`main.py` → `from utils import add` → resolve `utils` → `utils.py`.
Topo order: `[utils.py, main.py]`.

### Phase 2: Compilation

**utils.py IR:**
```
entry:
  BRANCH end_add_1
func_add_0:
  %0 = SYMBOLIC param:a
  DECL_VAR a %0
  %1 = SYMBOLIC param:b
  DECL_VAR b %1
  %2 = LOAD_VAR a
  %3 = LOAD_VAR b
  %4 = BINOP + %2 %3
  RETURN %4
end_add_1:
  %5 = CONST func_add_0
  DECL_VAR add %5
```

**utils.py exports:** `{functions: {"add": "func_add_0"}}`

**main.py IR:**
```
entry:
  %0 = CALL_FUNCTION "import" "from utils import add"
  DECL_VAR add %0
  %1 = CONST 10
  %2 = CONST 20
  %3 = CALL_FUNCTION add %1 %2
  STORE_VAR result %3
```

### Phase 3: Linking

1. **Strip** `entry:` labels from both modules
2. **Namespace** utils labels: `func_add_0` → `utils.func_add_0`, etc.
3. **Rebase** main registers by 6 (utils uses %0–%5)
4. **Drop** main's import stub (`CALL_FUNCTION "import"` + `DECL_VAR add`) — `add` is in utils.py exports
5. **Prepend** single `entry:` label
6. **Concatenate** utils first, then main

**Merged IR:**
```
entry:
  BRANCH utils.end_add_1
utils.func_add_0:
  %0 = SYMBOLIC param:a
  DECL_VAR a %0
  %1 = SYMBOLIC param:b
  DECL_VAR b %1
  %2 = LOAD_VAR a
  %3 = LOAD_VAR b
  %4 = BINOP + %2 %3
  RETURN %4
utils.end_add_1:
  %5 = CONST utils.func_add_0
  DECL_VAR add %5
  %6 = CONST 10
  %7 = CONST 20
  %8 = CALL_FUNCTION add %6 %7
  STORE_VAR result %8
```

This is one continuous stream. The VM:
1. Hits `BRANCH utils.end_add_1` — skips the function body
2. Hits `CONST utils.func_add_0` — handler looks up in `func_symbol_table`, creates `BoundFuncRef`
3. Hits `DECL_VAR add` — stores the `BoundFuncRef` in local_vars
4. Hits `CALL_FUNCTION add` — looks up `add` in local_vars, finds `BoundFuncRef`, dispatches to `utils.func_add_0`
5. Function body runs, returns `30`
6. Hits `STORE_VAR result 30`

**Result:** `result = 30`. Zero LLM calls. Identical behavior to single-file.

---

## 7. Data Model

```python
@dataclass(frozen=True)
class ModuleUnit:
    path: Path
    language: Language
    ir: tuple[InstructionBase, ...]    # raw, un-namespaced (immutable)
    exports: ExportTable
    imports: tuple[ImportRef, ...]

@dataclass
class LinkedProgram:
    modules: dict[Path, ModuleUnit]
    merged_ir: list[InstructionBase]
    merged_cfg: CFG
    merged_registry: FunctionRegistry
    entry_module: Path
    import_graph: dict[Path, list[Path]]
    func_symbol_table: dict          # for ExecutionStrategies
    class_symbol_table: dict         # for ExecutionStrategies
    unresolved_imports: list[ImportRef]
```

---

## 8. Registry Namespace Awareness

The registry scanner (`interpreter/registry.py`) uses label prefix checks to find functions and classes. After namespacing, labels like `utils.func_add_0` don't start with `func_` — they start with the module prefix. Three helpers handle this:

```python
_is_func_label("func_add_0")          → True
_is_func_label("utils.func_add_0")    → True  (checks for ".func_" substring)

_is_class_label("class_User_0")       → True
_is_class_label("geom.class_User_0")  → True

_is_end_class_label("end_class_User_1")       → True
_is_end_class_label("geom.end_class_User_1")  → True
```

These replace the original `startswith(FUNC_LABEL_PREFIX)` checks. Single-file compilation is unaffected.

---

## 9. Error Handling

| Scenario | Behavior |
|----------|----------|
| Cyclic import | `CyclicImportError` with full cycle path |
| File not found | Import skipped; compilation continues |
| Parse error in imported file | Exception from `frontend.lower()` |
| Export not found | Import stub left as-is (VM handles symbolically) |
| Name collisions across modules | No collision — labels are namespaced |

---

## 10. Limitations

- No incremental caching — recompiles all files every time
- No package manager integration (pip/npm/maven/cargo)
- No virtual environment or node_modules scanning
- No C preprocessor macro expansion (only `#include`)
- No cross-language linking
- No cycle-breaking (aborts on cycles)

---

## 11. Code Map

```
interpreter/project/
    types.py       ImportRef, ExportTable, ModuleUnit, LinkedProgram, CyclicImportError
    imports.py     extract_imports() — tree-sitter walkers for 15 languages + regex for COBOL
    resolver.py    ImportResolver protocol + 13 language resolvers + topological_sort()
    compiler.py    compile_module(), compile_project(), build_export_table()
    linker.py      link_modules() — strip, namespace, rebase, drop stubs, concatenate

interpreter/registry.py
    _is_func_label(), _is_class_label(), _is_end_class_label()

interpreter/api.py
    analyze_project(), run_project()

mcp_server/tools.py      handle_load_project()
mcp_server/server.py      load_project MCP tool registration
```

---

## 12. Test Coverage

179 tests across unit and integration:

| Test File | Tests | Covers |
|-----------|-------|--------|
| `test_types.py` | 26 | Data model: ImportRef, ExportTable, ModuleUnit, LinkedProgram |
| `test_export_table.py` | 10 | Export extraction from IR + symbol tables |
| `test_import_extraction.py` | 14 | Python import extraction (all forms) |
| `test_all_language_imports.py` | 33 | Import extraction across all 15 tree-sitter languages |
| `test_cobol_imports.py` | 11 | COBOL COPY/CALL extraction + resolver |
| `test_resolver.py` | 10 | Python resolver + protocol |
| `test_topo_sort.py` | 9 | Topological sort, cycles, edge cases |
| `test_linker.py` | 18 | Namespace, rebase, register helpers |
| `test_project_pipeline.py` | 14 | Full compile→link pipeline (Python, JS, Java, C) |
| `test_fixture_projects.py` | 5 | On-disk fixture projects |
| `test_all_languages_execution.py` | 20 | Multi-file execution for all 15 languages |
| `test_api_integration.py` | 3 | analyze_project(), run_project() |
| `test_mcp_tool.py` | 5 | MCP load_project tool |
