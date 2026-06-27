# COBOL Connection Emission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `extract_cobol_connections()` — an analysis-only API that compiles a COBOL project and returns all `COPY` and `CALL` inter-program connections as structured data, without executing the VM.

**Architecture:** A new file `interpreter/project/cobol_connections.py` holds the `ProgramRef` / `Connection` data model and the `extract_cobol_connections()` function. The function calls the existing `compile_cobol()` and post-processes the finished `LinkedProgram` — reading `ModuleUnit.imports` for connection names and `LinkedProgram.import_graph` for resolved CALL file paths. No existing files are modified.

**Tech Stack:** Python 3.11+, `dataclasses`, `json`, existing `interpreter.project.cobol_compile.compile_cobol`, `interpreter.project.types.ImportKind`.

## Global Constraints

- TDD: write failing test first, then implement, then verify green
- Run full test suite with `poetry run python -m pytest` before every commit
- Format with `poetry run python -m black .` before every commit
- Do not modify `cobol_compile.py`, `ModuleUnit`, `LinkedProgram`, or any existing file
- All new tests decorated with `@covers(NotLanguageFeature.INFRASTRUCTURE)` from `tests.covers`
- `Connection.kind` is a plain `str` (`"COPY"` or `"CALL"`), not a `Literal` — avoids runtime overhead with no real benefit here

---

## File Map

| File | Status | Responsibility |
|------|--------|---------------|
| `interpreter/project/cobol_connections.py` | **Create** | `ProgramRef`, `Connection`, `extract_cobol_connections()` |
| `tests/unit/project/test_cobol_connections.py` | **Create** | Unit tests for data model and `to_json()` |
| `tests/integration/project/test_cobol_connections.py` | **Create** | Integration tests for `extract_cobol_connections()` |

---

## Task 1: Data Model — `ProgramRef`, `Connection`, `Connection.to_json()`

**Files:**
- Create: `interpreter/project/cobol_connections.py`
- Test: `tests/unit/project/test_cobol_connections.py`

**Interfaces:**
- Produces: `ProgramRef(name: str, file_path: Path | None)`, `Connection(kind: str, source: ProgramRef, target: ProgramRef)`, `Connection.to_json() -> str`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/unit/project/test_cobol_connections.py`:

```python
"""Unit tests for Connection data model."""

import json
from pathlib import Path

from tests.covers import covers, NotLanguageFeature
from interpreter.project.cobol_connections import Connection, ProgramRef


class TestProgramRef:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_program_ref_stores_name_and_path(self):
        ref = ProgramRef(name="ACCTMGR", file_path=Path("/src/ACCTMGR.cbl"))
        assert ref.name == "ACCTMGR"
        assert ref.file_path == Path("/src/ACCTMGR.cbl")

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_program_ref_file_path_may_be_none(self):
        ref = ProgramRef(name="DFHEIBLK", file_path=None)
        assert ref.file_path is None

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_program_ref_is_hashable(self):
        ref = ProgramRef(name="PROG", file_path=None)
        assert hash(ref) is not None
        assert {ref}  # can be used in a set


class TestConnection:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_connection_stores_kind_source_target(self):
        src = ProgramRef(name="MAIN", file_path=Path("/src/MAIN.cbl"))
        tgt = ProgramRef(name="SUB", file_path=Path("/src/SUB.cbl"))
        conn = Connection(kind="CALL", source=src, target=tgt)
        assert conn.kind == "CALL"
        assert conn.source is src
        assert conn.target is tgt

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_to_json_includes_all_fields(self):
        src = ProgramRef(name="MAIN", file_path=Path("/src/MAIN.cbl"))
        tgt = ProgramRef(name="SUB", file_path=Path("/src/SUB.cbl"))
        conn = Connection(kind="CALL", source=src, target=tgt)
        data = json.loads(conn.to_json())
        assert data["kind"] == "CALL"
        assert data["source_name"] == "MAIN"
        assert data["source_file"] == "/src/MAIN.cbl"
        assert data["target_name"] == "SUB"
        assert data["target_file"] == "/src/SUB.cbl"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_copy_to_json_has_null_target_file(self):
        src = ProgramRef(name="MAIN", file_path=Path("/src/MAIN.cbl"))
        tgt = ProgramRef(name="DFHEIBLK", file_path=None)
        conn = Connection(kind="COPY", source=src, target=tgt)
        data = json.loads(conn.to_json())
        assert data["kind"] == "COPY"
        assert data["target_file"] is None

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_connection_is_hashable(self):
        src = ProgramRef(name="MAIN", file_path=None)
        tgt = ProgramRef(name="SUB", file_path=None)
        conn = Connection(kind="CALL", source=src, target=tgt)
        assert {conn}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
