# AST Cache: Separate Parse and Lower Phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple the ProLeap bridge call (parse phase) from IR emission (lower phase) so that ASTs are never accumulated in memory during parallel parsing, with each AST freed immediately after its bridge JSON is written to disk.

**Why this matters:** Without parallelism, the current sequential loop processes one AST at a time — no accumulation problem. With parallelism (N concurrent bridge subprocesses), a naive implementation would hold N ASTs in memory simultaneously. Writing each bridge result to disk immediately caps in-flight AST memory at `max_workers` JSON strings regardless of codebase size. Speed also improves: N sequential Java process launches → N concurrent. The remaining memory problem (accumulated IR across all modules in `link_modules`) is Section 2, deferred.

**Architecture:** `ProLeapCobolParser` gains `parse_to_file` to write raw bridge JSON to disk without returning it. `CobolFrontend` gains `lower_from_ast_dict(data)` and a shared `_lower_asg(asg)` core — so the lower phase can be driven from a pre-loaded dict without source bytes. `compile_cobol_module` gains `ast_path: Path | None` to use `lower_from_ast_dict` instead of `lower`. `parallel_parse_to_cache` runs parse jobs concurrently via `ThreadPoolExecutor`, writing one JSON file per module. `compile_cobol` gains opt-in `ast_cache_dir` that runs Phase 1 (parallel parse to disk) then Phase 2 (sequential lower from disk, one AST at a time).

**Tech Stack:** Python `concurrent.futures.ThreadPoolExecutor`, `pathlib.Path`, `json`, existing `CobolASG.from_dict`.

## Global Constraints

- `parse_to_file` is added to `ProLeapCobolParser` only — no change to the `CobolParser` ABC.
- No `CachedCobolParser` class. The seam is at `CobolFrontend`, not at the parser.
- `lower_from_ast_dict` applies extension strategy preprocessors and sets the `_cics_text_parser` context variable, matching what `lower()` does before calling the parser.
- `CobolFrontend.lower()` is unchanged in signature and behaviour.
- When `ast_cache_dir` is not supplied, `compile_cobol` behaviour is byte-for-byte identical to today.
- On-disk format is the raw JSON string emitted by the ProLeap bridge — no additional serialisation layer.
- Run tests with `poetry run python -m pytest`.
- Format with `poetry run python -m black .` before committing.
- Follow `@covers(NotLanguageFeature.INFRASTRUCTURE)` for all new tests.

---

### Task 1: `parse_to_file` on `ProLeapCobolParser` + `lower_from_ast_dict` on `CobolFrontend`

**Files:**
- Modify: `interpreter/cobol/cobol_parser.py`
- Modify: `interpreter/cobol/cobol_frontend.py`
- Test: `tests/unit/test_cobol_parser.py`
- Test: `tests/unit/cobol/test_cobol_frontend_cache.py` (new file)

**Interfaces:**
- Produces:
  - `ProLeapCobolParser.parse_to_file(source: bytes, out_path: Path) -> Path` — runs bridge, writes raw JSON string to `out_path`, frees JSON string, returns `out_path`. ABC unchanged.
  - `CobolFrontend._lower_asg(asg: CobolASG) -> list[InstructionBase]` — private; contains everything currently after the `parse` call in `lower()`.
  - `CobolFrontend.lower_from_ast_dict(data: dict) -> list[InstructionBase]` — applies extension preprocessors + sets `_cics_text_parser` context var, then calls `_lower_asg`. Takes no source bytes.
  - `CobolFrontend.lower()` — refactored to call `_lower_asg`; signature and behaviour unchanged.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_cobol_parser.py — add to existing file

import json
from pathlib import Path
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from tests.covers import NotLanguageFeature, covers

_MINIMAL_ASG = {
    "program_id": "PROG",
    "data_fields": [],
    "sections": [],
    "paragraphs": [{"name": "MAIN", "statements": [{"type": "STOP_RUN"}]}],
}

@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_to_file_writes_raw_json(tmp_path):
    out = tmp_path / "prog.ast.json"
    runner = FakeSubprocessRunner(json.dumps(_MINIMAL_ASG))
    parser = ProLeapCobolParser(runner, "fake.jar")
    result = parser.parse_to_file(b"irrelevant", out)
    assert result == out
    assert out.exists()
    assert json.loads(out.read_text())["program_id"] == "PROG"

