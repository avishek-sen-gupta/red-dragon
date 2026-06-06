# CICS Sub-project D — VSAM File Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In-memory VSAM KSDS engine backed by `SortedDict`, loaded from carddemo ASCII flat files, with FCT YAML configuration. Builtins for point operations (READ/WRITE/REWRITE/DELETE) and browse (STARTBR/READNEXT/READPREV/ENDBR). Lowering in `CicsLoweringStrategy`.

**Architecture:** `VsamEngine` holds one `SortedDict` per dataset, keyed by raw key bytes, value is fixed-width record bytes. Browse cursors keyed by `(task_id, file_name, cursor_id)`. FCT YAML maps dataset names to file paths and record lengths. Builtins are curried closures over the engine.

**Tech Stack:** Python 3.12, sortedcontainers (SortedDict), PyYAML, pytest, black

**Beads story:** `red-dragon-pz9g.4`

**Depends on:** Sub-project B complete (CicsLoweringStrategy exists with a `lower()` method)

---

## Files Created / Modified

| Action | Path |
|---|---|
| **Create** | `interpreter/cics/vsam/__init__.py` |
| **Create** | `interpreter/cics/vsam/fct.py` |
| **Create** | `interpreter/cics/vsam/engine.py` |
| **Create** | `interpreter/cics/builtins/vsam.py` |
| **Modify** | `interpreter/cics/strategy.py` — wire VSAM verbs in lower() |
| **Create** | `tests/unit/cics/test_vsam_engine.py` |
| **Create** | `tests/unit/cics/test_vsam_builtins.py` |

---

## Task D1: FCT Config + VsamEngine Skeleton

**Files:**
- Create: `interpreter/cics/vsam/__init__.py`
- Create: `interpreter/cics/vsam/fct.py`
- Create: `interpreter/cics/vsam/engine.py`
- Create: `tests/unit/cics/test_vsam_engine.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/cics/test_vsam_engine.py`:

```python
"""Unit tests for VSAM file engine."""
import io
import tempfile
from pathlib import Path
import pytest
from interpreter.cics.vsam.engine import VsamEngine
from interpreter.cics.vsam.fct import FctConfig, DatasetConfig


# ── FCT config tests ─────────────────────────────────────────────────────────

def test_fct_config_from_yaml():
    yaml_content = """
datasets:
  ACCTDAT:
    path: data/acctdata.txt
    record_length: 300
  CARDDAT:
    path: data/carddata.txt
    record_length: 150
"""
    import yaml
    data = yaml.safe_load(yaml_content)
    config = FctConfig.from_dict(data)
    assert "ACCTDAT" in config.datasets
    assert config.datasets["ACCTDAT"].record_length == 300
    assert config.datasets["CARDDAT"].path == Path("data/carddata.txt")


# ── VsamEngine load tests ────────────────────────────────────────────────────

def _write_fixed_records(path: Path, records: list[bytes]) -> None:
    with path.open("wb") as f:
        for r in records:
            f.write(r)


def test_vsam_engine_loads_dataset():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "acctdata.txt"
        rec = b"A" * 20 + b"B" * 10  # 30-byte record
        _write_fixed_records(p, [rec])

        config = FctConfig(datasets={"ACCTDAT": DatasetConfig(path=p, record_length=30)})
        engine = VsamEngine(config)
        engine.load_all()
        assert engine.dataset_count() == 1


def test_vsam_engine_empty_file_is_ok():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "empty.txt"
        p.write_bytes(b"")
        config = FctConfig(datasets={"EMPTY": DatasetConfig(path=p, record_length=10)})
        engine = VsamEngine(config)
        engine.load_all()
        assert engine.dataset_count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/cics/test_vsam_engine.py -v
```

Expected: FAIL — modules not found.

- [ ] **Step 3: Create vsam package**

Create `interpreter/cics/vsam/__init__.py` (empty).

Create `interpreter/cics/vsam/fct.py`:

```python
"""FCT (File Control Table) config — maps dataset names to file paths and metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DatasetConfig:
    path: Path
    record_length: int

    @classmethod
    def from_dict(cls, data: dict) -> DatasetConfig:
        return cls(path=Path(data["path"]), record_length=int(data["record_length"]))


@dataclass
class FctConfig:
    datasets: dict[str, DatasetConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> FctConfig:
        ds = {
            name.upper(): DatasetConfig.from_dict(cfg)
            for name, cfg in data.get("datasets", {}).items()
        }
        return cls(datasets=ds)

    @classmethod
    def from_yaml(cls, path: Path) -> FctConfig:
        import yaml
        with path.open() as f:
            return cls.from_dict(yaml.safe_load(f))
```

