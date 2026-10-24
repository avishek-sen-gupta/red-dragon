# Linker & Multi-File Project Execution Design

**Date:** 2026-03-22 (revised 2026-03-23)  
**Status:** Implemented  
**Code:** `interpreter/project/`

---

## 1. Overview

RedDragon's multi-file project support extends the single-file pipeline to real-world codebases. Given a project directory, it compiles each source file for the selected language independently, resolves imports between modules, then a **linker** merges them into a single IR stream that looks exactly like what the single-file pipeline would produce if all source files were concatenated in dependency order.

**Design principle:** The linker's output is indistinguishable from single-file compilation. The VM, CFG builder and registry run completely unmodified.

**Supported:** All 15 tree-sitter frontends through `compile_directory`. COBOL links through `compile_cobol`: the main program plus a fixed list of other programs, which the caller finds — usually with `discover_callee_programs`, which follows `CALL 'LITERAL'` edges through ordered search directories (ADR-181). The three stages — parse, lower, link — each write a file (`.ast.json`, `.unit.json`, `.linked.json`) into a work directory and skip a program whose file already exists; `compile_cobol` returns the `LinkedProgram` read back from the linked file (ADR-183, §7.1). A build that lowers each program once uses `lower_program` and `link_units` instead: one image, no main, entered by program name (ADR-185, §7.3).

---

## 2. Pipeline

```
Project directory
    │
    ▼
Phase 1: Source discovery + import extraction
    │  scan by language extensions
    │  extract_imports() per file — tree-sitter AST or Lark grammar (COBOL)
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
    └──► execute_cfg()  (no changes)
```

### Entry points

| Function | Module | Purpose |
|----------|--------|---------|
| `compile_directory(directory, language)` | `compiler.py` | Full pipeline: scan → compile → link |

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
| COBOL | Lark LALR grammar: `COPY name`, `CALL 'name'` | `include`, `require` | No tree-sitter; light grammar (not plain regex) so keywords inside string literals don't produce false imports |

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

All files matching the selected language extensions are compiled; imports then define dependency edges among that discovered set. **Kahn's algorithm** produces a topological sort (dependencies before dependents). Cycles raise `CyclicImportError` with the full cycle path.

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

Python, TypeScript, and JavaScript emit import statements using the `IMPORT_MODULE` opcode:

```
%0 = IMPORT_MODULE "utils" resolved:"utils.py"
%1 = LOAD_FIELD add %0
DECL_VAR add %1
```

The linker buffers each `IMPORT_MODULE` together with any subsequent `LOAD_FIELD` instructions and `DECL_VAR` instructions whose value register traces back to the import — this is called an **import cluster**. A cluster is dropped when **all** declared names are already provided by a dependency module's exports (functions, classes, or variables); if any name is unresolved, the entire cluster is kept and passed to the VM, which handles it symbolically.

`CALL_FUNCTION "import"` / `CALL_FUNCTION "require"` (legacy pattern, still present in older frontend output) is handled by the same cluster logic for backward compatibility.