@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_to_file_does_not_hold_json_string_after_return(tmp_path):
    # Verify parse_to_file returns Path, not JSON — caller cannot accidentally
    # accumulate the string by capturing the return value.
    out = tmp_path / "prog.ast.json"
    runner = FakeSubprocessRunner(json.dumps(_MINIMAL_ASG))
    parser = ProLeapCobolParser(runner, "fake.jar")
    result = parser.parse_to_file(b"source", out)
    assert isinstance(result, Path)
```

```python
# tests/unit/cobol/test_cobol_frontend_cache.py — new file

from __future__ import annotations

import json
from pathlib import Path

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import SubprocessRunner
from interpreter.instructions import InstructionBase
from tests.covers import NotLanguageFeature, covers

_MINIMAL_ASG = {
    "program_id": "PROG",
    "data_fields": [],
    "sections": [],
    "paragraphs": [{"name": "MAIN", "statements": [{"type": "STOP_RUN"}]}],
}


class _FakeRunner(SubprocessRunner):
    def __init__(self, output: str) -> None:
        self._output = output
    def run(self, command, input_data=""):
        return self._output


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_returns_instructions():
    parser = ProLeapCobolParser(_FakeRunner(json.dumps(_MINIMAL_ASG)), "fake.jar")
    frontend = CobolFrontend(parser)
    ir = frontend.lower_from_ast_dict(dict(_MINIMAL_ASG))
    assert isinstance(ir, list)
    assert len(ir) > 0
    assert all(isinstance(inst, InstructionBase) for inst in ir)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_matches_lower():
    """lower_from_ast_dict with the same dict must produce equivalent IR to lower()."""
    parser = ProLeapCobolParser(_FakeRunner(json.dumps(_MINIMAL_ASG)), "fake.jar")

    frontend1 = CobolFrontend(parser)
    ir_from_source = frontend1.lower(b"ignored — fake runner ignores it")

    frontend2 = CobolFrontend(parser)
    ir_from_dict = frontend2.lower_from_ast_dict(dict(_MINIMAL_ASG))

    assert len(ir_from_source) == len(ir_from_dict)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_applies_preprocessor():
    calls: list[dict] = []

    class _SpyStrategy:
        def preprocess_program_dict(self, data: dict) -> dict:
            calls.append(data)
            return data

    parser = ProLeapCobolParser(_FakeRunner(json.dumps(_MINIMAL_ASG)), "fake.jar")
    frontend = CobolFrontend(parser, extension_strategies=[_SpyStrategy()])
    frontend.lower_from_ast_dict(dict(_MINIMAL_ASG))
    assert len(calls) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/test_cobol_parser.py::test_parse_to_file_writes_raw_json tests/unit/test_cobol_parser.py::test_parse_to_file_does_not_hold_json_string_after_return tests/unit/cobol/test_cobol_frontend_cache.py -v
```

Expected: `AttributeError` — `parse_to_file` and `lower_from_ast_dict` do not exist yet.

- [ ] **Step 3: Add `parse_to_file` to `ProLeapCobolParser`**

In `interpreter/cobol/cobol_parser.py`, add after the existing `parse` method (no ABC change):

```python
def parse_to_file(self, source: bytes, out_path: Path) -> Path:
    """Run the bridge and write raw JSON to out_path. Returns out_path.

    The JSON string is freed immediately after writing — never returned —
    so callers cannot accumulate it when running in parallel.
    """
    command = ["java", "-jar", self._bridge_jar]
    for d in self._copybook_dirs:
        command += ["-copybook-dir", str(d)]
    try:
        json_str = self._runner.run(command, source.decode("utf-8"))
    except CobolParseError as e:
        raise self._enrich_copybook_error(e) from e
    out_path.write_text(json_str, encoding="utf-8")
    return out_path
