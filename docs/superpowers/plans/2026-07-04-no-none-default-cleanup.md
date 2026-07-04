# No-`None`-Default Parameter Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the 49 confirmed-fixable `None`-default parameters (buckets A–D of red-dragon-nz4y) across `interpreter/`, replacing each with an empty structure, an existing/new null-object sentinel, or (for `vm`/`initial_vm`) a required argument — per `.claude/conditional/design-principles.md`'s "No `None` as a default parameter" rule.

**Architecture:** No new abstractions beyond one new sentinel (`NO_NODE`, for tree-sitter source nodes) and one new no-op callable (`_NO_CICS_TEXT_PARSER`). Every other fix reuses a pattern or object that already exists in the codebase (`NO_REGISTER`, `NullFrontendObserver()`, `CobolASG()`, `TypeEnvironment(...)`, `TypeEnvironmentBuilder()`, `Path(".")`, `[]`/`{}`). Each task is scoped to one file (or one tightly-coupled pair of functions in the same file) so it can be reviewed independently.

**Tech Stack:** Python 3.13, pytest, `pylint_plugins/no_none_default.py` (the checker that found these sites) for regression verification.

## Global Constraints

- Every fix in this plan is **behavior-preserving** — the goal is to make the signature itself enforce what the body already did via `or []` / `if x is None: x = ...`, not to change what callers get back. The one exception is Task 15 (`vm`/`initial_vm`), which is a deliberate behavior change (making a previously-optional argument required) with a real call-site migration.
- Do not touch any bucket-E (deferred) or red-dragon-79iv (`cobol_parser`/`llm_client`) site. If a task's file also contains one of those, leave it untouched — the task descriptions below call this out explicitly wherever it applies.
- Run `poetry run python -m pytest <affected test file(s)> -q` after every task. Run the **full** suite (`poetry run python -m pytest -q`, several minutes — see project memory on this) at the end of each phase, not just at the very end.
- `git commit` triggers a pre-commit hook that reruns the full suite — always commit with `run_in_background: true` or an explicit multi-minute timeout, never the default.
- After all tasks: rerun `poetry run pylint --load-plugins=pylint_plugins.no_none_default --disable=all --enable=no-none-default interpreter/` and confirm the count has dropped from 70 to 21 (18 deferred bucket E + 3 red-dragon-79iv).

---

## Phase 0 — Shared sentinel (prerequisite for Phase 2's `node`-family tasks)

### Task 1: Add the `NO_NODE` sentinel

**Files:**
- Modify: `interpreter/frontends/_base.py` (add near top, after imports)
- Test: `tests/unit/frontends/test_base_no_node.py` (new file)

**Interfaces:**
- Produces: `NO_NODE` — a module-level sentinel object, importable as `from interpreter.frontends._base import NO_NODE`. Used as the default value for every `node: Any = None` parameter fixed in Phase 2.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/frontends/test_base_no_node.py
from interpreter.frontends._base import NO_NODE


def test_no_node_is_a_stable_singleton():
    from interpreter.frontends._base import NO_NODE as no_node_again

    assert NO_NODE is no_node_again
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/frontends/test_base_no_node.py -v`
Expected: FAIL with `ImportError: cannot import name 'NO_NODE' from 'interpreter.frontends._base'`

- [ ] **Step 3: Write minimal implementation**

Find the top of `interpreter/frontends/_base.py` (its imports section) and add, immediately after the last import:

```python
NO_NODE = object()  # sentinel: no source-tree node available (diagnostics/source-location only)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/frontends/test_base_no_node.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/_base.py tests/unit/frontends/test_base_no_node.py
git commit -m "feat(frontends): add NO_NODE sentinel for tree-sitter node defaults"
```

---

## Phase 1 — Bucket A (pure collections + body-confirmed static fallbacks)

### Task 2: `interpreter/cobol/cobol_parser.py` — `copybook_dirs` (2 sites)

**Files:**
- Modify: `interpreter/cobol/cobol_parser.py:51` (`ProLeapCobolParser.__init__`), `interpreter/cobol/cobol_parser.py:121` (`make_cobol_parser`)
- Test: `tests/unit/cobol/test_cobol_parser_copybook_dirs_default.py` (new file)

**Interfaces:**
- Consumes: nothing new.
- Produces: `ProLeapCobolParser(runner, bridge_jar, copybook_dirs: list[Path] = [])`, `make_cobol_parser(copybook_dirs: list[Path] = []) -> ProLeapCobolParser` — same call shape as before, just no `None` default.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cobol/test_cobol_parser_copybook_dirs_default.py
import inspect

from interpreter.cobol.cobol_parser import ProLeapCobolParser, make_cobol_parser


def test_proleap_cobol_parser_copybook_dirs_defaults_to_empty_list():
    sig = inspect.signature(ProLeapCobolParser.__init__)
    assert sig.parameters["copybook_dirs"].default == []


def test_make_cobol_parser_copybook_dirs_defaults_to_empty_list():
    sig = inspect.signature(make_cobol_parser)
    assert sig.parameters["copybook_dirs"].default == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cobol/test_cobol_parser_copybook_dirs_default.py -v`
Expected: FAIL — both assertions fail (`default` is `None`, not `[]`)

- [ ] **Step 3: Write minimal implementation**

In `interpreter/cobol/cobol_parser.py`, change both signatures:

```python
def make_cobol_parser(
    copybook_dirs: list[Path] = [],
) -> ProLeapCobolParser:
```

```python
    def __init__(
        self,
        runner: SubprocessRunner,
        bridge_jar: str,
        copybook_dirs: list[Path] = [],
    ):
```

Search the body of both for `copybook_dirs or` / `if copybook_dirs is None` and delete the fallback if present (read the current body first — if it already just stores/passes `copybook_dirs` through with no `None`-check, no further body change is needed).

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cobol/test_cobol_parser_copybook_dirs_default.py -v`
Expected: PASS

Also run the existing copybook test to confirm no regression:
Run: `PROLEAP_BRIDGE_JAR=$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/unit/cobol/test_cobol_parser_copybook.py -v`
Expected: PASS (unchanged)

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/cobol_parser.py tests/unit/cobol/test_cobol_parser_copybook_dirs_default.py
git commit -m "fix(cobol): copybook_dirs defaults to [] instead of None (cobol_parser.py)"
```

### Task 3: `interpreter/cobol/cobol_frontend.py` — `resolved_imports` (bucket A) — `cics_text_parser` SKIPPED

**SCOPE UPDATE (2026-07-04):** commit `968e7772` added an approved-but-unimplemented design (`docs/superpowers/specs/2026-07-04-generic-dialect-parsers-design.md`) that will remove `cics_text_parser` entirely, replacing it with a generic `DialectParser` array. **Do not touch `cics_text_parser` in this task — implement only `resolved_imports` (bucket A).** Ignore every `_NO_CICS_TEXT_PARSER` reference below; that part of this task is deferred, not part of this epic.

Only `resolved_imports` on `CobolFrontend.lower` (line 175) is in scope.

**Files:**
- Modify: `interpreter/cobol/cobol_frontend.py:66,175`
- Test: `tests/unit/cobol/test_cobol_frontend_lower_defaults.py` (new file)

**Interfaces:**
- Consumes: `_NO_CICS_TEXT_PARSER` — defined in this task's Step 3 (in `interpreter/cobol/cobol_statements.py`, next to `_cics_text_parser`'s `ContextVar` declaration around line 29), and reused by later Tasks 9, 10, 12.
- Produces: `CobolFrontend.__init__(self, cobol_parser: CobolParser, observer=NullFrontendObserver(), extension_strategies=(), cics_text_parser: CicsTextParserFn = _NO_CICS_TEXT_PARSER)`; `CobolFrontend.lower(self, source: bytes, namespace_resolver=Frontend._NULL_RESOLVER, resolved_imports: dict[str, PathName] = {}) -> list[InstructionBase]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cobol/test_cobol_frontend_lower_defaults.py
import inspect

import pytest

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_statements import _NO_CICS_TEXT_PARSER


def test_lower_resolved_imports_defaults_to_empty_dict():
    sig = inspect.signature(CobolFrontend.lower)
    assert sig.parameters["resolved_imports"].default == {}


def test_init_cics_text_parser_defaults_to_no_op():
    sig = inspect.signature(CobolFrontend.__init__)
    assert sig.parameters["cics_text_parser"].default is _NO_CICS_TEXT_PARSER


def test_no_cics_text_parser_raises_when_invoked():
    with pytest.raises(RuntimeError, match="CICS statement encountered"):
        _NO_CICS_TEXT_PARSER("anything")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cobol/test_cobol_frontend_lower_defaults.py -v`