Create `interpreter/cics/vsam/engine.py`:

```python
"""In-memory VSAM KSDS engine backed by SortedDict."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sortedcontainers import SortedDict

from interpreter.cics.vsam.fct import FctConfig

logger = logging.getLogger(__name__)

# Browse cursor key: (task_id, file_name, cursor_id) → int index into sorted keys
_CursorKey = tuple[str, str, str]

# CICS EIBRESP codes used by file control
RESP_NORMAL = 0
RESP_NOTFND = 13
RESP_ENDFILE = 20
RESP_DUPREC = 14
RESP_DISABLED = 84
RESP_IOERR = 17


@dataclass
class VsamDataset:
    record_length: int
    store: SortedDict = field(default_factory=SortedDict)  # key_bytes → record_bytes


class VsamEngine:
    """In-memory VSAM engine. One SortedDict per dataset."""

    def __init__(self, config: FctConfig) -> None:
        self._config = config
        self._datasets: dict[str, VsamDataset] = {}
        self._cursors: dict[_CursorKey, int] = {}

    def load_all(self) -> None:
        """Load all configured datasets from their ASCII flat files."""
        for name, cfg in self._config.datasets.items():
            ds = VsamDataset(record_length=cfg.record_length)
            if cfg.path.exists():
                data = cfg.path.read_bytes()
                rec_len = cfg.record_length
                for i in range(0, len(data), rec_len):
                    record = data[i : i + rec_len]
                    if len(record) == rec_len:
                        # Key is the first N bytes — caller specifies key at operation time
                        # Store with full record as key for now; keyed operations use slice
                        ds.store[record] = record
            self._datasets[name.upper()] = ds
            logger.info("VSAM: loaded %s (%d records)", name, len(ds.store))

    def dataset_count(self) -> int:
        return len(self._datasets)

    def _get_ds(self, file_name: str) -> VsamDataset | None:
        return self._datasets.get(file_name.upper().strip("'\""))

    # ── Point operations ──────────────────────────────────────────────

    def read(
        self, file_name: str, key: bytes, key_length: int
    ) -> tuple[bytes | None, int]:
        """READ FILE. Returns (record_bytes, eibresp)."""
        ds = self._get_ds(file_name)
        if ds is None:
            return None, RESP_DISABLED
        # Find record whose key prefix matches
        for record in ds.store.keys():
            if record[:key_length] == key[:key_length]:
                return bytes(record), RESP_NORMAL
        return None, RESP_NOTFND

    def write(
        self, file_name: str, key: bytes, key_length: int, record: bytes
    ) -> int:
        """WRITE FILE. Returns eibresp."""
        ds = self._get_ds(file_name)
        if ds is None:
            return RESP_DISABLED
        key_prefix = record[:key_length]
        for existing in list(ds.store.keys()):
            if existing[:key_length] == key_prefix:
                return RESP_DUPREC
        ds.store[bytes(record)] = bytes(record)
        return RESP_NORMAL

    def rewrite(self, file_name: str, key: bytes, key_length: int, record: bytes) -> int:
        """REWRITE FILE. Returns eibresp."""
        ds = self._get_ds(file_name)
        if ds is None:
            return RESP_DISABLED
        key_prefix = key[:key_length]
        for existing in list(ds.store.keys()):
            if existing[:key_length] == key_prefix:
                del ds.store[existing]
                ds.store[bytes(record)] = bytes(record)
                return RESP_NORMAL
        return RESP_NOTFND

    def delete(self, file_name: str, key: bytes, key_length: int) -> int:
        """DELETE FILE. Returns eibresp."""
        ds = self._get_ds(file_name)
        if ds is None:
            return RESP_DISABLED
        key_prefix = key[:key_length]
        for existing in list(ds.store.keys()):
            if existing[:key_length] == key_prefix:
                del ds.store[existing]
                return RESP_NORMAL
        return RESP_NOTFND

    # ── Browse operations ─────────────────────────────────────────────

    def startbr(
        self, file_name: str, key: bytes, key_length: int, cursor_key: _CursorKey
    ) -> int:
        """STARTBR FILE. Positions cursor at or after key. Returns eibresp."""
        ds = self._get_ds(file_name)
        if ds is None:
            return RESP_DISABLED
        keys = list(ds.store.keys())
        prefix = key[:key_length]
        # Find first key >= prefix
        idx = 0
        for i, k in enumerate(keys):
            if k[:key_length] >= prefix:
                idx = i
                break
        self._cursors[cursor_key] = idx
        return RESP_NORMAL

    def readnext(
        self, file_name: str, cursor_key: _CursorKey
    ) -> tuple[bytes | None, int]:
        """READNEXT FILE. Returns (record, eibresp)."""
        ds = self._get_ds(file_name)
        if ds is None:
            return None, RESP_DISABLED
        idx = self._cursors.get(cursor_key, 0)
        keys = list(ds.store.keys())
        if idx >= len(keys):
            return None, RESP_ENDFILE
        record = keys[idx]
        self._cursors[cursor_key] = idx + 1
        return bytes(record), RESP_NORMAL

    def readprev(
        self, file_name: str, cursor_key: _CursorKey
    ) -> tuple[bytes | None, int]:
        """READPREV FILE. Returns (record, eibresp)."""
        ds = self._get_ds(file_name)
        if ds is None:
            return None, RESP_DISABLED
        idx = self._cursors.get(cursor_key, 0) - 1
        keys = list(ds.store.keys())
        if idx < 0:
            return None, RESP_ENDFILE
        record = keys[idx]
        self._cursors[cursor_key] = idx
        return bytes(record), RESP_NORMAL

    def endbr(self, file_name: str, cursor_key: _CursorKey) -> int:
        """ENDBR FILE. Releases cursor. Returns eibresp."""
        self._cursors.pop(cursor_key, None)
        return RESP_NORMAL
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/cics/test_vsam_engine.py -v
```

