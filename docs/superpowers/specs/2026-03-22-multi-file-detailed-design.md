# Multi-File Project Support — Detailed Design

**Date:** 2026-03-22  
**Status:** Draft  
**Parent Spec:** [2026-03-22-multi-file-project-design.md](./2026-03-22-multi-file-project-design.md)  
**Epic:** red-dragon-iz14

---

## 1. Executive Summary

This document refines the multi-file project spec into a concrete, implementable
design that scales across all 15 deterministic frontends (Python, JavaScript,
TypeScript, Java, Go, Rust, C, C++, C#, Kotlin, Scala, Ruby, PHP, Lua, Pascal)
plus COBOL.

The key design principles:

1. **Frontend contract, not frontend knowledge** — the project layer never
   parses ASTs directly. Each frontend implements a `extract_imports()` method
   that returns uniform `ImportRef` objects. The project layer only orchestrates.

2. **Language-agnostic resolution protocol** — each language provides an
   `ImportResolver` strategy that maps an `ImportRef` to a file path (or
   reports it as external/unresolvable). This cleanly separates "what does the
   source say?" from "where is that file?"

3. **Compilation is the existing pipeline, verbatim** — `compile_module()` is
   just `frontend.lower() → build_cfg() → build_registry()` plus export
   extraction. Zero changes to IR, CFG, or registry internals.

4. **Linking is label-namespacing + reference rewriting** — done on the IR
   instruction stream before CFG construction, not after. This is cheaper,
   simpler, and lets `build_cfg()` and `build_registry()` work unmodified on
   the merged IR.

---

## 2. Architecture Overview

```
                        ┌──────────────────────────┐
                        │    analyze_project()      │
                        │    run_project()          │
                        └────────────┬─────────────┘
                                     │
                     ┌───────────────▼───────────────┐
                     │       Import Discovery        │
                     │  entry file → extract_imports  │
                     │  recursive BFS + cycle detect  │
                     └───────────────┬───────────────┘
                                     │
                     ┌───────────────▼───────────────┐
                     │      Import Resolution        │
                     │  ImportRef → file path         │
                     │  (per-language resolver)       │
                     └───────────────┬───────────────┘
                                     │ topo-sorted list[Path]
                     ┌───────────────▼───────────────┐
                     │     Per-Module Compilation     │
                     │  for each file:                │
                     │    lower() → IR                │
                     │    extract exports             │
                     │    store as ModuleUnit         │
                     └───────────────┬───────────────┘
                                     │ list[ModuleUnit]
                     ┌───────────────▼───────────────┐
                     │          Linker                │
                     │  Phase 1: build import tables  │
                     │  Phase 2: namespace IR labels  │
                     │  Phase 3: rewrite references   │
                     │  Phase 4: merge IR + build CFG │
                     └───────────────┬───────────────┘
                                     │ LinkedProgram
                          ┌──────────┴──────────┐
                          ▼                     ▼
                    execute_cfg()      analyze_interprocedural()
                    (no changes)       (no changes)
```

---

## 3. Data Model

### 3.1 Location

```
interpreter/project/
    __init__.py
    types.py          ← ImportRef, ExportTable, ModuleUnit, LinkedProgram
    imports.py         ← extract_imports() dispatch + base infrastructure
    resolver.py        ← ImportResolver protocol + per-language resolvers
    compiler.py        ← compile_module(), compile_project()
    linker.py          ← link_modules() — namespace + merge
```

### 3.2 Core Types

```python
# interpreter/project/types.py

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from interpreter.ir import IRInstruction
from interpreter.cfg_types import CFG
from interpreter.registry import FunctionRegistry
from interpreter.constants import Language


@dataclass(frozen=True)
class ImportRef:
    """A single import statement's resolved information.
    
    Represents what the source code *says*, not where the target *is*.
    Resolution (ImportRef → file path) is handled separately by ImportResolver.
    
    Fields:
        source_file:   Path of the file containing this import statement.
        module_path:   The module/package path as written in source.
                       Examples: "os.path", "./utils", "com.example.Utils",
                       "crate::utils", "<stdio.h>", "fmt".
        names:         Specific names imported. Empty tuple = import the module
                       itself. ("*",) = wildcard import.
                       Examples: ("join", "exists"), ("*",), ()
        is_relative:   Whether this is a relative import (Python's from . import,
                       JS/TS ./path, Rust crate::).
        relative_level: Number of parent levels for relative imports (Python's
                       from .. is 2, from . is 1, absolute is 0).
        is_system:     Whether this is a standard library / system import that
                       should NOT be resolved to a local file.
                       (C's <stdio.h>, Python's import os, Java's java.*)
        kind:          Import mechanism — helps the resolver choose strategy.
                       "import" | "include" | "use" | "require" | "mod" | "using"
        alias:         Optional alias name (Python's `as`, Kotlin's `as`,
                       C#'s `using X = Y`).
    """
    source_file: Path
    module_path: str
    names: tuple[str, ...] = ()
    is_relative: bool = False
    relative_level: int = 0
    is_system: bool = False
    kind: str = "import"
    alias: str | None = None


@dataclass(frozen=True)
class ExportTable:
    """A module's exported symbols.
    
    Maps exported names to their internal IR labels. Built during compilation
    by scanning the registry and top-level DECL_VAR instructions.
    
    Examples:
        functions:  {"helper": "func_helper_0", "main": "func_main_2"}
        classes:    {"User": "class_User_4"}
        variables:  {"PI": "%3"}  (top-level constants)
    """
    functions: dict[str, str] = field(default_factory=dict)   # name → func_label
    classes: dict[str, str] = field(default_factory=dict)      # name → class_label
    variables: dict[str, str] = field(default_factory=dict)    # name → register

    def lookup(self, name: str) -> str | None:
        """Look up an exported name across all symbol categories."""
        return (
            self.functions.get(name)
            or self.classes.get(name)
            or self.variables.get(name)
        )

    def all_names(self) -> set[str]:
        """All exported names."""
        return set(self.functions) | set(self.classes) | set(self.variables)


@dataclass(frozen=True)
class ModuleUnit:
    """A single compiled file — the atomic unit of multi-file compilation.
    
    Contains the raw (un-namespaced) IR and metadata. The linker operates
    on ModuleUnits to produce a LinkedProgram.
    """
    path: Path
    language: Language
    ir: tuple[IRInstruction, ...]    # immutable — frozen for safety
    exports: ExportTable
    imports: tuple[ImportRef, ...]    # imports discovered from this file


@dataclass
class LinkedProgram:
    """Merged multi-file program ready for execution or analysis.
    
    After linking, all labels are namespaced and cross-module references
    are resolved. The merged_ir/merged_cfg/merged_registry feed directly
    into execute_cfg() and analyze_interprocedural() with zero changes.
    """
    modules: dict[Path, ModuleUnit]
    merged_ir: list[IRInstruction]
    merged_cfg: CFG
    merged_registry: FunctionRegistry
    entry_module: Path
    import_graph: dict[Path, list[Path]]  # adjacency list: file → its imports
    
    # For diagnostics / debugging
    unresolved_imports: list[ImportRef] = field(default_factory=list)
```

### 3.3 Design Decisions vs. Original Spec

| Topic | Original Spec | This Design | Rationale |
|-------|--------------|-------------|-----------|
| ModuleUnit.cfg / registry | Included per-module CFG and registry | Removed — only raw IR stored | CFG and registry are rebuilt *once* from the merged, namespaced IR. Building them per-module and then trying to merge is more complex and error-prone than just merging IR first. |
| ExportTable | `dict[str, str]` (name → label) | Structured `ExportTable` with functions/classes/variables | Distinguishing symbol kinds is necessary for correct import rewriting (e.g., `from X import MyClass` needs class-aware label resolution). |
| ImportRef | `source_module`, `target_module`, `names` | Richer: adds `is_relative`, `is_system`, `kind`, `alias`, `relative_level` | Every language has different import semantics. These fields capture enough information for the language-specific resolver to do its job without re-parsing. |
| Linking phase | Operates on CFG blocks post-build | Operates on IR instructions pre-build | Rewriting IR operands is simpler than rewriting CFG block labels, successor lists, and registry entries simultaneously. Build CFG/registry once on the final merged IR. |
| IR tuple vs list | `list[IRInstruction]` | `tuple[IRInstruction, ...]` in ModuleUnit | ModuleUnits are frozen artifacts — immutability prevents accidental mutation before linking. |

---

## 4. Import Extraction — `extract_imports()`

### 4.1 Contract

Each frontend gains an `extract_imports()` method on `BaseFrontend`:

```python
# Added to interpreter/frontends/_base.py

def extract_imports(self, source: bytes, source_file: Path) -> list[ImportRef]:
    """Extract import statements from source without full lowering.
    
    Default implementation: parse with tree-sitter, walk root children,
    delegate to _extract_import_node() for each recognized import node type.
    Returns an empty list if the language doesn't override.
    
    This is intentionally separate from lower() because:
    1. Import discovery runs before compilation (we need the dependency graph first).
    2. It's much cheaper — only walks top-level statements, no IR emission.
    3. It can be called on files we haven't decided to compile yet.
    """
    parser = self._parser_factory.get_parser(self._language)
    tree = parser.parse(source)
    refs: list[ImportRef] = []
    for child in tree.root_node.children:
        extracted = self._extract_import_node(child, source, source_file)
        if extracted:
            refs.extend(extracted)
    return refs

def _extract_import_node(
    self, node, source: bytes, source_file: Path
) -> list[ImportRef] | None:
    """Override per language to handle language-specific import node types.
    
    Returns None or empty list if the node is not an import.
    """
    return None
```

### 4.2 Why on BaseFrontend (not standalone functions)?

The frontends already have `_parser_factory` and `_language` wired up. Import
extraction needs tree-sitter parsing. Putting it on the frontend avoids
duplicating parser setup code and keeps the contract in one place.

However, the implementation is in pure functions (same pattern as
`lower_python_if`, `lower_assignment`, etc.):

```python
# interpreter/frontends/python/imports.py  (new file per language)

def extract_python_imports(node, source: bytes, source_file: Path) -> list[ImportRef]:
    """Extract ImportRefs from a Python import_statement or import_from_statement."""
    ...
```

The frontend's `_extract_import_node()` override just dispatches:

```python
# In PythonFrontend
def _extract_import_node(self, node, source, source_file):
    if node.type == "import_statement":
        return extract_python_imports(node, source, source_file)
    if node.type == "import_from_statement":
        return extract_python_import_from(node, source, source_file)
    return None
```

### 4.3 Per-Language Import Node Mapping

Based on tree-sitter AST analysis of all 16 languages:

| Language | Import Node Types | Kind | Notes |
|----------|------------------|------|-------|
| **Python** | `import_statement`, `import_from_statement` | `import` | Relative imports via `relative_import` child with `import_prefix` dots |
| **JavaScript** | `import_statement` (ESM), `call_expression` where fn=`require` | `import`, `require` | ESM: `import_clause` + `from` + `string`. CJS: `require("path")` |
| **TypeScript** | Same as JavaScript | `import`, `require` | Identical AST structure via tree-sitter-typescript |
| **Java** | `import_declaration` | `import` | `scoped_identifier` chain. Static imports have `static` child |
| **Go** | `import_declaration` → `import_spec_list` → `import_spec` | `import` | String literal path. Package alias via `name` field |
| **Rust** | `use_declaration`, `mod_item` | `use`, `mod` | `scoped_identifier` with `crate`/`self`/`super`. `mod x;` declares submodule |
| **C** | `preproc_include` | `include` | `string_literal` = local, `system_lib_string` = system |
| **C++** | `preproc_include` | `include` | Same as C |
| **C#** | `using_directive` | `using` | `qualified_name` or `identifier`. Static and alias variants |
| **Kotlin** | `import_header` (inside `import_list`) | `import` | `identifier` with dot-separated `simple_identifier` children |
| **Scala** | `import_declaration` | `import` | Dot-separated `identifier` chain. `namespace_selectors` for `{A, B}`. `_` for wildcard |
| **Ruby** | `call` where fn=`require` or `require_relative` | `require` | String argument. `require_relative` sets `is_relative=True` |
| **PHP** | `namespace_use_declaration`, `require_expression`, `require_once_expression`, `include_expression`, `include_once_expression` | `use`, `require`, `include` | `namespace_use_clause` for use. String arg for require/include |
| **Lua** | `function_call` where fn=`require` | `require` | String argument to `require()` |
| **Pascal** | `declUses` → `moduleName` | `using` | Comma-separated unit names |
| **COBOL** | `COPY` statement, `CALL` statement | `include`, `require` | COPY = copybook inclusion. CALL = runtime linkage |

### 4.4 System Import Detection

Each language has conventions for distinguishing local vs. system imports:

| Language | System Import Heuristic |
|----------|------------------------|
| Python | Module name has no dots AND not relative (`import os`, `import sys`) — resolved by checking if file exists locally, fallback to system |
| JavaScript/TS | Path doesn't start with `.` or `/` (`import React from "react"`) |
| Java | Starts with `java.`, `javax.`, `sun.`, or any prefix not matching project package |
| Go | Contains no `.` in path (`"fmt"`, `"os"`) vs. `"github.com/user/pkg"` |
| Rust | Starts with `std::`, `core::`, `alloc::` |
| C/C++ | `system_lib_string` node type (angle brackets `<stdio.h>`) vs `string_literal` (quotes `"header.h"`) |
| C# | Starts with `System.`, `Microsoft.` |
| Kotlin/Scala | Starts with `java.`, `javax.`, `kotlin.`, `scala.` |
| Ruby | No `.` or `/` in path (`require "json"` vs `require_relative "./utils"`) |
| PHP | Namespace doesn't match project namespace prefix |
| Lua | No `.` or `/` in path |
| Pascal | Standard unit names: `SysUtils`, `Classes`, `System`, etc. |

**Implementation**: Each language's `imports.py` applies its own heuristic to set
`is_system`. The resolver skips system imports entirely (they're marked as
unresolvable and the linker treats them as external — the VM already handles
`CALL_FUNCTION "import"` symbolically).

---

## 5. Import Resolution — `ImportResolver`

### 5.1 Protocol

```python
# interpreter/project/resolver.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from interpreter.project.types import ImportRef


@dataclass(frozen=True)
class ResolvedImport:
    """Result of resolving an ImportRef to a file path."""
    ref: ImportRef
    resolved_path: Path | None  # None = unresolvable (external/system)
    is_external: bool = False   # True for system/third-party imports


class ImportResolver(ABC):
    """Language-specific strategy for resolving ImportRef → file path."""
    
    @abstractmethod
    def resolve(self, ref: ImportRef, project_root: Path) -> ResolvedImport:
        """Resolve a single import reference to a file path.
        
        Args:
            ref: The import reference to resolve.
            project_root: Root directory of the project.
            
        Returns:
            ResolvedImport with resolved_path (or None if external).
        """
        ...
```

### 5.2 Per-Language Resolver Implementations

Each resolver is a small, focused class. The common pattern:

1. Skip system imports → `ResolvedImport(ref, None, is_external=True)`
2. Compute candidate file paths from the module_path
3. Check which candidate exists on disk
4. Return the first match, or `ResolvedImport(ref, None)` if none found

**PythonImportResolver:**
```
"os.path" → skip (system)
"utils" → try: {source_dir}/utils.py, {source_dir}/utils/__init__.py
"models.user" → try: {source_dir}/models/user.py, {source_dir}/models/user/__init__.py
". utils" (relative, level=1) → try: {source_dir}/utils.py
".. models" (relative, level=2) → try: {source_dir}/../models/__init__.py
```

**JavaScriptImportResolver:**
```
"react" → skip (no-dot, no-slash = npm package)
"./utils" → try: {source_dir}/utils.js, {source_dir}/utils.ts,
             {source_dir}/utils/index.js, {source_dir}/utils/index.ts
"../models/user" → try: {parent_dir}/models/user.js, ...
```

**JavaImportResolver:**
```
"java.util.List" → skip (java.* = system)
"com.example.Utils" → try: {source_root}/com/example/Utils.java
```

**GoImportResolver:**
```
"fmt" → skip (no dot = stdlib)
"github.com/user/pkg" → skip (external, no local resolution without go.mod)
"./internal/utils" → try: {source_dir}/internal/utils/utils.go (convention)
```

**CIncludeResolver (C/C++):**
```
<stdio.h> → skip (system, already marked by is_system)
"header.h" → try: {source_dir}/header.h, {project_root}/header.h,
              {project_root}/include/header.h
"subdir/header.h" → try: {source_dir}/subdir/header.h, {project_root}/subdir/header.h
```

**RustImportResolver:**
```
std::collections → skip (std:: = system)
crate::utils → try: {crate_root}/src/utils.rs, {crate_root}/src/utils/mod.rs
self::helpers → try: {source_dir}/helpers.rs, {source_dir}/helpers/mod.rs
mod helpers → try: {source_dir}/helpers.rs, {source_dir}/helpers/mod.rs
```

**Resolver Registry:**
```python
# interpreter/project/resolver.py

_RESOLVERS: dict[Language, type[ImportResolver]] = {
    Language.PYTHON: PythonImportResolver,
    Language.JAVASCRIPT: JavaScriptImportResolver,
    Language.TYPESCRIPT: JavaScriptImportResolver,  # same resolution rules
    Language.JAVA: JavaImportResolver,
    Language.GO: GoImportResolver,
    Language.C: CIncludeResolver,
    Language.CPP: CIncludeResolver,  # same as C
    Language.CSHARP: CSharpImportResolver,
    Language.RUST: RustImportResolver,
    Language.KOTLIN: JvmImportResolver,  # Kotlin and Scala share JVM conventions
    Language.SCALA: JvmImportResolver,
    Language.RUBY: RubyImportResolver,
    Language.PHP: PhpImportResolver,
    Language.LUA: LuaImportResolver,
    Language.PASCAL: PascalImportResolver,
}

def get_resolver(language: Language) -> ImportResolver:
    cls = _RESOLVERS.get(language)
    if cls is None:
        return NullImportResolver()  # returns external for everything
    return cls()
```

---

## 6. Dependency Graph Construction

### 6.1 Algorithm

```python
# interpreter/project/resolver.py

def resolve_project_imports(
    entry_file: Path,
    language: Language,
    project_root: Path | None = None,
) -> tuple[list[Path], dict[Path, list[Path]], list[ImportRef]]:
    """Discover all files reachable from entry_file via imports.
    
    Returns:
        files_topo: Files in topological order (dependencies first).
        import_graph: Adjacency list (file → list of files it imports).
        unresolved: ImportRefs that couldn't be resolved to local files.
    """
    if project_root is None:
        project_root = _infer_project_root(entry_file)
    
    resolver = get_resolver(language)
    frontend = get_frontend(language)
    
    # BFS discovery
    discovered: dict[Path, list[ImportRef]] = {}  # file → its ImportRefs
    import_graph: dict[Path, list[Path]] = {}
    unresolved: list[ImportRef] = []
    queue: list[Path] = [entry_file.resolve()]
    
    while queue:
        file_path = queue.pop(0)
        if file_path in discovered:
            continue
        
        source = file_path.read_bytes()
        refs = frontend.extract_imports(source, file_path)
        discovered[file_path] = refs
        import_graph[file_path] = []
        
        for ref in refs:
            resolved = resolver.resolve(ref, project_root)
            if resolved.resolved_path is not None:
                target = resolved.resolved_path.resolve()
                import_graph[file_path].append(target)
                if target not in discovered:
                    queue.append(target)
            elif not resolved.is_external:
                unresolved.append(ref)
    
    # Cycle detection + topological sort
    files_topo = _topological_sort(import_graph)  # raises on cycle
    
    return files_topo, import_graph, unresolved
```

### 6.2 Cycle Detection

Import cycles are common in real codebases (Python mutual imports, C header
cycles with include guards, Java circular package dependencies).

**Strategy**: detect cycles during topological sort. For the initial
implementation, **report the cycle and abort**. This is correct behavior —
the linker needs a DAG to know compilation order. Cycle-breaking (via lazy
imports, forward declarations, or two-pass linking) is a future optimization.

```python
def _topological_sort(graph: dict[Path, list[Path]]) -> list[Path]:
    """Kahn's algorithm. Raises CyclicImportError on cycles."""
    in_degree = {node: 0 for node in graph}
    for node, deps in graph.items():
        for dep in deps:
            if dep not in in_degree:
                in_degree[dep] = 0
            in_degree[dep] += 1
    
    queue = deque(node for node, deg in in_degree.items() if deg == 0)
    result: list[Path] = []
    
    while queue:
        node = queue.popleft()
        result.append(node)
        for dep in graph.get(node, []):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)
    
    if len(result) != len(in_degree):
        # Find the cycle for error reporting
        remaining = set(in_degree) - set(result)
        cycle = _find_cycle(graph, remaining)
        raise CyclicImportError(cycle)
    
    return result
```

### 6.3 Project Root Inference

For the initial implementation, project root is inferred by walking up from
the entry file looking for common markers:

```python
_PROJECT_ROOT_MARKERS = {
    "pyproject.toml", "setup.py", "setup.cfg",    # Python
    "package.json",                                 # JS/TS
    "pom.xml", "build.gradle", "build.gradle.kts", # Java/Kotlin
    "go.mod",                                       # Go
    "Cargo.toml",                                   # Rust
    "*.sln", "*.csproj",                            # C#
    "Makefile", "CMakeLists.txt",                   # C/C++
    "composer.json",                                # PHP
    ".git",                                         # universal fallback
}
```

If no marker is found, the entry file's directory is the project root.

---

## 7. Per-Module Compilation

### 7.1 compile_module()

```python
# interpreter/project/compiler.py

def compile_module(
    file_path: Path,
    language: Language,
    source: bytes | None = None,
) -> ModuleUnit:
    """Compile a single file into a ModuleUnit.
    
    This is the existing single-file pipeline (lower → IR) plus export
    extraction. No CFG or registry is built here — that happens once
    after linking on the merged IR.
    """
    if source is None:
        source = file_path.read_bytes()
    
    frontend = get_frontend(language)
    ir = frontend.lower(source)
    
    # Extract exports from the frontend's symbol tables
    exports = _build_export_table(
        ir,
        frontend.func_symbol_table,
        frontend.class_symbol_table,
    )
    
    # Extract imports (we already have them from discovery, but compile_module
    # should be self-contained for single-file use too)
    imports = tuple(frontend.extract_imports(source, file_path))
    
    return ModuleUnit(
        path=file_path,
        language=language,
        ir=tuple(ir),
        exports=exports,
        imports=imports,
    )
```

### 7.2 Export Table Construction

```python
def _build_export_table(
    ir: list[IRInstruction],
    func_symbol_table: dict[str, FuncRef],
    class_symbol_table: dict[str, ClassRef],
) -> ExportTable:
    """Build export table from frontend symbol tables.
    
    Functions and classes are exported by their names as discovered during
    lowering. Top-level variables (DECL_VAR at module scope) are also
    exported.
    """
    functions = {ref.name: ref.label for ref in func_symbol_table.values()}
    classes = {ref.name: ref.label for ref in class_symbol_table.values()}
    
    # Top-level variables: DECL_VAR instructions before any func/class label
    variables: dict[str, str] = {}
    in_scope = True  # True while we're at module top-level
    for inst in ir:
        if inst.opcode == Opcode.LABEL and inst.label:
            if inst.label.startswith(FUNC_LABEL_PREFIX) or \
               inst.label.startswith(CLASS_LABEL_PREFIX):
                in_scope = False
            elif inst.label.startswith("end_"):
                in_scope = True
        if in_scope and inst.opcode == Opcode.DECL_VAR and len(inst.operands) >= 2:
            var_name = str(inst.operands[0])
            # Skip function/class declarations (they're already in the tables)
            if var_name not in functions and var_name not in classes:
                variables[var_name] = str(inst.operands[1])
    
    return ExportTable(functions=functions, classes=classes, variables=variables)
```

### 7.3 Why No Per-Module CFG?

The original spec builds CFG + registry per module, then merges them. This
is problematic:

1. **Label collisions**: Two modules can both have `func_helper_0`. You'd need
   to rename labels in CFG blocks, successor/predecessor lists, and registry
   entries — a fragile multi-site rewrite.

2. **Registry merge complexity**: Merging two `FunctionRegistry` objects with
   overlapping class names, method tables, and func_refs requires careful
   conflict resolution.

3. **Wasted work**: Per-module CFGs are never used — only the merged CFG
   matters for execution and analysis.

**Instead**: store raw IR per module. The linker namespaces the IR, concatenates
it, and builds CFG + registry exactly once on the final merged IR. This means
`build_cfg()` and `build_registry()` work completely unmodified.

---

## 8. Linker

### 8.1 Overview

The linker transforms a set of `ModuleUnit`s into a single `LinkedProgram`.
It operates on IR instructions (not CFGs), making the implementation
straightforward string manipulation.

### 8.2 Label Namespacing

Each module's IR labels get a prefix derived from its file path relative to
the project root:

```
/project/src/utils.py  (root=/project/) → prefix = "src.utils"
/project/main.py       (root=/project/) → prefix = "main"
/project/pkg/sub/mod.go (root=/project/) → prefix = "pkg.sub.mod"
```

The separator is `.` (not `__` as in the original spec) because:
- `__` conflicts with Python dunder names
- `.` is already used in qualified names across most languages
- It's more readable in debug output: `src.utils.func_helper_0` vs
  `src__utils__func_helper_0`

**Rules:**
1. Strip the project root prefix
2. Strip the file extension
3. Replace path separators (`/`) with `.`
4. The entry module's top-level code is **not** prefixed (it IS the program entry)

```python
def _module_prefix(file_path: Path, project_root: Path) -> str:
    """Compute the namespace prefix for a module."""
    relative = file_path.relative_to(project_root)
    stem = str(relative.with_suffix(""))
    return stem.replace("/", ".").replace("\\", ".")
```

### 8.3 IR Rewriting

The linker rewrites each module's IR instructions in three passes:

**Pass 1 — Namespace all labels:**
```
LABEL func_helper_0          →  LABEL src.utils.func_helper_0
BRANCH end_helper_1          →  BRANCH src.utils.end_helper_1
BRANCH_IF %0 if_true_2,if_false_3 → BRANCH_IF %0 src.utils.if_true_2,src.utils.if_false_3
```

**Pass 2 — Namespace all registers** (to avoid collisions between modules):
```
%0 = CONST "hello"           →  %src.utils.0 = CONST "hello"
STORE_VAR x %0               →  STORE_VAR x %src.utils.0
```

Wait — register namespacing is **not needed** if we process modules
sequentially and the register counter is reset per module. The linker
concatenates IR sequences; each module's registers are already unique
*within* that module. The only collision risk is between modules.

**Revised approach**: Instead of namespacing registers (which would break
thousands of operand references), we **rebase** register numbers:

```python
def _rebase_registers(ir: list[IRInstruction], offset: int) -> list[IRInstruction]:
    """Shift all %N registers by offset to avoid inter-module collisions."""
    ...
```

If module A uses %0..%47 and module B uses %0..%31, we rebase B's registers
to %48..%79. This is a simple integer offset, not a string rewrite.

**Pass 3 — Rewrite cross-module references:**

For each module's import table, replace:
- `CALL_FUNCTION "helper"` → `CALL_FUNCTION "src.utils.helper"` (if `helper` is
  imported from `src/utils.py`)
- `LOAD_VAR "helper"` → `LOAD_VAR "src.utils.helper"`  (same)
- `CONST "func_helper_0"` → `CONST "src.utils.func_helper_0"` (func ref in
  symbol tables)

### 8.4 Linking Algorithm

```python
# interpreter/project/linker.py

def link_modules(
    modules: dict[Path, ModuleUnit],
    import_graph: dict[Path, list[Path]],
    entry_module: Path,
    project_root: Path,
    topo_order: list[Path],
) -> LinkedProgram:
    """Link compiled modules into a single program.
    
    Steps:
    1. Build import tables (what each module imports from where)
    2. Compute namespace prefixes
    3. For each module in topo order:
       a. Namespace its labels
       b. Rebase its registers
       c. Rewrite imported references to their namespaced targets
    4. Concatenate all namespaced IR (entry module LAST — its top-level
       code is the program entry)
    5. Build CFG + registry on merged IR
    """
    # Phase 1: build import tables
    import_tables = _build_import_tables(modules, import_graph)
    
    # Phase 2: namespace + rewrite
    prefixes = {
        path: _module_prefix(path, project_root) for path in modules
    }
    
    all_ir: list[IRInstruction] = []
    reg_offset = 0
    
    # Non-entry modules first (their functions/classes are defined before use)
    for file_path in topo_order:
        if file_path == entry_module:
            continue  # entry module goes last
        
        module = modules[file_path]
        prefix = prefixes[file_path]
        import_table = import_tables.get(file_path, {})
        
        namespaced_ir = _namespace_module_ir(
            module.ir, prefix, reg_offset, import_table, prefixes, modules
        )
        all_ir.extend(namespaced_ir)
        reg_offset += _max_register(module.ir) + 1
    
    # Entry module last — its entry label becomes the program entry
    entry = modules[entry_module]
    entry_prefix = prefixes[entry_module]
    entry_import_table = import_tables.get(entry_module, {})
    entry_ir = _namespace_module_ir(
        entry.ir, entry_prefix, reg_offset, entry_import_table, prefixes, modules
    )
    all_ir.extend(entry_ir)
    
    # Phase 3: build merged CFG + registry
    merged_cfg = build_cfg(all_ir)
    
    # We need a frontend for symbol tables — reconstruct from modules
    merged_func_symbols, merged_class_symbols = _merge_symbol_tables(
        modules, prefixes
    )
    merged_registry = build_registry(
        all_ir, merged_cfg,
        func_symbol_table=merged_func_symbols,
        class_symbol_table=merged_class_symbols,
    )
    
    unresolved = []
    for mod in modules.values():
        for ref in mod.imports:
            if ref.is_system:
                continue
            resolved = any(
                ref.module_path in str(dep) for dep in import_graph.get(mod.path, [])
            )
            if not resolved:
                unresolved.append(ref)
    
    return LinkedProgram(
        modules=modules,
        merged_ir=all_ir,
        merged_cfg=merged_cfg,
        merged_registry=merged_registry,
        entry_module=entry_module,
        import_graph=import_graph,
        unresolved_imports=unresolved,
    )
```

### 8.5 Import Table Construction

```python
def _build_import_tables(
    modules: dict[Path, ModuleUnit],
    import_graph: dict[Path, list[Path]],
) -> dict[Path, dict[str, tuple[Path, str]]]:
    """Build per-module import tables.
    
    Returns:
        { source_file: { local_name: (target_file, target_export_name) } }
    
    Example:
        main.py has `from utils import helper`
        → { main.py: { "helper": (utils.py, "helper") } }
    """
    tables: dict[Path, dict[str, tuple[Path, str]]] = {}
    
    for source_path, module in modules.items():
        table: dict[str, tuple[Path, str]] = {}
        
        for ref in module.imports:
            if ref.is_system:
                continue
            
            # Find which resolved file this import points to
            target_path = _find_target_file(ref, import_graph.get(source_path, []))
            if target_path is None or target_path not in modules:
                continue
            
            target_module = modules[target_path]
            
            if ref.names:
                for name in ref.names:
                    if name == "*":
                        # Wildcard: import all exports
                        for export_name in target_module.exports.all_names():
                            table[export_name] = (target_path, export_name)
                    else:
                        actual_name = ref.alias if ref.alias else name
                        table[actual_name] = (target_path, name)
            else:
                # Module-level import (import utils → utils.helper)
                # We don't rewrite individual names here; the VM handles
                # attribute access on the module object. But we do need to
                # make the module's namespace available.
                module_name = ref.alias or ref.module_path.split(".")[-1]
                table[module_name] = (target_path, "__module__")
        
        tables[source_path] = table
    
    return tables
```

### 8.6 Entry Point Handling

The entry module's `entry:` label is the program's entry point. Since we
namespace everything, the entry module's entry label becomes e.g.
`main.entry`. The `LinkedProgram.merged_cfg.entry` will be set to this label
by `build_cfg()` (the first LABEL in the merged IR is the entry).

**Ordering matters**: the entry module's IR is placed last in the concatenated
sequence, so its `entry:` label is the first label the VM encounters. Wait —
that's wrong. If it's last, it's not the first.

**Correction**: The entry module's IR goes **first** in the merged sequence.
Non-entry modules' top-level code (which is just function/class definitions
with BRANCH-over patterns) follows. This way `build_cfg()` sees the entry
module's `entry:` label first and sets it as the CFG entry.