Expected: FAIL — `ImportError` for `_NO_CICS_TEXT_PARSER` (not yet defined), or once Step 3's `cobol_statements.py` edit is in place, `resolved_imports`/`cics_text_parser` defaults still `None`.

- [ ] **Step 3: Write minimal implementation**

First, in `interpreter/cobol/cobol_statements.py`, find the `_cics_text_parser: ContextVar[...]` declaration (around line 29) and add just above it (skip this step if Task 9 already added it — check first, since Tasks 3 and 9 both touch this file and only one needs to define it):

```python
def _no_cics_text_parser(*args: object, **kwargs: object) -> object:
    """Raised when a CICS statement is lowered without a CICS text parser
    configured — should only ever be reached by a program with real CICS
    statements that forgot to pass cics_text_parser."""
    raise RuntimeError(
        "CICS statement encountered but no cics_text_parser was configured"
    )


_NO_CICS_TEXT_PARSER: CicsTextParserFn = _no_cics_text_parser
```

Then in `interpreter/cobol/cobol_frontend.py`, import it and change both signatures:

```python
from interpreter.cobol.cobol_statements import _NO_CICS_TEXT_PARSER
```

```python
    def __init__(
        self,
        cobol_parser: CobolParser,
        observer: FrontendObserver = NullFrontendObserver(),
        extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
        cics_text_parser: CicsTextParserFn = _NO_CICS_TEXT_PARSER,
    ):
```

```python
    def lower(
        self,
        source: bytes,
        namespace_resolver: NamespaceResolver = Frontend._NULL_RESOLVER,
        resolved_imports: dict[str, PathName] = {},
    ) -> list[InstructionBase]:
```

Find where `resolved_imports` is used in the body (likely `resolved_imports or {}` somewhere) and delete that fallback — the parameter is never `None` now. Do **not** change anything about how `self._cics_text_parser` is later `.set()`/`.reset()` on the `_cics_text_parser` ContextVar — that mechanism is unaffected; only the constructor parameter's own default changes.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cobol/test_cobol_frontend_lower_defaults.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/cobol_frontend.py tests/unit/cobol/test_cobol_frontend_lower_defaults.py
git commit -m "fix(cobol): resolved_imports defaults to {} instead of None (cobol_frontend.py)"
```

### Task 4: `interpreter/cobol/real_file_provider.py` — `file_control`, `path_overrides`

**Files:**
- Modify: `interpreter/cobol/real_file_provider.py:55`
- Test: `tests/unit/cobol/test_real_file_provider_defaults.py` (new file)

**Interfaces:**
- Produces: the file provider's `__init__(base_dir: Path, file_control: list[FileControlEntry] = [], path_overrides: dict[str, Path] = {})`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cobol/test_real_file_provider_defaults.py
import inspect

from interpreter.cobol.real_file_provider import RealFileProvider


def test_file_control_and_path_overrides_default_to_empty():
    sig = inspect.signature(RealFileProvider.__init__)
    assert sig.parameters["file_control"].default == []
    assert sig.parameters["path_overrides"].default == {}
```

(If the class name differs from `RealFileProvider`, use the actual class name found at `real_file_provider.py:55` when writing this test — check the file first.)

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cobol/test_real_file_provider_defaults.py -v`
Expected: FAIL (both defaults are `None`)

- [ ] **Step 3: Write minimal implementation**

Change the constructor signature to:

```python
    def __init__(
        self,
        base_dir: Path,
        file_control: list[FileControlEntry] = [],
        path_overrides: dict[str, Path] = {},
    ) -> None:
```

Delete any `file_control or []` / `path_overrides or {}` fallback in the body.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cobol/test_real_file_provider_defaults.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/real_file_provider.py tests/unit/cobol/test_real_file_provider_defaults.py
git commit -m "fix(cobol): file_control/path_overrides default to [] / {} instead of None"
```

### Task 5: `interpreter/instructions.py` — `params`

**Files:**
- Modify: `interpreter/instructions.py:291` (`Const.func_ref` classmethod)
- Test: `tests/unit/test_instructions_func_ref_defaults.py` (new file)

**Interfaces:**
- Produces: `Const.func_ref(cls, result_reg, value, params: list[TypeExpr] = [], return_type: TypeExpr = UNKNOWN, **kw) -> "Const"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_instructions_func_ref_defaults.py
import inspect

from interpreter.instructions import Const


def test_func_ref_params_defaults_to_empty_list():
    sig = inspect.signature(Const.func_ref)
    assert sig.parameters["params"].default == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_instructions_func_ref_defaults.py -v`
Expected: FAIL (`default` is `None`)

- [ ] **Step 3: Write minimal implementation**

```python
    def func_ref(
        cls,
        result_reg: Register,
        value: Any,
        params: list[TypeExpr] = [],
        return_type: TypeExpr = UNKNOWN,
        **kw: Any,
    ) -> "Const":
```

Delete any `params or []` fallback in the body.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_instructions_func_ref_defaults.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/instructions.py tests/unit/test_instructions_func_ref_defaults.py
git commit -m "fix(ir): Const.func_ref params defaults to [] instead of None"
```

### Task 6: `interpreter/project/resolver.py` — `source_roots`

**Files:**
- Modify: `interpreter/project/resolver.py:188`
- Test: `tests/unit/project/test_resolver_source_roots_default.py` (new file)

**Interfaces:**
- Produces: the resolver class's `__init__(self, source_roots: list[Path] = [])`.

- [ ] **Step 1: Write the failing test**

Read `interpreter/project/resolver.py` around line 188 first to get the exact class name, then:

```python
# tests/unit/project/test_resolver_source_roots_default.py
import inspect

# Replace ResolverClassName with the actual class name at resolver.py:188
from interpreter.project.resolver import ResolverClassName


def test_source_roots_defaults_to_empty_list():
    sig = inspect.signature(ResolverClassName.__init__)
    assert sig.parameters["source_roots"].default == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/project/test_resolver_source_roots_default.py -v`
Expected: FAIL (`default` is `None`)

- [ ] **Step 3: Write minimal implementation**

Change the constructor to `def __init__(self, source_roots: list[Path] = []):` and delete any `source_roots or []` fallback in the body.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/project/test_resolver_source_roots_default.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/project/resolver.py tests/unit/project/test_resolver_source_roots_default.py
git commit -m "fix(project): source_roots defaults to [] instead of None (resolver.py)"
```

### Task 7: `interpreter/project/linker.py` — `data_layout` (bucket A) + `type_env_builder` (bucket B)

Both params live on `link_modules`; fixed together since it's one signature. **`symbol_table` in this same function is explicitly OUT OF SCOPE — leave it exactly as-is** (mutated in place, deferred per user decision).

**Files:**
- Modify: `interpreter/project/linker.py:455` (`link_modules`)
- Test: `tests/unit/project/test_linker_defaults.py` (new file)

**Interfaces:**
- Produces: `link_modules(modules, import_graph, project_root, topo_order, language, type_env_builder: TypeEnvironmentBuilder = TypeEnvironmentBuilder(), symbol_table: SymbolTable | None = None, data_layout: dict[str, dict] = {}) -> LinkedProgram`. Note `symbol_table` keeps its `None` default — not touched.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/project/test_linker_defaults.py
import inspect

from interpreter.project.linker import link_modules