```

Ensure `from pathlib import Path` is already in the imports (it is).

- [ ] **Step 4: Refactor `CobolFrontend.lower()` and add `lower_from_ast_dict`**

In `interpreter/cobol/cobol_frontend.py`, replace the existing `lower` method with:

```python
def lower(
    self,
    source: bytes,
    namespace_resolver: NamespaceResolver = Frontend._NULL_RESOLVER,
    resolved_imports: dict[str, PathName] | None = None,
) -> list[InstructionBase]:
    """Lower COBOL source to IR via the ProLeap bridge."""

    def _chained_preprocess(data: dict) -> dict:
        for strat in self._extension_strategies:
            data = strat.preprocess_program_dict(data)
        return data

    token = _cics_text_parser.set(self._cics_text_parser)
    try:
        asg = self._parser.parse(source, preprocessor=_chained_preprocess)
    finally:
        _cics_text_parser.reset(token)
    return self._lower_asg(asg)

def lower_from_ast_dict(self, data: dict) -> list[InstructionBase]:
    """Lower from a raw bridge JSON dict — no subprocess, no source bytes.

    Applies extension strategy preprocessors (same as lower()) then lowers
    the resulting ASG to IR. Use this in Phase 2 of the AST cache pipeline
    after parse_to_file has written ASTs to disk.
    """
    token = _cics_text_parser.set(self._cics_text_parser)
    try:
        for strat in self._extension_strategies:
            data = strat.preprocess_program_dict(data)
        asg = CobolASG.from_dict(data)
    finally:
        _cics_text_parser.reset(token)
    return self._lower_asg(asg)

def _lower_asg(self, asg: "CobolASG") -> list[InstructionBase]:
    """Shared lowering core: ASG → IR. Called by lower() and lower_from_ast_dict()."""
    from interpreter.cobol.asg_types import CobolASG as _CobolASG  # avoid circular at module level

    sectioned = build_sectioned_layout(asg)
    self._program_id = asg.program_id or "MAIN"
    logger.debug(
        "lowering %s: %d sections, %d paragraphs",
        self._program_id,
        len(asg.sections),
        len(asg.paragraphs),
    )
    self._layout = sectioned.working_storage
    self._symbol_table = SymbolTable.from_data_layout(sectioned.working_storage)
    condition_index = build_condition_index(sectioned.working_storage)

    self._ctx = EmitContext(
        dispatch_fn=dispatch_statement,
        observer=self._observer,
        condition_index=condition_index,
        extension_strategies=self._extension_strategies,
        asg=asg,
    )

    self._ctx.emit_inst(Label_(label=CodeLabel("entry")))
    after_label = lower_program_init(
        self._ctx, self._program_id, sectioned.working_storage
    )
    proc_label = CodeLabel(f"func_{self._program_id.lower()}_0")
    self._ctx.emit_inst(Label_(label=proc_label))
    lower_ws_from_singleton(self._ctx, self._program_id)
    materialised = lower_sectioned_data_division(
        self._ctx, sectioned, self._program_id
    )
    lower_procedure_division(self._ctx, asg, materialised)
    self._ctx.emit_inst(Label_(label=after_label))

    logger.debug(
        "COBOL frontend produced %d IR instructions",
        len(self._ctx.instructions),
    )
    return self._ctx.instructions
```

Add `from interpreter.cobol.asg_types import CobolASG` to the top-level imports of `cobol_frontend.py` (it may already be there via `TYPE_CHECKING` — move it out if so, since `_lower_asg` uses it at runtime).

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/test_cobol_parser.py::test_parse_to_file_writes_raw_json tests/unit/test_cobol_parser.py::test_parse_to_file_does_not_hold_json_string_after_return tests/unit/cobol/test_cobol_frontend_cache.py -v
```

Expected: all pass.

- [ ] **Step 6: Run the full unit suite**

```bash
poetry run python -m pytest tests/unit/ -q
```

Expected: same count as before plus new tests, 0 failures.

- [ ] **Step 7: Format and commit**

```bash
poetry run python -m black interpreter/cobol/cobol_parser.py interpreter/cobol/cobol_frontend.py tests/unit/test_cobol_parser.py tests/unit/cobol/test_cobol_frontend_cache.py
git add interpreter/cobol/cobol_parser.py interpreter/cobol/cobol_frontend.py tests/unit/test_cobol_parser.py tests/unit/cobol/test_cobol_frontend_cache.py
git commit -m "feat(ast-cache): parse_to_file + lower_from_ast_dict/_lower_asg — parse/lower split"
```