Actually, we need to be more careful. Each module's IR starts with
`LABEL "entry"`. After namespacing, they become `LABEL "src.utils.entry"`,
`LABEL "main.entry"`, etc. The entry module's namespaced entry label should
be what `build_cfg()` picks as the program entry.

**Revised approach**: Place the entry module's IR first. Its namespaced `entry`
label (`main.entry`) becomes the first label in the merged IR, and `build_cfg()`
will set that as `cfg.entry`. Non-entry modules follow in dependency order.

---

## 9. Variable Resolution for Module-Level Imports

The trickiest part of linking is handling `import utils` (module-level import
without `from`) correctly. When the user writes:

```python
# main.py
import utils
x = utils.helper(42)
```

The IR emitted is:
```
%0 = call_function "import" "utils"
store_var "utils" %0
%1 = load_var "utils"
%2 = call_method %1 "helper" ...
```

The linker does NOT need to rewrite `load_var "utils"` — the VM's method
dispatch on the module object is sufficient. However, for `from utils import
helper` the IR is:

```
%0 = call_function "import" "from utils import helper"
store_var "helper" %0
...
%1 = call_function "helper" ...
```

Here, `call_function "helper"` must be rewritten to
`call_function "src.utils.helper"` (the namespaced function label).

**Import rewriting rule**: For `from X import Y` style imports (where `names`
is non-empty in the ImportRef), rewrite `CALL_FUNCTION "Y"` and
`LOAD_VAR "Y"` in the importing module to use the namespaced target.

