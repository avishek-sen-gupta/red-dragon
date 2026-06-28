# Mandatory AST Cache + Real Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the two-phase AST cache path the only path through `compile_cobol`, and eliminate all fake parsers — every test that touches COBOL compilation uses a real `ProLeapCobolParser`.

**Architecture:** `parser` becomes a required keyword argument to `compile_cobol` and `compile_cobol_module`. When `ast_cache_dir` is not supplied, `compile_cobol` auto-creates a `TemporaryDirectory` and cleans it up before returning. Fake parsers in tests are replaced: `_FakeParser(asg)` + `lower(b"")` becomes `CobolFrontend(make_cobol_parser()).lower_from_ast_dict(asg.to_dict())`; fixture-based tests load JSON dicts directly.

**Tech Stack:** Python 3.11+, `tempfile.TemporaryDirectory`, `poetry run python -m pytest`

## Global Constraints

- Run `poetry run python -m black .` on every modified file before committing.
- Run `poetry run python -m pytest` (not `poetry run pytest`).
- Tests stay in `tests/unit/` even when they use the real bridge JAR — a test that only uses the JAR and no other external dependencies is still a unit test.
- NEVER reference external codebases (names, APIs, domains, packages) in any tracked artifact.
- `make_cobol_parser()` reads `PROLEAP_BRIDGE_JAR` env var, falls back to `"proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"`.
- `frontend.py`'s implicit `cobol_parser=None` fallback in `get_frontend` is NOT touched — out of scope.
- All changes use TDD: write the failing test first, then implement.

---

### Task 1: `make_cobol_parser` factory

**Files:**
- Modify: `interpreter/cobol/cobol_parser.py`
- Test: `tests/unit/test_cobol_parser.py` (add two tests at the bottom)

**Interfaces:**
- Produces: `make_cobol_parser(copybook_dirs: list[Path] | None = None) -> ProLeapCobolParser`

- [ ] **Step 1: Write the failing tests**

Add at the bottom of `tests/unit/test_cobol_parser.py`:

```python
from interpreter.cobol.cobol_parser import make_cobol_parser

@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_make_cobol_parser_returns_proleap_parser():
    parser = make_cobol_parser()
    assert isinstance(parser, ProLeapCobolParser)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_make_cobol_parser_with_copybook_dirs_passes_them_through(tmp_path):
    parser = make_cobol_parser(copybook_dirs=[tmp_path])
    assert isinstance(parser, ProLeapCobolParser)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/test_cobol_parser.py::test_make_cobol_parser_returns_proleap_parser tests/unit/test_cobol_parser.py::test_make_cobol_parser_with_copybook_dirs_passes_them_through -v
```

Expected: FAIL with `ImportError: cannot import name 'make_cobol_parser'`

- [ ] **Step 3: Add `make_cobol_parser` to `interpreter/cobol/cobol_parser.py`**

Add `import os` at the top of the file (with the other stdlib imports). Add `from interpreter.cobol.subprocess_runner import RealSubprocessRunner` to the existing subprocess_runner import. Then add after the `ProLeapCobolParser` class:

```python
def make_cobol_parser(
    copybook_dirs: list[Path] | None = None,
) -> ProLeapCobolParser:
    """Construct a ProLeapCobolParser from PROLEAP_BRIDGE_JAR env var.

    Falls back to the canonical build output path when the env var is unset.
    """
    bridge_jar = os.environ.get(
        "PROLEAP_BRIDGE_JAR",
        "proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar",
    )
    return ProLeapCobolParser(RealSubprocessRunner(), bridge_jar, copybook_dirs=copybook_dirs)
```

The existing import line is:
```python
from interpreter.cobol.subprocess_runner import SubprocessRunner, CobolParseError
```
Change it to:
```python
from interpreter.cobol.subprocess_runner import SubprocessRunner, CobolParseError, RealSubprocessRunner
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/test_cobol_parser.py::test_make_cobol_parser_returns_proleap_parser tests/unit/test_cobol_parser.py::test_make_cobol_parser_with_copybook_dirs_passes_them_through -v
```