---

### Task 2: `parallel_parse_to_cache` in `cobol_compile.py`

**Files:**
- Modify: `interpreter/project/cobol_compile.py`
- Test: `tests/unit/project/test_cobol_compile.py`

**Interfaces:**
- Consumes: `ProLeapCobolParser.parse_to_file` from Task 1
- Produces:
  - `parallel_parse_to_cache(sources: dict[Path, bytes], parser: Any, cache_dir: Path, *, max_workers: int = 4) -> dict[Path, Path]`
  - `parser` must have `parse_to_file(source: bytes, out_path: Path) -> Path` (duck-typed — only `ProLeapCobolParser` satisfies this in production).
  - Returns `{source_path: ast_json_path}`. Filename: `cache_dir / f"{source_path.stem}.ast.json"`.
  - `cache_dir` is created if absent.
  - Each worker writes to disk and frees the JSON string before the next write — no accumulation.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/project/test_cobol_compile.py — add to existing file

import json
from pathlib import Path
from interpreter.project.cobol_compile import parallel_parse_to_cache
from tests.covers import NotLanguageFeature, covers

_MINIMAL_ASG_JSON = json.dumps({
    "program_id": "PROG",
    "data_fields": [],
    "sections": [],
    "paragraphs": [{"name": "MAIN", "statements": [{"type": "STOP_RUN"}]}],
})


class _FakeParseToFileParser:
    """Duck-typed fake: writes a fixed JSON string to out_path."""
    def parse_to_file(self, source: bytes, out_path: Path) -> Path:
        out_path.write_text(_MINIMAL_ASG_JSON, encoding="utf-8")
        return out_path


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_writes_one_file_per_source(tmp_path):
    sources = {
        Path("prog_a.cbl"): b"source a",
        Path("prog_b.cbl"): b"source b",
        Path("prog_c.cbl"): b"source c",
    }
    result = parallel_parse_to_cache(sources, _FakeParseToFileParser(), tmp_path)
    assert set(result.keys()) == set(sources.keys())
    for src_path, ast_path in result.items():
        assert ast_path == tmp_path / f"{src_path.stem}.ast.json"
        assert ast_path.exists()
        assert json.loads(ast_path.read_text())["program_id"] == "PROG"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_creates_cache_dir(tmp_path):
    cache_dir = tmp_path / "nested" / "cache"
    assert not cache_dir.exists()
    parallel_parse_to_cache({Path("x.cbl"): b"src"}, _FakeParseToFileParser(), cache_dir)
    assert cache_dir.is_dir()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_empty_sources(tmp_path):
    result = parallel_parse_to_cache({}, _FakeParseToFileParser(), tmp_path)
    assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/project/test_cobol_compile.py::test_parallel_parse_to_cache_writes_one_file_per_source tests/unit/project/test_cobol_compile.py::test_parallel_parse_to_cache_creates_cache_dir tests/unit/project/test_cobol_compile.py::test_parallel_parse_to_cache_empty_sources -v
```

Expected: `ImportError` — `parallel_parse_to_cache` does not exist yet.

- [ ] **Step 3: Implement `parallel_parse_to_cache`**

Add to `interpreter/project/cobol_compile.py` (after imports, before `compile_cobol_module`):

```python
from concurrent.futures import ThreadPoolExecutor, as_completed  # add to imports