For `import X` style imports (where `names` is empty), no rewriting is
needed — the existing `call_function "import"` + `call_method` pattern works.

---

## 10. API Integration

### 10.1 New API Functions

```python
# interpreter/api.py (additions)

def analyze_project(
    entry_file: str | Path,
    language: str | Language,
    project_root: str | Path | None = None,
) -> InterproceduralResult:
    """Multi-file analysis: discover → compile → link → analyze.
    
    Returns the same InterproceduralResult as single-file analysis,
    but with cross-module call graphs and dataflow.
    """
    from interpreter.project.compiler import compile_project
    from interpreter.interprocedural.analyze import analyze_interprocedural
    
    linked = compile_project(Path(entry_file), Language(language), 
                             project_root=Path(project_root) if project_root else None)
    return analyze_interprocedural(linked.merged_cfg, linked.merged_registry)


def run_project(
    entry_file: str | Path,
    language: str | Language,
    project_root: str | Path | None = None,
    max_steps: int = 500,
    verbose: bool = False,
) -> VMState:
    """Multi-file execution: discover → compile → link → execute.
    
    Returns the same VMState as single-file run().
    """
    from interpreter.project.compiler import compile_project
    
    linked = compile_project(Path(entry_file), Language(language),
                             project_root=Path(project_root) if project_root else None)
    
    config = VMConfig(max_steps=max_steps, verbose=verbose)
    vm, stats = execute_cfg(linked.merged_cfg, linked.merged_cfg.entry,
                           linked.merged_registry, config)
    return vm
```

