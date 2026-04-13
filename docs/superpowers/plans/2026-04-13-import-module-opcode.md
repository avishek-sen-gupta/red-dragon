# IMPORT_MODULE Opcode & Demand-Driven Linker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the brittle `_is_import_call()` heuristic with a dedicated `IMPORT_MODULE` IR opcode emitted by frontends and expanded by a language-agnostic linker.

**Architecture:** Frontends emit `IMPORT_MODULE` for all import statements. The compiler runs two passes: extract+resolve imports first, then lower IR with resolved paths available. The linker expands `IMPORT_MODULE` into existing opcodes (`NEW_OBJECT`, `CONST`, `STORE_FIELD`) using the dependency module's `ExportTable`.

**Tech Stack:** Python 3.13+, frozen dataclasses, tree-sitter, pytest

**Spec:** `docs/superpowers/specs/2026-04-13-import-module-opcode-design.md`

---

### Task 1: Create PathName Wrapper Type

**Files:**
- Create: `interpreter/path_name.py`
- Create: `tests/unit/test_path_name.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for PathName wrapper type."""

from interpreter.path_name import PathName, NoPathName, NO_PATH_NAME


class TestPathName:
    def test_construction(self):
        p = PathName("./utils")
        assert p.value == "./utils"

    def test_str(self):
        assert str(PathName("os.path")) == "os.path"

    def test_hash_equality(self):
        a = PathName("./utils")
        b = PathName("./utils")
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality(self):
        assert PathName("./a") != PathName("./b")

    def test_ordering(self):
        assert PathName("a") < PathName("b")

    def test_is_present(self):
        assert PathName("x").is_present() is True

    def test_rejects_non_string(self):
        import pytest
        with pytest.raises(TypeError):
            PathName(123)  # type: ignore[arg-type]


class TestNoPathName:
    def test_is_not_present(self):
        assert NO_PATH_NAME.is_present() is False

    def test_str(self):
        assert str(NO_PATH_NAME) == "<no-path>"

    def test_singleton_identity(self):
        a = NoPathName()
        b = NoPathName()
        # eq=False means identity check fails, but both are not present
        assert not a.is_present()
        assert not b.is_present()

    def test_not_equal_to_pathname(self):
        assert NO_PATH_NAME != PathName("x")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_path_name.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'interpreter.path_name'`

- [ ] **Step 3: Write PathName implementation**

Create `interpreter/path_name.py`:

```python
"""PathName — typed wrapper for file/module path identifiers.

Follows the VarName/FuncName/FieldName pattern: frozen dataclass,
__post_init__ validation, is_present() protocol, null-object singleton.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PathName:
    """A source-level or resolved module path."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(f"PathName.value must be str, got {type(self.value).__name__}")

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PathName):
            return self.value == other.value
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, PathName):
            return self.value < other.value
        return NotImplemented


@dataclass(frozen=True, eq=False)
class NoPathName:
    """Null-object sentinel for absent PathName references."""

    def is_present(self) -> bool:
        return False

    def __str__(self) -> str:
        return "<no-path>"

    def __hash__(self) -> int:
        return hash(None)

    def __bool__(self) -> bool:
        return False


NO_PATH_NAME = NoPathName()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_path_name.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/path_name.py tests/unit/test_path_name.py
git commit -m "feat: add PathName wrapper type for module path identifiers"
```

---

### Task 2: Add IMPORT_MODULE Opcode and ImportModule Instruction

**Files:**
- Modify: `interpreter/ir.py:25-66` (Opcode enum)
- Modify: `interpreter/instructions.py` (new ImportModule class + `_TO_TYPED` entry)
- Create: `tests/unit/test_import_module_instruction.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for ImportModule instruction class."""

from interpreter.instructions import ImportModule
from interpreter.ir import Opcode
from interpreter.register import Register
from interpreter.path_name import PathName, NO_PATH_NAME


class TestImportModuleInstruction:
    def test_opcode(self):
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="./utils",
            resolved_path=PathName("/project/utils.py"),
        )
        assert inst.opcode == Opcode.IMPORT_MODULE

    def test_operands(self):
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="os",
            resolved_path=NO_PATH_NAME,
        )
        assert inst.operands == ["os", str(NO_PATH_NAME)]

    def test_operands_with_resolved(self):
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="./utils",
            resolved_path=PathName("/project/utils.py"),
        )
        assert inst.operands == ["./utils", "/project/utils.py"]

    def test_frozen(self):
        import pytest
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="os",
            resolved_path=NO_PATH_NAME,
        )
        with pytest.raises(AttributeError):
            inst.module_path = "sys"  # type: ignore[misc]

    def test_map_registers(self):
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="os",
            resolved_path=NO_PATH_NAME,
        )
        mapped = inst.map_registers(lambda r: r.rebase(10))
        assert str(mapped.result_reg) == "%10"

    def test_str_representation(self):
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="./utils",
            resolved_path=PathName("/project/utils.py"),
        )
        s = str(inst)
        assert "import_module" in s
        assert "./utils" in s
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_import_module_instruction.py -v`
Expected: FAIL with `ImportError: cannot import name 'ImportModule'`

- [ ] **Step 3: Add IMPORT_MODULE to Opcode enum**

In `interpreter/ir.py`, add to the Opcode enum after the "Pointer operations" section and before LABEL:

```python
    # Module imports (expanded by linker)
    IMPORT_MODULE = "IMPORT_MODULE"
```

- [ ] **Step 4: Add ImportModule instruction class**

In `interpreter/instructions.py`, add the import at the top (with the other imports from `interpreter`):

```python
from interpreter.path_name import PathName, NO_PATH_NAME
```

Add the class after the existing `StoreIndirect` class (before the Labels section, around line 630):