Expected: PASS

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black interpreter/cobol/cobol_parser.py tests/unit/test_cobol_parser.py
git add interpreter/cobol/cobol_parser.py tests/unit/test_cobol_parser.py
git commit -m "feat(parser): make_cobol_parser factory reading PROLEAP_BRIDGE_JAR"
```

---

### Task 2: Remove non-cache path from `compile_cobol` and `compile_cobol_module`

**Files:**
- Modify: `interpreter/project/cobol_compile.py`
- Modify: `tests/unit/project/test_cobol_compile.py`

**Interfaces:**
- Consumes: `make_cobol_parser()` from Task 1
- `compile_cobol_module(source, *, parser: Any, ..., ast_path: Path)` — `parser` required, `ast_path` required (no default)
- `compile_cobol(source, *, parser: Any, ..., ast_cache_dir: Path | None = None)` — `parser` required

- [ ] **Step 1: Write failing tests in `tests/unit/project/test_cobol_compile.py`**

Replace the imports block at the top to add:
```python
from interpreter.cobol.cobol_parser import make_cobol_parser
```

Rewrite `test_compile_cobol_module_returns_frontend_and_module` to require a real parser + ast_path:
```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_module_returns_frontend_and_module(tmp_path):
    parser = make_cobol_parser()
    ast_path = tmp_path / "prog.ast.json"
    parser.parse_to_file(_SRC, ast_path)
    frontend, module = compile_cobol_module(_SRC, parser=parser, ast_path=ast_path)
    assert isinstance(module, ModuleUnit)
    assert len(module.ir) > 0
    assert frontend.data_layout is not None
    assert frontend.func_symbol_table is not None
```

Update `test_compile_cobol_single_module_runs` (already uses `_, linked`):
```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_single_module_runs():
    _, linked = compile_cobol(_SRC, parser=make_cobol_parser())
    assert isinstance(linked, LinkedProgram)
    assert linked.merged_cfg is not None
    vm = run_linked(linked, entry_point=EntryPoint.top_level(), max_steps=10_000)
    assert vm is not None
```

Update `test_compile_cobol_links_extra_subprogram` — add `parser=make_cobol_parser()`:
```python
    _, linked = compile_cobol(
        caller, extra_subprogram_sources={"CALLEE": callee}, parser=make_cobol_parser()
    )
```

Update `test_source_transform_applied_to_on_disk_callees_only` — add `parser=make_cobol_parser()` to the `compile_cobol` call.

Delete `_FakeParseToFileParser` class entirely (lines 139–145).

Update all `parallel_parse_to_cache` tests to use `make_cobol_parser()`:
```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_writes_one_file_per_source(tmp_path):
    sources = {
        Path("prog_a.cbl"): _SRC,
        Path("prog_b.cbl"): _SRC,
        Path("prog_c.cbl"): _SRC,
    }
    result = parallel_parse_to_cache(sources, make_cobol_parser(), tmp_path)
    assert set(result.keys()) == set(sources.keys())
    for src_path, ast_path in result.items():
        path_hash = hashlib.md5(str(src_path).encode()).hexdigest()[:8]
        assert ast_path == tmp_path / f"{src_path.stem}-{path_hash}.ast.json"
        assert ast_path.exists()
        assert json.loads(ast_path.read_text())["program_id"] is not None
```

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_creates_cache_dir(tmp_path):
    cache_dir = tmp_path / "nested" / "cache"
    assert not cache_dir.exists()
    parallel_parse_to_cache({Path("x.cbl"): _SRC}, make_cobol_parser(), cache_dir)
    assert cache_dir.is_dir()
```

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_empty_sources(tmp_path):
    result = parallel_parse_to_cache({}, make_cobol_parser(), tmp_path)
    assert result == {}
```

Update the four `ast_cache_dir` tests to use `make_cobol_parser()`:
```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_ast_cache_dir_single_module_writes_json(tmp_path):
    cache = tmp_path / "ast-cache"
    _, linked = compile_cobol(_HELLO, parser=make_cobol_parser(), ast_cache_dir=cache)
    assert isinstance(linked, LinkedProgram)
    assert cache.is_dir()
    assert len(list(cache.glob("*.ast.json"))) == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_ast_cache_dir_multi_module_writes_one_json_per_module(tmp_path):
    cache = tmp_path / "ast-cache"
    _, linked = compile_cobol(
        _CALLER,
        parser=make_cobol_parser(),
        extra_subprogram_sources={"CALLEE": _CALLEE},
        ast_cache_dir=cache,
    )
    assert isinstance(linked, LinkedProgram)
    assert len(list(cache.glob("*.ast.json"))) == 2


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_ast_cache_dir_produces_runnable_program(tmp_path):
    _, linked = compile_cobol(
        _HELLO, parser=make_cobol_parser(), ast_cache_dir=tmp_path / "cache"
    )
    vm = run_linked(linked, entry_point=EntryPoint.top_level(), max_steps=10_000)
    assert vm is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_without_ast_cache_dir_uses_auto_temp():
    _, linked = compile_cobol(_HELLO, parser=make_cobol_parser())
    assert isinstance(linked, LinkedProgram)
    assert linked.merged_cfg is not None