### 10.2 MCP Integration

```python
# mcp_server/tools.py (additions)

def handle_load_project(entry_file: str, language: str) -> dict:
    """MCP tool: load and analyze a multi-file project."""
    from interpreter.project.compiler import compile_project
    
    linked = compile_project(Path(entry_file), Language(language))
    
    # Store in session for subsequent queries
    session = get_session()
    session.linked_program = linked
    
    return {
        "modules": len(linked.modules),
        "entry": str(linked.entry_module),
        "import_graph": {
            str(k): [str(v) for v in vs]
            for k, vs in linked.import_graph.items()
        },
        "unresolved_imports": len(linked.unresolved_imports),
        "merged_cfg_blocks": len(linked.merged_cfg.blocks),
        "merged_functions": len(linked.merged_registry.func_params),
        "merged_classes": len(linked.merged_registry.classes),
    }
```

---

## 11. Implementation Plan — Phased Rollout

### Phase 0 — Foundation (Issues: red-dragon-3wuj, red-dragon-gl1q)

**Goal**: Data model + base infrastructure. No actual import extraction yet.

1. Create `interpreter/project/` package with `types.py`
2. Implement `ImportRef`, `ExportTable`, `ModuleUnit`, `LinkedProgram`
3. Add `extract_imports()` to `BaseFrontend` (returns empty list)
4. Add `_extract_import_node()` hook to `BaseFrontend`
5. Add `ImportResolver` protocol to `resolver.py`
6. Add `NullImportResolver` (marks everything external)
7. Tests: data model construction, ExportTable.lookup()