def test_data_layout_and_type_env_builder_default_away_from_none():
    sig = inspect.signature(link_modules)
    assert sig.parameters["data_layout"].default == {}
    assert sig.parameters["type_env_builder"].default is not None
    # symbol_table stays untouched — deferred, mutated in place downstream
    assert sig.parameters["symbol_table"].default is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/project/test_linker_defaults.py -v`
Expected: FAIL — `data_layout` default is `None`, `type_env_builder` default is `None`

- [ ] **Step 3: Write minimal implementation**

In `interpreter/project/linker.py`, change the signature (leave `symbol_table` line untouched):

```python
def link_modules(
    modules: dict[Path, ModuleUnit],
    import_graph: dict[Path, list[Path]],
    project_root: Path,
    topo_order: list[Path],
    language: Language,
    type_env_builder: TypeEnvironmentBuilder = TypeEnvironmentBuilder(),
    symbol_table: SymbolTable | None = None,
    data_layout: dict[str, dict] = {},
) -> LinkedProgram:
```

Then delete the now-dead fallback lines in the body:

```python
    if type_env_builder is None:
        type_env_builder = TypeEnvironmentBuilder()
    if data_layout is None:
        data_layout = {}
```

**Leave `if symbol_table is None: symbol_table = SymbolTable.empty()` exactly as it is** — do not touch it.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/project/test_linker_defaults.py -v`
Expected: PASS

Run the existing linker test suite too:
Run: `poetry run python -m pytest tests/unit/project/ -k linker -v`
Expected: PASS (unchanged)

- [ ] **Step 5: Commit**

```bash
git add interpreter/project/linker.py tests/unit/project/test_linker_defaults.py
git commit -m "fix(project): data_layout/type_env_builder default away from None in link_modules"
```

### Task 8: `interpreter/project/compiler.py` — `copybook_dirs` (bucket A only; `source` in same function stays untouched, deferred)

**Files:**
- Modify: `interpreter/project/compiler.py:163` (`compile_module`)
- Test: `tests/unit/project/test_compiler_copybook_dirs_default.py` (new file)

**Interfaces:**
- Produces: `compile_module(file_path, language, source: bytes | None = None, namespace_resolver=NamespaceResolver(), copybook_dirs: list[Path] = []) -> ModuleUnit`. `source` is untouched.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/project/test_compiler_copybook_dirs_default.py
import inspect

from interpreter.project.compiler import compile_module


def test_copybook_dirs_defaults_to_empty_list():
    sig = inspect.signature(compile_module)
    assert sig.parameters["copybook_dirs"].default == []
    # source stays untouched — deferred, its None means "derive from file_path"
    assert sig.parameters["source"].default is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/project/test_compiler_copybook_dirs_default.py -v`
Expected: FAIL (`copybook_dirs` default is `None`)

- [ ] **Step 3: Write minimal implementation**

```python
def compile_module(
    file_path: Path,
    language: Language,
    source: bytes | None = None,
    namespace_resolver: NamespaceResolver = NamespaceResolver(),
    copybook_dirs: list[Path] = [],
) -> ModuleUnit:
```

Delete any `copybook_dirs or []` fallback in the body. **Do not touch `source`.**

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/project/test_compiler_copybook_dirs_default.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/project/compiler.py tests/unit/project/test_compiler_copybook_dirs_default.py
git commit -m "fix(project): copybook_dirs defaults to [] instead of None (compiler.py)"
```

### Task 9: `interpreter/project/cobol_compile.py` — `copybook_dirs`, `extra_subprogram_sources`, `program_source_dir` (bucket A) — `cics_text_parser` SKIPPED

**SCOPE UPDATE (2026-07-04):** commit `968e7772` added an approved-but-unimplemented design (`docs/superpowers/specs/2026-07-04-generic-dialect-parsers-design.md`) that will remove `cics_text_parser` entirely, replacing it with a generic `DialectParser` array. **Do not touch `cics_text_parser` in this task — implement only `copybook_dirs`, `extra_subprogram_sources`, `program_source_dir`.** Ignore every `_NO_CICS_TEXT_PARSER` reference below (including the "define it in `cobol_statements.py`" step); that part of this task is deferred, not part of this epic.

Both `compile_cobol_module` (line 72) and `compile_cobol` (line 109) get fixed together — same file, same shape — for the three in-scope params only. **`ast_cache_dir` in `compile_cobol` stays exactly as-is** (deferred, lifecycle sentinel).

**Files:**
- Modify: `interpreter/project/cobol_compile.py:72,109`
- Test: `tests/unit/project/test_cobol_compile_defaults.py` (new file)