```

Note: `test_compile_cobol_without_ast_cache_dir_unchanged` is renamed to `test_compile_cobol_without_ast_cache_dir_uses_auto_temp` to reflect the new behavior.

- [ ] **Step 2: Run tests to see which fail**

```bash
poetry run python -m pytest tests/unit/project/test_cobol_compile.py -v 2>&1 | head -60
```

Expected: many failures (tests expect `parser=` to be required but the old code still accepts `None`)

- [ ] **Step 3: Update `interpreter/project/cobol_compile.py`**

Add `import tempfile` near the top (with other stdlib imports).

**Change `compile_cobol_module` signature** — remove `ast_path: Path | None = None` default, make `parser` and `ast_path` required, delete the `else` branch:

```python
def compile_cobol_module(
    source: bytes,
    *,
    parser: Any,
    copybook_dirs: list[Path] | None = None,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    path: Path = Path("__main__.cbl"),
    ast_path: Path,
) -> tuple[Any, ModuleUnit]:
    """Lower one COBOL source into a (frontend, ModuleUnit). The shared core."""
    frontend: Any = get_frontend(
        Language.COBOL,
        frontend_type=constants.FRONTEND_COBOL,
        observer=observer,
        copybook_dirs=copybook_dirs,
        cobol_parser=parser,
        extension_strategies=extension_strategies,
        cics_text_parser=cics_text_parser,
    )
    ir = frontend.lower_from_ast_dict(json.loads(ast_path.read_text("utf-8")))
    exports = build_export_table(
        ir, frontend.func_symbol_table, frontend.class_symbol_table
    )
    imports = tuple(extract_imports(source, path, Language.COBOL))
    module = ModuleUnit(
        path=path,
        language=Language.COBOL,
        ir=tuple(ir),
        exports=exports,
        imports=imports,
        symbol_table=frontend.symbol_table,
    )
    return frontend, module