### Phase 1 — Python End-to-End (Issues: red-dragon-881h, red-dragon-g9xm, red-dragon-co5y, red-dragon-jpug)

**Goal**: Full multi-file pipeline working for Python.

1. `PythonFrontend._extract_import_node()` — handles `import_statement`,
   `import_from_statement`
2. `PythonImportResolver` — resolves relative and absolute local imports
3. `resolve_project_imports()` — BFS discovery + topo sort
4. `compile_module()` + `_build_export_table()`
5. `link_modules()` — full linker with label namespacing, register rebasing,
   import rewriting
6. `compile_project()` — orchestrator: discover → compile → link
7. Integration tests with real multi-file Python projects

### Phase 2 — JavaScript/TypeScript (Issue: red-dragon-p2in)

1. `JavaScriptFrontend._extract_import_node()` — ESM imports + CJS require
2. `JavaScriptImportResolver` — ./relative, extension resolution (.js/.ts/.jsx/.tsx/index)
3. TypeScript shares the same implementation (same AST structure)
4. Tests with React-style multi-file projects

### Phase 3 — Java (Issue: red-dragon-xycm)

1. `JavaFrontend._extract_import_node()` — `import_declaration`
2. `JavaImportResolver` — `com.example.Utils` → `com/example/Utils.java`
3. Tests with Maven-style project layout

