# EntryPoint + run_linked() Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace stringly-typed entry_point with an explicit `EntryPoint` type, consolidate compilation into `compile_directory()`, and route all execution through `run_linked()`.

**Architecture:** New `EntryPoint` type with `function(predicate)` and `top_level()` factory methods. `run()` builds a single-module `LinkedProgram` and delegates to `run_linked()`. `compile_project()` is removed; `compile_directory()` drops `entry_file`. `LinkedProgram` gains `entry_points()` discovery and extra fields needed by execution strategies.

**Tech Stack:** Python 3.13, pytest, dataclasses

**Spec:** `docs/superpowers/specs/2026-03-31-run-linked-entry-point-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `interpreter/project/entry_point.py` | Create | `EntryPoint` type |
| `interpreter/project/types.py` | Modify | Drop `entry_module`, add `entry_points()`, add `language`, `type_env_builder`, `symbol_table`, `data_layout` fields |
| `interpreter/project/compiler.py` | Modify | Remove `compile_project()`, simplify `compile_directory()` signature, populate new LinkedProgram fields |
| `interpreter/project/linker.py` | Modify | Drop `entry_module` from link_modules output |
| `interpreter/run.py` | Modify | Add `run_linked()`, refactor `run()` to build LinkedProgram and delegate |
| `interpreter.py` | Modify | CLI entry_point arg → `EntryPoint` |
| `tests/unit/project/test_entry_point.py` | Create | Unit tests for `EntryPoint` type |
| `tests/unit/project/test_types.py` | Modify | Update `LinkedProgram` tests (drop `entry_module`, test `entry_points()`) |
| `tests/unit/project/test_compile_directory.py` | Modify | Drop `entry_file` from calls, drop `test_entry_module_set_correctly` |
| `tests/unit/test_run_linked.py` | Create | Unit tests for `run_linked()` |
| `tests/integration/test_ctor_dispatch_entry_point.py` | Modify | Migrate 24 call sites to `EntryPoint.function(...)` |
| ~70 other test files | Modify | Migrate `run()` calls to use `EntryPoint.top_level()` or `EntryPoint.function(...)` |
| `docs/architectural-design-decisions.md` | Modify | Add ADR for this change |

---

### Task 1: Create `EntryPoint` type

**Files:**
- Create: `interpreter/project/entry_point.py`
- Create: `tests/unit/project/test_entry_point.py`

- [ ] **Step 1: Write failing tests for EntryPoint**

```python
# tests/unit/project/test_entry_point.py
"""Tests for EntryPoint type."""

from interpreter.func_name import FuncName
from interpreter.project.entry_point import EntryPoint
from interpreter.refs.func_ref import FuncRef
from interpreter.ir import CodeLabel


def _make_func_ref(name: str) -> FuncRef:
    return FuncRef(name=FuncName(name), label=CodeLabel(f"func_{name}"), params=())


class TestEntryPointTopLevel:
    def test_is_top_level(self):
        ep = EntryPoint.top_level()
        assert ep.is_top_level is True

    def test_is_not_function(self):
        ep = EntryPoint.top_level()
        assert ep.is_function is False


class TestEntryPointFunction:
    def test_is_function(self):
        ep = EntryPoint.function(lambda f: f.name == FuncName("main"))
        assert ep.is_function is True

    def test_is_not_top_level(self):
        ep = EntryPoint.function(lambda f: f.name == FuncName("main"))
        assert ep.is_top_level is False

    def test_resolve_single_match(self):
        ep = EntryPoint.function(lambda f: f.name == FuncName("main"))
        candidates = [_make_func_ref("main"), _make_func_ref("helper")]
        result = ep.resolve(candidates)
        assert result.name == FuncName("main")

    def test_resolve_no_match_raises(self):
        ep = EntryPoint.function(lambda f: f.name == FuncName("main"))
        candidates = [_make_func_ref("helper")]
        import pytest
        with pytest.raises(ValueError, match="No function matched"):
            ep.resolve(candidates)

    def test_resolve_multiple_matches_raises(self):
        ep = EntryPoint.function(lambda f: f.name == FuncName("main"))
        candidates = [_make_func_ref("main"), _make_func_ref("main")]
        import pytest
        with pytest.raises(ValueError, match="Multiple functions matched"):
            ep.resolve(candidates)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/project/test_entry_point.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement EntryPoint**