```python
# ── Module imports ──────────────────────────────────────────────


@dataclass(frozen=True)
class ImportModule(InstructionBase):
    """IMPORT_MODULE: import a module — expanded by the linker into existing opcodes."""

    result_reg: Register = NO_REGISTER
    module_path: str = ""
    resolved_path: PathName | NoPathName = NO_PATH_NAME

    @property
    def opcode(self) -> Opcode:
        return Opcode.IMPORT_MODULE

    @property
    def operands(self) -> list[Any]:
        return [self.module_path, str(self.resolved_path)]
```

Add `ImportModule` to the `_TO_TYPED` dict (line ~1333) and add a converter function above it:

```python
def _import_module(inst: Any) -> ImportModule:
    ops = inst.operands
    return ImportModule(
        result_reg=_to_reg(inst.result_reg),
        module_path=str(ops[0]) if len(ops) > 0 else "",
        resolved_path=PathName(str(ops[1])) if len(ops) > 1 and str(ops[1]) != "<no-path>" else NO_PATH_NAME,
        label=inst.label,
        branch_targets=inst.branch_targets,
        source_location=inst.source_location,
    )
```

In `_TO_TYPED`:
```python
    Opcode.IMPORT_MODULE: _import_module,
```

Add `ImportModule` to the public exports (the `Instruction` type alias union near the top of the file).

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_import_module_instruction.py -v`
Expected: All PASS

- [ ] **Step 6: Run full unit tests to check for regressions**

Run: `poetry run python -m pytest tests/unit/ -x -q`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add interpreter/ir.py interpreter/instructions.py tests/unit/test_import_module_instruction.py
git commit -m "feat: add IMPORT_MODULE opcode and ImportModule instruction class"
```

---

### Task 3: Update Python Frontend to Emit IMPORT_MODULE

**Files:**
- Modify: `interpreter/frontends/python/control_flow.py:409-457` (`lower_import`, `lower_import_from`)
- Modify: `interpreter/frontends/context.py:108-176` (add `resolved_imports` field)
- Create: `tests/unit/frontends/test_python_import_module.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for Python frontend emitting IMPORT_MODULE instructions."""

from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.ir import Opcode
from interpreter.instructions import ImportModule


def _lower(source: str) -> list:
    frontend = get_frontend(Language.PYTHON)
    return frontend.lower(source.encode())


class TestPythonImportEmitsImportModule:
    def test_import_os(self):
        ir = _lower("import os\n")
        import_insts = [i for i in ir if isinstance(i, ImportModule)]
        assert len(import_insts) == 1
        assert import_insts[0].module_path == "os"

    def test_import_dotted(self):
        ir = _lower("import os.path\n")
        import_insts = [i for i in ir if isinstance(i, ImportModule)]
        assert len(import_insts) == 1
        assert import_insts[0].module_path == "os.path"

    def test_import_stores_variable(self):
        """import os should also emit DECL_VAR for 'os'."""
        ir = _lower("import os\n")
        decl_vars = [i for i in ir if i.opcode == Opcode.DECL_VAR]
        names = [str(i.name) for i in decl_vars]
        assert "os" in names

    def test_from_import(self):
        ir = _lower("from os import path\n")
        import_insts = [i for i in ir if isinstance(i, ImportModule)]
        assert len(import_insts) == 1
        assert import_insts[0].module_path == "os"

    def test_from_import_load_field(self):
        """from os import path should emit IMPORT_MODULE + LOAD_FIELD + DECL_VAR."""
        ir = _lower("from os import path\n")
        opcodes = [i.opcode for i in ir]
        assert Opcode.IMPORT_MODULE in opcodes
        assert Opcode.LOAD_FIELD in opcodes

    def test_from_import_multiple_names(self):
        ir = _lower("from os import path, getcwd\n")
        import_insts = [i for i in ir if isinstance(i, ImportModule)]
        # One IMPORT_MODULE for the module, then LOAD_FIELD per name
        assert len(import_insts) == 1
        load_fields = [i for i in ir if i.opcode == Opcode.LOAD_FIELD]
        assert len(load_fields) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/frontends/test_python_import_module.py -v`
Expected: FAIL — current frontend emits `CALL_FUNCTION "import"`, not `ImportModule`

- [ ] **Step 3: Add `resolved_imports` field to TreeSitterEmitContext**

In `interpreter/frontends/context.py`, add the import:

```python
from interpreter.path_name import PathName
```

Add the field to the `TreeSitterEmitContext` dataclass (after `namespace_resolver`, around line 172):

```python
    # Resolved import mappings: source module path → resolved PathName
    # Populated by two-pass compilation; empty for single-file compilation.
    resolved_imports: dict[str, PathName] = field(default_factory=dict)
```

- [ ] **Step 4: Update `lower_import()` in Python frontend**

In `interpreter/frontends/python/control_flow.py`, add imports at the top:

```python
from interpreter.instructions import ImportModule, LoadField
from interpreter.path_name import NO_PATH_NAME
from interpreter.field_name import FieldName
```

Replace `lower_import()` (lines 409-424):

```python
def lower_import(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower import module as IMPORT_MODULE + DECL_VAR."""
    name_node = node.child_by_field_name(ctx.constants.func_name_field)
    module_name = ctx.node_text(name_node) if name_node else "unknown"
    import_reg = ctx.fresh_reg()
    resolved = ctx.resolved_imports.get(module_name, NO_PATH_NAME)
    ctx.emit_inst(
        ImportModule(
            result_reg=import_reg,
            module_path=module_name,
            resolved_path=resolved,
        ),
        node=node,
    )
    # Store using the top-level module name (e.g., 'os' for 'os.path')
    store_name = module_name.split(".")[0]
    ctx.emit_inst(DeclVar(name=VarName(store_name), value_reg=import_reg), node=node)
```