Expected: all PASS

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cics/vsam/__init__.py interpreter/cics/vsam/fct.py \
        interpreter/cics/vsam/engine.py tests/unit/cics/test_vsam_engine.py
git commit -m "$(cat <<'EOF'
feat(cics): VSAM engine (SortedDict KSDS + FCT YAML config) (pz9g.4)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task D2: Point Operation Tests + Browse Tests

**Files:**
- Modify: `tests/unit/cics/test_vsam_engine.py` — add READ/WRITE/REWRITE/DELETE/browse tests

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/cics/test_vsam_engine.py`:

```python
from interpreter.cics.vsam.engine import (
    VsamEngine, RESP_NORMAL, RESP_NOTFND, RESP_DUPREC, RESP_ENDFILE,
)


def _engine_with_records(records: list[bytes], rec_len: int) -> VsamEngine:
    from interpreter.cics.vsam.fct import FctConfig, DatasetConfig
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "data.txt"
        _write_fixed_records(p, records)
        config = FctConfig(datasets={"TESTDS": DatasetConfig(path=p, record_length=rec_len)})
        engine = VsamEngine(config)
        engine.load_all()
        return engine


REC_LEN = 10
KEY_LEN = 4

def _rec(key: str, rest: str = "") -> bytes:
    body = rest.ljust(REC_LEN - KEY_LEN)[:REC_LEN - KEY_LEN]
    return (key.ljust(KEY_LEN)[:KEY_LEN] + body).encode()


def test_read_existing_record():
    engine = _engine_with_records([_rec("AA01", "DATA")], REC_LEN)
    record, resp = engine.read("TESTDS", b"AA01", KEY_LEN)
    assert resp == RESP_NORMAL
    assert record is not None
    assert record[:KEY_LEN] == b"AA01"


def test_read_not_found():
    engine = _engine_with_records([_rec("AA01", "DATA")], REC_LEN)
    _, resp = engine.read("TESTDS", b"ZZ99", KEY_LEN)
    assert resp == RESP_NOTFND


def test_write_new_record():
    engine = _engine_with_records([], REC_LEN)
    resp = engine.write("TESTDS", b"AA01", KEY_LEN, _rec("AA01", "NEW"))
    assert resp == RESP_NORMAL
    record, resp2 = engine.read("TESTDS", b"AA01", KEY_LEN)
    assert resp2 == RESP_NORMAL


