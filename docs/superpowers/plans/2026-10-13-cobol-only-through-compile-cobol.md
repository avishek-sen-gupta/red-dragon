# COBOL Only Through compile_cobol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `compile_cobol` compiles a fixed list of programs; finding that list is a separate shell step; `compile_directory` and the COBOL CLI stop compiling COBOL directories.

**Architecture:** Extract the CALL walk into `discover_callee_programs` (shell), give `compile_cobol` a `programs: Sequence[SourceFile]` list in place of its three discovery parameters, have `compile_program` discover before making strategies, move COBOL's `compile_directory` callers onto `compile_cobol`, then remove COBOL from `compile_directory`. All work in `~/code/red-dragon`; the forge changes only by submodule bump.

**Tech Stack:** Python 3.13, uv, pytest (xdist), ProLeap bridge JAR, import-linter, python-fp-lint, Talisman, beads.

**Spec:** `docs/superpowers/specs/2026-10-13-cobol-only-through-compile-cobol-design.md`

The spec names the shell step `discover_called_programs`; it is `discover_callee_programs` here, at the user's request after the spec was written.

## Global Constraints

- Work in `~/code/red-dragon`; never edit `~/code/red-dragon-forge/vendor/red-dragon`.
- `interpreter.project` must not import `interpreter.cobol` (`.importlinter` `cobol-isolation`); `compile_cobol` returns `Frontend`, not `CobolFrontend`.
- No comments beyond a one-line module/class header; no `Any` in new signatures; frozen dataclasses; `Sequence`/`Mapping` for read-only parameters.
- No `--no-verify`. Talisman flags words containing "pass" (e.g. `prepass`): keep the names and update the file's `.talismanrc` checksum with the value Talisman reports.
- Assertions in moved tests do not change.
- `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar` for running COBOL tests by hand; `make test PYTEST_ARGS="-q"` is the full suite.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01Y8tAV2ducgCCVspgN11inx`.

## Review Focus

- A linked subprogram and a discovered callee with the same program name: the linked one must be the one compiled (as `extra_subprogram_sources` won before).
- A callee that fails to lower must still be skipped with a warning, not abort the compile (existing behaviour, now on `programs`).
- Two programs in `programs` with the same path: the dict built from them must not silently drop one without the caller noticing — keep "last wins" and say so in the docstring, as today's dict did.
- The CLI given a directory must fail with a message, not a traceback.
- Label prefixes for linked subprograms change from an absolute cwd-based path to `NAME`; any forge test that matched the old prefix would fail in Task 7's run.

---

### Task 1: `SourceFile` and `discover_callee_programs` (shell step, behaviour unchanged)

**Files:**
- Create: `interpreter/project/source_file.py`
- Create: `interpreter/project/cobol_discovery.py`
- Modify: `interpreter/project/cobol_compile.py` (`_resolve_call_sources` removed; `compile_cobol` calls the new function)
- Create: `tests/unit/project/test_cobol_discovery.py`
- Modify: `tests/unit/project/test_cobol_compile.py` (move `test_source_transform_applied_to_on_disk_callees_only` out)

**Interfaces:**
- Produces: `SourceFile(path: Path, source: bytes)` (frozen dataclass); `discover_callee_programs(source: bytes, search_dirs: Sequence[Path], source_transform: Callable[[str], str] = _identity) -> tuple[SourceFile, ...]`.

- [ ] **Step 1: Write the failing discovery tests**

`tests/unit/project/test_cobol_discovery.py`:

```python
"""discover_callee_programs: the shell step that turns a main program and ordered
search directories into the list of programs to compile."""

from pathlib import Path

from interpreter.project.cobol_discovery import discover_callee_programs
from interpreter.project.source_file import SourceFile
from tests.covers import NotLanguageFeature, covers