```

**Change `compile_cobol` signature and body** — `parser` required, remove the non-cache `else` branch, add `TemporaryDirectory` auto-creation:

```python
def compile_cobol(
    source: bytes,
    *,
    parser: Any,
    copybook_dirs: list[Path] | None = None,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    program_source_dir: Path | None = None,
    extra_subprogram_sources: dict[str, bytes] | None = None,
    source_transform: Callable[[str], str] = lambda s: s,
    ast_cache_dir: Path | None = None,
) -> tuple[Any, LinkedProgram]:
    """Compile a COBOL program (single or multi-module) into a LinkedProgram.

    Always uses the two-phase AST cache: Phase 1 parses all sources to
    ast_cache_dir in parallel; Phase 2 loads each JSON and lowers sequentially
    (at most one ASG live at a time). When ast_cache_dir is None a TemporaryDirectory
    is created and cleaned up before returning.

    Returns (main_frontend, linked).
    """
    _owned_tmp: tempfile.TemporaryDirectory | None = None
    if ast_cache_dir is None:
        _owned_tmp = tempfile.TemporaryDirectory()
        cache_dir: Path = Path(_owned_tmp.name)
    else:
        cache_dir = ast_cache_dir

    try:
        # Note: program_source_dir disk resolution is intentionally excluded from the
        # ast-cache path — only extra_subprogram_sources are cached. This is a known
        # scope limitation: callers using program_source_dir + ast_cache_dir together
        # will get a LinkedProgram without disk-resolved callees.
        main_path = Path("__main__.cbl")
        base = program_source_dir or Path(".")

        sub_sources: dict[str, bytes] = dict(extra_subprogram_sources or {})
        all_sources: dict[Path, bytes] = {main_path: source}
        for prog_name, prog_src in sub_sources.items():
            all_sources[(base / f"{prog_name}.cbl").resolve()] = prog_src

        parallel_parse_to_cache(all_sources, parser, cache_dir)

        def _ast_path(src_path: Path) -> Path:
            path_hash = hashlib.md5(str(src_path).encode()).hexdigest()[:8]
            return cache_dir / f"{src_path.stem}-{path_hash}.ast.json"

        main_frontend, main_module = compile_cobol_module(
            source,
            parser=parser,
            copybook_dirs=copybook_dirs,
            extension_strategies=extension_strategies,
            cics_text_parser=cics_text_parser,
            observer=observer,
            path=main_path,
            ast_path=_ast_path(main_path),
        )
        modules: dict[Path, ModuleUnit] = {main_path: main_module}

        for prog_name, prog_src in sub_sources.items():
            sub_path = (base / f"{prog_name}.cbl").resolve()
            try:
                _, sub_module = compile_cobol_module(
                    prog_src,
                    parser=parser,
                    copybook_dirs=copybook_dirs,
                    extension_strategies=extension_strategies,
                    cics_text_parser=cics_text_parser,
                    observer=observer,
                    path=sub_path,
                    ast_path=_ast_path(sub_path),
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "compile_cobol ast-cache: subprogram %s failed — skipping",
                    prog_name,
                    exc_info=True,
                )
                continue
            modules[sub_path] = sub_module

        if len(modules) == 1:
            instructions = list(main_module.ir)
            cfg = build_cfg(instructions)
            registry = build_registry(
                instructions,
                cfg,
                func_symbol_table=main_frontend.func_symbol_table,
                class_symbol_table=main_frontend.class_symbol_table,
            )
            return main_frontend, LinkedProgram(
                modules={},
                merged_ir=instructions,
                merged_cfg=cfg,
                merged_registry=registry,
                language=Language.COBOL,
                import_graph={},
                type_env_builder=main_frontend.type_env_builder,
                symbol_table=main_frontend.symbol_table,
                data_layout=main_frontend.data_layout,
                func_symbol_table=main_frontend.func_symbol_table,
                class_symbol_table=main_frontend.class_symbol_table,
            )

        import_graph: dict[Path, list[Path]] = {p: [] for p in modules}
        import_graph[main_path] = [p for p in modules if p != main_path]
        topo_order = topological_sort(import_graph)
        linked = link_modules(
            modules=modules,
            import_graph=import_graph,
            project_root=Path("/"),
            topo_order=topo_order,
            language=Language.COBOL,
            type_env_builder=main_frontend.type_env_builder,
            data_layout=main_frontend.data_layout,
        )
        main_program_id: str = main_frontend.program_id
        linked.entry_func_label = CodeLabel(
            f"__main__.func_{main_program_id.lower()}_0"
        )
        return main_frontend, linked
    finally:
        if _owned_tmp is not None:
            _owned_tmp.cleanup()
```

Also delete `_resolve_call_sources` and the non-cache path code that follows it (the second `main_path = Path("__main__.cbl")` block through the end of the function). The function now ends at the `finally` block above.

- [ ] **Step 4: Run tests**

```bash
poetry run python -m pytest tests/unit/project/test_cobol_compile.py -v
```

Expected: all 11 tests pass

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black interpreter/project/cobol_compile.py tests/unit/project/test_cobol_compile.py
git add interpreter/project/cobol_compile.py tests/unit/project/test_cobol_compile.py
git commit -m "feat(compile): parser required, auto-temp cache, non-cache path deleted"
```

---

### Task 3: Migrate production callers

**Files:**
- Modify: `interpreter/run.py`
- Modify: `interpreter/project/cobol_connections.py`
- Modify: `jackal/jackal/cobol_step.py`
- Modify: `tests/integration/project/test_cobol_connections.py`
- Modify: `tests/unit/cobol/test_cobol_frontend_cache.py`

**Interfaces:**
- Consumes: `make_cobol_parser()` from Task 1, new `compile_cobol(parser=...)` from Task 2

- [ ] **Step 1: Update `interpreter/run.py`**

Add to the import block (near where `compile_cobol` is already imported):
```python
from interpreter.cobol.cobol_parser import make_cobol_parser
```

Change the COBOL block (around line 1274):
```python
    if lang == Language.COBOL:
        frontend, linked = compile_cobol(
            source.encode("utf-8"),
            parser=make_cobol_parser(copybook_dirs=copybook_dirs),
            copybook_dirs=copybook_dirs,
            observer=observer,
        )
```