poetry run python -m pytest tests/unit/project/test_cobol_connections.py -v
```

Expected: `ModuleNotFoundError: No module named 'interpreter.project.cobol_connections'`

- [ ] **Step 3: Implement the data model**

Create `interpreter/project/cobol_connections.py`:

```python
# pyright: standard
"""COBOL inter-program connection extraction.

ProgramRef      — identifies a program or copybook by name and optional file path.
Connection      — a directed COPY or CALL relationship between two ProgramRefs.
extract_cobol_connections() — compile a COBOL project and return all connections.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.types import ImportKind


@dataclass(frozen=True)
class ProgramRef:
    """Identifies a COBOL program or copybook."""

    name: str
    file_path: Path | None


@dataclass(frozen=True)
class Connection:
    """A directed COPY or CALL relationship between two COBOL programs."""

    kind: str  # "COPY" or "CALL"
    source: ProgramRef
    target: ProgramRef

    def to_json(self) -> str:
        return json.dumps(
            {
                "kind": self.kind,
                "source_name": self.source.name,
                "source_file": str(self.source.file_path)
                if self.source.file_path
                else None,
                "target_name": self.target.name,
                "target_file": str(self.target.file_path)
                if self.target.file_path
                else None,
            }
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
poetry run python -m pytest tests/unit/project/test_cobol_connections.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 5: Run full suite to check no regressions**

```bash
poetry run python -m black . && poetry run python -m pytest
```

Expected: same count as before, all PASS

- [ ] **Step 6: Commit**

```bash
git add interpreter/project/cobol_connections.py tests/unit/project/test_cobol_connections.py
git commit -m "feat(connections): ProgramRef, Connection, to_json data model"
```

---

## Task 2: `extract_cobol_connections()` — CALL and COPY extraction

**Files:**
- Modify: `interpreter/project/cobol_connections.py` (add `extract_cobol_connections`)
- Test: `tests/integration/project/test_cobol_connections.py`

**Interfaces:**
- Consumes: `ProgramRef`, `Connection` from Task 1; `compile_cobol` from `interpreter.project.cobol_compile`; `ImportKind` from `interpreter.project.types`
- Produces:
  ```python
  def extract_cobol_connections(
      source: bytes,
      *,
      copybook_dirs: list[Path] | None = None,
      program_source_dir: Path | None = None,
      extra_subprogram_sources: dict[str, bytes] | None = None,
      parser: Any = None,
      extension_strategies: Sequence[Any] = (),
      cics_text_parser: Any = None,
      observer: FrontendObserver = NullFrontendObserver(),
      source_transform: Callable[[str], str] = lambda s: s,
  ) -> list[Connection]
  ```

- [ ] **Step 1: Write failing integration tests**

Create `tests/integration/project/test_cobol_connections.py`:

```python
"""Integration tests for extract_cobol_connections().

Tests use inline COBOL source (extra_subprogram_sources) for CALL connections
and tmp_path fixture files for COPY connections (ProLeap resolves COPY on disk).
"""

from pathlib import Path

from tests.covers import covers, NotLanguageFeature
from interpreter.project.cobol_connections import Connection, extract_cobol_connections

_MAIN_CALL = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAIN.
       PROCEDURE DIVISION.
           CALL 'HELPER'.
           GOBACK.
"""