```python
# interpreter/project/entry_point.py
"""EntryPoint type — explicit specification of how to enter a program for execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from interpreter.refs.func_ref import FuncRef


@dataclass(frozen=True)
class EntryPoint:
    """Specifies how to enter a program for execution.

    Two modes:
    - top_level(): execute module code top-to-bottom
    - function(predicate): run preamble, then dispatch into the matched function
    """

    _predicate: Callable[[FuncRef], bool]
    _is_top_level: bool

    @staticmethod
    def function(predicate: Callable[[FuncRef], bool]) -> EntryPoint:
        """Dispatch into the single function matching the predicate."""
        return EntryPoint(_predicate=predicate, _is_top_level=False)

    @staticmethod
    def top_level() -> EntryPoint:
        """Execute module code top-to-bottom (preamble + top-level statements)."""
        return EntryPoint(_predicate=lambda _: False, _is_top_level=True)

    @property
    def is_top_level(self) -> bool:
        return self._is_top_level

    @property
    def is_function(self) -> bool:
        return not self._is_top_level

    def resolve(self, candidates: list[FuncRef]) -> FuncRef:
        """Apply predicate to candidates and return the single match.

        Raises ValueError if zero or multiple matches.
        """
        matches = [f for f in candidates if self._predicate(f)]
        if len(matches) == 0:
            names = [str(f.name) for f in candidates]
            raise ValueError(
                f"No function matched the entry_point predicate. "
                f"Available: {names}"
            )
        if len(matches) > 1:
            names = [str(f.name) for f in matches]
            raise ValueError(
                f"Multiple functions matched the entry_point predicate: {names}. "
                f"Narrow the predicate to match exactly one."
            )
        return matches[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/project/test_entry_point.py -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Run full test suite (no regressions)**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All ~13,168 tests pass

- [ ] **Step 6: Commit**

```bash
bd backup
git add interpreter/project/entry_point.py tests/unit/project/test_entry_point.py
git commit -m "Add EntryPoint type with function(predicate) and top_level() modes"
```

---

### Task 2: Add execution-supporting fields to `LinkedProgram`

`build_execution_strategies()` currently reads `frontend.func_symbol_table`, `frontend.class_symbol_table`, `frontend.type_env_builder`, `frontend.symbol_table`, and `frontend.data_layout`. `LinkedProgram` already has the symbol tables but is missing `type_env_builder`, `symbol_table`, `data_layout`, and `language`.

**Files:**
- Modify: `interpreter/project/types.py`
- Modify: `tests/unit/project/test_types.py`

- [ ] **Step 1: Write failing tests for new LinkedProgram fields**

Add to `tests/unit/project/test_types.py` in `TestLinkedProgram`:

```python
def test_linked_program_has_language(self):
    lp = LinkedProgram(
        modules={},
        merged_ir=[],
        merged_cfg=CFG(blocks={}, entry=CodeLabel("entry")),
        merged_registry=FunctionRegistry(),
        import_graph={},
        language=Language.PYTHON,
        type_env_builder=TypeEnvironmentBuilder(),
        symbol_table=SymbolTable.empty(),
    )
    assert lp.language == Language.PYTHON
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/project/test_types.py::TestLinkedProgram::test_linked_program_has_language -v`
Expected: FAIL (unexpected keyword argument)

- [ ] **Step 3: Add fields to LinkedProgram**

In `interpreter/project/types.py`, modify `LinkedProgram`:

```python
@dataclass
class LinkedProgram:
    """Merged multi-file program ready for execution or analysis."""

    modules: dict[Path, ModuleUnit]
    merged_ir: list[InstructionBase]
    merged_cfg: CFG
    merged_registry: FunctionRegistry
    language: Language
    import_graph: dict[Path, list[Path]]
    type_env_builder: TypeEnvironmentBuilder
    symbol_table: SymbolTable
    data_layout: dict[str, dict] = field(default_factory=dict)
    unresolved_imports: list[ImportRef] = field(default_factory=list)
    func_symbol_table: dict[CodeLabel, FuncRef] = field(default_factory=dict)
    class_symbol_table: dict[CodeLabel, ClassRef] = field(default_factory=dict)