- [ ] **Step 2: Update `interpreter/project/cobol_connections.py`**

Add to imports:
```python
from interpreter.cobol.cobol_parser import make_cobol_parser
```

Change `extract_cobol_connections` signature — `parser` becomes required (no default):
```python
def extract_cobol_connections(
    source: bytes,
    *,
    copybook_dirs: list[Path] | None = None,
    program_source_dir: Path | None = None,
    extra_subprogram_sources: dict[str, bytes] | None = None,
    parser: Any,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    source_transform: Callable[[str], str] = lambda s: s,
) -> list[Connection]:
```

- [ ] **Step 3: Update `jackal/jackal/cobol_step.py`**

Find the `compile_cobol` call (around line 72). Change it to pass the parser it already constructs:

The current code around line 35 constructs a parser:
```python
parser = ProLeapCobolParser(
    ...
    bridge_jar=bridge_jar,
    ...
)
```

And later (around line 72):
```python
_, linked = compile_cobol(source.encode("utf-8"), copybook_dirs=copybook_dirs)
```

Change the `compile_cobol` call to:
```python
_, linked = compile_cobol(
    source.encode("utf-8"),
    parser=parser,
    copybook_dirs=copybook_dirs,
)
```

- [ ] **Step 4: Update `tests/integration/project/test_cobol_connections.py`**

Add import at top:
```python
from interpreter.cobol.cobol_parser import make_cobol_parser
```

Add `parser=make_cobol_parser()` to every `extract_cobol_connections(...)` call in the file. There are ~10 callsites. Example:
```python
conns = extract_cobol_connections(
    _MAIN_CALL,
    extra_subprogram_sources={"HELPER": _HELPER},
    parser=make_cobol_parser(),
)
```

- [ ] **Step 5: Update `tests/unit/cobol/test_cobol_frontend_cache.py`**

Replace `_FakeRunner` and fake-parser construction throughout. The file has three tests. New version:

```python
from __future__ import annotations

import json
from pathlib import Path

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import make_cobol_parser
from interpreter.instructions import InstructionBase
from tests.covers import NotLanguageFeature, covers

_MINIMAL_ASG = {
    "program_id": "PROG",
    "data_fields": [],
    "sections": [],
    "paragraphs": [{"name": "MAIN", "statements": [{"type": "STOP_RUN"}]}],
}

_MINIMAL_SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROG.
       PROCEDURE DIVISION.
           GOBACK.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_returns_instructions():
    frontend = CobolFrontend(make_cobol_parser())
    ir = frontend.lower_from_ast_dict(dict(_MINIMAL_ASG))
    assert isinstance(ir, list)
    assert len(ir) > 0
    assert all(isinstance(inst, InstructionBase) for inst in ir)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_matches_lower(tmp_path):
    """lower_from_ast_dict with the real bridge dict must produce equivalent IR to lower()."""
    parser = make_cobol_parser()
    ast_path = tmp_path / "prog.ast.json"
    parser.parse_to_file(_MINIMAL_SRC, ast_path)
    data = json.loads(ast_path.read_text())

    frontend1 = CobolFrontend(make_cobol_parser())
    ir_from_dict = frontend1.lower_from_ast_dict(data)

    frontend2 = CobolFrontend(make_cobol_parser())
    ir_from_source = frontend2.lower(_MINIMAL_SRC)

    assert len(ir_from_source) == len(ir_from_dict)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_applies_preprocessor():
    calls: list[dict] = []

    class _SpyStrategy:
        def handles(self, stmt) -> bool:
            return False

        def preprocess_program_dict(self, data: dict) -> dict:
            calls.append(data)
            return data

        def on_procedure_entry(self, ctx, materialised) -> None:
            pass

        def lower(self, ctx, stmt, materialised) -> None:
            pass

    frontend = CobolFrontend(make_cobol_parser(), extension_strategies=[_SpyStrategy()])
    frontend.lower_from_ast_dict(dict(_MINIMAL_ASG))
    assert len(calls) == 1
```

- [ ] **Step 6: Run tests**

```bash
poetry run python -m pytest tests/unit/cobol/test_cobol_frontend_cache.py tests/integration/project/test_cobol_connections.py -v
```

Expected: all pass