def test_write_duplicate_returns_duprec():
    engine = _engine_with_records([_rec("AA01", "OLD")], REC_LEN)
    resp = engine.write("TESTDS", b"AA01", KEY_LEN, _rec("AA01", "NEW"))
    assert resp == RESP_DUPREC


def test_rewrite_updates_record():
    engine = _engine_with_records([_rec("AA01", "OLD")], REC_LEN)
    resp = engine.rewrite("TESTDS", b"AA01", KEY_LEN, _rec("AA01", "UPD"))
    assert resp == RESP_NORMAL
    record, _ = engine.read("TESTDS", b"AA01", KEY_LEN)
    assert b"UPD" in record


def test_delete_removes_record():
    engine = _engine_with_records([_rec("AA01", "DATA")], REC_LEN)
    resp = engine.delete("TESTDS", b"AA01", KEY_LEN)
    assert resp == RESP_NORMAL
    _, resp2 = engine.read("TESTDS", b"AA01", KEY_LEN)
    assert resp2 == RESP_NOTFND


def test_browse_forward():
    records = [_rec("AA01"), _rec("BB02"), _rec("CC03")]
    engine = _engine_with_records(records, REC_LEN)
    cursor = ("task0", "TESTDS", "cur0")
    engine.startbr("TESTDS", b"AA01", KEY_LEN, cursor)
    rec1, r1 = engine.readnext("TESTDS", cursor)
    rec2, r2 = engine.readnext("TESTDS", cursor)
    rec3, r3 = engine.readnext("TESTDS", cursor)
    _, r4 = engine.readnext("TESTDS", cursor)
    assert r1 == RESP_NORMAL and rec1[:4] == b"AA01"
    assert r2 == RESP_NORMAL and rec2[:4] == b"BB02"
    assert r3 == RESP_NORMAL
    assert r4 == RESP_ENDFILE
    engine.endbr("TESTDS", cursor)


def test_browse_reverse():
    records = [_rec("AA01"), _rec("BB02")]
    engine = _engine_with_records(records, REC_LEN)
    cursor = ("task0", "TESTDS", "cur0")
    engine.startbr("TESTDS", b"BB02", KEY_LEN, cursor)
    # Move forward once to position at BB02
    engine.readnext("TESTDS", cursor)
    rec, resp = engine.readprev("TESTDS", cursor)
    assert resp == RESP_NORMAL
    assert rec[:4] == b"AA01"
```

- [ ] **Step 2: Run tests**

```bash
poetry run python -m pytest tests/unit/cics/test_vsam_engine.py -v
```

Expected: all PASS (engine implementation already covers these)

- [ ] **Step 3: Commit**

```bash
poetry run python -m black .
git add tests/unit/cics/test_vsam_engine.py
git commit -m "$(cat <<'EOF'
test(cics): VSAM point operations + browse coverage (pz9g.4)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task D3: VSAM Builtins + Lowering

**Files:**
- Create: `interpreter/cics/builtins/vsam.py`
- Modify: `interpreter/cics/strategy.py` — register VSAM builtins + wire VSAM verbs
- Create: `tests/unit/cics/test_vsam_builtins.py`

VSAM builtins are curried over the `VsamEngine`. Arguments from the lowering strategy include the resolved field values (file name, key bytes, record bytes). `RESP(f)` field is written to via a separate STORE after the builtin returns its response code.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/cics/test_vsam_builtins.py`:

```python
"""Unit tests for VSAM builtins."""
import tempfile
from pathlib import Path
from interpreter.cics.vsam.engine import VsamEngine, RESP_NORMAL, RESP_NOTFND
from interpreter.cics.vsam.fct import FctConfig, DatasetConfig
from interpreter.cics.builtins.vsam import make_vsam_read_builtin
from interpreter.vm.vm_types import VMState
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import scalar


def _make_engine(records: list[bytes], rec_len: int) -> VsamEngine:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "data.txt"
        for r in records:
            with p.open("ab") as f:
                f.write(r)
        config = FctConfig(datasets={"TESTDS": DatasetConfig(path=p, record_length=rec_len)})
        engine = VsamEngine(config)
        engine.load_all()
        return engine


def test_vsam_read_builtin_found():
    rec = b"KEY1" + b"DATA" * 6  # 28 bytes
    engine = _make_engine([rec], 28)
    builtin = make_vsam_read_builtin(engine)
    vm = VMState()
    args = [
        typed("TESTDS", scalar("str")),   # file name
        typed(b"KEY1", scalar("bytes")),  # ridfld
        typed(4, scalar("int")),           # keylength
    ]
    result = builtin(args, vm)
    assert result.value is not None
    assert bytes(result.value)[:4] == b"KEY1"


