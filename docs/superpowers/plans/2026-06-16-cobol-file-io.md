# COBOL File I/O Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement real on-disk COBOL file I/O for SEQUENTIAL, INDEXED, and RELATIVE file organizations, with AT END / INVALID KEY conditional clauses, FILE STATUS write-back, and OPEN multi-mode fix.

**Architecture:** A new `RealFileIOProvider` dispatches to three `FileOrganizationDriver` implementations (SequentialDriver, IndexedDriver, RelativeDriver) based on `FileControlEntry.organization`. Statement dataclasses gain conditional clause fields; bridge serializes them; lowering emits `IOResult`-extracting builtins and conditional branches. The file section gains a runtime `ALLOC_REGION` so FD record fields are readable after READ.

**Tech Stack:** Python dataclasses, `pathlib.Path`, Java/ProLeap bridge for serialization, `struct` / `io.BytesIO` for binary record layout, pytest for TDD.

---

## File Map

**Create:**
- `interpreter/cobol/file_enums.py` — OpenMode, FileOrganization, AccessMode enums
- `interpreter/cobol/file_drivers.py` — FileOrganizationDriver Protocol + 3 implementations
- `interpreter/cobol/real_file_provider.py` — RealFileIOProvider
- `tests/unit/cobol/test_file_enums.py`
- `tests/unit/cobol/test_file_drivers.py`
- `tests/unit/cobol/test_real_file_provider.py`
- `tests/nist/conftest.py`
- `tests/nist/test_sq.py`
- `tests/nist/test_ix.py`
- `tests/nist/test_rl.py`
- `tests/nist/__init__.py`

**Modify:**
- `interpreter/cobol/io_provider.py` — add `IOResult` dataclass; update all method signatures and return types; add `__cobol_io_status` / `__cobol_io_data` dispatch entries
- `interpreter/vm/builtins.py` — register `__cobol_io_status` and `__cobol_io_data` builtins
- `interpreter/cobol/cobol_statements.py` — `FileControlEntry`; `OpenStatement` mode_groups; `ReadStatement` conditional fields + key; `WriteStatement`, `RewriteStatement`, `StartStatement`, `DeleteStatement` conditional fields
- `interpreter/cobol/asg_types.py` — `CobolASG.file_control`
- `interpreter/cobol/sectioned_layout.py` — `MaterialisedSectionedLayout.file` field; extend `resolve()`, `has_field()`, `subscript_stride()`, `group_leaf_names()`
- `interpreter/cobol/lower_data_division.py` — emit ALLOC_REGION for file section in `lower_sectioned_data_division`
- `interpreter/cobol/lower_io.py` — full rewrite of all I/O lowering functions
- `interpreter/cobol/emit_context.py` — add `emit_file_status_update` helper
- `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` — AT END/INVALID KEY/KEY IS/OPEN multi-mode
- `proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java` — FILE-CONTROL serialization

---

## Task 1: Enums

**Files:**
- Create: `interpreter/cobol/file_enums.py`
- Create: `tests/unit/cobol/test_file_enums.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/cobol/test_file_enums.py
from interpreter.cobol.file_enums import OpenMode, FileOrganization, AccessMode


def test_open_mode_from_string():
    assert OpenMode("INPUT") == OpenMode.INPUT
    assert OpenMode("OUTPUT") == OpenMode.OUTPUT
    assert OpenMode("I-O") == OpenMode.IO
    assert OpenMode("EXTEND") == OpenMode.EXTEND


def test_file_organization_from_string():
    assert FileOrganization("SEQUENTIAL") == FileOrganization.SEQUENTIAL
    assert FileOrganization("INDEXED") == FileOrganization.INDEXED
    assert FileOrganization("RELATIVE") == FileOrganization.RELATIVE


def test_access_mode_from_string():
    assert AccessMode("SEQUENTIAL") == AccessMode.SEQUENTIAL
    assert AccessMode("RANDOM") == AccessMode.RANDOM
    assert AccessMode("DYNAMIC") == AccessMode.DYNAMIC


def test_invalid_open_mode_raises():
    import pytest
    with pytest.raises(ValueError):
        OpenMode("BOGUS")
```

- [ ] **Step 2: Run test, confirm FAIL**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_file_enums.py -v 2>&1 | tail -20
```

Expected: `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Implement `interpreter/cobol/file_enums.py`**

```python
# pyright: standard
"""COBOL file I/O enumerations.

All use the str mixin so they can be constructed directly from bridge JSON
strings: ``OpenMode("INPUT")`` and compared with plain string equality.
"""

from __future__ import annotations

from enum import Enum


class OpenMode(str, Enum):
    INPUT  = "INPUT"
    OUTPUT = "OUTPUT"
    IO     = "I-O"
    EXTEND = "EXTEND"


class FileOrganization(str, Enum):
    SEQUENTIAL = "SEQUENTIAL"
    INDEXED    = "INDEXED"
    RELATIVE   = "RELATIVE"


class AccessMode(str, Enum):
    SEQUENTIAL = "SEQUENTIAL"
    RANDOM     = "RANDOM"
    DYNAMIC    = "DYNAMIC"
```

- [ ] **Step 4: Run test, confirm PASS**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_file_enums.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
cd /Users/asgupta/code/red-dragon && git add interpreter/cobol/file_enums.py tests/unit/cobol/test_file_enums.py && git commit -m "feat(cobol): add OpenMode, FileOrganization, AccessMode enums"
```

---

## Task 2: IOResult dataclass + builtins

**Files:**
- Modify: `interpreter/cobol/io_provider.py` (add `IOResult`; update abstract method signatures; update `NullIOProvider` and `StubIOProvider`; add `__cobol_io_status` / `__cobol_io_data` to dispatch table)
- Modify: `interpreter/vm/builtins.py` (register `__cobol_io_status` / `__cobol_io_data`)
- Modify: `tests/unit/test_cobol_io_integration.py` (add round-trip test for IOResult builtins)

The key contract change: all methods return `IOResult` (status + data), not raw strings. `NullIOProvider` non-read ops return `IOResult("00", None)`. `StubIOProvider._read_record` returns `IOResult("10", None)` when no records remain, and `IOResult("00", data)` when a record is available. `_write_record` / `_rewrite_record` return `IOResult("00", None)`.

- [ ] **Step 1: Write failing test — IOResult construction and builtins**

Add to `tests/unit/test_cobol_io_integration.py` (find the class, add methods):

```python
def test_io_result_status_00():
    from interpreter.cobol.io_provider import IOResult
    r = IOResult(status="00", data="HELLO     ")
    assert r.status == "00"
    assert r.data == "HELLO     "

def test_io_result_at_end():
    from interpreter.cobol.io_provider import IOResult
    r = IOResult(status="10", data=None)
    assert r.status == "10"
    assert r.data is None
```

- [ ] **Step 2: Run test, confirm FAIL**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/test_cobol_io_integration.py::TestCobolIo::test_io_result_status_00 -v 2>&1 | tail -10
```

- [ ] **Step 3: Add `IOResult` to `io_provider.py` and update all method signatures**

At the top of `interpreter/cobol/io_provider.py`, after the existing imports, add:

```python
@dataclass(frozen=True)
class IOResult:
    """Structured return value for all CobolIOProvider methods.

    status: COBOL file status code (e.g. "00", "10", "22", "23", "35").
    data:   Populated on successful READ; None for all write-side verbs.
    """
    status: str
    data: str | None
```

Update `_COBOL_IO_DISPATCH` to add two new entries:

```python
_COBOL_IO_DISPATCH: dict[FuncName, str] = {
    FuncName("__cobol_accept"): "_accept",
    FuncName("__cobol_open_file"): "_open_file",
    FuncName("__cobol_close_file"): "_close_file",
    FuncName("__cobol_read_record"): "_read_record",
    FuncName("__cobol_write_record"): "_write_record",
    FuncName("__cobol_rewrite_record"): "_rewrite_record",
    FuncName("__cobol_start_file"): "_start_file",
    FuncName("__cobol_delete_record"): "_delete_record",
    FuncName("__cobol_io_status"): "_io_status",
    FuncName("__cobol_io_data"): "_io_data",
}
```

Add static helper methods to `CobolIOProvider`:

```python
def _io_status(self, raw: Any) -> Any:
    if isinstance(raw, IOResult):
        return raw.status
    return _UNCOMPUTABLE

def _io_data(self, raw: Any) -> Any:
    if isinstance(raw, IOResult):
        return raw.data or ""
    return _UNCOMPUTABLE
```

Update abstract method signatures (change return types to `IOResult`):

```python
@abstractmethod
def _open_file(self, filename: str, mode: str, record_length: int,
               organization: str, key_offset: int, key_length: int) -> IOResult: ...

@abstractmethod
def _close_file(self, filename: str) -> IOResult: ...

@abstractmethod
def _read_record(self, filename: str, key: str) -> IOResult: ...

@abstractmethod
def _write_record(self, filename: str, data: str) -> IOResult: ...

@abstractmethod
def _rewrite_record(self, filename: str, data: str) -> IOResult: ...

@abstractmethod
def _start_file(self, filename: str, key: str, relop: str) -> IOResult: ...

@abstractmethod
def _delete_record(self, filename: str) -> IOResult: ...
```

Update `NullIOProvider` — read returns `UNCOMPUTABLE`, all others return `IOResult("00", None)`:

```python
class NullIOProvider(CobolIOProvider):
    def _accept(self, from_device: str) -> Any:
        return _UNCOMPUTABLE

    def _open_file(self, filename: str, mode: str, record_length: int,
                   organization: str, key_offset: int, key_length: int) -> IOResult:
        return IOResult("00", None)

    def _close_file(self, filename: str) -> IOResult:
        return IOResult("00", None)

    def _read_record(self, filename: str, key: str) -> Any:
        return _UNCOMPUTABLE

    def _write_record(self, filename: str, data: str) -> IOResult:
        return IOResult("00", None)

    def _rewrite_record(self, filename: str, data: str) -> IOResult:
        return IOResult("00", None)

    def _start_file(self, filename: str, key: str, relop: str) -> IOResult:
        return IOResult("00", None)

    def _delete_record(self, filename: str) -> IOResult:
        return IOResult("00", None)
```

Update `StubIOProvider` to match new signatures:

- `_open_file` gains 4 extra params (ignored): returns `IOResult("00", None)`
- `_close_file` returns `IOResult("00", None)`
- `_read_record` gains `key` param (ignored): returns `IOResult("00", record)` on hit, `IOResult("10", None)` when empty
- `_write_record` returns `IOResult("00", None)`
- `_rewrite_record` returns `IOResult("00", None)`
- `_start_file` gains `relop` param (ignored): returns `IOResult("00", None)`
- `_delete_record` returns `IOResult("00", None)`

Full replacement of StubIOProvider methods:

```python
def _open_file(self, filename: str, mode: str, record_length: int,
               organization: str, key_offset: int, key_length: int) -> IOResult:
    stub = self.get_file(filename)
    stub.is_open = True
    logger.info("StubIOProvider OPEN %s mode=%s", filename, mode)
    return IOResult("00", None)

def _close_file(self, filename: str) -> IOResult:
    if filename in self._files:
        self._files[filename].is_open = False
    logger.info("StubIOProvider CLOSE %s", filename)
    return IOResult("00", None)

def _read_record(self, filename: str, key: str) -> IOResult:
    stub = self._files.get(filename)
    if stub and stub.records:
        record = stub.records.pop(0)
        logger.info("StubIOProvider READ %s → %r", filename, record)
        return IOResult("00", record)
    logger.info("StubIOProvider READ %s → AT END", filename)
    return IOResult("10", None)

def _write_record(self, filename: str, data: str) -> IOResult:
    stub = self.get_file(filename)
    stub.written.append(data)
    logger.info("StubIOProvider WRITE %s ← %r", filename, data)
    return IOResult("00", None)

def _rewrite_record(self, filename: str, data: str) -> IOResult:
    stub = self.get_file(filename)
    if stub.written:
        stub.written[-1] = data
    else:
        stub.written.append(data)
    logger.info("StubIOProvider REWRITE %s ← %r", filename, data)
    return IOResult("00", None)

def _start_file(self, filename: str, key: str, relop: str) -> IOResult:
    logger.info("StubIOProvider START %s key=%s relop=%s (no-op)", filename, key, relop)
    return IOResult("00", None)

def _delete_record(self, filename: str) -> IOResult:
    stub = self._files.get(filename)
    if stub and stub.records:
        removed = stub.records.pop(0)
        logger.info("StubIOProvider DELETE %s → removed %r", filename, removed)
    else:
        logger.info("StubIOProvider DELETE %s → no records", filename)
    return IOResult("00", None)
```

- [ ] **Step 4: Register builtins in `interpreter/vm/builtins.py`**

Find where other `__cobol_*` builtins or BYTE_BUILTINS are registered. Add:

```python
FuncName("__cobol_io_status"): lambda args, _vm: (
    args[0].value.status if hasattr(args[0].value, "status") else _UNCOMPUTABLE
),
FuncName("__cobol_io_data"): lambda args, _vm: (
    (args[0].value.data or "") if hasattr(args[0].value, "data") and args[0].value.data is not None
    else ("" if hasattr(args[0].value, "data") else _UNCOMPUTABLE)
),
```

Actually, since `_io_status` and `_io_data` are now handled via `CobolIOProvider.handle_call` dispatch table (they live on the provider), these don't need separate VM builtins — the provider dispatch already handles them. Skip this step; the dispatch table in `io_provider.py` is sufficient.

- [ ] **Step 5: Run tests, confirm PASS**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/test_cobol_io_integration.py -v 2>&1 | tail -20
```

- [ ] **Step 6: Run full suite, confirm no regressions**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/ -x -q 2>&1 | tail -20
```

- [ ] **Step 7: Commit**

```bash
cd /Users/asgupta/code/red-dragon && git add interpreter/cobol/io_provider.py tests/unit/test_cobol_io_integration.py && git commit -m "feat(cobol): IOResult dataclass; update all provider method signatures"
```

---

## Task 3: Statement dataclass changes (Python layer)

**Files:**
- Modify: `interpreter/cobol/cobol_statements.py` — add `FileControlEntry`; update `OpenStatement`, `ReadStatement`, `WriteStatement`, `RewriteStatement`, `StartStatement`, `DeleteStatement`
- Modify: `interpreter/cobol/asg_types.py` — add `CobolASG.file_control`
- Create: `tests/unit/cobol/test_io_statements.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/cobol/test_io_statements.py
import pytest
from interpreter.cobol.cobol_statements import (
    FileControlEntry,
    OpenStatement,
    ReadStatement,
    WriteStatement,
    RewriteStatement,
    StartStatement,
    DeleteStatement,
)
from interpreter.cobol.file_enums import OpenMode, FileOrganization, AccessMode


def test_file_control_entry_defaults():
    e = FileControlEntry(file_name="CUST-FILE")
    assert e.file_name == "CUST-FILE"
    assert e.assign_to == ""
    assert e.organization == FileOrganization.SEQUENTIAL
    assert e.access_mode == AccessMode.SEQUENTIAL
    assert e.record_key == ""
    assert e.relative_key == ""
    assert e.file_status_var == ""


def test_file_control_entry_from_dict():
    d = {
        "file_name": "CUST-FILE",
        "assign_to": "custfile.dat",
        "organization": "INDEXED",
        "access_mode": "DYNAMIC",
        "record_key": "CUST-ID",
        "relative_key": "",
        "file_status_var": "WS-STATUS",
    }
    e = FileControlEntry.from_dict(d)
    assert e.organization == FileOrganization.INDEXED
    assert e.access_mode == AccessMode.DYNAMIC
    assert e.record_key == "CUST-ID"
    assert e.file_status_var == "WS-STATUS"


def test_open_statement_mode_groups_from_dict():
    d = {
        "type": "OPEN",
        "mode_groups": [
            {"mode": "INPUT", "files": ["CUST-FILE"]},
            {"mode": "OUTPUT", "files": ["REPORT-FILE"]},
        ],
    }
    stmt = OpenStatement.from_dict(d)
    assert len(stmt.mode_groups) == 2
    assert stmt.mode_groups[0] == (OpenMode.INPUT, ["CUST-FILE"])
    assert stmt.mode_groups[1] == (OpenMode.OUTPUT, ["REPORT-FILE"])


def test_open_statement_to_dict_roundtrip():
    d = {"type": "OPEN", "mode_groups": [{"mode": "INPUT", "files": ["F1"]}]}
    assert OpenStatement.from_dict(d).to_dict() == d


def test_read_statement_conditional_fields():
    from interpreter.cobol.cobol_statements import MoveStatement
    d = {
        "type": "READ",
        "file_name": "CUST-FILE",
        "key": "CUST-ID",
        "at_end": [{"type": "MOVE", "source": "1", "targets": ["WS-EOF"]}],
        "not_at_end": [],
        "invalid_key": [],
        "not_invalid_key": [],
    }
    stmt = ReadStatement.from_dict(d)
    assert stmt.key == "CUST-ID"
    assert len(stmt.at_end) == 1
    assert stmt.not_at_end == []


def test_write_statement_invalid_key():
    d = {
        "type": "WRITE",
        "record_name": "CUST-REC",
        "invalid_key": [{"type": "MOVE", "source": "1", "targets": ["WS-ERR"]}],
        "not_invalid_key": [],
    }
    stmt = WriteStatement.from_dict(d)
    assert len(stmt.invalid_key) == 1
    assert stmt.not_invalid_key == []


def test_delete_statement_invalid_key():
    d = {
        "type": "DELETE",
        "file_name": "CUST-FILE",
        "invalid_key": [],
        "not_invalid_key": [{"type": "MOVE", "source": "0", "targets": ["WS-OK"]}],
    }
    stmt = DeleteStatement.from_dict(d)
    assert stmt.not_invalid_key != []
```

- [ ] **Step 2: Run tests, confirm FAIL**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_io_statements.py -v 2>&1 | tail -20
```

- [ ] **Step 3: Add `FileControlEntry` to `cobol_statements.py`**

Near the top of `interpreter/cobol/cobol_statements.py`, after the existing imports, add the import for the new enums:

```python
from interpreter.cobol.file_enums import OpenMode, FileOrganization, AccessMode
```

Then add `FileControlEntry` as a new frozen dataclass (before `OpenStatement`):

```python
@dataclass(frozen=True)
class FileControlEntry:
    """FILE-CONTROL entry from the ENVIRONMENT DIVISION."""

    file_name: str
    assign_to: str = ""
    organization: FileOrganization = FileOrganization.SEQUENTIAL
    access_mode: AccessMode = AccessMode.SEQUENTIAL
    record_key: str = ""
    relative_key: str = ""
    file_status_var: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> FileControlEntry:
        return cls(
            file_name=data["file_name"],
            assign_to=data.get("assign_to", ""),
            organization=FileOrganization(data.get("organization", "SEQUENTIAL")),
            access_mode=AccessMode(data.get("access_mode", "SEQUENTIAL")),
            record_key=data.get("record_key", ""),
            relative_key=data.get("relative_key", ""),
            file_status_var=data.get("file_status_var", ""),
        )

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "assign_to": self.assign_to,
            "organization": self.organization.value,
            "access_mode": self.access_mode.value,
            "record_key": self.record_key,
            "relative_key": self.relative_key,
            "file_status_var": self.file_status_var,
        }