_HELPER = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELPER.
       PROCEDURE DIVISION.
           GOBACK.
"""


class TestCallConnections:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_connection_detected(self):
        conns = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
        )
        call_conns = [c for c in conns if c.kind == "CALL"]
        assert len(call_conns) == 1
        assert call_conns[0].source.name == "MAIN"
        assert call_conns[0].target.name == "HELPER"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_call_target_file_path_resolved(self):
        conns = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
        )
        call_conns = [c for c in conns if c.kind == "CALL"]
        assert call_conns[0].target.file_path is not None
        assert call_conns[0].target.file_path.stem.upper() == "HELPER"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_no_connections_for_standalone_program(self):
        src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. STANDALONE.
       PROCEDURE DIVISION.
           GOBACK.
"""
        conns = extract_cobol_connections(src)
        assert conns == []

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_returns_list_of_connection_objects(self):
        conns = extract_cobol_connections(
            _MAIN_CALL,
            extra_subprogram_sources={"HELPER": _HELPER},
        )
        assert isinstance(conns, list)
        assert all(isinstance(c, Connection) for c in conns)

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_transitive_calls_included(self):
        """A calls B, B calls C — all three connections returned."""
        prog_a = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROGA.
       PROCEDURE DIVISION.
           CALL 'PROGB'.
           GOBACK.
"""
        prog_b = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROGB.
       PROCEDURE DIVISION.
           CALL 'PROGC'.
           GOBACK.
"""
        prog_c = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROGC.
       PROCEDURE DIVISION.
           GOBACK.
"""
        conns = extract_cobol_connections(
            prog_a,
            extra_subprogram_sources={"PROGB": prog_b, "PROGC": prog_c},
        )
        call_conns = [c for c in conns if c.kind == "CALL"]
        names = {(c.source.name.upper(), c.target.name.upper()) for c in call_conns}
        assert ("PROGA", "PROGB") in names
        assert ("PROGB", "PROGC") in names


class TestCopyConnections:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_copy_connection_detected(self, tmp_path: Path):
        cpy_file = tmp_path / "MYREC.cpy"
        cpy_file.write_text("       01 MY-FIELD PIC X(10).\n")

        src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
           COPY MYREC.
       PROCEDURE DIVISION.
           GOBACK.
"""
        conns = extract_cobol_connections(src, copybook_dirs=[tmp_path])
        copy_conns = [c for c in conns if c.kind == "COPY"]
        assert len(copy_conns) == 1
        assert copy_conns[0].source.name == "MAINPROG"
        assert copy_conns[0].target.name == "MYREC"

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_copy_target_file_path_is_none(self, tmp_path: Path):
        cpy_file = tmp_path / "MYREC.cpy"
        cpy_file.write_text("       01 MY-FIELD PIC X(10).\n")

        src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
           COPY MYREC.
       PROCEDURE DIVISION.
           GOBACK.
"""
        conns = extract_cobol_connections(src, copybook_dirs=[tmp_path])
        copy_conns = [c for c in conns if c.kind == "COPY"]
        assert copy_conns[0].target.file_path is None

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_to_json_roundtrips_for_copy(self, tmp_path: Path):
        import json
        cpy_file = tmp_path / "MYREC.cpy"
        cpy_file.write_text("       01 MY-FIELD PIC X(10).\n")

        src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINPROG.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
           COPY MYREC.
       PROCEDURE DIVISION.
           GOBACK.
"""
        conns = extract_cobol_connections(src, copybook_dirs=[tmp_path])
        copy_conns = [c for c in conns if c.kind == "COPY"]
        data = json.loads(copy_conns[0].to_json())
        assert data["kind"] == "COPY"
        assert data["target_file"] is None
        assert data["target_name"] == "MYREC"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