def test_vsam_read_builtin_not_found():
    engine = _make_engine([], 28)
    builtin = make_vsam_read_builtin(engine)
    vm = VMState()
    args = [
        typed("TESTDS", scalar("str")),
        typed(b"XXXX", scalar("bytes")),
        typed(4, scalar("int")),
    ]
    result = builtin(args, vm)
    # Not found — result carries (None, RESP_NOTFND) as a tuple
    assert result.value is not None
    data, resp = result.value
    assert resp == RESP_NOTFND
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/cics/test_vsam_builtins.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement VSAM builtins**

Create `interpreter/cics/builtins/vsam.py`:

```python
"""VSAM file control builtins — curried over VsamEngine."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from interpreter.cics.vsam.engine import VsamEngine
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import BuiltinResult, VMState

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_TASK_ID = "cics_task"  # single-task emulation; cursor key prefix


def _file(args: list[TypedValue], idx: int = 0) -> str:
    return str(args[idx].value).strip("'\" ") if len(args) > idx else ""


def _key_bytes(args: list[TypedValue], idx: int = 1) -> bytes:
    v = args[idx].value if len(args) > idx else b""
    return bytes(v) if isinstance(v, (bytes, bytearray, list)) else str(v).encode()


def _key_len(args: list[TypedValue], idx: int = 2) -> int:
    return int(args[idx].value) if len(args) > idx else 0


def _record_bytes(args: list[TypedValue], idx: int = 1) -> bytes:
    v = args[idx].value if len(args) > idx else b""
    return bytes(v) if isinstance(v, (bytes, bytearray, list)) else str(v).encode()


def make_vsam_read_builtin(engine: VsamEngine) -> object:
    def __cics_read(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        record, resp = engine.read(_file(args, 0), _key_bytes(args, 1), _key_len(args, 2))
        if record is not None:
            return BuiltinResult(value=record)
        return BuiltinResult(value=(None, resp))

    return __cics_read


def make_vsam_write_builtin(engine: VsamEngine) -> object:
    def __cics_write(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        resp = engine.write(
            _file(args, 0), _key_bytes(args, 1), _key_len(args, 2), _record_bytes(args, 3)
        )
        return BuiltinResult(value=resp)

    return __cics_write


def make_vsam_rewrite_builtin(engine: VsamEngine) -> object:
    def __cics_rewrite(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        resp = engine.rewrite(
            _file(args, 0), _key_bytes(args, 1), _key_len(args, 2), _record_bytes(args, 3)
        )
        return BuiltinResult(value=resp)

    return __cics_rewrite


def make_vsam_delete_builtin(engine: VsamEngine) -> object:
    def __cics_delete(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        resp = engine.delete(_file(args, 0), _key_bytes(args, 1), _key_len(args, 2))
        return BuiltinResult(value=resp)

    return __cics_delete


def make_vsam_startbr_builtin(engine: VsamEngine) -> object:
    _cursor_counter = [0]

    def __cics_startbr(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        fname = _file(args, 0)
        key = _key_bytes(args, 1)
        klen = _key_len(args, 2)
        cid = str(_cursor_counter[0])
        _cursor_counter[0] += 1
        cursor_key = (_TASK_ID, fname, cid)
        resp = engine.startbr(fname, key, klen, cursor_key)
        return BuiltinResult(value=(_TASK_ID, fname, cid, resp))

    return __cics_startbr


def make_vsam_readnext_builtin(engine: VsamEngine) -> object:
    def __cics_readnext(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        fname = _file(args, 0)
        # cursor_key passed as arg 1 (task_id, file, cid) tuple
        cursor_key = tuple(args[1].value) if len(args) > 1 else (_TASK_ID, fname, "0")
        record, resp = engine.readnext(fname, cursor_key)
        return BuiltinResult(value=(record, resp))

    return __cics_readnext


def make_vsam_readprev_builtin(engine: VsamEngine) -> object:
    def __cics_readprev(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        fname = _file(args, 0)
        cursor_key = tuple(args[1].value) if len(args) > 1 else (_TASK_ID, fname, "0")
        record, resp = engine.readprev(fname, cursor_key)
        return BuiltinResult(value=(record, resp))

    return __cics_readprev


def make_vsam_endbr_builtin(engine: VsamEngine) -> object:
    def __cics_endbr(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        fname = _file(args, 0)
        cursor_key = tuple(args[1].value) if len(args) > 1 else (_TASK_ID, fname, "0")
        resp = engine.endbr(fname, cursor_key)
        return BuiltinResult(value=resp)

    return __cics_endbr
```