Other languages (Java, Go, Rust, C, C#, Kotlin, Scala, etc.) emit no import IR — their import statements are no-ops during lowering. Ruby/PHP/Lua emit `CALL_FUNCTION require/require_once` which produce harmless symbolic values that don't overwrite the dependency's declarations.

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
  %0 = IMPORT_MODULE "utils" resolved:"utils.py"
  %1 = LOAD_FIELD add %0
  DECL_VAR add %1
  %2 = CONST 10
  %3 = CONST 20
  %4 = CALL_FUNCTION add %2 %3
  STORE_VAR result %4
```

### Phase 3: Linking

1. **Strip** `entry:` labels from both modules
2. **Namespace** utils labels: `func_add_0` → `utils.func_add_0`, etc.
3. **Rebase** main registers by 6 (utils uses %0–%5)
4. **Drop** main's import cluster (`IMPORT_MODULE` + `LOAD_FIELD add` + `DECL_VAR add`) — `add` is in utils.py exports
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
  %8 = CONST 10
  %9 = CONST 20
  %10 = CALL_FUNCTION add %8 %9
  STORE_VAR result %10
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
    symbol_table: SymbolTable = field(default_factory=SymbolTable.empty)
    entry_label: CodeLabel = NO_LABEL              # un-namespaced entry function
    program: str = NO_PROGRAM                      # COBOL PROGRAM-ID, upper-cased

@dataclass
class LinkedProgram:
    modules: dict[Path, ModuleUnit]
    merged_ir: list[InstructionBase]
    merged_cfg: CFG
    merged_registry: FunctionRegistry
    language: Language
    import_graph: dict[Path, list[Path]]
    type_env_builder: TypeEnvironmentBuilder
    symbol_table: SymbolTable
    unresolved_imports: list[ImportRef] = field(default_factory=list)
    func_symbol_table: dict[CodeLabel, FuncRef] = field(default_factory=dict)
    class_symbol_table: dict[CodeLabel, ClassRef] = field(default_factory=dict)
    entry_func_label: CodeLabel = NO_LABEL
    # Explicit entry function label. When several modules are linked (e.g. a
    # COBOL main program plus the subprograms it CALLs), multiple func_*
    # labels exist and a bare func_* entry predicate would be ambiguous;
    # callers that know the entry module set this to dispatch execution
    # into it rather than into a linked-in callee.
    programs: dict[str, CodeLabel] = field(default_factory=dict)
    # Each linked COBOL program's name to its namespaced entry label.

    def entry_points(self, predicate=lambda _: True) -> list[FuncRef]:
        """Query func_symbol_table values matching predicate (default: all)."""
        ...
```

Note: `ExportTable` keys/values are typed domain objects (`FuncName`, `ClassName`,
`VarName`, `CodeLabel`, `Register`), not bare strings — see §4 above.

### 7.1 Persisted units and linked programs (COBOL)

COBOL compiles in three stages chained only through files (ADR-183), so a
program lowered once can be linked into any number of run units, by any later
process:

| Stage | Reads | Writes |
|---|---|---|
| `parse_stage` | source bytes | `<stem>-<digest>.ast.json` (bridge JSON) |
| lowering (`_Lowering.lower`) | the AST file | a `<stem>[.<PROGRAM-ID>]-<digest>.unit.json` (a `ModuleUnit`) per program |
| `link_units` | unit files | `image-<digest>.linked.json` (a `LinkedProgram`, no main) |

An AST file is a compilation unit, `{"programs": [...]}`, and may hold several
programs, batch or nested. Lowering makes a unit of each, in pre-order. Under
`compile_cobol` the first keeps the source's path and unit name, and each other
program's module path is `<stem>.<PROGRAM-ID>.cbl`, its unit
`<stem>.<PROGRAM-ID>-<digest>.unit.json`; lowering reads the AST file to learn
the program names even when every unit is already on disk.

`compile_cobol` runs the three over a work directory, links its units (callees
first, the main last) into `<main stem>-<digest>.linked.json` with
`entry_func_label` at the main program — the first top-level program of the main
source — and returns the `LinkedProgram` read back
from the linked file; no frontend or in-memory unit
crosses a stage. A stage skips a program whose output already exists, so a kept
work directory reuses every stage's output.
`compile_program` takes the same `work_dir` and passes it through, so a coprocessor
compile keeps and reuses its files the same way.

- **Names.** `<digest>` covers the source bytes and `LoweringSettings` (LP mode,
  extension strategy names, tolerant mode, copybook directories), so an edited
  source or different settings get new files. The linked file's digest covers
  the unit files it is built from. Nothing checks whether an existing file is
  still current beyond that: copybook contents and the lowering version are not
  in the digest, and a work directory is deleted to rebuild.
- **What a unit carries.** Everything link needs, so link reads nothing but unit
  files: the IR (a COBOL unit's file definitions and data layout among it, as
  `Data` directives), exports, imports, symbol table, `entry_label` and `program`, the PROGRAM-ID.
  A unit carries no start-up: link adds the COBOL run-unit allocation once, from the
  frontend's `start_up_ir()`, the same for every program.
- **What the linked file carries.** Every `LinkedProgram` field, the modules
  included, except `merged_cfg` and `merged_registry`: `LinkedCodec.read`
  rebuilds both from the merged IR with `build_cfg` and `build_registry`, which is
  how `link_modules` produced them.
- **Without a work directory** (the default `FRESH_WORK_DIR`), `compile_cobol` uses a new owner-only directory
  from `tempfile.mkdtemp()` and leaves it in place. Test suites point `tempfile`
  at a session-scoped pytest directory (`tests/conftest.py`).

### 7.2 The file formats

`IrCodec` (`interpreter/project/ir_codec.py`) encodes values as self-describing
JSON. JSON-native values stand for themselves; every other value is
`{"$": <kind>, "v": <payload>}`: `enum`, `decimal` (through `cobol_numeric`'s
exact `to_text`/`from_text`), `bytes`, `path`, `tuple`, `frozenset`, `dict` (a
list of pairs, so any value can be a name), `loc`, `none`, `unknown_type`, and
`dc` for a dataclass (`{"c": class name, "v": {field: value}}`, decoded by
constructing the class, null-object classes to their singletons). An unknown
kind or class raises `UnitFormatError`.

`UnitCodec` and `LinkedCodec` write `{"format": 8, "unit" | "linked": …}` and raise
`UnitFormatError` naming the file when it does not decode, a file of format 7
included. Format 4 added `ModuleUnit.diagnostics`, the warnings lowering raised, so a
reused unit reports them again (HLASM fills it); format 5 gave each one a typed
`kind`, format 6 moved every fact, a DC warning's included, into it, and format 7 added
`ModuleUnit.object_module` (HLASM's ESD, TXT, RLD and END; `NO_OBJECT_MODULE` elsewhere), and format 8
added `ModuleUnit.using`, a COBOL program's USING signature: one `UsingParameter(mode, length)`
per bound LINKAGE parameter, mode VALUE where PROCEDURE DIVISION USING says BY VALUE. The encoding is verbose
(red-dragon-rfwv).

### 7.3 One image, entered by program (COBOL)

A build that lowers each program once and links a chosen list keeps lowering and
linking apart (ADR-185):

- `lower_program(source, *, parser, specs, copybook_dirs, work_dir, tolerant) -> tuple[Path, ...]`
  (`coprocessor_compile.py`) runs every spec's `source_prepass`, makes each
  spec's strategy and dialect parser, parses the source and lowers every program
  in it, in pre-order, and returns their unit files. Each unit's path is
  `<PROGRAM-ID>.cbl`, so each program's labels are namespaced by its own name. It
  discovers nothing.
- `link_units(units, work_dir) -> LinkedProgram` (`cobol_compile.py`) links the
  unit files in the order given, after the COBOL run-unit allocation, which is
  the same for every program. No unit is main: `link_every_module` keeps every
  unit rather than pruning to what an entry reaches, and `entry_func_label` is
  `NO_LABEL`. `programs` maps each unit's `program` to its namespaced
  `entry_label`. Two units of one `program` (or one unit file listed twice) are
  refused before linking with `DuplicateProgramInImage`, naming both unit files.
- A run enters the image with `ProgramEntry(name)` (`run_linked`,
  `run_linked_resumable`, `run_linked_traced`); a name not in `programs` raises
  `ProgramNotInImage`, whose message is `program <name> is not in the image`.
  The name is matched exactly, case included.
  `VMState.declarations` are `declarations_of(linked, name)`, that program's
  `Data`. CALLs, literal or by identifier, resolve at run time through
  `__entry_<PROGRAM-ID>` against every program in the image.
- A suspended run's `ExecutionState.entered` is the entry label whose
  declarations it holds; `resume_linked` restores them from it.
- An `EntryPoint` run still takes the declarations of the program at
  `entry_func_label`, which `compile_cobol` sets to its main program.

### 7.4 HLASM units

`compile_hlasm(source, *, parser, options, work_dir, programs=())` (`hlasm_compile.py`) runs
the same three stages per assembly: `<stem>-<digest>.ast.json`, `<stem>-<digest>.unit.json`,
then one `image-<digest>.linked.json`. The digest covers the source, the SYSLIB directories
and their file contents, the bridge binary and the supplied system-variable values, but not
the assembly clock (`HlasmLoweringSettings`). `lower_hlasm_program(program)` stops at the unit
file, named after the `SourceFile`'s path; `link_hlasm_units(units, work_dir)` links unit
files. Each unit carries its `ObjectModule` ("Object module" in
`docs/frontend-design/hlasm.md`), and link is a binder over them: `bind_image` builds the
start-up module (machine state, layout, TXT, RLD, once) and a `__hlasm_job__` module of one
job-step function per SD or LD name, which `programs` maps each name to, plus one per unit
entering at its END. `entry_func_label` is the first unit's END step, so `compile_hlasm`
enters its main source. Link never reads an AST file. An SD or LD
name in two units raises `DuplicateProgramInImage`.

`link_hlasm_units` also takes COBOL unit files, making one mixed image. Its modules run in a
fixed order: the COBOL run-unit allocation (`__cobol_start_up__`, only when a COBOL unit is
present), the binder's start-up, the units in the order given, then the job-step module. The
image's language is HLASM; `programs` holds each PROGRAM-ID beside the SD and LD names, and
`entry_func_label` is the first HLASM unit's END step. One duplicate check runs over SD, LD and
PROGRAM-ID names and names both units. Unit diagnostics, and the binder's
unresolved-EXTRN warnings, are logged each time the image is used.

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
    types.py               ImportRef, ExportTable, ModuleUnit, LinkedProgram, CyclicImportError
    imports.py             extract_imports() — tree-sitter walkers for 15 languages + Lark grammar for COBOL
    resolver.py            ImportResolver protocol + 13 language resolvers + topological_sort()
    compiler.py            compile_module(), compile_directory(), build_export_table()
    linker.py              link_modules() — prune to what the entry reaches, then link_every_module():
                           strip, namespace, rebase, drop stubs, concatenate
    source_roots.py        SourceRootDiscovery — Maven-style src/main/java root discovery (Java multi-module)
    entry_point.py         EntryPoint — top_level()/function(predicate) execution-entry spec
    program_entry.py       ProgramEntry — enter a linked image at the program of a name
    program_not_in_image.py ProgramNotInImage — the image holds no program of that name
    duplicate_program_in_image.py DuplicateProgramInImage — two units of one program in an image
    cobol_compile.py        compile_cobol()/compile_cobol_module(), parse_stage(),
                            lower_cobol_program(), link_units() — COBOL in three stages
                            chained through files (AST, unit, linked); compile_cobol links
                            the main program with a fixed list of other programs
    coprocessor_compile.py  CoprocessorSpec, compile_program(), lower_program() — one source's
                            programs lowered with every spec's prepass, strategy and dialect parser
    lowering_settings.py    LoweringSettings — the settings a compiled file's name digests
    hlasm_compile.py        compile_hlasm(), lower_hlasm_program(), link_hlasm_units() — HLASM assemblies bound into one image
                            through the same three file stages
    hlasm_lowering_settings.py HlasmLoweringSettings — the SYSLIB directories an HLASM file's name digests
    ir_codec.py             IrCodec — self-describing JSON for IR values
    unit_codec.py           UnitCodec — ModuleUnit <-> .unit.json
    linked_codec.py         LinkedCodec — LinkedProgram <-> .linked.json (CFG, registry rebuilt)
    unit_format_error.py    UnitFormatError — a unit or linked file that does not decode
    cobol_discovery.py      discover_callee_programs() — the CALL 'LITERAL' walk through ordered
                            search directories that produces that list
    source_file.py          SourceFile — a path and its bytes, already read

interpreter/registry.py
    _is_func_label(), _is_class_label(), _is_end_class_label()

```

---

## 12. Test Coverage

Core tests, in `tests/unit/project/` and `tests/integration/project/` (counts are collected items, as of 2026-10-11):

| Test File | Tests | Covers |
|-----------|-------|--------|
| `test_types.py` | 35 | Data model: ImportRef, ExportTable, ModuleUnit, LinkedProgram |
| `test_export_table.py` | 10 | Export extraction from IR + symbol tables |
| `test_import_extraction.py` | 14 | Python import extraction (all forms) |
| `test_all_language_imports.py` | 34 | Import extraction across all 15 tree-sitter languages |
| `test_cobol_imports.py` | 31 | COBOL COPY/CALL extraction + resolver |
| `test_resolver.py` | 23 | Python resolver + protocol |
| `test_topo_sort.py` | 10 | Topological sort, cycles, edge cases |
| `test_linker.py` | 20 | Namespace, rebase, register helpers |
| `test_lower_and_link.py` | 6 | Lowering one program at a time, linking an image, entering it by program, resuming with the entered program's declarations |
| `test_project_pipeline.py` | 14 | Full compile→link pipeline (Python, JS, Java, C) |
| `test_fixture_projects.py` | 5 | On-disk fixture projects |
| `test_all_languages_execution.py` | 21 | Multi-file execution for all 15 languages |