- [ ] **Step 7: Format and commit**

```bash
poetry run python -m black interpreter/run.py interpreter/project/cobol_connections.py tests/unit/cobol/test_cobol_frontend_cache.py tests/integration/project/test_cobol_connections.py
# For jackal:
cd /Users/asgupta/code/jackal && poetry run python -m black jackal/cobol_step.py && cd -
git add interpreter/run.py interpreter/project/cobol_connections.py tests/unit/cobol/test_cobol_frontend_cache.py tests/integration/project/test_cobol_connections.py
git -C /Users/asgupta/code/jackal add jackal/cobol_step.py
git commit -m "fix(callers): pass real parser to compile_cobol, make_cobol_parser in run.py and connections"
git -C /Users/asgupta/code/jackal commit -m "fix(cobol): pass constructed parser to compile_cobol"
```

---

### Task 4: Migrate `test_cobol_parser.py`

Delete `FakeSubprocessRunner` and rewrite all tests with real COBOL source and `make_cobol_parser()`. Tests that verified bridge internals (command construction, stdin wire format) are deleted — those properties are verified implicitly by any successful parse.

**Files:**
- Modify: `tests/unit/test_cobol_parser.py`

**Interfaces:**
- Consumes: `make_cobol_parser()` from Task 1

- [ ] **Step 1: Rewrite `tests/unit/test_cobol_parser.py`**

Replace the entire file with:

```python
"""Tests for COBOL parser subprocess bridge."""

from pathlib import Path

from interpreter.cobol.cobol_parser import ProLeapCobolParser, make_cobol_parser
from interpreter.cobol.subprocess_runner import CobolParseError
from interpreter.cobol.features import CobolFeature
from tests.covers import NotLanguageFeature, covers

import pytest

_MINIMAL = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       PROCEDURE DIVISION.
           GOBACK.
"""

_WITH_DATA = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       77 WS-A PIC 9(5).
       PROCEDURE DIVISION.
           GOBACK.
"""

_WITH_SECTION = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       77 WS-A PIC 9(5).
       PROCEDURE DIVISION.
       MAIN-SECTION SECTION.
       INIT-PARA.
           DISPLAY 'HELLO'.
           GOBACK.
"""


class TestProLeapCobolParser:
    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_parse_minimal_asg(self):
        parser = make_cobol_parser()
        asg = parser.parse(_MINIMAL)
        assert asg is not None

    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_parse_data_field(self):
        parser = make_cobol_parser()
        asg = parser.parse(_WITH_DATA)
        assert len(asg.data_fields) == 1
        assert asg.data_fields[0].name == "WS-A"

    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_parse_with_sections(self):
        parser = make_cobol_parser()
        asg = parser.parse(_WITH_SECTION)
        assert len(asg.sections) == 1
        assert asg.sections[0].name == "MAIN-SECTION"

    @covers(CobolFeature.PROLEAP_BRIDGE)
    def test_parse_error_raises(self):
        parser = make_cobol_parser()
        with pytest.raises(CobolParseError):
            parser.parse(b"THIS IS NOT VALID COBOL AT ALL {{{{")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_to_file_writes_valid_json(tmp_path):
    out = tmp_path / "prog.ast.json"
    parser = make_cobol_parser()
    result = parser.parse_to_file(_MINIMAL, out)
    assert result == out
    assert out.exists()
    import json
    data = json.loads(out.read_text())
    assert "paragraphs" in data or "sections" in data or "data_fields" in data


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_to_file_returns_path_not_string(tmp_path):
    out = tmp_path / "prog.ast.json"
    parser = make_cobol_parser()
    result = parser.parse_to_file(_MINIMAL, out)
    assert isinstance(result, Path)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_make_cobol_parser_returns_proleap_parser():
    parser = make_cobol_parser()
    assert isinstance(parser, ProLeapCobolParser)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_make_cobol_parser_with_copybook_dirs_passes_them_through(tmp_path):
    parser = make_cobol_parser(copybook_dirs=[tmp_path])
    assert isinstance(parser, ProLeapCobolParser)
```

- [ ] **Step 2: Run tests**

```bash
poetry run python -m pytest tests/unit/test_cobol_parser.py -v
```

Expected: all tests pass

- [ ] **Step 3: Format and commit**