**Interfaces:**
- Consumes: `_NO_CICS_TEXT_PARSER` (defined in this same task, Step 3 — no separate prerequisite task needed since it's only used here and in Tasks 10/12/13, all part of this plan; define it once in `interpreter/cobol/cobol_statements.py` next to `CicsTextParserFn`/`_cics_text_parser` so every consumer imports the same instance).
- Produces: `compile_cobol_module(source, *, parser, copybook_dirs: list[Path] = [], extension_strategies=(), cics_text_parser: CicsTextParserFn = _NO_CICS_TEXT_PARSER, observer=NullFrontendObserver(), path=Path("__main__.cbl"), ast_path) -> tuple[Any, ModuleUnit]` and the equivalent shape for `compile_cobol` (plus its `extra_subprogram_sources: dict[str, bytes] = {}`, `program_source_dir: Path = Path(".")`, `ast_cache_dir: Path | None = None` **unchanged**).

- [ ] **Step 1: Write the failing test**

First, check whether Task 3 already added `_NO_CICS_TEXT_PARSER` to `interpreter/cobol/cobol_statements.py` (if these tasks are being executed in order, it will have). If not yet present, find the `_cics_text_parser: ContextVar[...]` declaration (around line 29) and add just above it:

```python
def _no_cics_text_parser(*args: object, **kwargs: object) -> object:
    """Raised when a CICS statement is lowered without a CICS text parser
    configured — should only ever be reached by a program with real CICS
    statements that forgot to pass cics_text_parser."""
    raise RuntimeError(
        "CICS statement encountered but no cics_text_parser was configured"
    )


_NO_CICS_TEXT_PARSER: CicsTextParserFn = _no_cics_text_parser
```

Now the test:

```python
# tests/unit/project/test_cobol_compile_defaults.py
import inspect

import pytest

from interpreter.cobol.cobol_statements import _NO_CICS_TEXT_PARSER
from interpreter.project.cobol_compile import compile_cobol, compile_cobol_module


def test_compile_cobol_module_defaults_away_from_none():
    sig = inspect.signature(compile_cobol_module)
    assert sig.parameters["copybook_dirs"].default == []
    assert sig.parameters["cics_text_parser"].default is _NO_CICS_TEXT_PARSER


def test_compile_cobol_defaults_away_from_none():
    sig = inspect.signature(compile_cobol)
    assert sig.parameters["copybook_dirs"].default == []
    assert sig.parameters["extra_subprogram_sources"].default == {}
    assert sig.parameters["program_source_dir"].default == pytest.importorskip(
        "pathlib"
    ).Path(".")
    assert sig.parameters["cics_text_parser"].default is _NO_CICS_TEXT_PARSER
    # ast_cache_dir stays untouched — deferred, ephemeral-vs-owned lifecycle sentinel
    assert sig.parameters["ast_cache_dir"].default is None


def test_no_cics_text_parser_raises_when_invoked():
    with pytest.raises(RuntimeError, match="CICS statement encountered"):
        _NO_CICS_TEXT_PARSER("anything")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/project/test_cobol_compile_defaults.py -v`
Expected: FAIL — `ImportError` for `_NO_CICS_TEXT_PARSER` (not yet defined) or, once Step 1's `cobol_statements.py` edit is in place, defaults still `None`/`[]`-missing on `compile_cobol_module`/`compile_cobol`.

- [ ] **Step 3: Write minimal implementation**

In `interpreter/project/cobol_compile.py`, import `_NO_CICS_TEXT_PARSER`:

```python
from interpreter.cobol.cobol_statements import _NO_CICS_TEXT_PARSER
```

Change `compile_cobol_module`'s signature:

```python
def compile_cobol_module(
    source: bytes,
    *,
    parser: Any,
    copybook_dirs: list[Path] = [],
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = _NO_CICS_TEXT_PARSER,
    observer: FrontendObserver = NullFrontendObserver(),
    path: Path = Path("__main__.cbl"),
    ast_path: Path,
) -> tuple[Any, ModuleUnit]:
```

Change `compile_cobol`'s signature (leave `ast_cache_dir` untouched):

```python
def compile_cobol(
    source: bytes,
    *,
    parser: Any,
    copybook_dirs: list[Path] = [],
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = _NO_CICS_TEXT_PARSER,
    observer: FrontendObserver = NullFrontendObserver(),
    program_source_dir: Path = Path("."),
    extra_subprogram_sources: dict[str, bytes] = {},
    source_transform: Callable[[str], str] = lambda s: s,
    ast_cache_dir: Path | None = None,
) -> tuple[Any, LinkedProgram]:
```

Delete these now-dead lines inside `compile_cobol`'s body:

```python
        base = program_source_dir or Path(".")
```
becomes:
```python
        base = program_source_dir
```

And:
```python
        sub_sources: dict[str, bytes] = dict(extra_subprogram_sources or {})
```
becomes:
```python
        sub_sources: dict[str, bytes] = dict(extra_subprogram_sources)
```

**Do not touch** the `if ast_cache_dir is None:` block — leave it exactly as-is.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/project/test_cobol_compile_defaults.py -v`
Expected: PASS

Run the existing coverage-gaps suite for this module (integration-level, exercises `compile_cobol` end to end):
Run: `PROLEAP_BRIDGE_JAR=$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/test_cobol_coverage_gaps.py -q`
Expected: PASS (unchanged — this is the file with all the intrinsic-function tests from earlier work; must still be fully green)

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/cobol_statements.py interpreter/project/cobol_compile.py tests/unit/project/test_cobol_compile_defaults.py
git commit -m "fix(cobol): copybook_dirs/extra_subprogram_sources/program_source_dir/cics_text_parser default away from None (cobol_compile.py)"
```

### Task 10: `interpreter/project/cobol_connections.py` — ALREADY DONE by Task 9, this task is verification-only

**SCOPE UPDATE #2 (2026-07-04):** Task 9's implementer found that fixing `cobol_compile.py` alone would break `extract_cobol_connections`'s existing callers (`extract_cobol_connections` forwards `copybook_dirs`/`program_source_dir`/`extra_subprogram_sources` straight through to `compile_cobol`, unconditionally — several existing tests pass `extra_subprogram_sources` while omitting `program_source_dir`, and once `compile_cobol`'s dead fallbacks were deleted, an explicitly-forwarded `None` crashed with `TypeError`). Task 9's implementer reproduced this failure (12 tests) and fixed `cobol_connections.py`'s matching 3 defaults in lockstep, verified independently by the Task 9 reviewer (who reverted the file and reproduced the exact same 12 failures before confirming the fix). **The production fix for this task is therefore already committed** (as part of Task 9's commit `2d98aa60`).

This task now only needs to: (1) confirm the 3 signatures already match the target shape below, (2) add the dedicated test file this task was going to add anyway (harmless if it duplicates part of what Task 9's own test already covers), (3) not attempt to re-implement anything.

(The original scope note about `cics_text_parser` still applies — it stays untouched, deferred alongside the `DialectParser` migration.)

**Files:**
- Modify: `interpreter/project/cobol_connections.py:55` (`extract_cobol_connections`)
- Test: `tests/unit/project/test_cobol_connections_defaults.py` (new file)

**Interfaces:**
- Consumes: `_NO_CICS_TEXT_PARSER` from Task 9 (`interpreter.cobol.cobol_statements`).
- Produces: `extract_cobol_connections(source, *, copybook_dirs: list[Path] = [], program_source_dir: Path = Path("."), extra_subprogram_sources: dict[str, bytes] = {}, parser, extension_strategies=(), cics_text_parser=_NO_CICS_TEXT_PARSER, observer=NullFrontendObserver(), source_transform=lambda s: s) -> list[Connection]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/project/test_cobol_connections_defaults.py
import inspect
from pathlib import Path

from interpreter.cobol.cobol_statements import _NO_CICS_TEXT_PARSER
from interpreter.project.cobol_connections import extract_cobol_connections


def test_extract_cobol_connections_defaults_away_from_none():
    sig = inspect.signature(extract_cobol_connections)
    assert sig.parameters["copybook_dirs"].default == []
    assert sig.parameters["program_source_dir"].default == Path(".")
    assert sig.parameters["extra_subprogram_sources"].default == {}
    assert sig.parameters["cics_text_parser"].default is _NO_CICS_TEXT_PARSER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/project/test_cobol_connections_defaults.py -v`
Expected: FAIL — all four defaults still `None`

- [ ] **Step 3: Write minimal implementation**

In `interpreter/project/cobol_connections.py`, import `_NO_CICS_TEXT_PARSER` and change the signature:

```python
from interpreter.cobol.cobol_statements import _NO_CICS_TEXT_PARSER


def extract_cobol_connections(
    source: bytes,
    *,
    copybook_dirs: list[Path] = [],
    program_source_dir: Path = Path("."),
    extra_subprogram_sources: dict[str, bytes] = {},
    parser: Any,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = _NO_CICS_TEXT_PARSER,
    observer: FrontendObserver = NullFrontendObserver(),
    source_transform: Callable[[str], str] = lambda s: s,
) -> list[Connection]:
```

Delete any `program_source_dir or Path(".")` / `dict(extra_subprogram_sources or {})` fallback in the body (same shape as Task 9 — check the body first, since this function may share `_resolve_call_sources`-style logic with `cobol_compile.py`).

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/project/test_cobol_connections_defaults.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/project/cobol_connections.py tests/unit/project/test_cobol_connections_defaults.py
git commit -m "fix(cobol): copybook_dirs/extra_subprogram_sources/program_source_dir/cics_text_parser default away from None (cobol_connections.py)"
```

### Task 11: `interpreter/run.py` — `copybook_dirs` only (bucket A; `llm_client`/`io_provider` in the same `run()` signature stay untouched — 79iv/deferred)

**Files:**
- Modify: `interpreter/run.py:1237` (`run`)
- Test: `tests/unit/test_run_copybook_dirs_default.py` (new file)

**Interfaces:**
- Produces: `run(source, language=Language.PYTHON, entry_point=..., backend=..., max_steps=100, verbose=False, frontend_type=..., llm_client: Any = None, unresolved_call_strategy=..., io_provider: Any = None, copybook_dirs: list[Path] = []) -> VMState`. `llm_client` and `io_provider` are untouched.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_run_copybook_dirs_default.py
import inspect

from interpreter.run import run


def test_copybook_dirs_defaults_to_empty_list():
    sig = inspect.signature(run)
    assert sig.parameters["copybook_dirs"].default == []
    # llm_client and io_provider stay untouched in this task
    assert sig.parameters["llm_client"].default is None
    assert sig.parameters["io_provider"].default is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_run_copybook_dirs_default.py -v`
Expected: FAIL (`copybook_dirs` default is `None`)

- [ ] **Step 3: Write minimal implementation**

**Known state entering this task:** Task 2's review found that `run()` still defaulting `copybook_dirs` to `None` was breaking the now-unguarded `ProLeapCobolParser`/`make_cobol_parser` (which no longer tolerate `None`), so a stopgap normalization was added inside `run()`:

```python
    _copybook_dirs = copybook_dirs if copybook_dirs is not None else []
```

with `_copybook_dirs` used in place of `copybook_dirs` at the two call sites inside `run()` (the `compile_cobol`/`make_cobol_parser` call and the `get_frontend` call). This is itself a defensive `None`-check — reviewed and flagged as a temporary, tightly-coupled-to-this-task stopgap, not a pattern to preserve.

In `interpreter/run.py`'s `run()` signature, change the `copybook_dirs` line:

```python
    copybook_dirs: list[Path] = [],
```

Then **delete the stopgap entirely**: remove the `_copybook_dirs = copybook_dirs if copybook_dirs is not None else []` line, and change both call sites that currently read `_copybook_dirs` back to reading `copybook_dirs` directly (now safe, since the parameter itself is never `None`). Confirm via `grep -n "_copybook_dirs" interpreter/run.py` that no reference to the temporary variable remains after this edit.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_run_copybook_dirs_default.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/run.py tests/unit/test_run_copybook_dirs_default.py
git commit -m "fix(run): copybook_dirs defaults to [] instead of None"
```

**End of Phase 1 checkpoint:** run `poetry run python -m pytest -q` (full suite, background/long timeout) and confirm green before starting Phase 2.

---

## Phase 2 — Bucket B (reuse an existing sentinel)

### Task 12: `interpreter/frontend.py` — `copybook_dirs` (bucket A) only; `cics_text_parser` SKIPPED, `cobol_parser`/`llm_client` untouched (red-dragon-79iv)

**SCOPE UPDATE (2026-07-04):** commit `968e7772` added an approved-but-unimplemented design (`docs/superpowers/specs/2026-07-04-generic-dialect-parsers-design.md`) that will remove `cics_text_parser` entirely, replacing it with a generic `DialectParser` array. **Do not touch `cics_text_parser` in this task — implement only `copybook_dirs`.** Ignore every `_NO_CICS_TEXT_PARSER` reference below; that part of this task is deferred, not part of this epic (same as `cobol_parser`/`llm_client`, already out of scope per red-dragon-79iv).

**Files:**
- Modify: `interpreter/frontend.py:75` (`get_frontend`)
- Test: `tests/unit/test_get_frontend_defaults.py` (new file)

**Interfaces:**
- Consumes: `_NO_CICS_TEXT_PARSER` from Task 9.
- Produces: `get_frontend(language, frontend_type=..., llm_provider=..., llm_client: Any = None, observer=NullFrontendObserver(), repair_client=_NO_REPAIR_CLIENT, copybook_dirs: list[Path] = [], cobol_parser: Any = None, extension_strategies=(), cics_text_parser: Any = _NO_CICS_TEXT_PARSER) -> Frontend`. `llm_client` and `cobol_parser` are untouched — red-dragon-79iv.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_get_frontend_defaults.py
import inspect

from interpreter.cobol.cobol_statements import _NO_CICS_TEXT_PARSER
from interpreter.frontend import get_frontend


def test_get_frontend_defaults_away_from_none_except_deferred():
    sig = inspect.signature(get_frontend)
    assert sig.parameters["copybook_dirs"].default == []
    assert sig.parameters["cics_text_parser"].default is _NO_CICS_TEXT_PARSER
    # Deferred to red-dragon-79iv — untouched in this plan
    assert sig.parameters["cobol_parser"].default is None
    assert sig.parameters["llm_client"].default is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_get_frontend_defaults.py -v`
Expected: FAIL (`copybook_dirs` and `cics_text_parser` still default to `None`)

- [ ] **Step 3: Write minimal implementation**

In `interpreter/frontend.py`, import `_NO_CICS_TEXT_PARSER` and change only the two in-scope parameters:

```python
from interpreter.cobol.cobol_statements import _NO_CICS_TEXT_PARSER


def get_frontend(
    language: Language,
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    llm_provider: str = LLMProvider.CLAUDE,
    llm_client: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    repair_client: Any = _NO_REPAIR_CLIENT,
    copybook_dirs: list[Path] = [],
    cobol_parser: Any = None,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = _NO_CICS_TEXT_PARSER,
) -> Frontend:
```

Delete any `copybook_dirs or []` fallback in the body (there likely isn't one — `copybook_dirs` is passed straight through to `ProLeapCobolParser(...)`, which after Task 2 accepts `[]` natively). **Leave `if cobol_parser is None:` and the `llm_client` handling completely untouched** — those are red-dragon-79iv.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_get_frontend_defaults.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontend.py tests/unit/test_get_frontend_defaults.py
git commit -m "fix(frontend): copybook_dirs/cics_text_parser default away from None (get_frontend)"
```

### Task 13: `interpreter/cobol/emit_context.py` — `observer` (bucket B) + `asg` (bucket C)

**Files:**
- Modify: `interpreter/cobol/emit_context.py:101` (`EmitContext.__init__`)
- Test: `tests/unit/cobol/test_emit_context_defaults.py` (new file)

**Interfaces:**
- Produces: `EmitContext.__init__(self, dispatch_fn, observer: FrontendObserver = NullFrontendObserver(), condition_index=ConditionNameIndex({}), extension_strategies=(), asg: "CobolASG" = CobolASG()) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cobol/test_emit_context_defaults.py
import inspect

from interpreter.cobol.emit_context import EmitContext
from interpreter.frontend_observer import NullFrontendObserver


def test_observer_and_asg_default_away_from_none():
    sig = inspect.signature(EmitContext.__init__)
    assert isinstance(sig.parameters["observer"].default, NullFrontendObserver)
    assert sig.parameters["asg"].default is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cobol/test_emit_context_defaults.py -v`
Expected: FAIL — both defaults are `None`

- [ ] **Step 3: Write minimal implementation**

`CobolASG` is imported locally inside `__init__` today (`from interpreter.cobol.asg_types import CobolASG as _CobolASG`) to avoid a module-level circular import — move that import to module level if it's safe (check for a cycle first by running the test suite after moving it; if it cycles, keep the import local and instead build the default via a small no-arg helper called at class-body time, which still works since Python evaluates default expressions once at function-definition time, after the module's own top-level code — including any earlier local imports elsewhere in the file — has already run). Simplest safe approach: keep the local import exactly where it is, and change the signature + body to:

```python
    def __init__(
        self,
        dispatch_fn: DispatchFn,
        observer: FrontendObserver = NullFrontendObserver(),
        condition_index: ConditionNameIndex = ConditionNameIndex({}),
        extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
        asg: "CobolASG" = None,  # placeholder, reassigned below — see note
    ) -> None:
        from interpreter.cobol.asg_types import CobolASG as _CobolASG

        self._dispatch_fn = dispatch_fn
        self._observer = observer
        self._condition_index = condition_index
        self._extension_strategies = tuple(extension_strategies)
        self._asg: _CobolASG = asg if asg is not None else _CobolASG()
```

This does NOT satisfy the rule for `asg` (still `None` in the signature) because `CobolASG` can only be constructed after its local import runs. **Correct fix:** hoist the import to module level instead, since `interpreter.cobol.asg_types` is very unlikely to import `emit_context.py` back (verify with `grep -n "emit_context" interpreter/cobol/asg_types.py` — if empty, the cycle doesn't exist and the import is safe to hoist):

```python
from interpreter.cobol.asg_types import CobolASG
```

at the top of `emit_context.py`, then:

```python
    def __init__(
        self,
        dispatch_fn: DispatchFn,
        observer: FrontendObserver = NullFrontendObserver(),
        condition_index: ConditionNameIndex = ConditionNameIndex({}),
        extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
        asg: CobolASG = CobolASG(),
    ) -> None:
        self._dispatch_fn = dispatch_fn
        self._observer = observer
        self._condition_index = condition_index
        self._extension_strategies = tuple(extension_strategies)
        self._asg: CobolASG = asg
```

If `grep` shows a real cycle, stop and use the sentinel pattern instead (`_NO_ASG = object()`, checked via `is`) rather than forcing the module-level import — note which path was taken in the commit message.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cobol/test_emit_context_defaults.py -v`
Expected: PASS

Run the broader COBOL lowering suite to catch any circular-import fallout:
Run: `PROLEAP_BRIDGE_JAR=$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/unit/cobol/ tests/integration/test_cobol_coverage_gaps.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/emit_context.py tests/unit/cobol/test_emit_context_defaults.py
git commit -m "fix(cobol): observer/asg default away from None (emit_context.py)"
```

### Task 14: `interpreter/cobol/lower_arithmetic.py` — `zoned_display_reg`

**Files:**
- Modify: `interpreter/cobol/lower_arithmetic.py:529` (`_store_move_value`)
- Test: `tests/unit/cobol/test_lower_arithmetic_store_move_value_default.py` (new file)

**Interfaces:**
- Produces: `_store_move_value(ctx, target, source_value_reg, materialised, zoned_display_reg: Register = NO_REGISTER) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cobol/test_lower_arithmetic_store_move_value_default.py
import inspect

from interpreter.cobol.lower_arithmetic import _store_move_value
from interpreter.register import NO_REGISTER


def test_zoned_display_reg_defaults_to_no_register():
    sig = inspect.signature(_store_move_value)
    assert sig.parameters["zoned_display_reg"].default is NO_REGISTER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cobol/test_lower_arithmetic_store_move_value_default.py -v`
Expected: FAIL — `ImportError` if `NO_REGISTER` isn't yet imported in `lower_arithmetic.py`, or default still `None`.

- [ ] **Step 3: Write minimal implementation**

In `interpreter/cobol/lower_arithmetic.py`, add (if not already imported):

```python
from interpreter.register import NO_REGISTER
```

Change the signature:

```python
def _store_move_value(
    ctx: EmitContext,
    target: RefModOperand,
    source_value_reg: Register,
    materialised: MaterialisedSectionedLayout,
    zoned_display_reg: Register = NO_REGISTER,
) -> None:
```

Find the body's `if zoned_display_reg is None:` (or similar) check and replace it with the equivalent check against `NO_REGISTER` — e.g. `if zoned_display_reg is NO_REGISTER:` or, if `Register` has an `is_present()` method (it does, per `NoRegister.is_present()`), prefer `if not zoned_display_reg.is_present():`.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cobol/test_lower_arithmetic_store_move_value_default.py -v`
Expected: PASS

Run the arithmetic lowering suite:
Run: `poetry run python -m pytest tests/unit/cobol/ -k arithmetic -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/lower_arithmetic.py tests/unit/cobol/test_lower_arithmetic_store_move_value_default.py
git commit -m "fix(cobol): zoned_display_reg defaults to NO_REGISTER instead of None"
```

### Task 15: `interpreter/ir.py` — `literal_type` (keep as empty string, not `TypeExpr`)

**Files:**
- Modify: `interpreter/ir.py:249` (`IRInstruction`)
- Test: `tests/unit/test_ir_instruction_literal_type_default.py` (new file)

**Interfaces:**
- Produces: `IRInstruction(opcode, result_reg=NO_REGISTER, operands=[], label=NO_LABEL, branch_targets=[], source_location=NO_SOURCE_LOCATION, literal_type: str = "") -> Any`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ir_instruction_literal_type_default.py
import inspect

from interpreter.ir import IRInstruction


def test_literal_type_defaults_to_empty_string():
    sig = inspect.signature(IRInstruction)
    assert sig.parameters["literal_type"].default == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_ir_instruction_literal_type_default.py -v`
Expected: FAIL (`default` is `None`)

- [ ] **Step 3: Write minimal implementation**

```python
def IRInstruction(
    opcode: Opcode,
    result_reg: Register = NO_REGISTER,
    operands: list[Any] = [],
    label: CodeLabel = NO_LABEL,
    branch_targets: list[CodeLabel] = [],
    source_location: SourceLocation = NO_SOURCE_LOCATION,
    literal_type: str = "",
) -> Any:
```

Find any `literal_type or ""` / `if literal_type is None` check in the body and simplify accordingly (delete the fallback; if the body does something like `if literal_type:` to test "was one given," that check is unaffected since `""` is also falsy — verify this stays correct by reading the body before editing).

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_ir_instruction_literal_type_default.py -v`
Expected: PASS

Run the IR test suite:
Run: `poetry run python -m pytest tests/unit/test_ir.py -v` (adjust path if the actual IR test file has a different name — check `tests/unit/` first)
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/ir.py tests/unit/test_ir_instruction_literal_type_default.py
git commit -m "fix(ir): literal_type defaults to empty string instead of None"
```

### Task 16: `interpreter/handlers/calls.py` — `type_env`

**Files:**
- Modify: `interpreter/handlers/calls.py:137` (`_try_class_constructor_call`)
- Test: `tests/unit/handlers/test_calls_type_env_default.py` (new file)

**Interfaces:**
- Produces: `_try_class_constructor_call(func_val, args, inst, vm, cfg, registry, current_label, overload_resolver=NullOverloadResolver(), type_env: TypeEnvironment = TypeEnvironment(register_types=MappingProxyType({}), var_types=MappingProxyType({})), type_hint=UNKNOWN) -> ExecutionResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/handlers/test_calls_type_env_default.py
import inspect

from interpreter.handlers.calls import _try_class_constructor_call


def test_type_env_defaults_away_from_none():
    sig = inspect.signature(_try_class_constructor_call)
    assert sig.parameters["type_env"].default is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/handlers/test_calls_type_env_default.py -v`
Expected: FAIL (`default` is `None`)

- [ ] **Step 3: Write minimal implementation**

At the top of `interpreter/handlers/calls.py`, ensure these are imported at module level (they're currently imported *locally* inside the function body — move them to the top of the file so they're available as a default-expression value, checking first for any circular-import risk the same way as Task 13):

```python
from types import MappingProxyType
from interpreter.types.type_environment import TypeEnvironment
```

Change the signature:

```python
def _try_class_constructor_call(
    func_val: Any,
    args: list[TypedValue],
    inst: InstructionBase,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: CodeLabel,
    overload_resolver: OverloadResolver = NullOverloadResolver(),
    type_env: TypeEnvironment = TypeEnvironment(
        register_types=MappingProxyType({}), var_types=MappingProxyType({})
    ),
    type_hint: TypeExpr = UNKNOWN,
) -> ExecutionResult:
```

Delete the now-dead body block:

```python
    if type_env is None:
        type_env = _TE(
            register_types=MappingProxyType({}),
            var_types=MappingProxyType({}),
        )
```

(and the now-unused local `from interpreter.types.type_environment import TypeEnvironment as _TE` import, if it becomes unused after this change — check the rest of the function body first).

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/handlers/test_calls_type_env_default.py -v`
Expected: PASS

Run the calls handler suite:
Run: `poetry run python -m pytest tests/unit/handlers/ -k calls -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/handlers/calls.py tests/unit/handlers/test_calls_type_env_default.py
git commit -m "fix(handlers): type_env defaults to an empty TypeEnvironment instead of None"
```

### Task 17: `interpreter/frontends/_base.py` — `node` (4 sites)

**Files:**
- Modify: `interpreter/frontends/_base.py:181,210,254,279` (`_emit`, `_emit_inst`, `_emit_class_ref`, `_emit_func_ref`)
- Test: `tests/unit/frontends/test_base_node_defaults.py` (new file)

**Interfaces:**
- Consumes: `NO_NODE` from Task 1.
- Produces: all four methods' `node` parameter defaults to `NO_NODE` instead of `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/frontends/test_base_node_defaults.py
import inspect

from interpreter.frontends._base import (
    NO_NODE,
    TreeSitterFrontendBase,  # replace with the actual class name in _base.py if different
)


def test_all_four_node_params_default_to_no_node():
    for method_name in ("_emit", "_emit_inst", "_emit_class_ref", "_emit_func_ref"):
        method = getattr(TreeSitterFrontendBase, method_name)
        sig = inspect.signature(method)
        assert sig.parameters["node"].default is NO_NODE, method_name
```

(Check `interpreter/frontends/_base.py` for the actual base class name before writing this test — the four methods at lines 181/210/254/279 all belong to one class.)

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/frontends/test_base_node_defaults.py -v`
Expected: FAIL — all four defaults are `None`

- [ ] **Step 3: Write minimal implementation**

Change each of the four signatures in `interpreter/frontends/_base.py`:

```python
    def _emit(
        self,
        opcode: Opcode,
        *,
        result_reg: Register = NO_REGISTER,
        operands: list[Any] = [],
        label: CodeLabel = NO_LABEL,
        branch_targets: list[CodeLabel] = [],
        source_location: SourceLocation = NO_SOURCE_LOCATION,
        node: Any = NO_NODE,
    ) -> InstructionBase:
```

```python
    def _emit_inst(self, inst: Instruction, *, node: Any = NO_NODE) -> Instruction:
```

```python
    def _emit_class_ref(
        self,
        class_name: str,
        class_label: str,
        parents: list[str],
        result_reg: str,
        node: Any = NO_NODE,
    ) -> InstructionBase:
```

```python
    def _emit_func_ref(
        self, func_name: str, func_label: CodeLabel, result_reg: str, node: Any = NO_NODE
    ) -> InstructionBase:
```

In each body, find where `node` feeds into `source_location`/diagnostics construction (likely something like `source_location_from(node) if node is not None else NO_SOURCE_LOCATION` or similar) and update the guard to check `node is not NO_NODE` instead of `node is not None`.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/frontends/test_base_node_defaults.py -v`
Expected: PASS

Run the broader frontend base suite:
Run: `poetry run python -m pytest tests/unit/frontends/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/_base.py tests/unit/frontends/test_base_node_defaults.py
git commit -m "fix(frontends): node params default to NO_NODE instead of None (_base.py)"
```

### Task 18: `interpreter/frontends/context.py` — `node` (4 sites)

**Files:**
- Modify: `interpreter/frontends/context.py:207,228,234,254` (`emit_inst`, `emit_decl_var`, `emit_func_ref`, `emit_class_ref`)
- Test: `tests/unit/frontends/test_context_node_defaults.py` (new file)

**Interfaces:**
- Consumes: `NO_NODE` from Task 1 (`from interpreter.frontends._base import NO_NODE`).
- Produces: all four methods' `node` parameter defaults to `NO_NODE`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/frontends/test_context_node_defaults.py
import inspect

from interpreter.frontends._base import NO_NODE
from interpreter.frontends.context import (
    EmitContext,  # replace with actual class name if different
)


def test_all_four_node_params_default_to_no_node():
    for method_name in ("emit_inst", "emit_decl_var", "emit_func_ref", "emit_class_ref"):
        method = getattr(EmitContext, method_name)
        sig = inspect.signature(method)
        assert sig.parameters["node"].default is NO_NODE, method_name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/frontends/test_context_node_defaults.py -v`
Expected: FAIL — all four defaults are `None`

- [ ] **Step 3: Write minimal implementation**

Import `NO_NODE` at the top of `interpreter/frontends/context.py`:

```python
from interpreter.frontends._base import NO_NODE
```

Change each signature:

```python
    def emit_inst(self, inst: Instruction, *, node: Any = NO_NODE) -> Instruction:
```

```python
    def emit_decl_var(
        self, name: str, val_reg: str, *, node: Any = NO_NODE
    ) -> Instruction:
```

```python
    def emit_func_ref(
        self,
        func_name: str,
        func_label: CodeLabel,
        result_reg: str,
        node: Any = NO_NODE,
    ) -> Instruction:
```

```python
    def emit_class_ref(
        self,
        class_name: str,
        class_label: CodeLabel,
        parents: list[str],
        result_reg: str,
        node: Any = NO_NODE,
    ) -> Instruction:
```

Update any `node is not None` guard in each body to `node is not NO_NODE`.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/frontends/test_context_node_defaults.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/context.py tests/unit/frontends/test_context_node_defaults.py
git commit -m "fix(frontends): node params default to NO_NODE instead of None (context.py)"
```

### Task 19: `interpreter/frontends/csharp/expressions.py` — `node` (2 sites, currently untyped)

**Files:**
- Modify: `interpreter/frontends/csharp/expressions.py:498,510` (`emit_byref_load`, `emit_byref_store`)
- Test: `tests/unit/frontends/csharp/test_expressions_node_defaults.py` (new file)

**Interfaces:**
- Consumes: `NO_NODE` from Task 1.
- Produces: `emit_byref_load(ctx, name: str, *, node: Any = NO_NODE) -> Register`, `emit_byref_store(ctx, name: str, val_reg: str, *, node: Any = NO_NODE) -> None`. Both gain a type annotation they didn't have before (`node=None` → `node: Any = NO_NODE`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/frontends/csharp/test_expressions_node_defaults.py
import inspect

from interpreter.frontends._base import NO_NODE
from interpreter.frontends.csharp.expressions import emit_byref_load, emit_byref_store


def test_node_defaults_to_no_node_and_is_annotated():
    for fn in (emit_byref_load, emit_byref_store):
        sig = inspect.signature(fn)
        assert sig.parameters["node"].default is NO_NODE
        assert sig.parameters["node"].annotation is not inspect.Parameter.empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/frontends/csharp/test_expressions_node_defaults.py -v`
Expected: FAIL — defaults are `None` and annotations are missing

- [ ] **Step 3: Write minimal implementation**

Import `NO_NODE` at the top of `interpreter/frontends/csharp/expressions.py`:

```python
from interpreter.frontends._base import NO_NODE
```

Change both signatures:

```python
def emit_byref_load(ctx: TreeSitterEmitContext, name: str, *, node: Any = NO_NODE) -> Register:
```

```python
def emit_byref_store(
    ctx: TreeSitterEmitContext, name: str, val_reg: str, *, node: Any = NO_NODE
) -> None:
```

(Add `from typing import Any` to the imports if not already present.) Update any `node is not None` guard in each body to `node is not NO_NODE`.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/frontends/csharp/test_expressions_node_defaults.py -v`
Expected: PASS

Run the C# frontend suite:
Run: `poetry run python -m pytest tests/unit/frontends/csharp/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/csharp/expressions.py tests/unit/frontends/csharp/test_expressions_node_defaults.py
git commit -m "fix(csharp): node params default to NO_NODE instead of None, add missing annotations"
```

### Task 20: `interpreter/frontends/rust/expressions.py` — `node` (3 sites)

**Files:**
- Modify: `interpreter/frontends/rust/expressions.py:344,356,368` (`lower_rust_int_const`, `lower_rust_none_const`, `lower_rust_default_return_const`)
- Test: `tests/unit/frontends/rust/test_expressions_node_defaults.py` (new file)

**Interfaces:**
- Consumes: `NO_NODE` from Task 1.
- Produces: all three functions' `node` parameter defaults to `NO_NODE`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/frontends/rust/test_expressions_node_defaults.py
import inspect

from interpreter.frontends._base import NO_NODE
from interpreter.frontends.rust.expressions import (
    lower_rust_default_return_const,
    lower_rust_int_const,
    lower_rust_none_const,
)


def test_node_defaults_to_no_node():
    for fn in (
        lower_rust_int_const,
        lower_rust_none_const,
        lower_rust_default_return_const,
    ):
        sig = inspect.signature(fn)
        assert sig.parameters["node"].default is NO_NODE, fn.__name__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/frontends/rust/test_expressions_node_defaults.py -v`
Expected: FAIL — all three defaults are `None`

- [ ] **Step 3: Write minimal implementation**

Import `NO_NODE` at the top of `interpreter/frontends/rust/expressions.py`:

```python
from interpreter.frontends._base import NO_NODE
```

Change each signature:

```python
def lower_rust_int_const(
    ctx: TreeSitterEmitContext, value: int, node: Any = NO_NODE
) -> Register:
```

```python
def lower_rust_none_const(
    ctx: TreeSitterEmitContext, node: Any = NO_NODE
) -> Register:
```

```python
def lower_rust_default_return_const(
    ctx: TreeSitterEmitContext, node: Any = NO_NODE
) -> Register:
```

Update any `node is not None` / `node is None` guard in each body to check against `NO_NODE` instead.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/frontends/rust/test_expressions_node_defaults.py -v`
Expected: PASS

Run the Rust frontend suite:
Run: `poetry run python -m pytest tests/unit/frontends/rust/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/rust/expressions.py tests/unit/frontends/rust/test_expressions_node_defaults.py
git commit -m "fix(rust): node params default to NO_NODE instead of None"
```

### Task 21: `interpreter/frontends/go/declarations.py` — `prev_value_node` (untyped)

**Files:**
- Modify: `interpreter/frontends/go/declarations.py:400` (`_lower_const_spec`)
- Test: `tests/unit/frontends/go/test_declarations_prev_value_node_default.py` (new file)

**Interfaces:**
- Consumes: `NO_NODE` from Task 1.
- Produces: `_lower_const_spec(ctx, node: Any, prev_value_node: Any = NO_NODE) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/frontends/go/test_declarations_prev_value_node_default.py
import inspect

from interpreter.frontends._base import NO_NODE
from interpreter.frontends.go.declarations import _lower_const_spec


def test_prev_value_node_defaults_to_no_node_and_is_annotated():
    sig = inspect.signature(_lower_const_spec)
    assert sig.parameters["prev_value_node"].default is NO_NODE
    assert sig.parameters["prev_value_node"].annotation is not inspect.Parameter.empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/frontends/go/test_declarations_prev_value_node_default.py -v`
Expected: FAIL — default is `None`, annotation missing

- [ ] **Step 3: Write minimal implementation**

Import `NO_NODE` (and `Any` if not already imported) at the top of `interpreter/frontends/go/declarations.py`:

```python
from interpreter.frontends._base import NO_NODE
```

Change the signature:

```python
def _lower_const_spec(
    ctx: TreeSitterEmitContext, node: Any, prev_value_node: Any = NO_NODE
) -> None:
```

Update any `prev_value_node is not None` / `is None` guard in the body to check against `NO_NODE`.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/frontends/go/test_declarations_prev_value_node_default.py -v`
Expected: PASS

Run the Go frontend suite:
Run: `poetry run python -m pytest tests/unit/frontends/go/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/go/declarations.py tests/unit/frontends/go/test_declarations_prev_value_node_default.py
git commit -m "fix(go): prev_value_node defaults to NO_NODE instead of None, add missing annotation"
```

### Task 22: `interpreter/frontends/java/declarations.py` — `compact_body` (untyped)

**Files:**
- Modify: `interpreter/frontends/java/declarations.py:392` (`_emit_record_init`)
- Test: `tests/unit/frontends/java/test_declarations_compact_body_default.py` (new file)

**Interfaces:**
- Consumes: `NO_NODE` from Task 1.
- Produces: `_emit_record_init(ctx, param_names: list[str], field_inits: list[FieldInit] = [], compact_body: Any = NO_NODE) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/frontends/java/test_declarations_compact_body_default.py
import inspect

from interpreter.frontends._base import NO_NODE
from interpreter.frontends.java.declarations import _emit_record_init


def test_compact_body_defaults_to_no_node_and_is_annotated():
    sig = inspect.signature(_emit_record_init)
    assert sig.parameters["compact_body"].default is NO_NODE
    assert sig.parameters["compact_body"].annotation is not inspect.Parameter.empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/frontends/java/test_declarations_compact_body_default.py -v`
Expected: FAIL — default is `None`, annotation missing

- [ ] **Step 3: Write minimal implementation**

Import `NO_NODE` (and `Any` if not already imported) at the top of `interpreter/frontends/java/declarations.py`:

```python
from interpreter.frontends._base import NO_NODE
```

Change the signature:

```python
def _emit_record_init(
    ctx: TreeSitterEmitContext,
    param_names: list[str],
    field_inits: list[FieldInit] = [],
    compact_body: Any = NO_NODE,
) -> None:
```

Update any `compact_body is not None` / `is None` guard in the body to check against `NO_NODE`.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/frontends/java/test_declarations_compact_body_default.py -v`
Expected: PASS

Run the Java frontend suite:
Run: `poetry run python -m pytest tests/unit/frontends/java/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/java/declarations.py tests/unit/frontends/java/test_declarations_compact_body_default.py
git commit -m "fix(java): compact_body defaults to NO_NODE instead of None, add missing annotation"
```

**End of Phase 2 checkpoint:** run `poetry run python -m pytest -q` (full suite) and confirm green before starting Phase 3.

---

## Phase 3 — Bucket D (`vm`/`initial_vm`: drop default, require argument, migrate call sites)

### Task 23: `interpreter/run.py` — make `vm`/`initial_vm` required across all 5 functions, migrate every caller

This is the one behavior-changing task in the plan. Do it as a single task (not split further) because the 5 signature changes and their call-site migrations are tightly coupled — a partial migration would leave the suite red.

**Files:**
- Modify: `interpreter/run.py:500` (`execute_cfg`), `interpreter/run.py:633` (`run_resumable`), `interpreter/run.py:700` (`execute_cfg_traced`), `interpreter/run.py:1040` (`run_linked_resumable`), `interpreter/run.py:955` (`run_linked`)
- Modify (call-site migration): every caller across `interpreter/` and `tests/` that currently omits `vm`/`initial_vm`
- Test: `tests/unit/test_run_vm_required.py` (new file)

**Interfaces:**
- Produces: `execute_cfg(cfg, entry_point, registry, config=VMConfig(), strategies=ExecutionStrategies(), *, vm: VMState) -> tuple[VMState, ExecutionStats]` (and the equivalent required-`vm`/`initial_vm` shape for the other four). Note `vm`/`initial_vm` move after `*` to force keyword-only, matching how they're called everywhere today (grep confirms no positional callers) and making the "this is now mandatory, not just reordered" intent explicit at call sites.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_run_vm_required.py
import inspect

import pytest

from interpreter.run import (
    execute_cfg,
    execute_cfg_traced,
    run_linked,
    run_linked_resumable,
    run_resumable,
)


@pytest.mark.parametrize(
    "fn,param_name",
    [
        (execute_cfg, "vm"),
        (run_resumable, "vm"),
        (execute_cfg_traced, "vm"),
        (run_linked_resumable, "initial_vm"),
        (run_linked, "initial_vm"),
    ],
)
def test_vm_param_has_no_default(fn, param_name):
    sig = inspect.signature(fn)
    assert sig.parameters[param_name].default is inspect.Parameter.empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_run_vm_required.py -v`
Expected: FAIL — all five parameters currently have a `None` default, not "empty" (no default)

- [ ] **Step 3: Write minimal implementation**

First, find every caller relying on the omitted-argument path:

```bash
grep -rn "execute_cfg(\|run_resumable(\|execute_cfg_traced(\|run_linked_resumable(\|run_linked(" interpreter/ tests/ --include="*.py"
```

For each call site found, check whether it already passes `vm=`/`initial_vm=` explicitly. For any that don't, add `vm=VMState()` (or `initial_vm=VMState()`) to the call — importing `VMState` from `interpreter.vm.vm` (or wherever it's already imported in that file) if not already available there.

Then change the five signatures in `interpreter/run.py`. Example for `execute_cfg` (repeat the same shape for the other four, using `initial_vm` where that's the parameter name):

```python
def execute_cfg(
    cfg: CFG,
    entry_point: str | CodeLabel,
    registry: FunctionRegistry,
    config: VMConfig = VMConfig(),
    strategies: ExecutionStrategies = ExecutionStrategies(),
    *,
    vm: VMState,
) -> tuple[VMState, ExecutionStats]:
```

Inside each function's body, delete the now-dead:

```python
    if vm is None:
        vm = VMState()
```

(or the `initial_vm` equivalent).

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_run_vm_required.py -v`
Expected: PASS

Run the full `run.py`-adjacent suite (this is the widest-blast-radius task in the plan):
Run: `poetry run python -m pytest tests/unit/ tests/integration/ -q`
Expected: PASS — if anything fails with `TypeError: execute_cfg() missing 1 required keyword-only argument: 'vm'` (or similar for the other four), that call site was missed in the grep above; add `vm=VMState()`/`initial_vm=VMState()` there and rerun.

- [ ] **Step 5: Commit**

```bash
git add interpreter/run.py tests/unit/test_run_vm_required.py
git commit -m "fix(run): vm/initial_vm are now required keyword-only args, not None-defaulted

VMState is mutated in place during execution; a None default combined
with an internal 'if vm is None: vm = VMState()' fallback risked a
future refactor accidentally sharing one VMState instance across calls
via a literal default (the same bug the None-default cleanup exists to
prevent). Every existing call site that omitted vm/initial_vm now
passes VMState() explicitly. Ref red-dragon-nz4y."
```

**End of Phase 3 checkpoint:** run `poetry run python -m pytest -q` (full suite) one more time — this is the final gate before the epic-closing step below.

---

## Final step: verify the pylint count dropped correctly

- [ ] Run: `poetry run pylint --load-plugins=pylint_plugins.no_none_default --disable=all --enable=no-none-default interpreter/ 2>/dev/null | grep -c C9701`
- [ ] Expected: **26** (18 bucket-E deferred sites + 3 red-dragon-79iv sites — `cobol_parser`, `llm_client` ×2 + 5 `cics_text_parser` sites, skipped mid-plan on 2026-07-04 pending the approved `DialectParser` design)
- [ ] If the count is anything else, diff the current violation list against the 26 expected sites (`project_root` ×2, `ast_cache_dir`, `io_provider` ×4, `value` ×2, `finally_node`/`else_node` ×4, `text` ×2, `source`, `symbol_table`, `ctx`, `cobol_parser`, `llm_client` ×2, `cics_text_parser` ×5) and investigate any mismatch before closing out.
- [ ] Update `bd update red-dragon-nz4y --description="..."` to note buckets A–D are closed (minus `cics_text_parser`), only bucket E (18 sites) + `cics_text_parser` (5 sites, deferred to the `DialectParser` migration) remain open on this ticket.
- [ ] `bd close red-dragon-nz4y` is **not** appropriate yet — bucket E and `cics_text_parser` sites are still open on it. Leave the issue open, scoped down.