```

Also add `"FileControlEntry"` to `__all__` in `cobol_statements.py`.

- [ ] **Step 4: Replace `OpenStatement` with mode_groups version**

Replace the existing `OpenStatement` class (lines 890–905 in current file):

```python
@dataclass(frozen=True)
class OpenStatement:
    """OPEN [mode file1 file2 ...] ... — one or more mode groups."""

    mode_groups: list[tuple[OpenMode, list[str]]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> OpenStatement:
        groups = [
            (OpenMode(g["mode"]), list(g["files"]))
            for g in data.get("mode_groups", [])
        ]
        return cls(mode_groups=groups)

    def to_dict(self) -> dict:
        return {
            "type": "OPEN",
            "mode_groups": [
                {"mode": mode.value, "files": list(files)}
                for mode, files in self.mode_groups
            ],
        }
```

- [ ] **Step 5: Replace `ReadStatement` with conditional-clause version**

Replace existing `ReadStatement` (lines 922–940):

```python
@dataclass(frozen=True)
class ReadStatement:
    """READ file-name [INTO target] [KEY key] [AT END ...] [INVALID KEY ...]."""

    file_name: str = ""
    into: str = ""
    key: str = ""
    at_end: list[CobolStatementType] = field(default_factory=list)
    not_at_end: list[CobolStatementType] = field(default_factory=list)
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> ReadStatement:
        return cls(
            file_name=data.get("file_name", ""),
            into=data.get("into", ""),
            key=data.get("key", ""),
            at_end=[parse_statement(c) for c in data.get("at_end", [])],
            not_at_end=[parse_statement(c) for c in data.get("not_at_end", [])],
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[parse_statement(c) for c in data.get("not_invalid_key", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "READ", "file_name": self.file_name}
        if self.into:
            result["into"] = self.into
        if self.key:
            result["key"] = self.key
        if self.at_end:
            result["at_end"] = [c.to_dict() for c in self.at_end]
        if self.not_at_end:
            result["not_at_end"] = [c.to_dict() for c in self.not_at_end]
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        return result
```

- [ ] **Step 6: Add `invalid_key` / `not_invalid_key` to `WriteStatement`, `RewriteStatement`, `StartStatement`, `DeleteStatement`**

For each, add the two fields (same `list[CobolStatementType]` pattern) and update `from_dict` / `to_dict`.

`WriteStatement`:
```python
@dataclass(frozen=True)
class WriteStatement:
    record_name: str = ""
    from_field: str = ""
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> WriteStatement:
        return cls(
            record_name=data.get("record_name", ""),
            from_field=data.get("from_field", ""),
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[parse_statement(c) for c in data.get("not_invalid_key", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "WRITE", "record_name": self.record_name}
        if self.from_field:
            result["from_field"] = self.from_field
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        return result
```

`RewriteStatement` — same shape as WriteStatement.

`StartStatement`:
```python
@dataclass(frozen=True)
class StartStatement:
    file_name: str = ""
    key: str = ""
    relop: str = ""
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> StartStatement:
        return cls(
            file_name=data.get("file_name", ""),
            key=data.get("key", ""),
            relop=data.get("relop", "="),
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[parse_statement(c) for c in data.get("not_invalid_key", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "START", "file_name": self.file_name}
        if self.key:
            result["key"] = self.key
        if self.relop:
            result["relop"] = self.relop
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        return result
```

`DeleteStatement`:
```python
@dataclass(frozen=True)
class DeleteStatement:
    file_name: str = ""
    invalid_key: list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> DeleteStatement:
        return cls(
            file_name=data.get("file_name", ""),
            invalid_key=[parse_statement(c) for c in data.get("invalid_key", [])],
            not_invalid_key=[parse_statement(c) for c in data.get("not_invalid_key", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"type": "DELETE", "file_name": self.file_name}
        if self.invalid_key:
            result["invalid_key"] = [c.to_dict() for c in self.invalid_key]
        if self.not_invalid_key:
            result["not_invalid_key"] = [c.to_dict() for c in self.not_invalid_key]
        return result
```

- [ ] **Step 7: Add `file_control` to `CobolASG` in `asg_types.py`**

Add import at the top: `from interpreter.cobol.cobol_statements import FileControlEntry` (note: may need to check circular imports; if so, use `TYPE_CHECKING`).

Add field to `CobolASG`:
```python
file_control: list[FileControlEntry] = field(default_factory=list)
```

In `from_dict`:
```python
file_control=[
    FileControlEntry.from_dict(e) for e in data.get("file_control", [])
],
```

In `to_dict`:
```python
if self.file_control:
    result["file_control"] = [e.to_dict() for e in self.file_control]
```

- [ ] **Step 8: Run tests, confirm PASS**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_io_statements.py -v 2>&1 | tail -20
```

- [ ] **Step 9: Run full unit suite, check for regressions**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/ -x -q 2>&1 | tail -20
```

- [ ] **Step 10: Format and commit**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m black . && git add interpreter/cobol/cobol_statements.py interpreter/cobol/asg_types.py tests/unit/cobol/test_io_statements.py && git commit -m "feat(cobol): FileControlEntry, OpenStatement mode_groups, I/O conditional clause fields"
```

---

## Task 4: Bridge changes — AT END / INVALID KEY / KEY IS / OPEN multi-mode / FILE-CONTROL

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java`
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java`
- Rebuild JAR

This task has no Python unit test because bridge correctness is exercised via integration. Write a minimal hand-crafted JSON fixture test instead to confirm the bridge emits the new fields.

- [ ] **Step 1: Locate the serialization methods in `StatementSerializer.java`**

Open `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java`. Locate:
- `serializeOpen` (around line 1305)
- `serializeRead` (around line 1381)
- `serializeWrite` (around line 1396)
- `serializeRewrite` (around line 1412)
- `serializeStart` (around line 1428)
- `serializeDelete` (around line 1444)

Also locate helper `serializeStatements(List<Statement>)` — used for `SEARCH`'s `at_end`; reuse the same helper for I/O conditional clauses.

- [ ] **Step 2: Fix `serializeOpen` to emit `mode_groups`**

Replace the body that iterates files under a single mode. New implementation:

```java
private JsonNode serializeOpen(OpenStatement stmt) {
    ObjectNode node = mapper.createObjectNode();
    node.put("type", "OPEN");
    ArrayNode modeGroups = node.putArray("mode_groups");
    for (OpenStatement.OpenOperand op : stmt.getOpenOperands()) {
        ObjectNode grp = mapper.createObjectNode();
        grp.put("mode", op.getOpenMode().name().replace("_", "-"));
        ArrayNode files = grp.putArray("files");
        for (FileName fn : op.getFileNames()) {
            files.add(fn.getName().toUpperCase());
        }
        modeGroups.add(grp);
    }
    return node;
}
```

Note: ProLeap's `OpenStatement` uses `getOpenOperands()` returning a `List<OpenStatement.OpenOperand>`. Each `OpenOperand` has `getOpenMode()` (an enum: `INPUT`, `OUTPUT`, `IO`, `EXTEND`) and `getFileNames()`. The ProLeap enum value for I-O is `IO` — convert to `"I-O"` by checking name equality.

Actual conversion:
```java
String modeName = op.getOpenMode().name();
if (modeName.equals("IO")) modeName = "I-O";
grp.put("mode", modeName);
```

- [ ] **Step 3: Fix `serializeRead` — add AT END, NOT AT END, INVALID KEY, NOT INVALID KEY, KEY IS**

In `serializeRead`, after capturing `file_name` and `into`, add:

```java
// KEY IS clause (random access)
if (stmt.getReadIntoPhrase() != null && stmt.getReadIntoPhrase().getQualifiedDataName() != null) {
    // already handled as "into"
}
if (stmt.getReadKeyPhrase() != null) {
    node.put("key", stmt.getReadKeyPhrase().getQualifiedDataName().getDataName().getName().toUpperCase());
}

// AT END
if (stmt.getAtEndPhrase() != null) {
    node.set("at_end", serializeStatements(stmt.getAtEndPhrase().getStatements()));
} else {
    node.set("at_end", mapper.createArrayNode());
}

// NOT AT END
if (stmt.getNotAtEndPhrase() != null) {
    node.set("not_at_end", serializeStatements(stmt.getNotAtEndPhrase().getStatements()));
} else {
    node.set("not_at_end", mapper.createArrayNode());
}

// INVALID KEY
if (stmt.getInvalidKeyPhrase() != null) {
    node.set("invalid_key", serializeStatements(stmt.getInvalidKeyPhrase().getStatements()));
} else {
    node.set("invalid_key", mapper.createArrayNode());
}

// NOT INVALID KEY
if (stmt.getNotInvalidKeyPhrase() != null) {
    node.set("not_invalid_key", serializeStatements(stmt.getNotInvalidKeyPhrase().getStatements()));
} else {
    node.set("not_invalid_key", mapper.createArrayNode());
}
```

- [ ] **Step 4: Fix `serializeWrite`, `serializeRewrite`, `serializeStart`, `serializeDelete` — add INVALID KEY / NOT INVALID KEY**

For each:
```java
if (stmt.getInvalidKeyPhrase() != null) {
    node.set("invalid_key", serializeStatements(stmt.getInvalidKeyPhrase().getStatements()));
} else {
    node.set("invalid_key", mapper.createArrayNode());
}
if (stmt.getNotInvalidKeyPhrase() != null) {
    node.set("not_invalid_key", serializeStatements(stmt.getNotInvalidKeyPhrase().getStatements()));
} else {
    node.set("not_invalid_key", mapper.createArrayNode());
}
```

For `serializeStart` also add `relop` from the `StartStatement.getStartKey().getRelationalOperator()`:
```java
if (stmt.getStartKey() != null) {
    node.put("key", stmt.getStartKey().getQualifiedDataName().getDataName().getName().toUpperCase());
    if (stmt.getStartKey().getRelationalOperator() != null) {
        node.put("relop", stmt.getStartKey().getRelationalOperator().toString());
    }
}
```

- [ ] **Step 5: Add `serializeFileControl` to `AsgSerializer.java`**

In `AsgSerializer.java`, find `serializeDataDivision` (around line 86). After that method, add:

```java
private JsonNode serializeFileControl(CompilationUnit cu) {
    ArrayNode result = mapper.createArrayNode();
    if (cu.getEnvironmentDivision() == null) return result;
    EnvironmentDivision env = cu.getEnvironmentDivision();
    if (env.getInputOutputSection() == null) return result;
    InputOutputSection ios = env.getInputOutputSection();
    if (ios.getFileControlParagraph() == null) return result;
    for (FileControlEntry fce : ios.getFileControlParagraph().getFileControlEntries()) {
        ObjectNode entry = mapper.createObjectNode();
        entry.put("file_name", fce.getFileName().getName().toUpperCase());

        if (fce.getAssignClause() != null) {
            String assign = fce.getAssignClause().getLiteral() != null
                ? fce.getAssignClause().getLiteral().toString().replace("'", "").replace("\"", "")
                : fce.getAssignClause().toString();
            entry.put("assign_to", assign.trim());
        } else {
            entry.put("assign_to", "");
        }

        String org = "SEQUENTIAL";
        if (fce.getOrganizationClause() != null) {
            org = fce.getOrganizationClause().getOrganization().name();
            if (org.equals("INDEXED")) org = "INDEXED";
            else if (org.equals("RELATIVE")) org = "RELATIVE";
            else org = "SEQUENTIAL";
        }
        entry.put("organization", org);

        String access = "SEQUENTIAL";
        if (fce.getAccessModeClause() != null) {
            access = fce.getAccessModeClause().getAccessMode().name();
        }
        entry.put("access_mode", access);

        if (fce.getRecordKeyClause() != null && fce.getRecordKeyClause().getRecordKey() != null) {
            entry.put("record_key", fce.getRecordKeyClause().getRecordKey().getDataName().getName().toUpperCase());
        } else {
            entry.put("record_key", "");
        }

        if (fce.getRelativeKeyClause() != null && fce.getRelativeKeyClause().getRelativeKey() != null) {
            entry.put("relative_key", fce.getRelativeKeyClause().getRelativeKey().getDataName().getName().toUpperCase());
        } else {
            entry.put("relative_key", "");
        }

        if (fce.getFileStatusClause() != null) {
            entry.put("file_status_var", fce.getFileStatusClause().getQualifiedDataName().getDataName().getName().toUpperCase());
        } else {
            entry.put("file_status_var", "");
        }

        result.add(entry);
    }
    return result;
}
```

Then in the main `serialize` method (or wherever the top-level ASG JSON is assembled), add:
```java
asg.set("file_control", serializeFileControl(cu));
```

- [ ] **Step 6: Rebuild the bridge JAR**

```bash
cd /Users/asgupta/code/red-dragon/proleap-bridge && mvn -q package -DskipTests && echo "BUILD OK"
```

Verify the JAR is at `target/proleap-bridge-0.1.0-shaded.jar`:
```bash
ls -lh /Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
```

- [ ] **Step 7: Smoke-test bridge on a simple COBOL file with OPEN multi-mode**

```bash
PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar \
poetry run python -c "
from interpreter.cobol.cobol_parser import CobolParser
src = '''
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUST-FILE ASSIGN TO \"cust.dat\"
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS CUST-ID
               FILE STATUS IS WS-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD CUST-FILE.
       01 CUST-REC.
          05 CUST-ID PIC X(5).
          05 CUST-NAME PIC X(20).
       WORKING-STORAGE SECTION.
       01 WS-STATUS PIC XX.
       PROCEDURE DIVISION.
       MAIN.
           OPEN INPUT CUST-FILE OUTPUT REPORT-FILE
           STOP RUN.
'''
import json
from interpreter.cobol.subprocess_runner import run_bridge
result = run_bridge(src)
asg = json.loads(result)
print('file_control:', json.dumps(asg.get('file_control', []), indent=2))
print('open stmt:', json.dumps([s for s in asg.get('statements', []) if s.get('type') == 'OPEN'], indent=2))
" 2>&1 | grep -A 30 "file_control\|open stmt\|mode_groups"
```

Expected output shows `file_control` array with one entry (CUST-FILE, INDEXED, DYNAMIC) and OPEN with `mode_groups`.

- [ ] **Step 8: Commit bridge changes**

```bash
cd /Users/asgupta/code/red-dragon && git add proleap-bridge/src/ && git commit -m "feat(bridge): serialize AT END/INVALID KEY/KEY IS/OPEN mode_groups/FILE-CONTROL"
```

---

## Task 5: MaterialisedSectionedLayout — file section region

**Files:**
- Modify: `interpreter/cobol/sectioned_layout.py`
- Modify: `interpreter/cobol/lower_data_division.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_cobol_io_integration.py`:

```python
def test_file_section_region_accessible(self):
    """After READ, FD sub-fields should be readable via the file section region."""
    # This test verifies that lower_sectioned_data_division emits an ALLOC_REGION
    # for the file section when the FD layout is non-empty.
    from interpreter.cobol.asg_types import CobolASG, CobolField
    from interpreter.cobol.sectioned_layout import build_sectioned_layout, MaterialisedSectionedLayout
    from interpreter.cobol.data_layout import build_data_layout
    from interpreter.cobol.lower_data_division import lower_sectioned_data_division

    file_field = CobolField(
        name="CUST-REC", level=1, pic="", usage="DISPLAY", offset=0,
        children=[
            CobolField(name="CUST-ID", level=5, pic="X(5)", usage="DISPLAY", offset=0),
        ]
    )
    asg = CobolASG(file_fields=[file_field])
    layout = build_sectioned_layout(asg)
    assert layout.file.total_bytes > 0
    # MaterialisedSectionedLayout must have a .file attribute after our changes
    # (actual lowering tested in integration)
    assert hasattr(MaterialisedSectionedLayout.__dataclass_fields__, "file")
```

- [ ] **Step 2: Run test, confirm FAIL**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest "tests/unit/test_cobol_io_integration.py::TestCobolIo::test_file_section_region_accessible" -v 2>&1 | tail -15
```

- [ ] **Step 3: Add `file` field to `MaterialisedSectionedLayout`**

In `interpreter/cobol/sectioned_layout.py`, extend `MaterialisedSectionedLayout`:

```python
@dataclass(frozen=True)
class MaterialisedSectionedLayout:
    working_storage: tuple[DataLayout, Register]
    linkage: tuple[DataLayout, Register]
    local_storage: tuple[DataLayout, Register]
    file: tuple[DataLayout, Register] = field(default_factory=lambda: (DataLayout(), NO_REGISTER))
```

(Need to import `NO_REGISTER` from `interpreter.register` — it's already imported in `lower_data_division.py`, add it here too.)

Extend `resolve()` to also check file section (lowest precedence — after linkage):

```python
def resolve(self, name: str, qualifiers: tuple[str, ...] = ()) -> tuple[FieldLayout, Register]:
    # ... existing LS > WS > LK checks ...
    # Add after LK check:
    file_layout, file_reg = self.file
    file_fl = file_layout.lookup_as_storage(name, qualifiers)
    if file_fl is not None:
        return file_fl, file_reg

    raise KeyError(f"Field {name!r} not found in any DATA DIVISION section")
```

Extend `has_field()`:
```python
def has_field(self, name: str) -> bool:
    ls_layout, _ = self.local_storage
    ws_layout, _ = self.working_storage
    lk_layout, _ = self.linkage
    file_layout, _ = self.file
    return (
        ls_layout.lookup_as_storage(name) is not None
        or ws_layout.lookup_as_storage(name) is not None
        or lk_layout.lookup_as_storage(name) is not None
        or file_layout.lookup_as_storage(name) is not None
    )
```

Extend `subscript_stride()` and `group_leaf_names()` — add `self.file` to the iteration tuple in each.

- [ ] **Step 4: Emit ALLOC_REGION for file section in `lower_sectioned_data_division`**

In `interpreter/cobol/lower_data_division.py`, update `lower_sectioned_data_division`:

```python
if layout.file.total_bytes > 0:
    file_reg = lower_data_division(ctx, layout.file)
else:
    file_reg = NO_REGISTER

return MaterialisedSectionedLayout(
    working_storage=(layout.working_storage, ws_reg),
    linkage=(layout.linkage, lk_reg),
    local_storage=(layout.local_storage, ls_reg),
    file=(layout.file, file_reg),
)
```

- [ ] **Step 5: Run test, confirm PASS**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest "tests/unit/test_cobol_io_integration.py::TestCobolIo::test_file_section_region_accessible" -v 2>&1 | tail -10
```

- [ ] **Step 6: Run full unit suite**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/ -x -q 2>&1 | tail -20
```

- [ ] **Step 7: Commit**

```bash
cd /Users/asgupta/code/red-dragon && git add interpreter/cobol/sectioned_layout.py interpreter/cobol/lower_data_division.py && git commit -m "feat(cobol): add file section region to MaterialisedSectionedLayout"
```

---

## Task 6: File organization drivers

**Files:**
- Create: `interpreter/cobol/file_drivers.py`
- Create: `tests/unit/cobol/test_file_drivers.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/cobol/test_file_drivers.py
import struct
from pathlib import Path
import pytest
from interpreter.cobol.file_drivers import SequentialDriver, IndexedDriver, RelativeDriver
from interpreter.cobol.file_enums import OpenMode
from interpreter.cobol.io_provider import IOResult


RECORD_LEN = 10  # short records for tests


def _bytes(s: str) -> bytes:
    return s.encode().ljust(RECORD_LEN)[:RECORD_LEN]


class TestSequentialDriver:
    def test_write_and_read_three_records(self, tmp_path):
        path = tmp_path / "seq.dat"
        drv = SequentialDriver()
        drv.open(path, OpenMode.OUTPUT, RECORD_LEN, 0, 0)
        drv.write(_bytes("AAAAAA"))
        drv.write(_bytes("BBBBBB"))
        drv.write(_bytes("CCCCCC"))
        drv.close()

        drv2 = SequentialDriver()
        drv2.open(path, OpenMode.INPUT, RECORD_LEN, 0, 0)
        r1 = drv2.read_seq()
        assert r1.status == "00"
        assert r1.data is not None and r1.data[:6] == "AAAAAA"
        r2 = drv2.read_seq()
        assert r2.data is not None and r2.data[:6] == "BBBBBB"
        r3 = drv2.read_seq()
        assert r3.data is not None and r3.data[:6] == "CCCCCC"
        eof = drv2.read_seq()
        assert eof == IOResult("10", None)
        drv2.close()

    def test_rewrite_updates_last_read(self, tmp_path):
        path = tmp_path / "seq.dat"
        drv = SequentialDriver()
        drv.open(path, OpenMode.OUTPUT, RECORD_LEN, 0, 0)
        drv.write(_bytes("AAAAAA"))
        drv.write(_bytes("BBBBBB"))
        drv.close()

        drv2 = SequentialDriver()
        drv2.open(path, OpenMode.IO, RECORD_LEN, 0, 0)
        drv2.read_seq()
        drv2.rewrite(_bytes("XXXXXX"))
        drv2.close()

        drv3 = SequentialDriver()
        drv3.open(path, OpenMode.INPUT, RECORD_LEN, 0, 0)
        first = drv3.read_seq()
        assert first.data is not None and first.data[:6] == "XXXXXX"


class TestIndexedDriver:
    KEY_OFF = 0
    KEY_LEN = 3

    def test_write_out_of_order_and_read_by_key(self, tmp_path):
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RECORD_LEN, self.KEY_OFF, self.KEY_LEN)
        drv.write(_bytes("CCC"))  # key = b"CCC"
        drv.write(_bytes("AAA"))  # key = b"AAA"
        drv.write(_bytes("BBB"))  # key = b"BBB"
        drv.close()

        drv2 = IndexedDriver()
        drv2.open(path, OpenMode.INPUT, RECORD_LEN, self.KEY_OFF, self.KEY_LEN)
        r = drv2.read_key(b"AAA")
        assert r.status == "00"
        assert r.data is not None and r.data[:3] == "AAA"

    def test_duplicate_key_returns_22(self, tmp_path):
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RECORD_LEN, self.KEY_OFF, self.KEY_LEN)
        drv.write(_bytes("AAA"))
        result = drv.write(_bytes("AAA"))
        assert result.status == "22"
        drv.close()

    def test_missing_key_returns_23(self, tmp_path):
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RECORD_LEN, self.KEY_OFF, self.KEY_LEN)
        drv.write(_bytes("AAA"))
        drv.close()

        drv2 = IndexedDriver()
        drv2.open(path, OpenMode.INPUT, RECORD_LEN, self.KEY_OFF, self.KEY_LEN)
        r = drv2.read_key(b"ZZZ")
        assert r.status == "23"
        drv2.close()

    def test_delete_compacts_file(self, tmp_path):
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RECORD_LEN, self.KEY_OFF, self.KEY_LEN)
        drv.write(_bytes("AAA"))
        drv.write(_bytes("BBB"))
        drv.write(_bytes("CCC"))
        drv.close()

        drv2 = IndexedDriver()
        drv2.open(path, OpenMode.IO, RECORD_LEN, self.KEY_OFF, self.KEY_LEN)
        drv2.read_key(b"BBB")
        drv2.delete()
        drv2.close()

        drv3 = IndexedDriver()
        drv3.open(path, OpenMode.INPUT, RECORD_LEN, self.KEY_OFF, self.KEY_LEN)
        r = drv3.read_key(b"BBB")
        assert r.status == "23"

    def test_start_positions_for_sequential_scan(self, tmp_path):
        path = tmp_path / "idx.dat"
        drv = IndexedDriver()
        drv.open(path, OpenMode.OUTPUT, RECORD_LEN, self.KEY_OFF, self.KEY_LEN)
        for c in ["AAA", "BBB", "CCC", "DDD"]:
            drv.write(_bytes(c))
        drv.close()

        drv2 = IndexedDriver()
        drv2.open(path, OpenMode.INPUT, RECORD_LEN, self.KEY_OFF, self.KEY_LEN)
        drv2.start(b"BBB", ">=")
        r1 = drv2.read_seq()
        assert r1.data is not None and r1.data[:3] == "BBB"
        r2 = drv2.read_seq()
        assert r2.data is not None and r2.data[:3] == "CCC"


class TestRelativeDriver:
    def test_write_and_read_slot_3(self, tmp_path):
        path = tmp_path / "rel.dat"
        key3 = (3).to_bytes(4, "big")
        drv = RelativeDriver()
        drv.open(path, OpenMode.OUTPUT, RECORD_LEN, 0, 0)
        drv.write(key3, _bytes("SLOT3 "))
        drv.close()

        drv2 = RelativeDriver()
        drv2.open(path, OpenMode.INPUT, RECORD_LEN, 0, 0)
        r = drv2.read_key(key3)
        assert r.status == "00"
        assert r.data is not None and r.data[:5] == "SLOT3"

    def test_empty_slot_returns_23(self, tmp_path):
        path = tmp_path / "rel.dat"
        key1 = (1).to_bytes(4, "big")
        key3 = (3).to_bytes(4, "big")
        drv = RelativeDriver()
        drv.open(path, OpenMode.OUTPUT, RECORD_LEN, 0, 0)
        drv.write(key3, _bytes("SLOT3 "))
        drv.close()

        drv2 = RelativeDriver()
        drv2.open(path, OpenMode.INPUT, RECORD_LEN, 0, 0)
        r = drv2.read_key(key1)
        assert r.status == "23"

    def test_delete_clears_slot(self, tmp_path):
        path = tmp_path / "rel.dat"
        key2 = (2).to_bytes(4, "big")
        drv = RelativeDriver()
        drv.open(path, OpenMode.OUTPUT, RECORD_LEN, 0, 0)
        drv.write(key2, _bytes("SLOT2 "))
        drv.close()

        drv2 = RelativeDriver()
        drv2.open(path, OpenMode.IO, RECORD_LEN, 0, 0)
        drv2.read_key(key2)
        drv2.delete()
        drv2.close()

        drv3 = RelativeDriver()
        drv3.open(path, OpenMode.INPUT, RECORD_LEN, 0, 0)
        r = drv3.read_key(key2)
        assert r.status == "23"

    def test_seq_read_skips_empty_slots(self, tmp_path):
        path = tmp_path / "rel.dat"
        key1 = (1).to_bytes(4, "big")
        key3 = (3).to_bytes(4, "big")
        drv = RelativeDriver()
        drv.open(path, OpenMode.OUTPUT, RECORD_LEN, 0, 0)
        drv.write(key1, _bytes("SLOT1 "))
        drv.write(key3, _bytes("SLOT3 "))  # slot 2 is empty
        drv.close()

        drv2 = RelativeDriver()
        drv2.open(path, OpenMode.INPUT, RECORD_LEN, 0, 0)
        r1 = drv2.read_seq()
        assert r1.data is not None and r1.data[:5] == "SLOT1"
        r2 = drv2.read_seq()
        assert r2.data is not None and r2.data[:5] == "SLOT3"
        eof = drv2.read_seq()
        assert eof.status == "10"
```

- [ ] **Step 2: Run tests, confirm FAIL**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_file_drivers.py -v 2>&1 | tail -20
```

- [ ] **Step 3: Implement `interpreter/cobol/file_drivers.py`**

```python
# pyright: standard
"""COBOL file organization drivers — flat-file implementations of SequentialDriver,
IndexedDriver, and RelativeDriver.

All three use plain flat files of fixed-length records. Only the access pattern
differs.
"""

from __future__ import annotations

import bisect
import io
from pathlib import Path
from typing import Protocol, runtime_checkable

from interpreter.cobol.file_enums import OpenMode
from interpreter.cobol.io_provider import IOResult


@runtime_checkable
class FileOrganizationDriver(Protocol):
    def open(self, path: Path, mode: OpenMode, record_length: int,
             key_offset: int, key_length: int) -> None: ...
    def close(self) -> None: ...
    def read_seq(self) -> IOResult: ...
    def read_key(self, key: bytes) -> IOResult: ...
    def start(self, key: bytes, relop: str) -> IOResult: ...
    def write(self, data: bytes, key: bytes = b"") -> IOResult: ...
    def rewrite(self, data: bytes, key: bytes = b"") -> IOResult: ...
    def delete(self, key: bytes = b"") -> IOResult: ...


class SequentialDriver:
    """Flat file of concatenated fixed-length records."""

    def __init__(self) -> None:
        self._fh: io.RawIOBase | None = None
        self._record_length = 0
        self._last_pos = 0

    def open(self, path: Path, mode: OpenMode, record_length: int,
             key_offset: int, key_length: int) -> None:
        self._record_length = record_length
        if mode == OpenMode.OUTPUT:
            self._fh = open(path, "w+b")
        elif mode == OpenMode.EXTEND:
            self._fh = open(path, "a+b")
        else:  # INPUT or IO
            self._fh = open(path, "r+b" if mode == OpenMode.IO else "rb")

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def read_seq(self) -> IOResult:
        assert self._fh is not None
        self._last_pos = self._fh.tell()
        data = self._fh.read(self._record_length)
        if not data:
            return IOResult("10", None)
        padded = data.ljust(self._record_length)
        return IOResult("00", padded.decode("latin-1"))

    def read_key(self, key: bytes) -> IOResult:
        return IOResult("23", None)  # not supported on sequential

    def start(self, key: bytes, relop: str) -> IOResult:
        return IOResult("00", None)

    def write(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        self._fh.seek(0, 2)  # end
        self._fh.write(data[:self._record_length].ljust(self._record_length))
        return IOResult("00", None)

    def rewrite(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        self._fh.seek(self._last_pos)
        self._fh.write(data[:self._record_length].ljust(self._record_length))
        return IOResult("00", None)

    def delete(self, key: bytes = b"") -> IOResult:
        return IOResult("00", None)


class IndexedDriver:
    """Flat file of fixed-length records kept sorted by key at all times.

    Binary search is used for all keyed operations. Writes shift the tail to
    maintain sort order; deletes compact in place.
    """

    def __init__(self) -> None:
        self._fh: io.RawIOBase | None = None
        self._record_length = 0
        self._key_offset = 0
        self._key_length = 0
        self._cursor = 0  # byte offset for sequential scan after start()
        self._last_pos = 0  # byte offset of last-read record

    def open(self, path: Path, mode: OpenMode, record_length: int,
             key_offset: int, key_length: int) -> None:
        self._record_length = record_length
        self._key_offset = key_offset
        self._key_length = key_length
        if mode == OpenMode.OUTPUT:
            self._fh = open(path, "w+b")
        else:
            self._fh = open(path, "r+b" if mode == OpenMode.IO else "rb")
        self._cursor = 0

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def _record_count(self) -> int:
        assert self._fh is not None
        pos = self._fh.tell()
        self._fh.seek(0, 2)
        size = self._fh.tell()
        self._fh.seek(pos)
        return size // self._record_length

    def _key_at(self, slot: int) -> bytes:
        assert self._fh is not None
        self._fh.seek(slot * self._record_length + self._key_offset)
        return self._fh.read(self._key_length)

    def _record_at(self, slot: int) -> bytes:
        assert self._fh is not None
        self._fh.seek(slot * self._record_length)
        return self._fh.read(self._record_length)

    def _find_slot(self, key: bytes) -> tuple[int, bool]:
        """Binary search. Returns (slot, exact_match)."""
        lo, hi = 0, self._record_count()
        while lo < hi:
            mid = (lo + hi) // 2
            k = self._key_at(mid)
            if k < key:
                lo = mid + 1
            elif k > key:
                hi = mid
            else:
                return mid, True
        return lo, False

    def read_seq(self) -> IOResult:
        assert self._fh is not None
        if self._cursor >= self._record_count() * self._record_length:
            return IOResult("10", None)
        self._last_pos = self._cursor
        self._fh.seek(self._cursor)
        data = self._fh.read(self._record_length)
        self._cursor += self._record_length
        if not data:
            return IOResult("10", None)
        return IOResult("00", data.ljust(self._record_length).decode("latin-1"))

    def read_key(self, key: bytes) -> IOResult:
        slot, found = self._find_slot(key)
        if not found:
            return IOResult("23", None)
        self._last_pos = slot * self._record_length
        data = self._record_at(slot)
        return IOResult("00", data.decode("latin-1"))

    def start(self, key: bytes, relop: str) -> IOResult:
        slot, found = self._find_slot(key)
        n = self._record_count()
        if relop in ("=", "=="):
            if not found:
                return IOResult("23", None)
            self._cursor = slot * self._record_length
        elif relop in (">", ">="):
            if relop == ">" and found:
                slot += 1
            if slot >= n:
                return IOResult("23", None)
            self._cursor = slot * self._record_length
        else:
            self._cursor = slot * self._record_length
        return IOResult("00", None)

    def write(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        if not key:
            key = data[self._key_offset:self._key_offset + self._key_length]
        slot, found = self._find_slot(key)
        if found:
            return IOResult("22", None)
        n = self._record_count()
        record = data[:self._record_length].ljust(self._record_length)
        # Shift tail forward
        self._fh.seek(0, 2)
        self._fh.write(b"\x00" * self._record_length)  # extend
        for i in range(n, slot, -1):
            src = self._record_at(i - 1)
            self._fh.seek(i * self._record_length)
            self._fh.write(src)
        self._fh.seek(slot * self._record_length)
        self._fh.write(record)
        return IOResult("00", None)

    def rewrite(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        if not key:
            key = data[self._key_offset:self._key_offset + self._key_length]
        slot, found = self._find_slot(key)
        if not found:
            return IOResult("23", None)
        self._fh.seek(slot * self._record_length)
        self._fh.write(data[:self._record_length].ljust(self._record_length))
        return IOResult("00", None)

    def delete(self, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        if not key and self._last_pos >= 0:
            slot = self._last_pos // self._record_length
        else:
            slot, found = self._find_slot(key)
            if not found:
                return IOResult("23", None)
        n = self._record_count()
        # Shift tail backward
        for i in range(slot, n - 1):
            src = self._record_at(i + 1)
            self._fh.seek(i * self._record_length)
            self._fh.write(src)
        self._fh.seek((n - 1) * self._record_length)
        self._fh.truncate()
        return IOResult("00", None)


_SLOT_FLAG_ACTIVE = b"\xff"
_SLOT_FLAG_EMPTY  = b"\x00"


class RelativeDriver:
    """Flat file of fixed-length slots.

    Each slot: [1-byte flag | record_length bytes].
    flag 0x00 = empty, 0xFF = active.
    Relative record number passed as 4-byte big-endian key bytes.
    """

    def __init__(self) -> None:
        self._fh: io.RawIOBase | None = None
        self._record_length = 0
        self._slot_size = 0
        self._cursor_slot = 0  # for sequential read
        self._last_slot = 0

    def open(self, path: Path, mode: OpenMode, record_length: int,
             key_offset: int, key_length: int) -> None:
        self._record_length = record_length
        self._slot_size = 1 + record_length
        if mode == OpenMode.OUTPUT:
            self._fh = open(path, "w+b")
        else:
            self._fh = open(path, "r+b" if mode == OpenMode.IO else "rb")
        self._cursor_slot = 0

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def _total_slots(self) -> int:
        assert self._fh is not None
        pos = self._fh.tell()
        self._fh.seek(0, 2)
        size = self._fh.tell()
        self._fh.seek(pos)
        return size // self._slot_size

    def _decode_key(self, key: bytes) -> int:
        return int.from_bytes(key[:4], "big")

    def _slot_pos(self, n: int) -> int:
        return (n - 1) * self._slot_size

    def read_key(self, key: bytes) -> IOResult:
        assert self._fh is not None
        n = self._decode_key(key)
        self._fh.seek(self._slot_pos(n))
        flag = self._fh.read(1)
        if not flag or flag == _SLOT_FLAG_EMPTY:
            return IOResult("23", None)
        data = self._fh.read(self._record_length)
        self._last_slot = n
        return IOResult("00", data.decode("latin-1"))

    def read_seq(self) -> IOResult:
        assert self._fh is not None
        total = self._total_slots()
        while self._cursor_slot < total:
            slot = self._cursor_slot
            self._cursor_slot += 1
            self._fh.seek(slot * self._slot_size)
            flag = self._fh.read(1)
            if flag == _SLOT_FLAG_ACTIVE:
                data = self._fh.read(self._record_length)
                self._last_slot = slot + 1
                return IOResult("00", data.decode("latin-1"))
        return IOResult("10", None)

    def start(self, key: bytes, relop: str) -> IOResult:
        n = self._decode_key(key)
        self._cursor_slot = n - 1
        return IOResult("00", None)

    def write(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        n = self._decode_key(key)
        self._fh.seek(self._slot_pos(n))
        flag = self._fh.read(1)
        if flag == _SLOT_FLAG_ACTIVE:
            return IOResult("22", None)
        # Extend file if needed
        total = self._total_slots()
        if n > total:
            self._fh.seek(0, 2)
            self._fh.write(b"\x00" * self._slot_size * (n - total))
        self._fh.seek(self._slot_pos(n))
        self._fh.write(_SLOT_FLAG_ACTIVE)
        self._fh.write(data[:self._record_length].ljust(self._record_length))
        return IOResult("00", None)

    def rewrite(self, data: bytes, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        n = self._decode_key(key) if key else self._last_slot
        self._fh.seek(self._slot_pos(n))
        flag = self._fh.read(1)
        if not flag or flag == _SLOT_FLAG_EMPTY:
            return IOResult("23", None)
        self._fh.write(data[:self._record_length].ljust(self._record_length))
        return IOResult("00", None)

    def delete(self, key: bytes = b"") -> IOResult:
        assert self._fh is not None
        n = self._decode_key(key) if key else self._last_slot
        self._fh.seek(self._slot_pos(n))
        self._fh.write(_SLOT_FLAG_EMPTY)
        return IOResult("00", None)
```

- [ ] **Step 4: Run tests, confirm PASS**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_file_drivers.py -v 2>&1 | tail -30
```

- [ ] **Step 5: Commit**

```bash
cd /Users/asgupta/code/red-dragon && git add interpreter/cobol/file_drivers.py tests/unit/cobol/test_file_drivers.py && git commit -m "feat(cobol): SequentialDriver, IndexedDriver, RelativeDriver implementations"
```

---

## Task 7: RealFileIOProvider

**Files:**
- Create: `interpreter/cobol/real_file_provider.py`
- Create: `tests/unit/cobol/test_real_file_provider.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/cobol/test_real_file_provider.py
from pathlib import Path
import pytest
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.cobol.cobol_statements import FileControlEntry
from interpreter.cobol.file_enums import FileOrganization, AccessMode, OpenMode
from interpreter.cobol.io_provider import IOResult


def _make_provider(tmp_path: Path, entries: list[dict]) -> RealFileIOProvider:
    fce_list = [FileControlEntry.from_dict(e) for e in entries]
    return RealFileIOProvider(base_dir=tmp_path, file_control=fce_list)


class TestRealFileIOProvider:
    def test_sequential_write_and_read(self, tmp_path):
        prov = _make_provider(tmp_path, [
            {"file_name": "SEQ-FILE", "assign_to": "seq.dat", "organization": "SEQUENTIAL"},
        ])
        prov._open_file("SEQ-FILE", "OUTPUT", 10, "SEQUENTIAL", 0, 0)
        prov._write_record("SEQ-FILE", "HELLO     ")
        prov._close_file("SEQ-FILE")

        prov2 = _make_provider(tmp_path, [
            {"file_name": "SEQ-FILE", "assign_to": "seq.dat", "organization": "SEQUENTIAL"},
        ])
        prov2._open_file("SEQ-FILE", "INPUT", 10, "SEQUENTIAL", 0, 0)
        r = prov2._read_record("SEQ-FILE", "")
        assert r.status == "00"
        assert r.data is not None and r.data.startswith("HELLO")
        prov2._close_file("SEQ-FILE")

    def test_path_override_takes_precedence(self, tmp_path):
        custom_path = tmp_path / "custom.dat"
        fce = FileControlEntry(file_name="F1", assign_to="ignored.dat",
                               organization=FileOrganization.SEQUENTIAL)
        prov = RealFileIOProvider(
            base_dir=tmp_path,
            file_control=[fce],
            path_overrides={"F1": custom_path},
        )
        prov._open_file("F1", "OUTPUT", 5, "SEQUENTIAL", 0, 0)
        prov._write_record("F1", "HELLO")
        prov._close_file("F1")
        assert custom_path.exists()

    def test_indexed_write_and_keyed_read(self, tmp_path):
        prov = _make_provider(tmp_path, [
            {"file_name": "IDX-FILE", "assign_to": "idx.dat",
             "organization": "INDEXED", "record_key": "KEY-FIELD"},
        ])
        prov._open_file("IDX-FILE", "OUTPUT", 10, "INDEXED", 0, 3)
        prov._write_record("IDX-FILE", "AAAFILLER ")
        prov._write_record("IDX-FILE", "BBBFILLER ")
        prov._close_file("IDX-FILE")

        prov2 = _make_provider(tmp_path, [
            {"file_name": "IDX-FILE", "assign_to": "idx.dat",
             "organization": "INDEXED", "record_key": "KEY-FIELD"},
        ])
        prov2._open_file("IDX-FILE", "INPUT", 10, "INDEXED", 0, 3)
        r = prov2._read_record("IDX-FILE", "BBB")
        assert r.status == "00"
        assert r.data is not None and r.data[:3] == "BBB"
        prov2._close_file("IDX-FILE")
```

- [ ] **Step 2: Run tests, confirm FAIL**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_real_file_provider.py -v 2>&1 | tail -20
```

- [ ] **Step 3: Implement `interpreter/cobol/real_file_provider.py`**

```python
# pyright: standard
"""RealFileIOProvider — disk-backed COBOL I/O using FileOrganizationDrivers."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from interpreter.cobol.cobol_statements import FileControlEntry
from interpreter.cobol.file_drivers import (
    FileOrganizationDriver,
    IndexedDriver,
    RelativeDriver,
    SequentialDriver,
)
from interpreter.cobol.file_enums import FileOrganization, OpenMode
from interpreter.cobol.io_provider import CobolIOProvider, IOResult
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm import Operators

logger = logging.getLogger(__name__)
_UNCOMPUTABLE = Operators.UNCOMPUTABLE


class RealFileIOProvider(CobolIOProvider):
    """Disk-backed COBOL I/O provider.

    Constructed with:
    - base_dir: root for resolving relative paths from assign_to.
    - file_control: list of FileControlEntry parsed from the ASG.
    - path_overrides: test hook; takes precedence over all other path resolution.
    """

    def __init__(
        self,
        base_dir: Path,
        file_control: list[FileControlEntry],
        path_overrides: dict[str, Path] | None = None,
    ) -> None:
        self._base_dir = base_dir
        self._file_control: dict[str, FileControlEntry] = {
            e.file_name: e for e in file_control
        }
        self._path_overrides: dict[str, Path] = path_overrides or {}
        self._drivers: dict[str, FileOrganizationDriver] = {}

    def _resolve_path(self, file_name: str, assign_to: str) -> Path:
        if file_name in self._path_overrides:
            return self._path_overrides[file_name]
        if assign_to and assign_to[0] not in ('"', "'"):
            # identifier — check environment variable
            env_val = os.environ.get(assign_to.upper())
            if env_val:
                return Path(env_val)
        clean = assign_to.strip("'\"") if assign_to else file_name.lower() + ".dat"
        return self._base_dir / clean

    def _accept(self, from_device: str) -> object:
        return _UNCOMPUTABLE

    def _open_file(self, filename: str, mode: str, record_length: int,
                   organization: str, key_offset: int, key_length: int) -> IOResult:
        fce = self._file_control.get(filename)
        assign_to = fce.assign_to if fce else ""
        org = FileOrganization(organization) if organization else FileOrganization.SEQUENTIAL
        path = self._resolve_path(filename, assign_to)
        open_mode = OpenMode(mode)

        if org == FileOrganization.INDEXED:
            drv: FileOrganizationDriver = IndexedDriver()
        elif org == FileOrganization.RELATIVE:
            drv = RelativeDriver()
        else:
            drv = SequentialDriver()

        try:
            drv.open(path, open_mode, record_length, key_offset, key_length)
        except FileNotFoundError:
            logger.warning("OPEN %s: file not found at %s", filename, path)
            return IOResult("35", None)

        self._drivers[filename] = drv
        logger.info("OPEN %s mode=%s org=%s path=%s", filename, mode, org, path)
        return IOResult("00", None)

    def _close_file(self, filename: str) -> IOResult:
        drv = self._drivers.pop(filename, None)
        if drv:
            drv.close()
        return IOResult("00", None)

    def _read_record(self, filename: str, key: str) -> IOResult:
        drv = self._drivers.get(filename)
        if not drv:
            return IOResult("47", None)
        fce = self._file_control.get(filename)
        if key:
            key_bytes = key.encode("latin-1")
            return drv.read_key(key_bytes)
        return drv.read_seq()

    def _write_record(self, filename: str, data: str) -> IOResult:
        drv = self._drivers.get(filename)
        if not drv:
            return IOResult("47", None)
        return drv.write(data.encode("latin-1"))

    def _rewrite_record(self, filename: str, data: str) -> IOResult:
        drv = self._drivers.get(filename)
        if not drv:
            return IOResult("47", None)
        return drv.rewrite(data.encode("latin-1"))

    def _start_file(self, filename: str, key: str, relop: str) -> IOResult:
        drv = self._drivers.get(filename)
        if not drv:
            return IOResult("47", None)
        return drv.start(key.encode("latin-1") if key else b"", relop or ">=")

    def _delete_record(self, filename: str) -> IOResult:
        drv = self._drivers.get(filename)
        if not drv:
            return IOResult("47", None)
        return drv.delete()
```

- [ ] **Step 4: Run tests, confirm PASS**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/cobol/test_real_file_provider.py -v 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
cd /Users/asgupta/code/red-dragon && git add interpreter/cobol/real_file_provider.py tests/unit/cobol/test_real_file_provider.py && git commit -m "feat(cobol): RealFileIOProvider with disk-backed I/O"
```

---

## Task 8: Update `lower_io.py` and `emit_context.py` — conditional clauses + FILE STATUS

**Files:**
- Modify: `interpreter/cobol/lower_io.py`
- Modify: `interpreter/cobol/emit_context.py`
- Modify: `tests/unit/test_cobol_io_integration.py` (add AT END / INVALID KEY integration tests)

- [ ] **Step 1: Write failing integration tests**

Add to `tests/unit/test_cobol_io_integration.py`:

```python
def test_at_end_fires_when_no_records(self):
    """READ AT END clause fires when sequential file is exhausted."""
    src = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ATENDTEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-EOF PIC 9 VALUE 0.
       PROCEDURE DIVISION.
           READ CUST-FILE
               AT END MOVE 1 TO WS-EOF
           END-READ
           DISPLAY WS-EOF
           STOP RUN.
    """
    from interpreter.cobol.io_provider import StubIOProvider
    from interpreter.vm.vm_config import VMConfig
    from interpreter.run import run
    config = VMConfig(io_provider=StubIOProvider(files={"CUST-FILE": {"records": []}}))
    result = run(src, language="cobol", config=config)
    assert "1" in str(result.display_output)


def test_not_at_end_fires_on_success(self):
    """READ NOT AT END clause fires when record is available."""
    src = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. NOTATENDTEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-GOT-REC PIC 9 VALUE 0.
       PROCEDURE DIVISION.
           READ CUST-FILE
               NOT AT END MOVE 1 TO WS-GOT-REC
           END-READ
           DISPLAY WS-GOT-REC
           STOP RUN.
    """
    from interpreter.cobol.io_provider import StubIOProvider
    from interpreter.vm.vm_config import VMConfig
    from interpreter.run import run
    config = VMConfig(io_provider=StubIOProvider(files={"CUST-FILE": {"records": ["HELLO     "]}}))
    result = run(src, language="cobol", config=config)
    assert "1" in str(result.display_output)
```

- [ ] **Step 2: Run tests, confirm FAIL**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/test_cobol_io_integration.py -k "at_end" -v 2>&1 | tail -20
```

- [ ] **Step 3: Add `emit_file_status_update` to `EmitContext`**

In `interpreter/cobol/emit_context.py`, add this method to the `EmitContext` class. First check what imports are needed (Register, VarName, etc. — already in the file).

The method looks up `CobolASG.file_control` for the file name and, if a FILE STATUS variable is declared, emits a STORE to it:

```python
def emit_file_status_update(
    self,
    file_name: str,
    status_reg: Register,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """Write the I/O status code to the FILE STATUS variable if declared."""
    from interpreter.cobol.cobol_statements import FileControlEntry
    # Find the FileControlEntry for this file
    fce: FileControlEntry | None = None
    for entry in self._asg.file_control:  # type: ignore[attr-defined]
        if entry.file_name == file_name:
            fce = entry
            break
    if fce is None or not fce.file_status_var:
        return
    if not materialised.has_field(fce.file_status_var):
        return
    target_ref, target_rr = self.resolve_field_ref(fce.file_status_var, materialised)
    str_reg = self.emit_to_string(status_reg)
    self.emit_encode_and_write(target_rr, target_ref.fl, str_reg, target_ref.offset_reg)
```

Note: `EmitContext` must have access to `CobolASG` — check whether it currently holds a reference. Look at `EmitContext.__init__` signature and add `asg` parameter if missing.

- [ ] **Step 4: Rewrite `lower_open` in `lower_io.py`**

Replace the existing `lower_open` function:

```python
def lower_open(
    ctx: EmitContext,
    stmt: OpenStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """OPEN [mode file1 ...] ... — open files with org/key metadata via __cobol_open_file."""
    for mode, files in stmt.mode_groups:
        for filename in files:
            fn_reg = ctx.const_to_reg(filename)
            mode_reg = ctx.const_to_reg(mode.value)

            # Look up FileControlEntry for this file
            fce = next(
                (e for e in ctx.asg.file_control if e.file_name == filename),
                None,
            )
            org = fce.organization.value if fce else "SEQUENTIAL"
            # Resolve record length from file section layout
            record_length = 0
            try:
                fl, _ = materialised.resolve(filename)  # FD root record
                record_length = fl.byte_length
            except KeyError:
                pass
            key_offset, key_length = 0, 0
            if fce and fce.record_key:
                try:
                    key_fl, _ = materialised.resolve(fce.record_key)
                    key_offset = key_fl.offset
                    key_length = key_fl.byte_length
                except KeyError:
                    pass

            rl_reg = ctx.const_to_reg(record_length)
            org_reg = ctx.const_to_reg(org)
            koff_reg = ctx.const_to_reg(key_offset)
            klen_reg = ctx.const_to_reg(key_length)

            raw_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=raw_reg,
                    func_name=FuncName("__cobol_open_file"),
                    args=(
                        Register(str(fn_reg)), Register(str(mode_reg)),
                        Register(str(rl_reg)), Register(str(org_reg)),
                        Register(str(koff_reg)), Register(str(klen_reg)),
                    ),
                ),
            )
            status_reg = ctx.fresh_reg()
            ctx.emit_inst(CallFunction(
                result_reg=status_reg,
                func_name=FuncName("__cobol_io_status"),
                args=(Register(str(raw_reg)),),
            ))
            ctx.emit_file_status_update(filename, status_reg, materialised)
            logger.info("OPEN %s %s", mode.value, filename)
```

- [ ] **Step 5: Rewrite `lower_read` with AT END / INVALID KEY branches**

```python
def lower_read(
    ctx: EmitContext,
    stmt: ReadStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """READ file-name [INTO target] [AT END ...] [INVALID KEY ...] — with IOResult branching."""
    from interpreter.instructions import Binop, BranchIf, Branch, Label_
    from interpreter.operator_kind import resolve_binop

    fn_reg = ctx.const_to_reg(stmt.file_name)

    # Key for random access
    if stmt.key and materialised.has_field(stmt.key):
        key_ref, key_rr = ctx.resolve_field_ref(stmt.key, materialised)
        key_val_reg = ctx.emit_decode_field(key_rr, key_ref.fl, key_ref.offset_reg)
        key_str_reg = ctx.emit_to_string(key_val_reg)
    else:
        key_str_reg = ctx.const_to_reg("")

    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=raw_reg,
            func_name=FuncName("__cobol_read_record"),
            args=(Register(str(fn_reg)), Register(str(key_str_reg))),
        ),
    )

    # Extract status and data
    status_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(
        result_reg=status_reg,
        func_name=FuncName("__cobol_io_status"),
        args=(Register(str(raw_reg)),),
    ))
    ctx.emit_file_status_update(stmt.file_name, status_reg, materialised)

    data_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(
        result_reg=data_reg,
        func_name=FuncName("__cobol_io_data"),
        args=(Register(str(raw_reg)),),
    ))

    # Write data into file section region at offset 0
    try:
        file_root_ref, file_rr = materialised.resolve(stmt.file_name)
        ctx.emit_encode_and_write(file_rr, file_root_ref.fl, data_reg, None)
    except KeyError:
        pass

    # INTO copy
    if stmt.into and materialised.has_field(stmt.into):
        target_ref, target_rr = ctx.resolve_field_ref(stmt.into, materialised)
        str_reg = ctx.emit_to_string(data_reg)
        ctx.emit_encode_and_write(target_rr, target_ref.fl, str_reg, target_ref.offset_reg)

    # Branch on status
    has_at_end = bool(stmt.at_end or stmt.not_at_end)
    has_inv_key = bool(stmt.invalid_key or stmt.not_invalid_key)
    after_label = ctx.fresh_label("read_after")

    if has_at_end:
        at_end_label = ctx.fresh_label("read_at_end")
        ok_label = ctx.fresh_label("read_ok")
        cond_reg = ctx.fresh_reg()
        ten_reg = ctx.const_to_reg("10")
        ctx.emit_inst(Binop(
            result_reg=cond_reg,
            operator=resolve_binop("=="),
            left=status_reg,
            right=Register(str(ten_reg)),
        ))
        ctx.emit_inst(BranchIf(
            condition=cond_reg,
            true_label=at_end_label,
            false_label=ok_label,
        ))
        ctx.emit_inst(Label_(label=at_end_label))
        for s in stmt.at_end:
            ctx.dispatch(s, materialised)
        ctx.emit_inst(Branch(label=after_label))
        ctx.emit_inst(Label_(label=ok_label))
        for s in stmt.not_at_end:
            ctx.dispatch(s, materialised)
        ctx.emit_inst(Branch(label=after_label))

    if has_inv_key:
        inv_key_label = ctx.fresh_label("read_inv_key")
        not_inv_label = ctx.fresh_label("read_not_inv")
        cond_reg = ctx.fresh_reg()
        twenty_three_reg = ctx.const_to_reg("23")
        ctx.emit_inst(Binop(
            result_reg=cond_reg,
            operator=resolve_binop("=="),
            left=status_reg,
            right=Register(str(twenty_three_reg)),
        ))
        ctx.emit_inst(BranchIf(
            condition=cond_reg,
            true_label=inv_key_label,
            false_label=not_inv_label,
        ))
        ctx.emit_inst(Label_(label=inv_key_label))
        for s in stmt.invalid_key:
            ctx.dispatch(s, materialised)
        ctx.emit_inst(Branch(label=after_label))
        ctx.emit_inst(Label_(label=not_inv_label))
        for s in stmt.not_invalid_key:
            ctx.dispatch(s, materialised)
        ctx.emit_inst(Branch(label=after_label))

    ctx.emit_inst(Label_(label=after_label))
    logger.info("READ %s INTO %s", stmt.file_name, stmt.into or "(none)")
```

- [ ] **Step 6: Add `_lower_invalid_key_branch` helper and update `lower_write`, `lower_rewrite`, `lower_start`, `lower_delete`**

Add a helper at the bottom of `lower_io.py`:

```python
def _lower_invalid_key_branch(
    ctx: EmitContext,
    status_reg: Register,
    file_name: str,
    invalid_key: list,
    not_invalid_key: list,
    materialised: MaterialisedSectionedLayout,
    after_label: str,
) -> None:
    """Emit INVALID KEY / NOT INVALID KEY branching on status == '23'."""
    from interpreter.instructions import Binop, BranchIf, Branch, Label_
    from interpreter.operator_kind import resolve_binop

    if not (invalid_key or not_invalid_key):
        return

    inv_label = ctx.fresh_label(f"{file_name}_inv_key")
    not_inv_label = ctx.fresh_label(f"{file_name}_not_inv")
    cond_reg = ctx.fresh_reg()
    twenty_three_reg = ctx.const_to_reg("23")
    ctx.emit_inst(Binop(
        result_reg=cond_reg,
        operator=resolve_binop("=="),
        left=status_reg,
        right=Register(str(twenty_three_reg)),
    ))
    ctx.emit_inst(BranchIf(
        condition=cond_reg,
        true_label=inv_label,
        false_label=not_inv_label,
    ))
    ctx.emit_inst(Label_(label=inv_label))
    for s in invalid_key:
        ctx.dispatch(s, materialised)
    ctx.emit_inst(Branch(label=after_label))
    ctx.emit_inst(Label_(label=not_inv_label))
    for s in not_invalid_key:
        ctx.dispatch(s, materialised)
    ctx.emit_inst(Branch(label=after_label))
```

Update `lower_write`:

```python
def lower_write(ctx, stmt, materialised):
    # ... existing data extraction ...
    raw_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(result_reg=raw_reg, func_name=FuncName("__cobol_write_record"),
                               args=(Register(str(fn_reg)), Register(str(data_reg)))))
    status_reg = ctx.fresh_reg()
    ctx.emit_inst(CallFunction(result_reg=status_reg, func_name=FuncName("__cobol_io_status"),
                               args=(Register(str(raw_reg)),)))
    ctx.emit_file_status_update(stmt.record_name, status_reg, materialised)
    after_label = ctx.fresh_label("write_after")
    _lower_invalid_key_branch(ctx, status_reg, stmt.record_name,
                               stmt.invalid_key, stmt.not_invalid_key, materialised, after_label)
    ctx.emit_inst(Label_(label=after_label))  # import Label_ at top
```

Same pattern for `lower_rewrite`, `lower_start`, `lower_delete` — extract status via `__cobol_io_status`, call `emit_file_status_update`, then `_lower_invalid_key_branch`.

- [ ] **Step 7: Run integration tests, confirm AT END / NOT AT END PASS**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/test_cobol_io_integration.py -v 2>&1 | tail -30
```

- [ ] **Step 8: Run full unit suite**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/ -x -q 2>&1 | tail -20
```

- [ ] **Step 9: Format and commit**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m black . && git add interpreter/cobol/lower_io.py interpreter/cobol/emit_context.py tests/unit/test_cobol_io_integration.py && git commit -m "feat(cobol): AT END/INVALID KEY lowering + FILE STATUS write-back in lower_io"
```

---

## Task 9: NIST-85 test harness

**Files:**
- Create: `tests/nist/__init__.py`
- Create: `tests/nist/conftest.py`
- Create: `tests/nist/test_sq.py`
- Create: `tests/nist/test_ix.py`
- Create: `tests/nist/test_rl.py`

NIST programs live at:
`/Users/asgupta/code/red-dragon/proleap-bridge/proleap-cobol-parser/target/test-classes/gov/nist/`

Each program has a HEADER comment (line 2) like:
```
* SQ230A AUTHOR - JMDRAKE  WRITTEN 79-03-05  MCDONNELL DOUGLAS COBOL/32
```
or a `SUBPRG:` tag for dependency chains.

The `ASSIGN TO` literal (the X-card) in NIST programs looks like `ASSIGN TO SQ-FS1` — these are environment variables or need to be mapped to `tmp_path/<name>.dat`.

- [ ] **Step 1: Create `tests/nist/__init__.py`**

Empty file.

- [ ] **Step 2: Create `tests/nist/conftest.py`**

```python
"""NIST-85 test harness — shared fixtures for SQ/IX/RL test suites.

NIST COBOL programs use ASSIGN TO environment names (e.g. SQ-FS1) which we
map to tmp_path/<name>.dat via the RealFileIOProvider path_overrides.
Programs in writer-reader chains share a tmp_path via pytest's session-scoped
tmp_path_factory.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.cobol.cobol_statements import FileControlEntry
from interpreter.vm.vm_config import VMConfig

NIST_DIR = Path(
    "/Users/asgupta/code/red-dragon/proleap-bridge/proleap-cobol-parser"
    "/target/test-classes/gov/nist"
)

# Regex to find ASSIGN TO <name> in FILE-CONTROL
_ASSIGN_RE = re.compile(r"ASSIGN\s+TO\s+(\S+)", re.IGNORECASE)


def extract_assign_names(src: str) -> list[str]:
    """Extract all ASSIGN TO names from COBOL source."""
    return _ASSIGN_RE.findall(src)


def make_path_overrides(src: str, tmp_path: Path) -> dict[str, Path]:
    """Map each ASSIGN TO name to a .dat file in tmp_path."""
    names = extract_assign_names(src)
    return {name.upper(): tmp_path / f"{name.lower()}.dat" for name in names}


def make_provider(src: str, tmp_path: Path) -> RealFileIOProvider:
    overrides = make_path_overrides(src, tmp_path)
    return RealFileIOProvider(
        base_dir=tmp_path,
        file_control=[],  # let OPEN metadata drive driver selection
        path_overrides=overrides,
    )


def extract_pass_fail(output: str) -> tuple[int, int]:
    """Extract PASS and FAIL counts from NIST PRINT-FILE output."""
    pass_count = len(re.findall(r"\bPASS\b", output))
    fail_count = len(re.findall(r"\bFAIL\b", output))
    return pass_count, fail_count
```

- [ ] **Step 3: Create `tests/nist/test_sq.py` (first 5 sequential programs only)**

For the initial skeleton, pick 5 representative SQ programs. Full 170-program list can be expanded later.

```python
"""NIST-85 Sequential File I/O tests (SQ series).

Run with: poetry run python -m pytest tests/nist/test_sq.py -m nist -v
"""
import pytest
from pathlib import Path
from tests.nist.conftest import NIST_DIR, make_provider, extract_pass_fail
from interpreter.run import run
from interpreter.vm.vm_config import VMConfig

pytestmark = pytest.mark.nist


def _run_nist(prog_name: str, tmp_path: Path) -> None:
    src_path = NIST_DIR / f"{prog_name}.CBL"
    if not src_path.exists():
        pytest.skip(f"NIST source not found: {src_path}")
    src = src_path.read_text()
    provider = make_provider(src, tmp_path)
    config = VMConfig(io_provider=provider)
    result = run(src, language="cobol", config=config)
    output = "\n".join(str(x) for x in result.display_output) if hasattr(result, "display_output") else ""
    passes, fails = extract_pass_fail(output)
    assert fails == 0, f"{prog_name}: {fails} FAIL(s), {passes} PASS(es)\n{output[:2000]}"


@pytest.mark.parametrize("prog", [
    "SQ101A", "SQ102A", "SQ103A", "SQ104A", "SQ105A",
])
def test_sq_program(prog: str, tmp_path: Path) -> None:
    _run_nist(prog, tmp_path)
```

- [ ] **Step 4: Create `tests/nist/test_ix.py` and `tests/nist/test_rl.py`** (same structure, different prog names)

`test_ix.py`:
```python
import pytest
from pathlib import Path
from tests.nist.conftest import NIST_DIR, make_provider, extract_pass_fail
from interpreter.run import run
from interpreter.vm.vm_config import VMConfig

pytestmark = pytest.mark.nist

def _run_nist(prog_name: str, tmp_path: Path) -> None:
    src_path = NIST_DIR / f"{prog_name}.CBL"
    if not src_path.exists():
        pytest.skip(f"NIST source not found: {src_path}")
    src = src_path.read_text()
    provider = make_provider(src, tmp_path)
    config = VMConfig(io_provider=provider)
    result = run(src, language="cobol", config=config)
    output = "\n".join(str(x) for x in result.display_output) if hasattr(result, "display_output") else ""
    passes, fails = extract_pass_fail(output)
    assert fails == 0, f"{prog_name}: {fails} FAIL(s)\n{output[:2000]}"

@pytest.mark.parametrize("prog", ["IX101A", "IX102A", "IX103A"])
def test_ix_program(prog: str, tmp_path: Path) -> None:
    _run_nist(prog, tmp_path)
```

`test_rl.py` — same pattern with `["RL101A", "RL102A", "RL103A"]`.

- [ ] **Step 5: Register `nist` mark in `pyproject.toml` (or `pytest.ini`)**

Check that `nist` mark is registered alongside `carddemo_e2e`. If not, add:

```toml
[tool.pytest.ini_options]
markers = [
    "nist: NIST-85 COBOL file I/O integration tests (skipped in CI)",
]
```

- [ ] **Step 6: Confirm NIST tests are collected but skipped in default run**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/nist/ --collect-only 2>&1 | tail -20
```

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/nist/ -m "not nist" -q 2>&1 | tail -10
```

- [ ] **Step 7: Commit**

```bash
cd /Users/asgupta/code/red-dragon && git add tests/nist/ && git commit -m "feat(cobol/nist): NIST-85 test harness for SQ/IX/RL programs"
```

---

## Task 10: Full suite green + format

- [ ] **Step 1: Run full unit suite**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m pytest tests/unit/ -q 2>&1 | tail -20
```

Fix any remaining failures before proceeding.

- [ ] **Step 2: Run black formatter**

```bash
cd /Users/asgupta/code/red-dragon && poetry run python -m black .
```

- [ ] **Step 3: Final commit**

```bash
cd /Users/asgupta/code/red-dragon && git add -u && git commit -m "chore: format all new COBOL file I/O files with black"
```

---

## Self-Review Against Spec

### Spec coverage

| Spec Section | Tasks |
|---|---|
| Enums (OpenMode/FileOrganization/AccessMode) | Task 1 |
| IOResult dataclass + provider contract | Task 2 |
| `__cobol_io_status` / `__cobol_io_data` dispatch | Task 2 |
| FileControlEntry + CobolASG.file_control | Task 3 |
| OpenStatement mode_groups | Task 3 |
| ReadStatement / WriteStatement / etc. conditional fields | Task 3 |
| Bridge: AT END/INVALID KEY/KEY IS/OPEN multi-mode | Task 4 |
| Bridge: FILE-CONTROL serialization | Task 4 |
| MaterialisedSectionedLayout.file field | Task 5 |
| ALLOC_REGION for file section | Task 5 |
| SequentialDriver / IndexedDriver / RelativeDriver | Task 6 |
| RealFileIOProvider | Task 7 |
| lower_open multi-mode + org/key metadata | Task 8 |
| lower_read with AT END/INVALID KEY branches | Task 8 |
| lower_write/rewrite/start/delete INVALID KEY | Task 8 |
| FILE STATUS write-back | Task 8 |
| NIST-85 harness | Task 9 |

### Type consistency

- `IOResult` defined in `io_provider.py`; imported by `file_drivers.py`, `real_file_provider.py`, lowering tests.
- `FileControlEntry` defined in `cobol_statements.py`; imported by `asg_types.py` and `real_file_provider.py`.
- `OpenMode`, `FileOrganization`, `AccessMode` defined in `file_enums.py`; imported by `file_drivers.py`, `real_file_provider.py`, `cobol_statements.py`.
- `emit_file_status_update` on `EmitContext` — requires `EmitContext` to have access to `CobolASG`. **Check**: if `EmitContext` doesn't currently hold `asg`, this method will fail. Add `asg: CobolASG` parameter to `EmitContext.__init__` and pass it from `CobolFrontend`.

### Known gap to verify before Task 8

Before implementing `emit_file_status_update`, read `EmitContext.__init__` to confirm whether `asg: CobolASG` is already a field. If not, add it.

Run:
```bash
grep -n "def __init__\|self\._asg\|self\.asg\|CobolASG" /Users/asgupta/code/red-dragon/interpreter/cobol/emit_context.py | head -20
```