### Phase 4 — C/C++ (Issue: red-dragon-p373)

1. `CFrontend._extract_import_node()` — `preproc_include`
2. `CIncludeResolver` — quoted includes with directory search
3. Skip system includes (angle brackets)
4. `CppFrontend` shares the same implementation

### Phase 5 — Remaining Languages (Issues: red-dragon-6eoq, red-dragon-v8wl, red-dragon-px9t, red-dragon-btbr)

Batch implementation of import extraction for:
- Go, Rust, C#, Kotlin, Scala, Ruby, PHP, Lua, Pascal

Each language follows the same pattern:
1. Add `imports.py` with extraction functions
2. Add resolver class
3. Override `_extract_import_node()` in the frontend
4. Add tests

### Phase 6 — API + MCP (Issue: red-dragon-xhda)

1. Add `analyze_project()` and `run_project()` to `api.py`
2. Add `load_project` MCP tool
3. Update session management for multi-file state
4. End-to-end integration tests

---

## 12. Testing Strategy

### Unit Tests

```
tests/unit/project/
    test_types.py              ← ImportRef, ExportTable, ModuleUnit construction
    test_export_table.py       ← export extraction from IR + symbol tables
    test_linker.py             ← label namespacing, register rebasing, reference rewriting
    test_resolver_python.py    ← PythonImportResolver path resolution
    test_resolver_js.py        ← JavaScriptImportResolver
    test_resolver_java.py      ← JavaImportResolver
    test_resolver_c.py         ← CIncludeResolver
    ...
    test_topo_sort.py          ← topological sort + cycle detection
    test_import_extraction.py  ← per-language extract_imports()
```