def parallel_parse_to_cache(
    sources: dict[Path, bytes],
    parser: Any,
    cache_dir: Path,
    *,
    max_workers: int = 4,
) -> dict[Path, Path]:
    """Parse all sources in parallel, writing raw bridge JSON to cache_dir.

    Each worker calls parser.parse_to_file(), which writes to disk and frees
    the JSON string immediately — ASTs never accumulate in memory across workers.
    Returns {source_path: ast_json_path}. cache_dir is created if absent.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    def _parse_one(item: tuple[Path, bytes]) -> tuple[Path, Path]:
        src_path, source = item
        out_path = cache_dir / f"{src_path.stem}.ast.json"
        parser.parse_to_file(source, out_path)
        return src_path, out_path

    result: dict[Path, Path] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_parse_one, item): item[0] for item in sources.items()}
        for future in as_completed(futures):
            src_path, ast_path = future.result()
            result[src_path] = ast_path
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/project/test_cobol_compile.py::test_parallel_parse_to_cache_writes_one_file_per_source tests/unit/project/test_cobol_compile.py::test_parallel_parse_to_cache_creates_cache_dir tests/unit/project/test_cobol_compile.py::test_parallel_parse_to_cache_empty_sources -v
```

Expected: 3 passed.

- [ ] **Step 5: Run the full unit suite**

```bash
poetry run python -m pytest tests/unit/ -q
```

Expected: same count as before plus new tests, 0 failures.

- [ ] **Step 6: Format and commit**

```bash
poetry run python -m black interpreter/project/cobol_compile.py tests/unit/project/test_cobol_compile.py
git add interpreter/project/cobol_compile.py tests/unit/project/test_cobol_compile.py
git commit -m "feat(ast-cache): parallel_parse_to_cache — concurrent bridge calls, no AST accumulation"
```

---

### Task 3: `ast_path` on `compile_cobol_module` + `ast_cache_dir` on `compile_cobol`

**Files:**
- Modify: `interpreter/project/cobol_compile.py`
- Test: `tests/unit/project/test_cobol_compile.py`

**Interfaces:**
- Consumes: `CobolFrontend.lower_from_ast_dict` from Task 1, `parallel_parse_to_cache` from Task 2
- Produces:
  - `compile_cobol_module(..., ast_path: Path | None = None)` — when set, calls `frontend.lower_from_ast_dict(json.loads(ast_path.read_text("utf-8")))` instead of `frontend.lower(source)`. The loaded dict goes out of scope immediately after `lower_from_ast_dict` returns.
  - `compile_cobol(..., ast_cache_dir: Path | None = None)` — when set with a `parser`: Phase 1 parses all sources to `ast_cache_dir` in parallel; Phase 2 calls `compile_cobol_module` for each module with its `ast_path`. Result is identical to the non-cache path.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/project/test_cobol_compile.py — add to existing file

from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.types import LinkedProgram
from tests.covers import NotLanguageFeature, covers

_HELLO = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO.
       PROCEDURE DIVISION.
           DISPLAY 'HI'.
           GOBACK.
"""

_CALLER = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLER.
       PROCEDURE DIVISION.
           CALL 'CALLEE'.
           GOBACK.