```bash
poetry run python -m black tests/unit/test_cobol_parser.py
git add tests/unit/test_cobol_parser.py
git commit -m "test(parser): replace FakeSubprocessRunner with real bridge in all tests"
```

---

### Task 5: Migrate `test_cobol_frontend.py`

Replace `_FakeParser` throughout. The migration pattern is:

**Old pattern:**
```python
asg = CobolASG(data_fields=[...], paragraphs=[...])
frontend = CobolFrontend(_FakeParser(asg))
instructions = frontend.lower(b"")
```

**New pattern:**
```python
data = CobolASG(data_fields=[...], paragraphs=[...]).to_dict()
frontend = CobolFrontend(make_cobol_parser())
instructions = frontend.lower_from_ast_dict(data)
```

The key: `CobolASG` and all its members (`CobolField`, `CobolParagraph`, `CobolSection`, all statement types) have `.to_dict()` methods. Calling `.to_dict()` on the `CobolASG` produces the exact dict format that `lower_from_ast_dict` expects. No COBOL source needed.

**Files:**
- Modify: `tests/unit/test_cobol_frontend.py`

**Interfaces:**
- Consumes: `make_cobol_parser()` from Task 1, `lower_from_ast_dict` (already exists on `CobolFrontend`)

- [ ] **Step 1: Update imports at the top of `test_cobol_frontend.py`**

Remove `CobolParser` from imports (used only by `_FakeParser`). Add:
```python
from interpreter.cobol.cobol_parser import make_cobol_parser
```

- [ ] **Step 2: Delete `_FakeParser` class**

Delete lines 65–73 (the `_FakeParser` class definition).

- [ ] **Step 3: Update `TestDataDivisionLowering` — five tests**

For every test in this class, the pattern is the same. Example for `test_alloc_region_size`:
```python
def test_alloc_region_size(self):
    data = CobolASG(
        data_fields=[
            CobolField(name="WS-A", level=77, pic="9(5)", usage="DISPLAY", offset=0),
        ],
    ).to_dict()
    frontend = CobolFrontend(make_cobol_parser())
    instructions = frontend.lower_from_ast_dict(data)
    # ... assertions unchanged ...
```

Apply this pattern to all five tests in `TestDataDivisionLowering`:
`test_alloc_region_size`, `test_initial_value_encoding`, `test_entry_label_emitted`, `test_group_field_total_bytes`, `test_multiple_fields_with_values`.

- [ ] **Step 4: Update `TestProcedureDivisionLowering._lower_with_field_and_stmts` helper**

This helper is used by all tests in the class. Change it once:
```python
def _lower_with_field_and_stmts(
    self,
    fields: list[CobolField],
    stmts: list[CobolStatementType],
) -> list[InstructionBase]:
    data = CobolASG(
        data_fields=fields,
        paragraphs=[CobolParagraph(name="MAIN", statements=stmts)],
    ).to_dict()
    frontend = CobolFrontend(make_cobol_parser())
    return frontend.lower_from_ast_dict(data)
```

All tests calling `self._lower_with_field_and_stmts(...)` need no other changes.

- [ ] **Step 5: Update any tests in `TestProcedureDivisionLowering` that build `CobolASG` directly (not via the helper)**

Search the class for any remaining `CobolFrontend(_FakeParser(asg))` patterns and apply the same `.to_dict()` + `lower_from_ast_dict` migration.

- [ ] **Step 6: Update all remaining test classes**

Apply the same pattern to every other class in the file:
`TestComputeLowering`, `TestPerformLoopLowering`, `TestSectionPerform`, `TestTier1Lowering`, `TestTier2Lowering`, `TestSearchLowering`, `TestCallAlterEntryCancelLowering`, `TestBareStatements`, `TestDataLayout`, `TestMoveCorrespondingLowering`, `TestSectionedLayout`, `TestSingletonInit`.

In every test:
1. Find `CobolASG(...).` → add `.to_dict()` before passing to `_FakeParser`
2. Find `CobolFrontend(_FakeParser(asg))` → change to `CobolFrontend(make_cobol_parser())`
3. Find `.lower(b"")` → change to `.lower_from_ast_dict(data)` where `data` is the `.to_dict()` result

For classes that have a helper method like `_lower_with_field_and_stmts`, update the helper once and all callers are fixed automatically.

- [ ] **Step 7: Run tests**

```bash
poetry run python -m pytest tests/unit/test_cobol_frontend.py -v
```