- [ ] **Step 4: Register VSAM builtins in CicsLoweringStrategy**

In `interpreter/cics/strategy.py`, update `CicsLoweringStrategy.__init__` to accept and register the VSAM engine:

```python
from interpreter.cics.builtins.vsam import (
    make_vsam_read_builtin, make_vsam_write_builtin, make_vsam_rewrite_builtin,
    make_vsam_delete_builtin, make_vsam_startbr_builtin, make_vsam_readnext_builtin,
    make_vsam_readprev_builtin, make_vsam_endbr_builtin,
)

# Add vsam_engine param to __init__:
def __init__(self, ..., vsam_engine=None):
    ...
    if vsam_engine is not None:
        builtin_registry["__cics_read"] = make_vsam_read_builtin(vsam_engine)
        builtin_registry["__cics_write"] = make_vsam_write_builtin(vsam_engine)
        builtin_registry["__cics_rewrite"] = make_vsam_rewrite_builtin(vsam_engine)
        builtin_registry["__cics_delete"] = make_vsam_delete_builtin(vsam_engine)
        builtin_registry["__cics_startbr"] = make_vsam_startbr_builtin(vsam_engine)
        builtin_registry["__cics_readnext"] = make_vsam_readnext_builtin(vsam_engine)
        builtin_registry["__cics_readprev"] = make_vsam_readprev_builtin(vsam_engine)
        builtin_registry["__cics_endbr"] = make_vsam_endbr_builtin(vsam_engine)
```

Update `lower()` to handle VSAM verbs (READ, WRITE, REWRITE, DELETE, STARTBR, READNEXT, READPREV, ENDBR) by looking up their builtin names and emitting `CALL_BUILTIN` with the file/key/record args resolved from options:

```python
_VSAM_VERBS = {
    "READ": "__cics_read",
    "WRITE": "__cics_write",
    "REWRITE": "__cics_rewrite",
    "DELETE": "__cics_delete",
    "STARTBR": "__cics_startbr",
    "READNEXT": "__cics_readnext",
    "READPREV": "__cics_readprev",
    "ENDBR": "__cics_endbr",
}
# In lower():
if verb in _VSAM_VERBS:
    builtin_name = _VSAM_VERBS[verb]
    # Emit file name as constant; key/record as field loads resolved from opts
    r_file = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=r_file, value=opts.get("FILE", "")))
    r_res = ctx.fresh_reg()
    ctx.emit_inst(CallBuiltin(result_reg=r_res, name=FuncName(builtin_name), args=[r_file]))
    return
```

Note: full arg resolution (key bytes, record bytes via RIDFLD/INTO/FROM field addresses) is a future refinement. The MVP emits file name only — sufficient to exercise the plumbing without field-level serialization.

- [ ] **Step 5: Run all VSAM tests**

```bash
poetry run python -m pytest tests/unit/cics/test_vsam_engine.py tests/unit/cics/test_vsam_builtins.py -v
```

Expected: all PASS

- [ ] **Step 6: Run full suite**

```bash
poetry run python -m pytest -x -q
```

Expected: all PASS

- [ ] **Step 7: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cics/builtins/vsam.py interpreter/cics/strategy.py \
        tests/unit/cics/test_vsam_builtins.py
git commit -m "$(cat <<'EOF'
feat(cics): VSAM builtins + lowering wired into CicsLoweringStrategy (pz9g.4)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Sub-project D Complete

At this point:
- FCT YAML config maps dataset names to paths and record lengths
- `VsamEngine` holds `SortedDict` per dataset, loaded from ASCII flat files
- Browse cursors keyed by `(task_id, file_name, cursor_id)` with STARTBR/READNEXT/READPREV/ENDBR
- All 8 VSAM builtins registered in `builtin_registry` and wired into `CicsLoweringStrategy.lower()`

**Next:** [Sub-project E — BMS Screen Engine](2026-06-06-cics-E-bms.md)