poetry run python -m pytest tests/integration/project/test_cobol_connections.py -v
```

Expected: `ImportError` — `extract_cobol_connections` not defined yet

- [ ] **Step 3: Implement `extract_cobol_connections()`**

Add to `interpreter/project/cobol_connections.py` (after the dataclasses):

```python
def extract_cobol_connections(
    source: bytes,
    *,
    copybook_dirs: list[Path] | None = None,
    program_source_dir: Path | None = None,
    extra_subprogram_sources: dict[str, bytes] | None = None,
    parser: Any = None,
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    source_transform: Callable[[str], str] = lambda s: s,
) -> list[Connection]:
    """Compile a COBOL project and return all COPY and CALL connections.

    Calls compile_cobol() with the same arguments, then post-processes
    the finished LinkedProgram — no VM execution takes place.

    CALL target file paths are resolved from LinkedProgram.import_graph.
    COPY target file paths are always None (copybooks are inlined by ProLeap
    before red-dragon sees the ASG; the name is extracted from raw source).
    """
    _, linked = compile_cobol(
        source,
        parser=parser,
        copybook_dirs=copybook_dirs,
        extension_strategies=extension_strategies,
        cics_text_parser=cics_text_parser,
        observer=observer,
        program_source_dir=program_source_dir,
        extra_subprogram_sources=extra_subprogram_sources,
        source_transform=source_transform,
    )

    # Build {caller_path -> {called_name_upper -> resolved_path}} from import_graph.
    call_resolution: dict[Path, dict[str, Path]] = {}
    for caller_path, callee_paths in linked.import_graph.items():
        call_resolution[caller_path] = {p.stem.upper(): p for p in callee_paths}

    connections: list[Connection] = []
    for module_path, module in linked.modules.items():
        source_ref = ProgramRef(name=module_path.stem, file_path=module_path)
        call_map = call_resolution.get(module_path, {})
        for ref in module.imports:
            if ref.kind == ImportKind.INCLUDE:
                connections.append(
                    Connection(
                        kind="COPY",
                        source=source_ref,
                        target=ProgramRef(name=ref.module_path, file_path=None),
                    )
                )
            elif ref.kind == ImportKind.REQUIRE:
                target_path = call_map.get(ref.module_path.upper())
                connections.append(
                    Connection(
                        kind="CALL",
                        source=source_ref,
                        target=ProgramRef(
                            name=ref.module_path, file_path=target_path
                        ),
                    )
                )

    return connections
```

- [ ] **Step 4: Run integration tests to confirm they pass**

```bash
poetry run python -m pytest tests/integration/project/test_cobol_connections.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 5: Run full suite to check no regressions**

```bash
poetry run python -m black . && poetry run python -m pytest
```

Expected: same count as before + 8 new tests, all PASS

- [ ] **Step 6: Commit**

```bash
git add interpreter/project/cobol_connections.py tests/integration/project/test_cobol_connections.py
git commit -m "feat(connections): extract_cobol_connections — COPY and CALL post-hoc extraction"
```

---

## Self-Review

**Spec coverage:**
- [x] Full project scope via `extra_subprogram_sources` / `program_source_dir` — covered (transitive test in Task 2)
- [x] COPY connections — covered (`TestCopyConnections`)
- [x] CALL connections — covered (`TestCallConnections`)
- [x] `ProgramRef` with `name` + `file_path` — covered (Task 1)
- [x] `Connection.to_json()` flat JSON — covered (unit + integration)
- [x] Analysis-only (no execution) — guaranteed: `extract_cobol_connections` never calls `run_linked`
- [x] COPY `target.file_path` is `None` — covered (`test_copy_target_file_path_is_none`)
- [x] CALL `target.file_path` resolved from `import_graph` — covered (`test_call_target_file_path_resolved`)
- [x] No existing files modified — plan touches only new files

**Placeholder scan:** None found.

**Type consistency:** `ProgramRef`, `Connection`, `extract_cobol_connections` names are consistent across Tasks 1 and 2. `Connection.kind` is `str` throughout.