Expected: all tests pass (same count as before)

- [ ] **Step 8: Format and commit**

```bash
poetry run python -m black tests/unit/test_cobol_frontend.py
git add tests/unit/test_cobol_frontend.py
git commit -m "test(frontend): replace _FakeParser with lower_from_ast_dict + real parser"
```

---

### Task 6: Migrate `test_cobol_e2e.py`

Same migration as Task 5. `test_cobol_e2e.py` has two patterns:
1. **Fixture-based:** `asg = _load_fixture("hello_world.json")` — `_load_fixture` currently returns `CobolASG`. Change it to return `dict`.
2. **Inline ASG:** same `.to_dict()` + `lower_from_ast_dict` pattern as Task 5.

**Files:**
- Modify: `tests/unit/test_cobol_e2e.py`

**Interfaces:**
- Consumes: `make_cobol_parser()` from Task 1

- [ ] **Step 1: Update imports**

Remove `CobolParser` from imports. Add:
```python
from interpreter.cobol.cobol_parser import make_cobol_parser
```

- [ ] **Step 2: Delete `_FakeParser` class**

Delete the `_FakeParser` class definition (lines 35–42).

- [ ] **Step 3: Update `_load_fixture` helper to return `dict`**

```python
def _load_fixture(name: str) -> dict:
    fixture_path = FIXTURE_DIR / name
    return json.loads(fixture_path.read_text())
```

- [ ] **Step 4: Update all fixture-based tests**

Every test that does:
```python
asg = _load_fixture("hello_world.json")
frontend = CobolFrontend(_FakeParser(asg))
instructions = frontend.lower(b"")
```

Changes to:
```python
data = _load_fixture("hello_world.json")
frontend = CobolFrontend(make_cobol_parser())
instructions = frontend.lower_from_ast_dict(data)
```

Apply to all tests in: `TestHelloWorldFixture`, `TestMoveFieldsFixture`, `TestArithmeticFixture`, `TestPerformReturnFixture`.

- [ ] **Step 5: Update all inline-ASG tests**

Every test that constructs `CobolASG(...)` directly and passes it to `_FakeParser`:
```python
asg = CobolASG(...)
frontend = CobolFrontend(_FakeParser(asg))
instructions = frontend.lower(b"")
```
Changes to:
```python
data = CobolASG(...).to_dict()
frontend = CobolFrontend(make_cobol_parser())
instructions = frontend.lower_from_ast_dict(data)
```

Apply to all remaining test classes: `TestCobolFrontendIdempotency`, `TestMultipleStatementTypes`, `TestIfElseExecution`, `TestPerformTimesExecution`, `TestPerformUntilExecution`, `TestPerformVaryingExecution`, `TestNumericValueVerification`, `TestSectionFallThrough`, `TestNestedPerformNumericValues`, `TestGotoInsidePerform`, `TestPicXDigitOnlyValue`.

- [ ] **Step 6: Run tests**

```bash
poetry run python -m pytest tests/unit/test_cobol_e2e.py -v
```

Expected: all tests pass (same count as before)

- [ ] **Step 7: Run the full unit suite to check for regressions**

```bash
poetry run python -m pytest tests/unit/ -q
```

Expected: same count as before this task began, 0 failures

- [ ] **Step 8: Format and commit**

```bash
poetry run python -m black tests/unit/test_cobol_e2e.py
git add tests/unit/test_cobol_e2e.py
git commit -m "test(e2e): replace _FakeParser with lower_from_ast_dict + real parser"
```

---

### Task 7: Final verification

- [ ] **Step 1: Run the full test suite**

```bash
poetry run python -m pytest -q
```

Expected: same total count as before this feature began, 0 failures

- [ ] **Step 2: Verify no fake parsers remain**

```bash
grep -rn "FakeParser\|FakeSubprocessRunner\|FakeRunner\|FakeParseToFile" tests/ --include="*.py"
```

Expected: 0 matches

- [ ] **Step 3: Verify `parser` is required (no optional default) in both public functions**

```bash
grep -n "parser: Any = None" interpreter/project/cobol_compile.py
```

Expected: 0 matches

- [ ] **Step 4: Commit**

```bash
git commit --allow-empty -m "chore: final verification — all fake parsers removed, parser required"
```

(Only create this commit if verification surfaced a real fix; otherwise skip it.)