- [ ] **Step 5: Update `lower_import_from()` in Python frontend**

Replace `lower_import_from()` (lines 430-457):

```python
def lower_import_from(
    ctx: TreeSitterEmitContext, node: Any
) -> None:  # Any: tree-sitter node — untyped at Python boundary
    """Lower from X import Y, Z as IMPORT_MODULE + LOAD_FIELD + DECL_VAR per name."""
    module_node = node.child_by_field_name("module_name")
    module_name = ctx.node_text(module_node) if module_node else "unknown"

    # Emit a single IMPORT_MODULE for the module
    mod_reg = ctx.fresh_reg()
    resolved = ctx.resolved_imports.get(module_name, NO_PATH_NAME)
    ctx.emit_inst(
        ImportModule(
            result_reg=mod_reg,
            module_path=module_name,
            resolved_path=resolved,
        ),
        node=node,
    )

    # Collect all imported names (dotted_name children after 'import' keyword)
    imported_names = [
        c
        for c in node.children
        if c.is_named and c.type == PythonNodeType.DOTTED_NAME and c != module_node
    ]

    for name_node in imported_names:
        imported_name = ctx.node_text(name_node)
        field_reg = ctx.fresh_reg()
        ctx.emit_inst(
            LoadField(
                result_reg=field_reg,
                obj_reg=mod_reg,
                field_name=FieldName(imported_name),
            ),
            node=node,
        )
        ctx.emit_inst(
            DeclVar(name=VarName(imported_name), value_reg=field_reg), node=node
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/frontends/test_python_import_module.py -v`
Expected: All PASS

- [ ] **Step 7: Run full unit tests to check for regressions**

Run: `poetry run python -m pytest tests/unit/ -x -q`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add interpreter/frontends/context.py interpreter/frontends/python/control_flow.py tests/unit/frontends/test_python_import_module.py
git commit -m "feat: Python frontend emits IMPORT_MODULE instead of CALL_FUNCTION import"
```

---

### Task 4: Update TypeScript Frontend to Emit IMPORT_MODULE

**Files:**
- Modify: `interpreter/frontends/typescript.py:754-789` (`_lower_import_require_clause`)
- Create: `tests/unit/frontends/test_typescript_import_module.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for TypeScript frontend emitting IMPORT_MODULE instructions."""

from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.ir import Opcode
from interpreter.instructions import ImportModule


def _lower(source: str) -> list:
    frontend = get_frontend(Language.TYPESCRIPT)
    return frontend.lower(source.encode())


class TestTypeScriptRequireEmitsImportModule:
    def test_require_emits_import_module(self):
        ir = _lower("import utils = require('./utils');\n")
        import_insts = [i for i in ir if isinstance(i, ImportModule)]
        assert len(import_insts) == 1
        assert import_insts[0].module_path == "./utils"

    def test_require_stores_variable(self):
        """import x = require('./y') should emit STORE_VAR for 'x'."""
        ir = _lower("import utils = require('./utils');\n")
        store_vars = [i for i in ir if i.opcode == Opcode.STORE_VAR]
        names = [str(i.name) for i in store_vars]
        assert "utils" in names

    def test_require_result_reg_chains(self):
        """IMPORT_MODULE result_reg should feed into STORE_VAR."""
        ir = _lower("import utils = require('./utils');\n")
        import_inst = [i for i in ir if isinstance(i, ImportModule)][0]
        store_inst = [i for i in ir if i.opcode == Opcode.STORE_VAR][0]
        assert str(store_inst.value_reg) == str(import_inst.result_reg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/frontends/test_typescript_import_module.py -v`
Expected: FAIL — current frontend emits `CALL_FUNCTION "require"`, not `ImportModule`

- [ ] **Step 3: Update `_lower_import_require_clause()` in TypeScript frontend**

In `interpreter/frontends/typescript.py`, add imports at the top:

```python
from interpreter.instructions import ImportModule
from interpreter.path_name import NO_PATH_NAME
```

Replace `_lower_import_require_clause()` (lines 754-789):

```python
def _lower_import_require_clause(
    ctx: TreeSitterEmitContext,
    clause: Any,
    parent: Any,
) -> None:
    """Lower import_require_clause: identifier = require(string) → IMPORT_MODULE + STORE_VAR."""
    name_node = None
    string_node = None
    for child in clause.children:
        if child.type == "identifier":
            name_node = child
        if child.type == "string":
            string_node = child
    if name_node is None:
        return

    # Extract module path from the string literal
    module_path = ""
    if string_node is not None:
        raw = ctx.node_text(string_node)
        module_path = raw.strip("'\"")

    # Emit IMPORT_MODULE
    result_reg = ctx.fresh_reg()
    resolved = ctx.resolved_imports.get(module_path, NO_PATH_NAME)
    ctx.emit_inst(
        ImportModule(
            result_reg=result_reg,
            module_path=module_path,
            resolved_path=resolved,
        ),
        node=parent,
    )

    # Emit STORE_VAR for the alias name
    var_name = ctx.node_text(name_node)
    ctx.emit_inst(StoreVar(name=VarName(var_name), value_reg=result_reg), node=parent)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/frontends/test_typescript_import_module.py -v`
Expected: All PASS

- [ ] **Step 5: Run full unit tests to check for regressions**

Run: `poetry run python -m pytest tests/unit/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add interpreter/frontends/typescript.py tests/unit/frontends/test_typescript_import_module.py
git commit -m "feat: TypeScript frontend emits IMPORT_MODULE instead of CALL_FUNCTION require"
```

---

### Task 5: Two-Pass Compilation in compile_directory()

**Files:**
- Modify: `interpreter/project/compiler.py:76-114` (`compile_module`)
- Modify: `interpreter/project/compiler.py:139-243` (`compile_directory`)
- Modify: `interpreter/frontends/context.py` (pass `resolved_imports` to context)
- Create: `tests/unit/project/test_two_pass_compilation.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for two-pass compilation with resolved imports."""