### Integration Tests

```
tests/integration/project/
    test_python_project.py     ← multi-file Python: import → compile → link → execute
    test_js_project.py         ← multi-file JS/TS project
    test_java_project.py       ← multi-file Java project
    test_cross_module_calls.py ← verify cross-module function calls work in VM
    test_cross_module_classes.py ← verify cross-module class instantiation
    test_interprocedural.py    ← verify cross-module call graphs + dataflow
```

### Test Fixtures

```
tests/fixtures/projects/
    python_basic/
        main.py                ← from utils import helper; helper(42)
        utils.py               ← def helper(x): return x + 1
    python_relative/
        src/
            main.py            ← from .utils import helper
            utils.py
    python_package/
        main.py
        models/
            __init__.py
            user.py
    js_esm/
        main.js                ← import { add } from './math.js'
        math.js
    java_simple/
        Main.java
        com/example/Utils.java
```

---

## 13. Error Handling

| Error | Behavior |
|-------|----------|
| Cyclic import | `CyclicImportError` with the cycle path printed |
| File not found | Import marked as unresolved; compilation continues without it |
| Parse error in imported file | `ParseError` with file path context |
| Export not found | `CALL_FUNCTION "import" "from X import Y"` left as-is (VM handles symbolically) |
| Duplicate export names across modules | Namespacing prevents collisions — each module's exports are prefixed |