def _program(program_id: str, *calls: str) -> bytes:
    call_lines = "".join(f"           CALL '{c}'.\n" for c in calls)
    return (
        "       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. {program_id}.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-NAME PIC X(8) VALUE 'DYNAMIC'.\n"
        "       PROCEDURE DIVISION.\n"
        f"{call_lines}"
        "           CALL WS-NAME.\n"
        "           GOBACK.\n"
    ).encode()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_discovery_follows_static_calls_through_ordered_directories(tmp_path: Path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "MID.cbl").write_bytes(_program("MID", "LEAF"))
    (second / "MID.cbl").write_bytes(_program("SHADOWED"))
    (second / "LEAF.cbl").write_bytes(_program("LEAF"))
    (second / "DYNAMIC.cbl").write_bytes(_program("DYNAMIC"))

    found = discover_callee_programs(
        _program("MAIN", "MID"), (first, second), lambda s: s.replace("GOBACK", "EXIT PROGRAM")
    )

    assert sorted(found, key=lambda f: f.path.name) == [
        SourceFile(
            (second / "LEAF.cbl").resolve(),
            _program("LEAF").replace(b"GOBACK", b"EXIT PROGRAM"),
        ),
        SourceFile(
            (first / "MID.cbl").resolve(),
            _program("MID", "LEAF").replace(b"GOBACK", b"EXIT PROGRAM"),
        ),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_discovery_without_search_directories_finds_nothing():
    assert discover_callee_programs(_program("MAIN", "MID"), ()) == ()
```

One behaviour per test: the first pins transitivity, first-directory-wins, the transform on every program read, and that `CALL WS-NAME` is not followed (DYNAMIC is never returned); the second pins the empty search path.

- [ ] **Step 2: Run them**

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run --no-sync pytest -q -n0 tests/unit/project/test_cobol_discovery.py 2>&1 | tail -3`
Expected: FAIL, `ModuleNotFoundError: No module named 'interpreter.project.cobol_discovery'`.

- [ ] **Step 3: Create `SourceFile`**

`interpreter/project/source_file.py`:

```python
"""One source file handed to a compiler: its path and its bytes, already read."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceFile:
    path: Path
    source: bytes
```

- [ ] **Step 4: Move the CALL walk**

Create `interpreter/project/cobol_discovery.py` with a module header line, `_identity`, and `discover_callee_programs`, whose body is today's `_resolve_call_sources` (in `interpreter/project/cobol_compile.py`) with `main_path = Path("__main__.cbl")`, the search dirs resolved (`[d.resolve() for d in search_dirs]`) and the result returned as `tuple(SourceFile(path, source) for path, source in resolved.items())`. It imports `extract_imports`, `get_resolver`, `ImportKind`, `Language` exactly as `cobol_compile.py` does today. Delete `_resolve_call_sources` from `cobol_compile.py`, and in `compile_cobol` replace the `disk_sources = _resolve_call_sources(...)` block with:

```python
        disk_sources: dict[Path, bytes] = {
            found.path: found.source
            for found in discover_callee_programs(
                source, source_search_dirs, source_transform
            )
        }
```

(`compile_cobol`'s own parameters are unchanged in this task.)

- [ ] **Step 5: Move the transform test**

Delete `test_source_transform_applied_to_on_disk_callees_only` from `tests/unit/project/test_cobol_compile.py`; its contract (the transform applies to what discovery reads) is now Step 1's first test.

- [ ] **Step 6: Run discovery and compile tests**

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run --no-sync pytest -q -n0 tests/unit/project/test_cobol_discovery.py tests/unit/project/test_cobol_compile.py tests/unit/project/test_coprocessor_compile.py 2>&1 | tail -1`
Expected: all green.

- [ ] **Step 7: Mutation-check**

Make `discover_callee_programs` skip `source_transform` (read `target.read_text()` raw): the first test fails. Make it search only `search_dirs[-1:]`: the first test fails. Revert both.

- [ ] **Step 8: Gate and commit**

Run: `uv run --no-sync lint-imports 2>&1 | tail -1; make test PYTEST_ARGS="-q" > /tmp/claude-501/c1.log 2>&1; tail -1 /tmp/claude-501/c1.log`
Expected: `Contracts: 8 kept, 0 broken.`; suite green.

```bash
git add interpreter/project/source_file.py interpreter/project/cobol_discovery.py interpreter/project/cobol_compile.py tests/unit/project/test_cobol_discovery.py tests/unit/project/test_cobol_compile.py
git commit  # "refactor(cobol): the CALL walk becomes discover_callee_programs"
```

---

### Task 2: `compile_cobol` takes a fixed program list; `compile_program` discovers first

**Files:**
- Modify: `interpreter/project/cobol_compile.py` (`compile_cobol`)
- Modify: `interpreter/project/coprocessor_compile.py` (`compile_program`, both docstrings)
- Modify: `tests/unit/project/test_coprocessor_compile.py` (ordering test)
- Modify: `tests/unit/project/test_cobol_compile.py`, `tests/unit/project/test_cobol_compile_defaults.py`, `tests/integration/cobol_helpers.py`

**Interfaces:**
- Consumes: Task 1's `SourceFile`, `discover_callee_programs`.
- Produces: `compile_cobol(source: bytes, *, parser, programs: Sequence[SourceFile] = (), copybook_dirs: Sequence[Path] = (), extension_strategies=(), dialect_parsers=(), observer=NullFrontendObserver(), ast_cache_dir: Path | None = None, tolerant: bool = False, lp: LP = LP.LP32) -> tuple[Frontend, LinkedProgram]`. No `source_search_dirs`, `extra_subprogram_sources`, `source_transform`.

- [ ] **Step 1: Strengthen the ordering test (failing)**

In `tests/unit/project/test_coprocessor_compile.py`, change `test_every_specs_prepass_runs_before_any_make_strategy` to compile a caller that statically calls a callee on the search path, and assert every rewrite (including the callee's) precedes every `make_strategy`:

```python
def test_every_specs_prepass_runs_before_any_make_strategy(tmp_path, caplog):
    (tmp_path / "DISKCALL.cbl").write_bytes(_callee("DISKCALL"))
    specs = [
        CoprocessorSpec(name, _logging_factory(name), _logging_transform(name))
        for name in ("a", "b")
    ]

    with caplog.at_level(logging.INFO, logger=__name__):
        compile_program(
            _CALLS_BOTH_KINDS, make_cobol_parser(), specs, source_search_dirs=(tmp_path,)
        )

    messages = [r.message for r in caplog.records if r.name == __name__]
    assert messages[-2:] == ["make_strategy_a", "make_strategy_b"]
    assert sorted(messages[:-2]) == sorted(["prepass_a", "prepass_b"] * 2)
```

`_CALLS_BOTH_KINDS` and `_callee` are defined further down the file today; move both above this test. Two programs are rewritten (BOTHCALL and DISKCALL; the data-name callee is not linked here).

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run --no-sync pytest -q -n0 tests/unit/project/test_coprocessor_compile.py -k before_any 2>&1 | tail -1`
Expected: FAIL — the discovered callee's two rewrites come after `make_strategy_a`/`_b`.

- [ ] **Step 2: Rewrite `compile_cobol`'s body**

Replace the parameters `source_search_dirs`, `extra_subprogram_sources`, `source_transform` with `programs: Sequence[SourceFile] = ()`, change `copybook_dirs` to `Sequence[Path] = ()`, return `tuple[Frontend, LinkedProgram]` (import `Frontend` from `interpreter.frontend`). Inside the `try`:

```python
        main_path = Path("__main__.cbl")
        all_sources: dict[Path, bytes] = {
            main_path: source,
            **{program.path: program.source for program in programs},
        }
        parallel_parse_to_cache(all_sources, mode_parser, cache_dir)

        def _ast_path(src_path: Path) -> Path:
            return cache_dir / f"{src_path.stem}-{_digest(src_path)}.ast.json"

        lowering = _Lowering(
            parser=mode_parser,
            copybook_dirs=copybook_dirs,
            extension_strategies=extension_strategies,
            dialect_parsers=dialect_parsers,
            observer=observer,
            tolerant=tolerant,
            addressing_mode=mode,
        )
        main_frontend, main_module = lowering.lower(source, main_path, _ast_path(main_path))
        modules: dict[Path, ModuleUnit] = {
            main_path: main_module,
            **dict(
                pair
                for program in programs
                if program.path != main_path
                for pair in lowering.lower_or_skip(program, _ast_path(program.path))
            ),
        }
```

followed by today's import-graph, `with_start_up`, `link_modules` and `entry_func_label` code unchanged. `_Lowering` is a frozen dataclass in `cobol_compile.py` holding the shared arguments, with `lower(source, path, ast_path) -> tuple[Frontend, ModuleUnit]` (calls `compile_cobol_module`) and `lower_or_skip(program, ast_path) -> tuple[tuple[Path, ModuleUnit], ...]` that returns `()` and logs `"compile_cobol: %s failed to lower — skipping"` with `exc_info=True` when `compile_cobol_module` raises. Update the module docstring's last paragraph: it compiles the programs it is given and searches no directory.

- [ ] **Step 3: `compile_program` discovers before making strategies**

In `interpreter/project/coprocessor_compile.py`:

```python
    text = rewrite(source.decode("utf-8"))
    linked = {
        name: SourceFile(Path(f"{name}.cbl"), rewrite(sub.decode("utf-8")).encode("utf-8"))
        for name, sub in functools.reduce(
            lambda srcs, spec: {**srcs, **spec.linked_subprogram_sources()},
            specs,
            dict(linked_subprogram_sources),
        ).items()
    }
    discovered = tuple(
        found
        for found in discover_callee_programs(
            text.encode("utf-8"), all_source_search_dirs, rewrite
        )
        if found.path.stem.upper() not in linked
    )

    strategies = [spec.make_strategy() for spec in specs]
    dialect_parsers = [spec.dialect_parser for spec in specs]
    return compile_cobol(
        text.encode("utf-8"),
        parser=parser,
        programs=(*discovered, *linked.values()),
        extension_strategies=strategies,
        dialect_parsers=dialect_parsers,
        tolerant=tolerant,
    )
```

`all_source_search_dirs` is computed before `discovered` (move its existing `functools.reduce`). Restore the docstrings' single guarantee: every spec's rewrite runs on every compiled program — main, discovered and linked — before ANY spec's `make_strategy`; a linked subprogram wins over a discovered one of the same name. 

- [ ] **Step 4: Update the direct callers**

- `tests/integration/cobol_helpers.py` `run_cobol_programs`: `programs=tuple(SourceFile(Path(f"{name}.cbl"), to_fixed(lines).encode()) for name, lines in subprograms.items())`.
- `tests/unit/project/test_cobol_compile.py`: each `extra_subprogram_sources={"CALLEE": x}` becomes `programs=(SourceFile(Path("CALLEE.cbl"), x),)`.
- `tests/unit/project/test_cobol_compile_defaults.py`: replace the two removed-parameter asserts with `assert sig.parameters["programs"].default == ()` and `assert "source_search_dirs" not in sig.parameters`; `copybook_dirs` default becomes `()`.

Run: `rg -n "source_search_dirs|extra_subprogram_sources|source_transform" --type py . | grep -v "^./interpreter/project/\(coprocessor_compile\|cobol_discovery\).py" | grep -v "^./tests/unit/project/test_c\(oprocessor_compile\|obol_discovery\|obol_compile_defaults\).py"`
Expected: no output.

- [ ] **Step 5: Run**

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run --no-sync pytest -q -n0 tests/unit/project tests/integration/test_cobol_run_unit.py 2>&1 | tail -1`
Expected: all green, including Step 1's test.

- [ ] **Step 6: Mutation-check**

Move `strategies = [...]` above `discovered = ...`: Step 1's test fails; revert. Then drop the `if found.path.stem.upper() not in linked` filter: a same-named linked and discovered program would both be compiled. Add this test to `test_coprocessor_compile.py`, confirm it fails with the filter dropped, restore the filter, confirm it is green:

```python
def test_a_linked_subprogram_wins_over_a_discovered_one_of_the_same_name(tmp_path):
    (tmp_path / "DISKCALL.cbl").write_bytes(_callee("DISKCALL"))
    _, linked = compile_program(
        _CALLS_BOTH_KINDS,
        make_cobol_parser(),
        [],
        source_search_dirs=(tmp_path,),
        linked_subprogram_sources={
            "DISKCALL": _callee("DISKCALL"),
            "DNCALLEE": _callee("DNCALLEE"),
        },
    )
    assert sorted(str(p) for p in linked.modules) == [
        "DISKCALL.cbl",
        "DNCALLEE.cbl",
        "__main__.cbl",
        "__start_up__",
    ]
```

- [ ] **Step 7: Gate and commit**

Run: `uv run --no-sync lint-imports 2>&1 | tail -1; make test PYTEST_ARGS="-q" > /tmp/claude-501/c2.log 2>&1; tail -1 /tmp/claude-501/c2.log`
Expected: contracts kept; suite green.

```bash
git add -A interpreter/project tests/unit/project tests/integration/cobol_helpers.py
git commit  # "refactor(cobol): compile_cobol compiles a fixed program list"
```

---

### Task 3: Move COBOL's `compile_directory` tests onto `compile_cobol`

**Files:**
- Modify: `tests/integration/cobol_helpers.py` (new helper)
- Modify: `tests/integration/test_cobol_programs.py` (17 sites), `tests/integration/test_cobol_copybook_inlining.py` (6), `tests/integration/test_cobol_call_by_data_name.py` (1), `tests/integration/test_cobol_procedure_using.py` (1), `tests/integration/project/test_all_languages_execution.py` (1)

**Interfaces:**
- Consumes: Task 2's `compile_cobol(..., programs=...)`.
- Produces: `compile_programs_in(directory: Path, main: str) -> LinkedProgram` in `tests/integration/cobol_helpers.py`.

- [ ] **Step 1: Add the helper**

```python
def compile_programs_in(directory: Path, main: str) -> LinkedProgram:
    """Compile ``<directory>/<main>.cbl`` with every other program under the
    directory, as an explicit list, and the directory tree as copybook path --
    what a build names, not what a CALL walk finds."""
    from cobol_asg.cobol_parser import make_cobol_parser
    from interpreter.project.cobol_compile import compile_cobol
    from interpreter.project.source_file import SourceFile

    main_path = directory / f"{main}.cbl"
    copybook_dirs = [directory, *sorted(p for p in directory.rglob("*") if p.is_dir())]
    _, linked = compile_cobol(
        main_path.read_bytes(),
        parser=make_cobol_parser(copybook_dirs=copybook_dirs),
        programs=tuple(
            SourceFile(p, p.read_bytes())
            for ext in (".cbl", ".cob")
            for p in sorted(directory.rglob(f"*{ext}"))
            if p != main_path
        ),
        copybook_dirs=copybook_dirs,
    )
    return linked
```

- [ ] **Step 2: Replace every site**

Each `compile_directory(tmp_path, Language.COBOL)` becomes `compile_programs_in(tmp_path, "<MAIN>")`, where `<MAIN>` is the upper-cased name in the same test's `endswith("func_<main>_0")` entry predicate (`func_main_0` → `"MAIN"`, `func_mainprog_0` → `"MAINPROG"`, `func_chaina_0` → `"CHAINA"`, `func_proga_0` → `"PROGA"`, `func_mainclr_0` → `"MAINCLR"`). `test_missing_copybook_raises_clean_error` has no predicate: its main is `"MAIN"`. Do it with a script that pairs each call with the next predicate, then read the diff. Drop the now-unused `compile_directory` imports.

Run: `rg -n "compile_directory" tests/integration/test_cobol_*.py tests/integration/project/test_all_languages_execution.py | rg -i cobol`
Expected: no COBOL call sites remain (the all-languages file keeps its other languages).

- [ ] **Step 3: Run the moved tests**

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run --no-sync pytest -q tests/integration/test_cobol_programs.py tests/integration/test_cobol_copybook_inlining.py tests/integration/test_cobol_call_by_data_name.py tests/integration/test_cobol_procedure_using.py tests/integration/project/test_all_languages_execution.py 2>&1 | tail -1`
Expected: the same green/xfail counts as before the change (record them first with `git stash`), no assertion edited.

- [ ] **Step 4: Commit**

```bash
git add tests/integration
git commit  # "test(cobol): compile programs as an explicit list, not a directory"
```

---

### Task 4: The COBOL CLI takes a main program and search directories

**Files:**
- Modify: `interpreter/__main__.py`
- Create: `tests/integration/test_cobol_cli.py`
- Modify: `README.md` ("Running COBOL")

- [ ] **Step 1: Write the failing CLI test**

```python
"""python -m interpreter: a COBOL main program, its callees and copybooks found
through --search-dir."""

import os
import subprocess
import sys
from pathlib import Path

from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401
from tests.integration.cobol_helpers import to_fixed

_MAIN = ["IDENTIFICATION DIVISION.", "PROGRAM-ID. CLIMAIN.", "PROCEDURE DIVISION.",
         "    CALL 'CLISUB'.", "    GOBACK."]
_SUB = ["IDENTIFICATION DIVISION.", "PROGRAM-ID. CLISUB.", "DATA DIVISION.",
        "WORKING-STORAGE SECTION.", "COPY CLIBOOK.", "PROCEDURE DIVISION.",
        "    DISPLAY WS-GREETING.", "    GOBACK."]


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "interpreter", *args],
        capture_output=True, text=True, env=os.environ.copy(), check=False,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cli_runs_a_main_program_with_callees_and_copybooks_from_search_dirs(
    tmp_path: Path, bridge_jar
):
    lib = tmp_path / "lib"
    lib.mkdir()
    (tmp_path / "CLIMAIN.cbl").write_text(to_fixed(_MAIN))
    (lib / "CLISUB.cbl").write_text(to_fixed(_SUB))
    (lib / "CLIBOOK.cpy").write_text(to_fixed(["01 WS-GREETING PIC X(5) VALUE 'HELLO'."]))

    ran = _cli(str(tmp_path / "CLIMAIN.cbl"), "--search-dir", str(lib))
    rejected = _cli(str(tmp_path))

    assert (ran.returncode, ran.stdout.strip()) == (0, "HELLO")
    assert rejected.returncode == 2
    assert rejected.stderr.strip().endswith(f"{tmp_path} is a directory; give the main program's source file")
```

(If `to_fixed`'s name differs in `cobol_helpers.py`, use the existing fixed-format helper there.)

Run it; Expected: FAIL (`--search-dir` unrecognised, exit 2 with argparse usage).

- [ ] **Step 2: Rewrite the CLI**

`interpreter/__main__.py`: drop `--entry`, `_entry_point`, the `compile_directory` and `run` imports; add `ap.add_argument("--search-dir", action="append", type=Path, default=[], metavar="DIR", help="Search for called programs and copybooks here (repeatable, in order)")`. Main flow:

```python
    target = Path(args.path).resolve()
    if target.is_dir():
        emit_err(f"error: {target} is a directory; give the main program's source file")
        return 2
    if not target.is_file():
        emit_err(f"error: {target} does not exist")
        return 1
    search_dirs = [d.resolve() for d in args.search_dir]
    _, linked = compile_program(
        target.read_bytes(),
        make_cobol_parser(copybook_dirs=search_dirs),
        [],
        source_search_dirs=search_dirs,
    )
    run_linked(
        linked,
        EntryPoint.function(lambda ref: ref.label == linked.entry_func_label),
        max_steps=args.max_steps,
        verbose=args.verbose,
        initial_vm=initial_vm_state(),
    )
    return 0
```

Update the module docstring's usage lines to `python -m interpreter MAIN.cbl [--search-dir DIR]...`.

- [ ] **Step 3: Run; README**

Run the test; Expected: green (if `DISPLAY` output differs in trailing whitespace or newline, compare after `.strip()` as written; any other difference is a finding — stop and debug).
README "Running COBOL": replace the directory example and its paragraph with `uv run python -m interpreter cobol/MAINPROG.cbl --search-dir cobol/ --max-steps 100000 --log-level INFO` and: "`python -m interpreter MAIN.cbl [--search-dir DIR]...` compiles the main program, every program it statically CALLs that is found in the search directories (searched in order), and runs it from the main program. The search directories are also the copybook path. Other flags: `--max-steps` (default 50000), `--log-level`, `--verbose`."

- [ ] **Step 4: Commit**

```bash
git add interpreter/__main__.py tests/integration/test_cobol_cli.py README.md
git commit  # "feat(cli): COBOL CLI takes a main program and --search-dir"
```

---

### Task 5: `compile_directory` stops accepting COBOL

**Files:**
- Modify: `interpreter/project/compiler.py`
- Modify: `tests/unit/cobol/test_cobol_parser_copybook.py` (delete `test_collect_project_copybook_dirs`)
- Create or modify: `tests/unit/project/test_compile_directory.py` (new test)

- [ ] **Step 1: Failing test**

In `tests/unit/project/test_compile_directory.py`:

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_directory_rejects_a_language_with_no_source_extensions(tmp_path):
    (tmp_path / "MAIN.cbl").write_text("       PROGRAM-ID. MAIN.\n")
    with pytest.raises(ValueError, match="no source extensions registered for cobol"):
        compile_directory(tmp_path, Language.COBOL)
```

Run; Expected: FAIL (today it compiles the directory, or fails inside ProLeap).

- [ ] **Step 2: Remove COBOL from `compiler.py`**

Delete `_collect_copybook_dirs`, the `Language.COBOL` entries in `_LANGUAGE_EXTENSIONS`, `_COPYBOOK_EXTENSIONS` and its use (`copybook_exts`), and `_module_frontend`; `compile_module` and `compile_directory` call `get_frontend(language)` directly and lose `copybook_dirs`. At the top of `compile_directory`, after the directory check:

```python
    if language not in _LANGUAGE_EXTENSIONS:
        raise ValueError(f"no source extensions registered for {language.value}")
```

Remove now-unused imports (`get_cobol_frontend`, `Sequence`, `Frontend` if unused).

Run: `rg -n -i "cobol|copybook" interpreter/project/compiler.py`
Expected: no output.

- [ ] **Step 3: Delete the copybook-dir test; run**

Delete `test_collect_project_copybook_dirs`. Run `make test PYTEST_ARGS="-q"`; Expected: green.

- [ ] **Step 4: Commit**

```bash
git add -A interpreter/project/compiler.py tests/unit
git commit  # "refactor(project): compile_directory no longer compiles COBOL"
```

---

### Task 6: Living docs and ADR-181

**Files:**
- Modify: `docs/linker-design.md`, `docs/frontend-design/cobol.md` (where they describe COBOL through `compile_directory`, directory mode, or `compile_cobol`'s search dirs), `docs/notes-on-vm-design.md` if it does
- Modify: `docs/architectural-design-decisions.md` (append ADR-181)

- [ ] **Step 1: Find the stale passages**

Run: `rg -n "compile_directory|source_search_dirs|extra_subprogram_sources|source_transform|--entry|directory of sources" docs README.md --glob '!docs/superpowers/**' --glob '!docs/design/**' --glob '!docs/architectural-design-decisions.md' --glob '!docs/claude-md-audit-*'`
Rewrite each COBOL-related hit to the new shape (fixed program list; discovery as a shell step; `compile_program` discovers; CLI takes a main file). Non-COBOL `compile_directory` mentions stay.

- [ ] **Step 2: Append ADR-181**

```markdown

---

### ADR-181: COBOL compiles a fixed program list; discovery is a shell step (2026-10-13)

**Context:** COBOL compiled two ways: `compile_cobol`, the path every forge runtime uses, and `compile_directory`, which compiled every `.cbl`/`.cob` under a tree without extensions, dialects, LP mode, data layout or entry label. `compile_cobol` also decided what to compile, by walking `CALL 'LITERAL'` edges through search directories. Production toolchains separate these: a build names the programs to compile, one per compile; the binder pulls statically called program objects from libraries by name, and the runtime loads dynamically called ones from load libraries — already compiled.

**Decision:** `compile_cobol` takes the main program and a fixed list of `SourceFile`s and searches nothing. The CALL walk is `discover_callee_programs`, a shell step. `compile_program` rewrites, discovers and links before making any strategy, so every coprocessor rewrite runs on every compiled program before any strategy exists. `compile_directory` no longer accepts COBOL. The COBOL CLI takes a main program and `--search-dir` directories.

**Consequences:** `project/compiler.py` names no COBOL. A callee reached only by `CALL identifier` must be in the list (`linked_subprogram_sources`), as before. Persisting lowered programs and linking them later is red-dragon-ajps.
```

- [ ] **Step 3: Commit and push**

```bash
git add docs
git commit  # "docs: COBOL compiles a fixed program list (ADR-181)"
git push origin main
```

---

### Task 7: Bump the forge

**Files (in `~/code/red-dragon-forge`):** `vendor/red-dragon`

- [ ] **Step 1:** `git -C vendor/red-dragon fetch -q origin && git -C vendor/red-dragon checkout -q origin/main`
- [ ] **Step 2:** Run: `rg -n "source_search_dirs=|extra_subprogram_sources|source_transform|compile_directory\(.*COBOL" --type py -g '!vendor/**' . | grep -v "compile_program\|CoprocessorSpec\|bootstrap\|region.py\|program_compiler.py\|coprocessor.py"` — Expected: no direct `compile_cobol` discovery callers (the forge goes through `compile_program`, whose signature is unchanged).
- [ ] **Step 3:** Ensure Db2 is healthy (`docker inspect -f '{{.State.Health.Status}}' squall-db2`; restart and wait if not). Run in the background: `. ./bridge-env.sh && make test-all > /tmp/claude-501/forge-c.log 2>&1; grep -E "[0-9]+ (passed|failed)" /tmp/claude-501/forge-c.log`. Expected: every suite green. A failure that matches an old absolute label prefix for a linked subprogram is Review Focus item 5: fix the forge test's expectation, with a ruling.
- [ ] **Step 4:** Commit `vendor/red-dragon` (and any forge test fix) — "chore(vendor): bump red-dragon; COBOL compiles a fixed program list" — and push.