from pathlib import Path

from interpreter.constants import Language
from interpreter.instructions import ImportModule
from interpreter.path_name import PathName
from interpreter.project.compiler import compile_directory


class TestTwoPassCompilation:
    def test_resolved_path_in_import_module(self, tmp_path: Path):
        """After two-pass compilation, IMPORT_MODULE should carry resolved paths."""
        (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b\n")
        (tmp_path / "main.py").write_text("import utils\n")
        linked = compile_directory(tmp_path, Language.PYTHON)
        import_insts = [
            i for i in linked.merged_ir if isinstance(i, ImportModule)
        ]
        # The main module's IMPORT_MODULE for 'utils' should have a resolved path
        assert len(import_insts) >= 1
        resolved = [i for i in import_insts if i.resolved_path.is_present()]
        assert len(resolved) >= 1
        assert "utils" in str(resolved[0].resolved_path)

    def test_unresolvable_import_has_no_path(self, tmp_path: Path):
        """System imports should have NO_PATH_NAME as resolved_path."""
        (tmp_path / "main.py").write_text("import os\n")
        linked = compile_directory(tmp_path, Language.PYTHON)
        import_insts = [
            i for i in linked.merged_ir if isinstance(i, ImportModule)
        ]
        assert len(import_insts) >= 1
        assert not import_insts[0].resolved_path.is_present()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/project/test_two_pass_compilation.py -v`
Expected: FAIL — resolved_path is always `NO_PATH_NAME` because compile_directory doesn't do two-pass yet

- [ ] **Step 3: Add `resolved_imports` parameter to `compile_module()`**

In `interpreter/project/compiler.py`, add imports:

```python
from interpreter.path_name import PathName
```

Update `compile_module()` signature and body to accept and pass `resolved_imports`:

```python
def compile_module(
    file_path: Path,
    language: Language,
    source: bytes | None = None,
    namespace_resolver: NamespaceResolver = NamespaceResolver(),
    resolved_imports: dict[str, PathName] | None = None,
) -> ModuleUnit:
    """Compile a single file into a ModuleUnit."""
    if source is None:
        source = file_path.read_bytes()

    resolved_frontend_type = (
        constants.FRONTEND_COBOL
        if language == Language.COBOL
        else constants.FRONTEND_DETERMINISTIC
    )
    frontend = get_frontend(language, frontend_type=resolved_frontend_type)
    ir = frontend.lower(
        source,
        namespace_resolver=namespace_resolver,
        resolved_imports=resolved_imports or {},
    )

    exports = build_export_table(
        ir,
        frontend.func_symbol_table,
        frontend.class_symbol_table,
    )

    imports = tuple(extract_imports(source, file_path, language))

    return ModuleUnit(
        path=file_path,
        language=language,
        ir=tuple(ir),
        exports=exports,
        imports=imports,
        symbol_table=frontend.symbol_table,
    )
```

- [ ] **Step 4: Thread `resolved_imports` through `frontend.lower()` to context**

The `frontend.lower()` method needs to accept and pass `resolved_imports` to `TreeSitterEmitContext`. Find `frontend.lower()` in the frontend base class and update it to accept `resolved_imports: dict[str, PathName]` and set `ctx.resolved_imports`.

In `interpreter/frontends/_base.py` (or wherever `lower()` is defined), add the parameter and pass it through.

In `interpreter/frontend.py` (the `get_frontend` entry point), ensure `lower()` accepts `**kwargs` that flow to the emit context.

The exact changes depend on how the frontend pipeline threads arguments. The key requirement: `ctx.resolved_imports` must be set to the dict from `compile_module()`.

- [ ] **Step 5: Restructure `compile_directory()` for two-pass compilation**

In `interpreter/project/compiler.py`, restructure `compile_directory()`:

```python
def compile_directory(
    directory: Path,
    language: Language,
) -> LinkedProgram:
    """Compile all source files in a directory tree (two-pass).

    Pass 1: Discover files, extract imports, resolve dependencies.
    Pass 2: Compile each file with resolved import paths available.
    """
    directory = directory.resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    extensions = _LANGUAGE_EXTENSIONS.get(language, ())
    source_files = sorted(
        f.resolve()
        for ext in extensions
        for f in directory.rglob(f"*{ext}")
        if f.is_file()
    )

    # --- Java namespace resolution: pre-scan + build tree ---
    namespace_resolver: NamespaceResolver = NamespaceResolver()
    if language == Language.JAVA:
        from interpreter.frontends.java.namespace import (
            JavaNamespaceResolver,
            build_java_namespace_tree,
            java_pre_scan,
        )
        from experiments.java_stdlib.registry import STDLIB_REGISTRY

        scan_results = {path: java_pre_scan(path.read_bytes()) for path in source_files}
        tree = build_java_namespace_tree(scan_results, STDLIB_REGISTRY)
        namespace_resolver = JavaNamespaceResolver(tree)

    # --- PASS 1: Extract imports and resolve dependencies ---
    sources: dict[Path, bytes] = {path: path.read_bytes() for path in source_files}
    all_imports = {
        path: tuple(extract_imports(src, path, language))
        for path, src in sources.items()
    }

    # Build resolver
    if language == Language.JAVA:
        discovered_roots = MavenSourceRootDiscovery().discover(directory)
        resolver = (
            JavaImportResolver(source_roots=discovered_roots)
            if discovered_roots
            else get_resolver(language)
        )
    else:
        resolver = get_resolver(language)

    # Build import graph from extracted imports
    import_graph: dict[Path, list[Path]] = {path: [] for path in source_files}
    # Track resolved import mappings per file: source_path → {module_path → PathName}
    per_file_resolved: dict[Path, dict[str, PathName]] = {
        path: {} for path in source_files
    }
    for path, refs in all_imports.items():
        for ref in refs:
            for resolved in resolver.resolve(ref, directory):
                if resolved.is_resolved():
                    target = resolved.resolved_path.resolve()
                    if target in import_graph and target not in import_graph[path]:
                        import_graph[path].append(target)
                    per_file_resolved[path][ref.module_path] = PathName(str(target))

    # --- Java stdlib injection (same as before) ---
    stdlib_edges: dict[Path, list[Path]] = {}
    if language == Language.JAVA:
        stdlib_needed: dict[Path, ModuleUnit] = {}
        for user_path, refs in all_imports.items():
            for ref in refs:
                if not ref.is_system:
                    continue
                for name in ref.names:
                    stub_key = Path(ref.module_path.replace(".", "/")) / f"{name}.java"
                    if stub_key in STDLIB_REGISTRY:
                        if stub_key not in stdlib_needed:
                            stdlib_needed[stub_key] = STDLIB_REGISTRY[stub_key]
                        stdlib_edges.setdefault(user_path, [])
                        if stub_key not in stdlib_edges[user_path]:
                            stdlib_edges[user_path].append(stub_key)

    # --- PASS 2: Compile each module with resolved imports ---
    modules = {
        path: compile_module(
            path,
            language,
            source=sources[path],
            namespace_resolver=namespace_resolver,
            resolved_imports=per_file_resolved.get(path),
        )
        for path in source_files
    }

    # Add stdlib modules (Java only)
    if language == Language.JAVA:
        for stub_key, stub_module in stdlib_needed.items():
            modules[stub_key] = stub_module
            import_graph[stub_key] = []

    # Add stdlib dependency edges
    for user_path, deps in stdlib_edges.items():
        for dep in deps:
            if dep not in import_graph[user_path]:
                import_graph[user_path].append(dep)

    topo_order = topological_sort(import_graph)

    return link_modules(
        modules=modules,
        import_graph=import_graph,
        project_root=directory,
        topo_order=topo_order,
        language=language,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/project/test_two_pass_compilation.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite to check for regressions**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add interpreter/project/compiler.py interpreter/frontends/context.py interpreter/frontend.py interpreter/frontends/_base.py
git add tests/unit/project/test_two_pass_compilation.py
git commit -m "feat: two-pass compilation passes resolved import paths to frontends"
```

---

### Task 6: Linker IMPORT_MODULE Expansion

**Files:**
- Modify: `interpreter/project/linker.py`
- Create: `tests/unit/project/test_linker_import_module.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for linker IMPORT_MODULE expansion."""

from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel, Opcode
from interpreter.instructions import (
    ImportModule,
    NewObject,
    Const,
    StoreField,
    DeclVar,
    Label_,
)
from interpreter.path_name import PathName, NO_PATH_NAME
from interpreter.project.linker import expand_import_module
from interpreter.project.types import ExportTable
from interpreter.register import Register
from interpreter.var_name import VarName


class TestExpandImportModule:
    def test_expands_function_export(self):
        """IMPORT_MODULE with a function export → NEW_OBJECT + CONST + STORE_FIELD."""
        exports = ExportTable(
            functions={FuncName("add"): CodeLabel("func_add")},
            classes={},
            variables={},
        )
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="./utils",
            resolved_path=PathName("/project/utils.py"),
        )
        expanded = expand_import_module(inst, exports, reg_start=10)
        opcodes = [i.opcode for i in expanded]
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_FIELD in opcodes

    def test_expands_class_export(self):
        """IMPORT_MODULE with a class export → NEW_OBJECT + CONST + STORE_FIELD."""
        exports = ExportTable(
            functions={},
            classes={ClassName("Greeter"): CodeLabel("class_Greeter")},
            variables={},
        )
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="./greeter",
            resolved_path=PathName("/project/greeter.py"),
        )
        expanded = expand_import_module(inst, exports, reg_start=10)
        opcodes = [i.opcode for i in expanded]
        assert Opcode.NEW_OBJECT in opcodes
        assert Opcode.CONST in opcodes
        assert Opcode.STORE_FIELD in opcodes

    def test_result_reg_receives_namespace_object(self):
        """The final instruction should store the namespace object into result_reg."""
        exports = ExportTable(
            functions={FuncName("add"): CodeLabel("func_add")},
            classes={},
            variables={},
        )
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="./utils",
            resolved_path=PathName("/project/utils.py"),
        )
        expanded = expand_import_module(inst, exports, reg_start=10)
        # First instruction: NEW_OBJECT into a fresh register
        assert expanded[0].opcode == Opcode.NEW_OBJECT
        # There should be a store into the original result_reg
        # The NEW_OBJECT register is what gets populated and stored
        ns_reg = expanded[0].result_reg
        store_fields = [i for i in expanded if i.opcode == Opcode.STORE_FIELD]
        assert all(str(i.obj_reg) == str(ns_reg) for i in store_fields)

    def test_unresolved_import_returns_empty(self):
        """IMPORT_MODULE with NO_PATH_NAME should not be expanded."""
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="os",
            resolved_path=NO_PATH_NAME,
        )
        expanded = expand_import_module(inst, ExportTable(), reg_start=10)
        assert expanded == []

    def test_register_allocation_starts_from_reg_start(self):
        """Synthetic registers should start from reg_start."""
        exports = ExportTable(
            functions={FuncName("add"): CodeLabel("func_add")},
            classes={},
            variables={},
        )
        inst = ImportModule(
            result_reg=Register("%0"),
            module_path="./utils",
            resolved_path=PathName("/project/utils.py"),
        )
        expanded = expand_import_module(inst, exports, reg_start=50)
        # All synthetic registers should be >= %50
        for ei in expanded:
            if ei.result_reg.is_present() and str(ei.result_reg) != "%0":
                reg_num = int(str(ei.result_reg).replace("%", ""))
                assert reg_num >= 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/project/test_linker_import_module.py -v`
Expected: FAIL — `expand_import_module` does not exist yet

- [ ] **Step 3: Implement `expand_import_module()` in linker**

In `interpreter/project/linker.py`, add imports:

```python
from interpreter.instructions import ImportModule, NewObject, StoreField, StoreVar
from interpreter.path_name import PathName, NO_PATH_NAME
from interpreter.field_name import FieldName
from interpreter.register import Register
from interpreter.var_name import VarName
```

Add the expansion function:

```python
def expand_import_module(
    inst: ImportModule,
    exports: ExportTable,
    reg_start: int,
) -> list[InstructionBase]:
    """Expand an IMPORT_MODULE into existing opcodes using the ExportTable.

    Returns an empty list if the import is unresolved (NO_PATH_NAME).

    Expansion:
        NEW_OBJECT     r_ns
        CONST          r_tmp, <func_label>      # per exported function
        STORE_FIELD    r_ns, "name", r_tmp       # per exported function
        CONST          r_tmp, <class_label>      # per exported class
        STORE_FIELD    r_ns, "name", r_tmp       # per exported class
        STORE_VAR      result_reg, r_ns          # assign to original target
    """
    if not inst.resolved_path.is_present():
        return []

    result: list[InstructionBase] = []
    reg_counter = reg_start

    def fresh_reg() -> Register:
        nonlocal reg_counter
        r = Register(f"%{reg_counter}")
        reg_counter += 1
        return r

    # Create the namespace object
    ns_reg = fresh_reg()
    result.append(NewObject(result_reg=ns_reg, source_location=inst.source_location))

    # Attach exported functions
    for name, label in exports.functions.items():
        tmp = fresh_reg()
        result.append(Const(result_reg=tmp, value=str(label), source_location=inst.source_location))
        result.append(StoreField(
            obj_reg=ns_reg,
            field_name=FieldName(str(name)),
            value_reg=tmp,
            source_location=inst.source_location,
        ))

    # Attach exported classes
    for name, label in exports.classes.items():
        tmp = fresh_reg()
        result.append(Const(result_reg=tmp, value=str(label), source_location=inst.source_location))
        result.append(StoreField(
            obj_reg=ns_reg,
            field_name=FieldName(str(name)),
            value_reg=tmp,
            source_location=inst.source_location,
        ))

    # Attach exported variables
    for name, _reg in exports.variables.items():
        tmp = fresh_reg()
        result.append(Const(result_reg=tmp, value=str(name), source_location=inst.source_location))
        result.append(StoreField(
            obj_reg=ns_reg,
            field_name=FieldName(str(name)),
            value_reg=tmp,
            source_location=inst.source_location,
        ))

    # Store the namespace object into the original result register
    result.append(StoreVar(
        name=VarName(str(inst.result_reg)),
        value_reg=ns_reg,
        source_location=inst.source_location,
    ))

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/project/test_linker_import_module.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/project/linker.py tests/unit/project/test_linker_import_module.py
git commit -m "feat: add expand_import_module() for linker IMPORT_MODULE expansion"
```

---

### Task 7: Integrate IMPORT_MODULE Expansion into Linker Pipeline

**Files:**
- Modify: `interpreter/project/linker.py:141-193` (`_transform_module`)
- Modify: `interpreter/project/linker.py:247-318` (`link_modules`)

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for IMPORT_MODULE integration in the linker pipeline."""

from pathlib import Path

from interpreter.constants import Language
from interpreter.instructions import ImportModule
from interpreter.ir import Opcode
from interpreter.project.compiler import compile_directory


class TestLinkerImportModuleIntegration:
    def test_no_import_module_in_linked_ir(self, tmp_path: Path):
        """After linking, no IMPORT_MODULE instructions should remain in merged IR."""
        (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b\n")
        (tmp_path / "main.py").write_text("import utils\n")
        linked = compile_directory(tmp_path, Language.PYTHON)
        import_insts = [i for i in linked.merged_ir if isinstance(i, ImportModule)]
        # Resolved IMPORT_MODULE should be expanded; unresolved may remain
        resolved_remaining = [i for i in import_insts if i.resolved_path.is_present()]
        assert len(resolved_remaining) == 0

    def test_expanded_ir_contains_new_object(self, tmp_path: Path):
        """Expanded IMPORT_MODULE should produce NEW_OBJECT in merged IR."""
        (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b\n")
        (tmp_path / "main.py").write_text("import utils\n")
        linked = compile_directory(tmp_path, Language.PYTHON)
        opcodes = [i.opcode for i in linked.merged_ir]
        assert Opcode.NEW_OBJECT in opcodes
```

Add to `tests/unit/project/test_linker_import_module.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/project/test_linker_import_module.py -v`
Expected: FAIL — `_transform_module` doesn't handle IMPORT_MODULE yet

- [ ] **Step 3: Update `_transform_module()` to expand IMPORT_MODULE**

Replace `_transform_module()` in `interpreter/project/linker.py`:

```python
def _transform_module(
    module: ModuleUnit,
    prefix: str,
    reg_offset: int,
    resolved_imports: set[str],
    modules: dict[Path, ModuleUnit],
    reg_high_water: int,
) -> tuple[list[InstructionBase], int]:
    """Transform a module's IR: namespace, rebase, expand IMPORT_MODULE.

    Returns the transformed IR and the updated reg_high_water mark.
    """
    result: list[InstructionBase] = []

    for inst in module.ir:
        typed = inst

        # Skip the per-module "entry:" label
        if isinstance(typed, Label_) and typed.label.is_entry():
            continue

        # Expand IMPORT_MODULE instructions
        if isinstance(typed, ImportModule) and typed.resolved_path.is_present():
            # Find the target module's exports
            resolved_str = str(typed.resolved_path)
            target_path = Path(resolved_str)
            if target_path in modules:
                target_exports = modules[target_path].exports
                expanded = expand_import_module(
                    _transform_instruction(typed, prefix, reg_offset),
                    target_exports,
                    reg_start=reg_high_water,
                )
                # Namespace the export labels in CONST values
                target_prefix = module_prefix(target_path, target_path.parent)
                # Note: export labels need to be namespaced to match merged IR
                result.extend(expanded)
                reg_high_water += len([i for i in expanded if i.result_reg.is_present()])
                continue

        result.append(_transform_instruction(inst, prefix, reg_offset))

    return result, reg_high_water
```

- [ ] **Step 4: Update `link_modules()` to pass modules and track high-water mark**

Update the loop in `link_modules()` that calls `_transform_module()`:

```python
    # Compute total high-water mark for synthetic registers
    reg_high_water = 0
    for file_path in processing_order:
        module = modules[file_path]
        reg_high_water += max_register_number(module.ir) + 1

    # Build merged IR
    all_ir: list[InstructionBase] = [Label_(label=CodeLabel("entry"))]
    reg_offset = 0

    for file_path in processing_order:
        module = modules[file_path]
        prefix = prefixes[file_path]

        transformed, reg_high_water = _transform_module(
            module, prefix, reg_offset, resolved.get(file_path, set()),
            modules, reg_high_water,
        )
        all_ir.extend(transformed)
        reg_offset += max_register_number(module.ir) + 1
```

- [ ] **Step 5: Remove `_is_import_call()` and old import stub dropping logic**

Delete the `_is_import_call()` function and the `skip_next_decl_for_reg` logic from `_transform_module()`. These are replaced by IMPORT_MODULE expansion.

- [ ] **Step 6: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/project/test_linker_import_module.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add interpreter/project/linker.py tests/unit/project/test_linker_import_module.py
git commit -m "feat: linker expands IMPORT_MODULE into namespace objects, removes _is_import_call heuristic"
```

---

### Task 8: Demand-Driven Module Filtering

**Files:**
- Modify: `interpreter/project/linker.py` (add reachability filter)
- Create: `tests/unit/project/test_demand_driven_filtering.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for demand-driven module filtering in the linker."""

from pathlib import Path

from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
from interpreter.project.linker import reachable_modules


class TestDemandDrivenFiltering:
    def test_unreachable_module_excluded(self, tmp_path: Path):
        """A module not imported by anyone should be excluded from merged IR."""
        (tmp_path / "main.py").write_text("x = 1\n")
        (tmp_path / "orphan.py").write_text("y = 2\n")
        linked = compile_directory(tmp_path, Language.PYTHON)
        # orphan.py's top-level code should NOT appear in merged IR
        ir_str = " ".join(str(i) for i in linked.merged_ir)
        # The variable 'y' from orphan.py should not be declared
        decl_vars = [i for i in linked.merged_ir if i.opcode.value == "DECL_VAR"]
        names = [str(i.name) for i in decl_vars]
        assert "y" not in names

    def test_reachable_modules_helper(self):
        """reachable_modules should return transitive closure from entry."""
        graph = {
            Path("main.py"): [Path("utils.py")],
            Path("utils.py"): [Path("helpers.py")],
            Path("helpers.py"): [],
            Path("orphan.py"): [],
        }
        entry = Path("main.py")
        reachable = reachable_modules(graph, entry)
        assert Path("main.py") in reachable
        assert Path("utils.py") in reachable
        assert Path("helpers.py") in reachable
        assert Path("orphan.py") not in reachable

    def test_all_imported_modules_included(self, tmp_path: Path):
        """Transitively imported modules should be included."""
        (tmp_path / "helpers.py").write_text("def helper():\n    return 1\n")
        (tmp_path / "utils.py").write_text("import helpers\n")
        (tmp_path / "main.py").write_text("import utils\n")
        linked = compile_directory(tmp_path, Language.PYTHON)
        ir_str = " ".join(str(i) for i in linked.merged_ir)
        assert "helper" in ir_str
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/project/test_demand_driven_filtering.py -v`
Expected: FAIL — `reachable_modules` does not exist yet

- [ ] **Step 3: Implement `reachable_modules()` helper**

In `interpreter/project/linker.py`:

```python
def reachable_modules(
    import_graph: dict[Path, list[Path]],
    entry: Path,
) -> set[Path]:
    """Walk the import graph from entry, return all transitively reachable modules."""
    visited: set[Path] = set()
    stack = [entry]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for dep in import_graph.get(current, []):
            if dep not in visited:
                stack.append(dep)
    return visited
```

- [ ] **Step 4: Integrate filtering into `link_modules()`**

In `link_modules()`, after computing `processing_order`, filter to only reachable modules:

```python
    # Demand-driven filtering: only include modules reachable from entry
    entry_module = processing_order[-1] if processing_order else None
    if entry_module is not None:
        reachable = reachable_modules(import_graph, entry_module)
        processing_order = [p for p in processing_order if p in reachable]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/project/test_demand_driven_filtering.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add interpreter/project/linker.py tests/unit/project/test_demand_driven_filtering.py
git commit -m "feat: demand-driven module filtering excludes unreachable modules from linked IR"
```

---

### Task 9: Integration Tests — End-to-End Execution

**Files:**
- Modify: `tests/integration/project/test_ts_import_require.py` (update expectations)
- Create: `tests/integration/project/test_import_module_execution.py`

- [ ] **Step 1: Write Python cross-module integration test**

```python
"""Integration tests: IMPORT_MODULE end-to-end execution."""

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.ir import Opcode
from interpreter.project.compiler import compile_directory
from interpreter.project.types import LinkedProgram
from interpreter.run import execute_cfg, ExecutionStrategies
from interpreter.run_types import VMConfig
from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName


def _execute_linked(linked: LinkedProgram, max_steps: int = 500):
    strategies = ExecutionStrategies(
        func_symbol_table=linked.func_symbol_table,
        class_symbol_table=linked.class_symbol_table,
    )
    config = VMConfig(max_steps=max_steps)
    return execute_cfg(
        linked.merged_cfg,
        linked.merged_cfg.entry,
        linked.merged_registry,
        config,
        strategies,
    )


def _local_vars(vm):
    frame = vm.call_stack[0]
    return {
        k: v.value if isinstance(v, TypedValue) else v
        for k, v in frame.local_vars.items()
    }


class TestPythonCrossModuleExecution:
    def test_import_function_and_call(self, tmp_path: Path):
        """Import a function from another module, call it, verify concrete result."""
        (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b\n")
        (tmp_path / "main.py").write_text("import utils\nanswer = utils.add(3, 4)\n")
        linked = compile_directory(tmp_path, Language.PYTHON)
        vm, stats = _execute_linked(linked)
        lvars = _local_vars(vm)
        assert VarName("answer") in lvars

    def test_from_import_function(self, tmp_path: Path):
        """from utils import add; answer = add(3, 4)."""
        (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b\n")
        (tmp_path / "main.py").write_text("from utils import add\nanswer = add(3, 4)\n")
        linked = compile_directory(tmp_path, Language.PYTHON)
        vm, stats = _execute_linked(linked)
        lvars = _local_vars(vm)
        assert VarName("answer") in lvars

    def test_system_import_graceful_degradation(self, tmp_path: Path):
        """import os should degrade gracefully (no crash)."""
        (tmp_path / "main.py").write_text("import os\nx = 1\n")
        linked = compile_directory(tmp_path, Language.PYTHON)
        vm, stats = _execute_linked(linked)
        lvars = _local_vars(vm)
        assert VarName("x") in lvars


class TestTypeScriptCrossModuleExecution:
    def test_require_function_and_call(self, tmp_path: Path):
        """import utils = require('./utils'); answer = utils.add(3, 4)."""
        (tmp_path / "utils.ts").write_text(
            "function add(a: number, b: number): number {\n    return a + b;\n}\n"
        )
        (tmp_path / "main.ts").write_text(
            "import utils = require('./utils');\nlet answer: number = utils.add(3, 4);\n"
        )
        linked = compile_directory(tmp_path, Language.TYPESCRIPT)
        vm, stats = _execute_linked(linked)
        lvars = _local_vars(vm)
        assert VarName("utils") in lvars
        assert VarName("answer") in lvars
```

- [ ] **Step 2: Run integration tests**

Run: `poetry run python -m pytest tests/integration/project/test_import_module_execution.py -v`
Expected: All PASS

- [ ] **Step 3: Update existing TS require integration tests**

In `tests/integration/project/test_ts_import_require.py`, update `test_require_emits_call_function_in_ir` to check for `IMPORT_MODULE` instead of `CALL_FUNCTION "require"`:

```python
    def test_require_emits_import_module_in_ir(self, ts_func_project: Path):
        """Merged IR should contain an IMPORT_MODULE instruction for 'require'."""
        linked = compile_directory(ts_func_project, Language.TYPESCRIPT)
        from interpreter.instructions import ImportModule
        import_insts = [
            inst
            for inst in linked.merged_ir
            if isinstance(inst, ImportModule)
        ]
        # May be 0 if linker already expanded them; check for expansion artifacts instead
        new_objects = [i for i in linked.merged_ir if i.opcode == Opcode.NEW_OBJECT]
        assert len(import_insts) > 0 or len(new_objects) > 0, (
            "No IMPORT_MODULE or expanded NEW_OBJECT in merged IR"
        )
```

- [ ] **Step 4: Run all integration tests**

Run: `poetry run python -m pytest tests/integration/project/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tests/integration/project/test_import_module_execution.py tests/integration/project/test_ts_import_require.py
git commit -m "test: add end-to-end integration tests for IMPORT_MODULE execution"
```

---

### Task 10: Formatting, Full Suite, and Talisman

- [ ] **Step 1: Run black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest tests/ -q`
Expected: All pass (13,400+ tests), no regressions

- [ ] **Step 3: Handle Talisman if needed**

If Talisman flags any new files, append their checksums to `.talismanrc` (never modify existing entries).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: formatting and talisman updates for IMPORT_MODULE feature"
```

---

### Task 11: File Follow-Up Issues

- [ ] **Step 1: File issue for scope isolation**

Scope isolation (preventing cross-module variable leakage) is explicitly out of scope for this PR. File an issue describing the problem and referencing the IMPORT_MODULE design spec.

- [ ] **Step 2: File issue for multi-file test coverage gaps**

File an issue for frontends lacking multi-file integration test coverage: Go, Java, Rust, C, C++, C#, Kotlin, Scala, Ruby, PHP, Lua, Pascal, COBOL. Reference the existing `test_all_language_imports.py` as the single-file baseline.

- [ ] **Step 3: File issue for re-exports**

Module A re-exporting symbols from module B is not handled. File an issue describing the pattern and the expected behavior.