```

Key changes:
- Drop `entry_module: Path`
- Add `language: Language`
- Add `type_env_builder: TypeEnvironmentBuilder` — accumulated during lowering, needed by type inference
- Add `symbol_table: SymbolTable` — extracted before IR lowering, needed by execution strategies
- Add `data_layout: dict[str, dict]` — memory layout (COBOL), empty dict default for other languages

`LinkedProgram` is self-contained: it carries everything `run_linked()` needs. The compilation step (both `compile_directory()` and single-module `run()`) populates all fields. For multi-module compilation, `type_env_builder` and `symbol_table` are merged across modules.

- [ ] **Step 4: Fix all existing LinkedProgram construction sites**

Search for all `LinkedProgram(` and `entry_module=` and update:
- `interpreter/project/linker.py`: `link_modules()` — drop `entry_module` param, add `language` param
- `tests/unit/project/test_types.py`: update test fixtures — drop `entry_module`, add `language`
- Any other construction sites

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/project/ -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
bd backup
git add interpreter/project/types.py interpreter/project/linker.py tests/unit/project/test_types.py
git commit -m "Add language field to LinkedProgram, drop entry_module"
```

---

### Task 3: Add `entry_points()` to `LinkedProgram`

**Files:**
- Modify: `interpreter/project/types.py`
- Modify: `tests/unit/project/test_types.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/project/test_types.py`:

```python
class TestLinkedProgramEntryPoints:
    def _make_linked_with_funcs(self, func_names: list[str]) -> LinkedProgram:
        """Build a LinkedProgram with FuncRefs in the func_symbol_table."""
        func_symbol_table = {
            CodeLabel(f"func_{name}"): FuncRef(
                name=FuncName(name), label=CodeLabel(f"func_{name}"), params=()
            )
            for name in func_names
        }
        return LinkedProgram(
            modules={},
            merged_ir=[],
            merged_cfg=CFG(blocks={}, entry=CodeLabel("entry")),
            merged_registry=FunctionRegistry(),
            language=Language.PYTHON,
            import_graph={},
            type_env_builder=TypeEnvironmentBuilder(),
            symbol_table=SymbolTable.empty(),
            func_symbol_table=func_symbol_table,
        )

    def test_entry_points_returns_all_by_default(self):
        lp = self._make_linked_with_funcs(["main", "helper", "setup"])
        result = lp.entry_points()
        assert len(result) == 3

    def test_entry_points_with_predicate(self):
        lp = self._make_linked_with_funcs(["main", "helper", "setup"])
        result = lp.entry_points(lambda f: f.name == FuncName("main"))
        assert len(result) == 1
        assert result[0].name == FuncName("main")

    def test_entry_points_empty_when_no_match(self):
        lp = self._make_linked_with_funcs(["helper", "setup"])
        result = lp.entry_points(lambda f: f.name == FuncName("main"))
        assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/project/test_types.py::TestLinkedProgramEntryPoints -v`
Expected: FAIL (no `entry_points` method)

- [ ] **Step 3: Implement entry_points()**

Add to `LinkedProgram` in `interpreter/project/types.py`:

```python
def entry_points(
    self, predicate: Callable[[FuncRef], bool] = lambda _: True,
) -> list[FuncRef]:
    """Query available entry point functions.

    Returns FuncRefs from the func_symbol_table matching the predicate.
    Default predicate returns all functions.
    """
    return [ref for ref in self.func_symbol_table.values() if predicate(ref)]
```

Add `Callable` to the imports:
```python
from typing import Callable, Sequence
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/project/test_types.py::TestLinkedProgramEntryPoints -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
bd backup
git add interpreter/project/types.py tests/unit/project/test_types.py
git commit -m "Add entry_points(predicate) discovery method to LinkedProgram"
```

---

### Task 4: Implement `run_linked()`

**Files:**
- Modify: `interpreter/run.py`
- Create: `tests/unit/test_run_linked.py`

- [ ] **Step 1: Write failing tests for run_linked()**

```python
# tests/unit/test_run_linked.py
"""Tests for run_linked() — execute a LinkedProgram with EntryPoint."""

from interpreter.constants import Language
from interpreter.func_name import FuncName
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run


class TestRunLinkedViaRun:
    """Test run_linked() indirectly through run(), which delegates to it."""

    def test_top_level_execution(self):
        source = "x = 10\ny = x + 5\n"
        vm = run(source, language=Language.PYTHON, entry_point=EntryPoint.top_level())
        from interpreter.var_name import VarName
        assert vm.current_frame.local_vars[VarName("x")].value == 10
        assert vm.current_frame.local_vars[VarName("y")].value == 15

    def test_function_entry_point(self):
        source = """
def add(a, b):
    return a + b

def main():
    result = add(3, 7)
"""
        vm = run(
            source,
            language=Language.PYTHON,
            entry_point=EntryPoint.function(lambda f: f.name == FuncName("main")),
            max_steps=50,
        )
        from interpreter.var_name import VarName
        assert vm.current_frame.local_vars[VarName("result")].value == 10

    def test_no_match_raises(self):
        source = "x = 1\n"
        import pytest
        with pytest.raises(ValueError, match="No function matched"):
            run(
                source,
                language=Language.PYTHON,
                entry_point=EntryPoint.function(lambda f: f.name == FuncName("nonexistent")),
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_run_linked.py -v`
Expected: FAIL (run() doesn't accept EntryPoint)

- [ ] **Step 3: Implement run_linked() and refactor run()**

In `interpreter/run.py`:

1. Add import for `EntryPoint`:
```python
from interpreter.project.entry_point import EntryPoint
```

2. Add `run_linked()` function (place above `run()`):

```python
def run_linked(
    linked: LinkedProgram,
    entry_point: EntryPoint,
    max_steps: int = 100,
    verbose: bool = False,
    backend: str = LLMProvider.CLAUDE,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
) -> VMState:
    """Execute a LinkedProgram with the given entry point.

    Args:
        linked: Pre-compiled program (single-module or multi-module).
        entry_point: How to enter the program — top_level() or function(predicate).
        max_steps: Maximum interpretation steps.
        verbose: Print IR, CFG, and step-by-step info.
        backend: LLM backend for interpreter fallback.
        unresolved_call_strategy: Resolution strategy for unknown calls.
    """
    strategies = _build_strategies_from_linked(linked)

    vm_config = VMConfig(
        backend=backend,
        max_steps=max_steps,
        verbose=verbose,
        source_language=linked.language,
        unresolved_call_strategy=unresolved_call_strategy,
    )

    if entry_point.is_top_level:
        vm, exec_stats = execute_cfg(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            vm_config,
            strategies,
        )
    else:
        # Phase 1: preamble
        module_entry = linked.merged_cfg.entry
        vm, preamble_stats = execute_cfg(
            linked.merged_cfg, module_entry, linked.merged_registry, vm_config, strategies
        )

        # Resolve entry point function
        func_ref = entry_point.resolve(list(linked.func_symbol_table.values()))
        func_label = _resolve_entry_function(vm, str(func_ref.name), linked.merged_cfg)

        # Phase 2: dispatch into target function
        remaining = max_steps - preamble_stats.steps
        phase2_config = replace(vm_config, max_steps=max(remaining, 0))
        vm, phase2_stats = execute_cfg(
            linked.merged_cfg, func_label, linked.merged_registry, phase2_config, strategies, vm=vm
        )

    vm.data_layout = linked.data_layout
    return vm
```

3. Add `_build_strategies_from_linked()`:

```python
def _build_strategies_from_linked(linked: LinkedProgram) -> ExecutionStrategies:
    """Build ExecutionStrategies from a LinkedProgram's data."""
    conversion_rules = DefaultTypeConversionRules()
    type_resolver = TypeResolver(conversion_rules)
    type_env = infer_types(
        linked.merged_ir,
        type_resolver,
        type_env_builder=linked.type_env_builder,
        func_symbol_table=linked.func_symbol_table,
        class_symbol_table=linked.class_symbol_table,
    )
    class_nodes = tuple(
        TypeNode(name=str(cls), parents=tuple(str(p) for p in parents))
        for cls, parents in linked.merged_registry.class_parents.items()
    )
    type_graph = TypeGraph(DEFAULT_TYPE_NODES + class_nodes)
    overload_resolver = OverloadResolver(
        ArityThenTypeStrategy(DefaultTypeCompatibility(type_graph)),
        FallbackFirstWithWarning(),
    )
    return ExecutionStrategies(
        type_env=type_env,
        conversion_rules=conversion_rules,
        overload_resolver=overload_resolver,
        binop_coercion=_binop_coercion_for_language(linked.language),
        func_symbol_table=linked.func_symbol_table,
        class_symbol_table=linked.class_symbol_table,
        field_fallback=_field_fallback_for_language(linked.language),
        symbol_table=linked.symbol_table,
    )
```

4. Refactor `run()` to build a single-module LinkedProgram and delegate:

```python
def run(
    source: str,
    language: str | Language = Language.PYTHON,
    entry_point: EntryPoint = EntryPoint.top_level(),
    backend: str = LLMProvider.CLAUDE,
    max_steps: int = 100,
    verbose: bool = False,
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    llm_client: Any = None,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
) -> VMState:
    """End-to-end: parse → lower → build LinkedProgram → run_linked.

    Convenience wrapper that compiles a single source string into a
    LinkedProgram and delegates execution to run_linked().
    """
    lang = Language(language)

    # 1. Parse + Lower
    resolved_frontend_type = (
        constants.FRONTEND_COBOL if lang == Language.COBOL else frontend_type
    )
    frontend = get_frontend(
        lang,
        frontend_type=resolved_frontend_type,
        llm_provider=backend,
        llm_client=llm_client,
    )
    instructions = frontend.lower(source.encode("utf-8"))

    if verbose:
        logger.info("═══ IR ═══")
        for inst in instructions:
            logger.info("  %s", inst)

    # 2. Build CFG + registry
    cfg = build_cfg(instructions)
    registry = build_registry(
        instructions,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )

    # 3. Build single-module LinkedProgram
    linked = LinkedProgram(
        modules={},
        merged_ir=list(instructions),
        merged_cfg=cfg,
        merged_registry=registry,
        language=lang,
        import_graph={},
        type_env_builder=frontend.type_env_builder,
        symbol_table=frontend.symbol_table,
        data_layout=frontend.data_layout,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )

    # 4. Delegate to run_linked
    return run_linked(
        linked,
        entry_point=entry_point,
        max_steps=max_steps,
        verbose=verbose,
        backend=backend,
        unresolved_call_strategy=unresolved_call_strategy,
    )
```

Note: This refactoring drops `PipelineStats` collection from `run()`. If stats are needed, they can be added back as a follow-up. The priority is getting the execution path correct.

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_run_linked.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Run full test suite — expect many failures**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: MANY FAILURES — existing callers still pass `entry_point=""` string. This is expected; Task 5 handles migration.

- [ ] **Step 6: Commit (with known broken callers)**

Do NOT commit yet — proceed to Task 5 to migrate callers first.

---

### Task 5: Migrate all 145 call sites

**Files:**
- Modify: ~74 test files + `interpreter.py`

Two categories:
1. **~119 sites with no `entry_point`** → add `entry_point=EntryPoint.top_level()`
2. **26 sites with `entry_point="main"` etc.** → change to `EntryPoint.function(lambda f: f.name == FuncName("main"))`

- [ ] **Step 1: Migrate callers with no entry_point**

For each file containing `= run(` without `entry_point=`, add `entry_point=EntryPoint.top_level()` and import `EntryPoint`:

```python
from interpreter.project.entry_point import EntryPoint

# Change:
vm = run(source, language=Language.PYTHON)
# To:
vm = run(source, language=Language.PYTHON, entry_point=EntryPoint.top_level())
```

Add the import to each file:
```python
from interpreter.project.entry_point import EntryPoint
```

- [ ] **Step 2: Migrate callers with string entry_point**

For each file containing `entry_point="something"`, change to predicate:

```python
from interpreter.project.entry_point import EntryPoint
from interpreter.func_name import FuncName

# Change:
vm = run(source, language=Language.PYTHON, entry_point="main")
# To:
vm = run(source, language=Language.PYTHON, entry_point=EntryPoint.function(lambda f: f.name == FuncName("main")))
```

- [ ] **Step 3: Migrate interpreter.py CLI**

In `interpreter.py`, the CLI passes `entry_point=args.entry` (a string from argparse). Change to:

```python
from interpreter.project.entry_point import EntryPoint
from interpreter.func_name import FuncName

entry = (
    EntryPoint.function(lambda f: f.name == FuncName(args.entry))
    if args.entry
    else EntryPoint.top_level()
)
vm = run(
    source,
    language=args.language,
    entry_point=entry,
    ...
)
```

- [ ] **Step 4: Run Black**

Run: `poetry run python -m black .`

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All ~13,168 tests pass

- [ ] **Step 6: Commit**

```bash
bd backup
git add -A
git commit -m "Migrate all 145 run() call sites to EntryPoint type"
```

---

### Task 6: Simplify `compile_directory()` and remove `compile_project()`

**Files:**
- Modify: `interpreter/project/compiler.py`
- Modify: `interpreter/project/linker.py`
- Modify: `tests/unit/project/test_compile_directory.py`
- Modify: `tests/integration/project/test_project_pipeline.py`
- Modify: `tests/integration/project/test_fixture_projects.py`
- Modify: `tests/integration/project/test_java_multi_module.py`

- [ ] **Step 1: Write test for new compile_directory signature (no entry_file)**

Update `tests/unit/project/test_compile_directory.py`:

```python
def test_compiles_all_python_files(self, tmp_path):
    (tmp_path / "main.py").write_text("from utils import helper\nresult = helper(42)\n")
    (tmp_path / "utils.py").write_text("def helper(x):\n    return x + 1\n")
    (tmp_path / "orphan.py").write_text("CONSTANT = 99\n")

    linked = compile_directory(tmp_path, Language.PYTHON)

    assert isinstance(linked, LinkedProgram)
    assert len(linked.modules) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/project/test_compile_directory.py::TestCompileDirectory::test_compiles_all_python_files -v`
Expected: FAIL (missing `entry_file` argument)

- [ ] **Step 3: Remove compile_project(), simplify compile_directory()**

In `interpreter/project/compiler.py`:

1. Delete `compile_project()` function entirely.
2. Simplify `compile_directory()`:

```python
def compile_directory(
    directory: Path,
    language: Language,
) -> LinkedProgram:
    """Compile all source files in a directory tree.

    Compiles every file matching the language's extensions and links
    them into a single LinkedProgram.

    Args:
        directory: Root directory to scan recursively.
        language: Source language — determines which file extensions to include.

    Returns:
        A LinkedProgram with all files compiled and linked.
    """
    directory = directory.resolve()

    extensions = _LANGUAGE_EXTENSIONS.get(language, ())
    source_files = sorted(
        f.resolve()
        for ext in extensions
        for f in directory.rglob(f"*{ext}")
        if f.is_file()
    )

    modules = {path: compile_module(path, language) for path in source_files}
    import_graph = {path: [] for path in source_files}
    topo_order = list(source_files)

    return link_modules(
        modules=modules,
        import_graph=import_graph,
        project_root=directory,
        topo_order=topo_order,
        language=language,
    )
```

3. Update `link_modules()` in `interpreter/project/linker.py`: drop `entry_module` param, add `language` param, pass `language` to `LinkedProgram` constructor.

- [ ] **Step 4: Update all compile_directory() and compile_project() call sites**

- `tests/unit/project/test_compile_directory.py`: drop `entry_file` arg from all calls, remove `test_entry_module_set_correctly`
- `tests/integration/project/test_project_pipeline.py`: change `compile_project()` → `compile_directory()` with directory arg
- `tests/integration/project/test_fixture_projects.py`: same migration
- `tests/integration/project/test_java_multi_module.py`: same migration

- [ ] **Step 5: Run Black**

Run: `poetry run python -m black .`

- [ ] **Step 6: Run full test suite**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
bd backup
git add interpreter/project/compiler.py interpreter/project/linker.py tests/
git commit -m "Remove compile_project(), simplify compile_directory() to drop entry_file"
```

---

### Task 7: Update ADRs and documentation

**Files:**
- Modify: `docs/architectural-design-decisions.md`

- [ ] **Step 1: Add ADR entry**

Append to `docs/architectural-design-decisions.md`:

```markdown
### 2026-03-31: EntryPoint type and compilation consolidation

**Context:** `compile_project()` performed BFS import-tracing to discover files, while `compile_directory()` compiled all files in a directory. The BFS machinery added complexity without benefit — preamble ordering doesn't affect correctness since all modules register symbols via CONST+DECL_VAR. Meanwhile, `run()` used `entry_point: str = ""` where empty string implicitly meant "run top-to-bottom."

**Decision:**
1. Remove `compile_project()`. `compile_directory(directory, language)` is the sole compilation entry point.
2. Introduce `EntryPoint` type with `function(predicate)` and `top_level()` factory methods, replacing stringly-typed entry point.
3. Add `run_linked(linked, entry_point)` as the universal execution function. `run()` builds a single-module `LinkedProgram` and delegates to it.
4. `LinkedProgram` drops `entry_module`, gains `language` and `entry_points(predicate)`.

**Consequences:** Every caller explicitly states execution intent. Import-tracing utilities (`ImportResolver`, `topological_sort`, `extract_imports`) remain available for analysis but are not in the compilation path. 145 call sites migrated.
```

- [ ] **Step 2: Commit**

```bash
bd backup
git add docs/architectural-design-decisions.md
git commit -m "Add ADR: EntryPoint type and compilation consolidation"
```

---

### Task 8: File per-frontend multi-module integration test issues

**Files:** None (Beads issues only)

- [ ] **Step 1: File 16 Beads issues**

File one issue per frontend for multi-module `compile_directory() → run_linked()` integration tests:

```bash
bd create "Multi-module integration test: Python" --description="Write integration test: multi-file Python project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions. Test cross-module function calls." -t feature -p 2

bd create "Multi-module integration test: JavaScript" --description="Write integration test: multi-file JavaScript project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions. Test cross-module function calls via require/import." -t feature -p 2

bd create "Multi-module integration test: TypeScript" --description="Write integration test: multi-file TypeScript project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions." -t feature -p 2

bd create "Multi-module integration test: Java" --description="Migrate existing test_java_multi_module.py to use run_linked() with EntryPoint. Add concrete value assertions for cross-module dispatch." -t feature -p 2

bd create "Multi-module integration test: Go" --description="Write integration test: multi-file Go project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions." -t feature -p 2

bd create "Multi-module integration test: Kotlin" --description="Write integration test: multi-file Kotlin project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions." -t feature -p 2

bd create "Multi-module integration test: C#" --description="Write integration test: multi-file C# project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions." -t feature -p 2

bd create "Multi-module integration test: Ruby" --description="Write integration test: multi-file Ruby project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions." -t feature -p 2

bd create "Multi-module integration test: PHP" --description="Write integration test: multi-file PHP project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions. Remember <?php tag." -t feature -p 2

bd create "Multi-module integration test: Lua" --description="Write integration test: multi-file Lua project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions." -t feature -p 2

bd create "Multi-module integration test: Rust" --description="Write integration test: multi-file Rust project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions." -t feature -p 2

bd create "Multi-module integration test: C" --description="Write integration test: multi-file C project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions." -t feature -p 2

bd create "Multi-module integration test: C++" --description="Write integration test: multi-file C++ project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions." -t feature -p 2

bd create "Multi-module integration test: Scala" --description="Write integration test: multi-file Scala project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions." -t feature -p 2

bd create "Multi-module integration test: Pascal" --description="Write integration test: multi-file Pascal project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions." -t feature -p 2

bd create "Multi-module integration test: COBOL" --description="Write integration test: multi-file COBOL project in tmp_path, compile_directory(), run_linked() with EntryPoint.function(...), concrete value assertions. Uses FRONTEND_COBOL." -t feature -p 2
```

- [ ] **Step 2: Backup Beads**

```bash
bd backup
```