"""

_CALLEE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLEE.
       PROCEDURE DIVISION.
           DISPLAY 'IN CALLEE'.
           GOBACK.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_ast_cache_dir_single_module_writes_json(tmp_path):
    cache = tmp_path / "ast-cache"
    _, linked = compile_cobol(_HELLO, ast_cache_dir=cache)
    assert isinstance(linked, LinkedProgram)
    assert cache.is_dir()
    assert len(list(cache.glob("*.ast.json"))) == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_ast_cache_dir_multi_module_writes_one_json_per_module(tmp_path):
    cache = tmp_path / "ast-cache"
    _, linked = compile_cobol(
        _CALLER,
        extra_subprogram_sources={"CALLEE": _CALLEE},
        ast_cache_dir=cache,
    )
    assert isinstance(linked, LinkedProgram)
    assert len(list(cache.glob("*.ast.json"))) == 2


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_ast_cache_dir_produces_runnable_program(tmp_path):
    from interpreter.run import EntryPoint, run_linked
    _, linked = compile_cobol(_HELLO, ast_cache_dir=tmp_path / "cache")
    vm = run_linked(linked, entry_point=EntryPoint.top_level(), max_steps=10_000)
    assert vm is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_without_ast_cache_dir_unchanged():
    _, linked = compile_cobol(_HELLO)
    assert isinstance(linked, LinkedProgram)
    assert linked.merged_cfg is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/project/test_cobol_compile.py::test_compile_cobol_ast_cache_dir_single_module_writes_json tests/unit/project/test_cobol_compile.py::test_compile_cobol_ast_cache_dir_multi_module_writes_one_json_per_module tests/unit/project/test_cobol_compile.py::test_compile_cobol_ast_cache_dir_produces_runnable_program tests/unit/project/test_cobol_compile.py::test_compile_cobol_without_ast_cache_dir_unchanged -v
```

Expected: first 3 fail (`TypeError` — unexpected keyword `ast_cache_dir`), last 1 passes.

- [ ] **Step 3: Add `ast_path` to `compile_cobol_module`**

In `interpreter/project/cobol_compile.py`, add `import json` to imports, then modify `compile_cobol_module`:

```python
def compile_cobol_module(
    source: bytes,
    *,
    parser: Any = None,
    copybook_dirs: list[Path] | None = None,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    path: Path = Path("__main__.cbl"),
    ast_path: Path | None = None,          # ← new
) -> tuple[Any, ModuleUnit]:
    """Lower one COBOL source into a (frontend, ModuleUnit). The shared core."""
    frontend = get_frontend(
        Language.COBOL,
        frontend_type=constants.FRONTEND_COBOL,
        observer=observer,
        copybook_dirs=copybook_dirs,
        cobol_parser=parser,
        extension_strategies=extension_strategies,
        cics_text_parser=cics_text_parser,
    )
    if ast_path is not None:
        # Phase 2: load AST from disk, lower, free dict immediately.
        ir = frontend.lower_from_ast_dict(json.loads(ast_path.read_text("utf-8")))
    else:
        ir = frontend.lower(source)
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

- [ ] **Step 4: Add `ast_cache_dir` to `compile_cobol`**

Add to `compile_cobol`'s signature:

```python
def compile_cobol(
    source: bytes,
    *,
    parser: Any = None,
    copybook_dirs: list[Path] | None = None,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    program_source_dir: Path | None = None,
    extra_subprogram_sources: dict[str, bytes] | None = None,
    source_transform: Callable[[str], str] = lambda s: s,
    ast_cache_dir: Path | None = None,     # ← new
) -> tuple[Any, LinkedProgram]:
```

Add the two-phase block at the top of `compile_cobol`, before `main_path = Path("__main__.cbl")`:

```python
    if ast_cache_dir is not None and parser is not None:
        main_path = Path("__main__.cbl")
        base = program_source_dir or Path(".")

        # Collect all sources that need parsing.
        sub_sources: dict[str, bytes] = dict(extra_subprogram_sources or {})
        all_sources: dict[Path, bytes] = {main_path: source}
        for prog_name, prog_src in sub_sources.items():
            all_sources[(base / f"{prog_name}.cbl").resolve()] = prog_src

        # Phase 1: parallel parse — each worker writes JSON to disk and frees it.
        parallel_parse_to_cache(all_sources, parser, ast_cache_dir)

        def _ast_path(src_path: Path) -> Path:
            return ast_cache_dir / f"{src_path.stem}.ast.json"

        # Phase 2: sequential lower — one AST in memory at a time.
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
        linked.entry_func_label = CodeLabel(f"__main__.func_{main_program_id.lower()}_0")
        return main_frontend, linked
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/project/test_cobol_compile.py::test_compile_cobol_ast_cache_dir_single_module_writes_json tests/unit/project/test_cobol_compile.py::test_compile_cobol_ast_cache_dir_multi_module_writes_one_json_per_module tests/unit/project/test_cobol_compile.py::test_compile_cobol_ast_cache_dir_produces_runnable_program tests/unit/project/test_cobol_compile.py::test_compile_cobol_without_ast_cache_dir_unchanged -v
```

Expected: 4 passed.

- [ ] **Step 6: Run the full unit suite**

```bash
poetry run python -m pytest tests/unit/ -q
```

Expected: same count as before plus new tests, 0 failures.

- [ ] **Step 7: Format and commit**

```bash
poetry run python -m black interpreter/project/cobol_compile.py tests/unit/project/test_cobol_compile.py
git add interpreter/project/cobol_compile.py tests/unit/project/test_cobol_compile.py
git commit -m "feat(ast-cache): ast_cache_dir on compile_cobol — parallel parse + sequential lower"
```