---

## 14. Performance Considerations

**For v1**: No optimizations. Recompile everything every time.

**Future optimizations** (not in scope):
- **Content-hash caching**: Hash source bytes → skip recompile if unchanged
- **Parallel compilation**: Modules at the same topo level can compile in parallel
- **Lazy resolution**: Only compile transitively-imported modules, not the whole project
- **Incremental linking**: Only re-link modules that changed

**Expected performance** for a ~20 file project:
- Import discovery: ~50ms (parse 20 files, walk top-level only)
- Compilation: ~200ms (lower 20 files)
- Linking: ~10ms (IR rewriting is fast string manipulation)
- Total: ~260ms — well under the interactive threshold

---

## 15. What This Does NOT Include

Carried forward from the parent spec, confirmed:

- No incremental caching
- No package manager integration (pip/npm/maven/cargo)
- No virtual env or node_modules scanning
- No macro expansion (C preprocessor beyond `#include`)
- No cross-language linking
- No IDE integration (LSP) — MCP only
- No cycle-breaking strategies (abort on cycles)

---

## 16. Open Questions

1. **Should the entry module's top-level code be namespaced?** Current design
   says yes (for consistency). But this means `build_cfg()` entry becomes
   `main.entry` instead of `entry`. We'd need to ensure `execute_cfg()` finds
   the right entry — which it will, since `build_cfg()` sets `.entry` to the
   first block.

2. **Module-level imports with attribute access**: When user writes
   `import utils; utils.helper()`, the VM's `CALL_METHOD` dispatch needs to
   resolve `helper` on the module object. Currently, `call_function "import"`
   returns a symbolic value. For multi-file, should it return a module-like
   object with the target module's exports as fields?

   **Proposed answer**: Yes, for multi-file mode. The linker could emit a
   `NEW_OBJECT` + `STORE_FIELD` sequence for each export, creating a
   namespace object. But this is complex — defer to Phase 2. For v1, only
   `from X import Y` is fully supported.

3. **TypeScript path aliases** (`@/components/Button`): These require reading
   `tsconfig.json`. Defer to a future enhancement.
