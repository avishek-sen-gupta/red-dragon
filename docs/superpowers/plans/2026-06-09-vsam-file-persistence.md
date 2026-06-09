# VSAM File Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the in-memory VSAM engine a configurable backend — in-memory (default, unchanged) or file-backed write-through — plus an explicit `flush_to(dir)` snapshot, persisting to the raw fixed-length-record flat image the engine already reads.

**Architecture:** A `VsamBackend` seam owns persistence; the engine keeps its in-memory `SortedDict` working set and delegates load (seed/restore) + persist (durable write) to the backend. A shared raw-format codec (`format.py`) is the single source of the on-disk format, used by the backends and `flush_to`.

**Tech Stack:** Python 3.13, `sortedcontainers.SortedDict` (existing), stdlib `os`/`pathlib`/`tempfile`, pytest. Spec: `docs/superpowers/specs/2026-06-09-vsam-file-persistence-design.md`.

---

## Grounding facts (verified against current code)

- `interpreter/cics/vsam/engine.py`: `VsamDataset(record_length, key_offset=0, key_length=0, store: SortedDict)`. `VsamEngine.__init__(self, config: FctConfig)`. `load_all()` iterates `self._config.datasets.items()`, builds a `VsamDataset`, and if `cfg.path.exists()` reads `cfg.path.read_bytes()`, splits into `record_length` chunks, and does `ds.store[record] = record` (full record bytes are the dict key). Stores under `name.upper()`. `write`/`rewrite`/`delete` mutate `ds.store` and return an `int` RESP (`RESP_NORMAL = 0`). `_get_ds(file_name)` returns the dataset for `file_name.upper().strip("'\"")`.
- `interpreter/cics/vsam/fct.py`: `DatasetConfig(path: Path, record_length: int, key_offset=0, key_length=0)`; `FctConfig(datasets: dict[str, DatasetConfig])` (keys upper-cased by `from_dict`).
- The store's dict keys ARE the full record bytes, already in sorted (key) order — so `list(ds.store.keys())` is the records in deterministic order.
- Constraint: only touch `interpreter/cics/vsam/` (+ tests). No edits to `interpreter/vm/**`, `ir.py`, `run.py`, `executor.py`, `cfg.py`. Engine stays pure bytes/int. Default in-memory path must be byte-for-byte behavior-identical (existing tests untouched).

## File structure

- **Create** `interpreter/cics/vsam/format.py` — the raw flat-file codec (read/write). One responsibility: the on-disk format.
- **Create** `interpreter/cics/vsam/backend.py` — `VsamBackend` Protocol + `InMemoryBackend` + `FileBackend`. One responsibility: where the durable copy lives + load/persist.
- **Modify** `interpreter/cics/vsam/engine.py` — accept a backend, route `load_all` through it, write-through on mutations, add `flush_to`.
- **Test** `tests/unit/cics/test_vsam_format.py`, `tests/unit/cics/test_vsam_backend.py`, extend `tests/unit/cics/test_vsam_engine.py`, and a gated demo in `tests/integration/cics/test_vsam_persistence.py`.

Use `poetry run python -m pytest` and `poetry run python -m black` (project convention). `@covers(NotLanguageFeature.INFRASTRUCTURE)` on every test (covers-guard hook requires it).

---

### Task 1: Raw flat-file codec

**Files:**
- Create: `interpreter/cics/vsam/format.py`
- Test: `tests/unit/cics/test_vsam_format.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cics/test_vsam_format.py
"""Raw fixed-length-record flat-file codec for VSAM dataset images."""
from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cics.vsam.format import read_flat_file, write_flat_file
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_round_trip(tmp_path: Path) -> None:
    recs = [b"AAAA", b"BBBB", b"CCCC"]
    p = tmp_path / "ds.dat"
    write_flat_file(p, recs, 4)
    assert read_flat_file(p, 4) == recs


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_missing_file_reads_empty(tmp_path: Path) -> None:
    assert read_flat_file(tmp_path / "nope.dat", 4) == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_size_not_multiple_of_record_length_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.dat"
    p.write_bytes(b"AAAAB")  # 5 bytes, record_length 4
    with pytest.raises(ValueError):
        read_flat_file(p, 4)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_wrong_length_record_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_flat_file(tmp_path / "x.dat", [b"AAAA", b"BB"], 4)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_write_is_atomic_no_temp_left(tmp_path: Path) -> None:
    p = tmp_path / "ds.dat"
    write_flat_file(p, [b"AAAA"], 4)
    # only the target file remains (the temp was renamed away)
    assert [f.name for f in tmp_path.iterdir()] == ["ds.dat"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_format.py -v`
Expected: FAIL — `ModuleNotFoundError: interpreter.cics.vsam.format`.

- [ ] **Step 3: Implement the codec**

```python
# interpreter/cics/vsam/format.py
"""Raw fixed-length-record flat-file codec for VSAM dataset images.

The on-disk format is a concatenation of fixed-length records (an
IDCAMS-REPRO-style sequential image) — the same format VsamEngine seeds are in,
so a written file round-trips through read_flat_file and can itself be a seed.
This is the single source of the persisted format (used by the backends and by
VsamEngine.flush_to).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable


def read_flat_file(path: Path, record_length: int) -> list[bytes]:
    """Read a flat file as a list of fixed-length records.

    A missing file yields []. Raises ValueError if the file size is not a
    multiple of record_length (corrupt / wrong record length).
    """
    if not path.exists():
        return []
    data = path.read_bytes()
    if record_length <= 0:
        raise ValueError(f"record_length must be positive, got {record_length}")
    if len(data) % record_length != 0:
        raise ValueError(
            f"{path}: size {len(data)} is not a multiple of record_length "
            f"{record_length}"
        )
    return [data[i : i + record_length] for i in range(0, len(data), record_length)]


def write_flat_file(path: Path, records: Iterable[bytes], record_length: int) -> None:
    """Write records as a fixed-length flat file, atomically.

    Each record must be exactly record_length bytes (raises ValueError otherwise).
    Writes to a temp file in the same directory then os.replace()s it into place,
    so a crash mid-write cannot truncate the dataset.
    """
    payload = bytearray()
    for rec in records:
        if len(rec) != record_length:
            raise ValueError(
                f"record length {len(rec)} != record_length {record_length}"
            )
        payload += rec
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_format.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black interpreter/cics/vsam/format.py tests/unit/cics/test_vsam_format.py
poetry run lint-imports
git add interpreter/cics/vsam/format.py tests/unit/cics/test_vsam_format.py
git commit -m "feat(vsam): raw fixed-length flat-file codec (read/write, atomic)"
```

---

### Task 2: Backend protocol + InMemoryBackend + FileBackend

**Files:**
- Create: `interpreter/cics/vsam/backend.py`
- Test: `tests/unit/cics/test_vsam_backend.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cics/test_vsam_backend.py
"""VSAM persistence backends: InMemoryBackend (default) and FileBackend."""
from __future__ import annotations

from pathlib import Path

from interpreter.cics.vsam.backend import InMemoryBackend, FileBackend
from interpreter.cics.vsam.fct import DatasetConfig
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inmemory_loads_seed_and_persist_is_noop(tmp_path: Path) -> None:
    seed = tmp_path / "seed.dat"
    seed.write_bytes(b"AAAABBBB")  # two 4-byte records
    cfg = DatasetConfig(path=seed, record_length=4)
    be = InMemoryBackend()
    assert be.load("DS", cfg) == [b"AAAA", b"BBBB"]
    be.persist("DS", cfg, [b"CCCC"])  # no-op
    assert seed.read_bytes() == b"AAAABBBB"  # seed untouched


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_file_backend_first_run_seeds_then_persists_to_backing_dir(tmp_path: Path) -> None:
    seed = tmp_path / "seed.dat"
    seed.write_bytes(b"AAAA")
    backing = tmp_path / "store"
    cfg = DatasetConfig(path=seed, record_length=4)
    be = FileBackend(backing)
    # first run: no backing file yet -> seed from cfg.path
    assert be.load("DS", cfg) == [b"AAAA"]
    # persist writes the backing file, NOT the seed
    be.persist("DS", cfg, [b"AAAA", b"ZZZZ"])
    assert (backing / "DS.dat").read_bytes() == b"AAAAZZZZ"
    assert seed.read_bytes() == b"AAAA"  # seed untouched
    # subsequent load reads the backing file, not the seed
    assert be.load("DS", cfg) == [b"AAAA", b"ZZZZ"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_backend.py -v`
Expected: FAIL — `ModuleNotFoundError: interpreter.cics.vsam.backend`.

- [ ] **Step 3: Implement the backends**

```python
# interpreter/cics/vsam/backend.py
"""VSAM persistence backends.

The engine keeps records in memory (SortedDict); a backend owns the durable copy
and is selected at engine instantiation. InMemoryBackend (default) seeds from the
read-only DatasetConfig.path and never persists. FileBackend keeps a durable
write-through copy in a backing directory, separate from the seeds.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from interpreter.cics.vsam.fct import DatasetConfig
from interpreter.cics.vsam.format import read_flat_file, write_flat_file


@runtime_checkable
class VsamBackend(Protocol):
    """Persistence boundary for the VSAM engine. Records are full record bytes
    in key order. queue.Empty-style: the default impl preserves legacy behavior.
    """

    def load(self, name: str, cfg: DatasetConfig) -> list[bytes]:
        """Return the dataset's records (key order), or [] if none."""
        ...

    def persist(self, name: str, cfg: DatasetConfig, records: list[bytes]) -> None:
        """Durably store the dataset's records. May be a no-op (in-memory)."""
        ...


class InMemoryBackend:
    """Default: seed from the read-only DatasetConfig.path; never persist."""

    def load(self, name: str, cfg: DatasetConfig) -> list[bytes]:
        return read_flat_file(cfg.path, cfg.record_length)

    def persist(self, name: str, cfg: DatasetConfig, records: list[bytes]) -> None:
        return None


class FileBackend:
    """Write-through file persistence in a backing directory (separate from seeds).

    load() returns the backing file <backing_dir>/<NAME>.dat if it exists, else
    seeds from cfg.path (first run). persist() writes the backing file.
    """

    def __init__(self, backing_dir: Path) -> None:
        self._dir = Path(backing_dir)

    def _backing_path(self, name: str) -> Path:
        return self._dir / f"{name.upper()}.dat"

    def load(self, name: str, cfg: DatasetConfig) -> list[bytes]:
        backing = self._backing_path(name)
        if backing.exists():
            return read_flat_file(backing, cfg.record_length)
        return read_flat_file(cfg.path, cfg.record_length)

    def persist(self, name: str, cfg: DatasetConfig, records: list[bytes]) -> None:
        write_flat_file(self._backing_path(name), records, cfg.record_length)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_backend.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black interpreter/cics/vsam/backend.py tests/unit/cics/test_vsam_backend.py
poetry run lint-imports
git add interpreter/cics/vsam/backend.py tests/unit/cics/test_vsam_backend.py
git commit -m "feat(vsam): VsamBackend protocol + InMemoryBackend/FileBackend"
```

---

### Task 3: Wire the backend into VsamEngine (load, write-through, flush_to)

**Files:**
- Modify: `interpreter/cics/vsam/engine.py`
- Test: `tests/unit/cics/test_vsam_engine.py` (extend; do not change existing tests)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/unit/cics/test_vsam_engine.py (keep existing tests + imports)
from pathlib import Path
from interpreter.cics.vsam.backend import FileBackend
from interpreter.cics.vsam.fct import FctConfig, DatasetConfig
from interpreter.cics.vsam.engine import VsamEngine
from interpreter.cics.vsam.format import read_flat_file
from tests.covers import covers, NotLanguageFeature


def _cfg(seed: Path) -> FctConfig:
    return FctConfig(datasets={"DS": DatasetConfig(path=seed, record_length=4)})


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_write_through_persists_and_survives_new_engine(tmp_path: Path) -> None:
    seed = tmp_path / "seed.dat"
    seed.write_bytes(b"AAAA")            # one record, key "AAAA"
    backing = tmp_path / "store"
    eng = VsamEngine(_cfg(seed), backend=FileBackend(backing))
    eng.load_all()
    assert eng.write("DS", b"ZZZZ", 4, b"ZZZZ") == 0          # RESP_NORMAL
    # the backing file reflects the write (sorted: AAAA, ZZZZ)
    assert read_flat_file(backing / "DS.dat", 4) == [b"AAAA", b"ZZZZ"]
    # a FRESH engine over the same backing dir loads the mutated state
    eng2 = VsamEngine(_cfg(seed), backend=FileBackend(backing))
    eng2.load_all()
    rec, resp = eng2.read("DS", b"ZZZZ", 4)
    assert resp == 0 and rec == b"ZZZZ"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_default_engine_writes_no_files(tmp_path: Path) -> None:
    seed = tmp_path / "seed.dat"
    seed.write_bytes(b"AAAA")
    eng = VsamEngine(_cfg(seed))   # default InMemoryBackend
    eng.load_all()
    eng.write("DS", b"ZZZZ", 4, b"ZZZZ")
    # nothing new written anywhere; seed untouched
    assert seed.read_bytes() == b"AAAA"
    assert [f.name for f in tmp_path.iterdir()] == ["seed.dat"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_flush_to_snapshot_in_memory_engine(tmp_path: Path) -> None:
    seed = tmp_path / "seed.dat"
    seed.write_bytes(b"AAAA")
    out = tmp_path / "snap"
    eng = VsamEngine(_cfg(seed))   # in-memory
    eng.load_all()
    eng.write("DS", b"ZZZZ", 4, b"ZZZZ")
    eng.flush_to(out)
    assert read_flat_file(out / "DS.dat", 4) == [b"AAAA", b"ZZZZ"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_engine.py -v -k "write_through or default_engine or flush_to"`
Expected: FAIL — `VsamEngine.__init__()` takes no `backend` kwarg / no `flush_to`.

- [ ] **Step 3: Modify the engine**

In `interpreter/cics/vsam/engine.py`:

(a) Add imports near the top:
```python
from pathlib import Path

from interpreter.cics.vsam.backend import InMemoryBackend, VsamBackend
```

(b) Change `__init__` to accept a backend:
```python
    def __init__(self, config: FctConfig, backend: VsamBackend | None = None) -> None:
        self._config = config
        self._backend: VsamBackend = backend if backend is not None else InMemoryBackend()
        self._datasets: dict[str, VsamDataset] = {}
        self._cursors: dict[_CursorKey, int] = {}
        self._cursor_dir: dict[_CursorKey, str] = {}
```

(c) Replace the body of `load_all` to source records from the backend:
```python
    def load_all(self) -> None:
        """Load all configured datasets via the backend (seed or persisted state)."""
        for name, cfg in self._config.datasets.items():
            ds = VsamDataset(
                record_length=cfg.record_length,
                key_offset=cfg.key_offset,
                key_length=cfg.key_length,
            )
            for record in self._backend.load(name, cfg):
                if len(record) == cfg.record_length:
                    ds.store[record] = record
            self._datasets[name.upper()] = ds
            logger.info("VSAM: loaded %s (%d records)", name, len(ds.store))
```

(d) Add a private write-through helper and call it after each successful mutation:
```python
    def _persist(self, file_name: str) -> None:
        """Write-through the dataset's current records via the backend."""
        canonical = file_name.upper().strip("'\"")
        cfg = self._config.datasets.get(canonical)
        ds = self._datasets.get(canonical)
        if cfg is None or ds is None:
            return
        self._backend.persist(canonical, cfg, list(ds.store.keys()))
```
In `write`, before `return RESP_NORMAL`: `self._persist(file_name)`.
In `rewrite`, after the `del`/re-insert and before `return RESP_NORMAL`: `self._persist(file_name)`.
In `delete`, after the `del` and before `return RESP_NORMAL`: `self._persist(file_name)`.
(Do NOT persist on the NOTFND/DUPREC/DISABLED paths — only after a successful mutation.)

(e) Add `flush_to`:
```python
    def flush_to(self, directory: Path) -> None:
        """Snapshot every dataset's current records to <directory>/<NAME>.dat
        via the raw codec, regardless of the configured backend."""
        from interpreter.cics.vsam.format import write_flat_file

        for name, ds in self._datasets.items():
            cfg = self._config.datasets.get(name)
            if cfg is None:
                continue
            write_flat_file(
                Path(directory) / f"{name}.dat",
                list(ds.store.keys()),
                cfg.record_length,
            )
```

- [ ] **Step 4: Run tests to verify they pass + no regressions**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_engine.py tests/unit/cics/test_vsam_builtins.py tests/integration/cics/test_vsam_browse.py tests/integration/cics/test_vsam_roundtrip.py -v`
Expected: PASS (new tests + all existing VSAM tests; default path unchanged).

- [ ] **Step 5: Format, lint, full suite, commit**

```bash
poetry run python -m black interpreter/cics/vsam/engine.py tests/unit/cics/test_vsam_engine.py
poetry run lint-imports
poetry run python -m pytest -x -q
git add interpreter/cics/vsam/engine.py tests/unit/cics/test_vsam_engine.py
git commit -m "feat(vsam): configurable backend + write-through + flush_to in VsamEngine"
```

---

### Task 4: Gated demo — real CardDemo REWRITE + WRITE persist to a flat file

**Files:**
- Create: `tests/integration/cics/test_vsam_persistence.py`

**Context:** Reuse the durable real-CardDemo harness in `tests/integration/cics/test_carddemo_signon_real.py` — the `_usrsec_engine()`-style four-dataset seeding (`_xref_record`/`_acct_record`/`_cust_record` + USRSEC), `generate_symbolic_copybooks` stage-0, `ProLeapCobolParser(... copybook_dirs=[sym_dir, cpy, cpy-bms, _CICS_COPYBOOKS])`, `CicsLoweringStrategy`, `compile_cics_program`, and the `CicsRegion` driving (the account-UPDATE REWRITE flow and the transaction-ADD WRITE flow already pass there). The ONLY change for this demo: construct the engine with a `FileBackend(tmp_path/"store")` instead of the default, run the flow, then read the backing flat file with the codec and assert the mutation persisted.

- [ ] **Step 1: Write the gated demo test**

```python
# tests/integration/cics/test_vsam_persistence.py
"""Gated demo: a real CardDemo REWRITE/WRITE turn persists to the VSAM flat file.

Reuses the durable signon-real harness; the only difference is a FileBackend so
mutations write through to <tmp>/store/<NAME>.dat, which we then read back with
the raw codec and assert the change is on disk. Gated on CARDDEMO_HOME +
BMS_TOOLS_HOME (built hlasm_export) + ProLeap JAR, like the other real flows.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from interpreter.cics.vsam.backend import FileBackend
from interpreter.cics.vsam.format import read_flat_file
from tests.covers import covers, NotLanguageFeature
from tests.integration.cics.bms_tools_helpers import BMS_TOOLS_AVAILABLE
from tests.integration.cobol_helpers import JAR_AVAILABLE

_CARDDEMO_HOME = os.environ.get("CARDDEMO_HOME")

pytestmark = pytest.mark.skipif(
    not _CARDDEMO_HOME or not JAR_AVAILABLE or not BMS_TOOLS_AVAILABLE,
    reason="manual: set CARDDEMO_HOME + BMS_TOOLS_HOME (built hlasm_export) + ProLeap JAR",
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_account_update_rewrite_persists_to_flat_file(tmp_path: Path) -> None:
    # IMPLEMENTER: build the same region setup the account-UPDATE REWRITE test in
    # test_carddemo_signon_real.py uses, but construct the VsamEngine with a
    # FileBackend over `backing`:
    #     backing = tmp_path / "store"
    #     engine = VsamEngine(fct_config, backend=FileBackend(backing))
    #     engine.load_all()
    # Drive the update flow that changes ACCT-ACTIVE-STATUS 'Y' -> 'N' and REWRITEs
    # (the existing test_real_carddemo_account_update_rewrite path), then:
    backing = tmp_path / "store"
    acct_records = read_flat_file(backing / "ACCTDAT.dat", 300)
    # ACCT-ID 9(11) @ offset 0; ACCT-ACTIVE-STATUS X(1) @ offset 11.
    target = next(r for r in acct_records if r[0:11] == "00000000011".encode("cp037"))
    assert target[11:12] == "N".encode("cp037"), "REWRITE not persisted to flat file"
```

> **Implementer note:** Factor the shared region/engine setup out of `test_carddemo_signon_real.py` (or import its helpers) rather than copy-paste; the only delta is the `backend=FileBackend(backing)` argument to `VsamEngine`. Add a second test asserting the transaction-ADD **WRITE** persisted: after the add-transaction flow, `read_flat_file(backing / "TRANSACT.dat", <reclen>)` contains the new record (match on the generated TRAN-ID / the seeded fields). Use the record lengths/offsets already defined in the durable test's seed helpers.

- [ ] **Step 2: Run gated (with env)**

Run: `BMS_TOOLS_HOME=~/code/bms-tools CARDDEMO_HOME=/Users/asgupta/code/aws-mainframe-carddemo/app poetry run python -m pytest tests/integration/cics/test_vsam_persistence.py -v`
Expected: PASS — the REWRITE/WRITE mutations are present in the backing flat files. (Without the env it SKIPS — that's fine in CI.)

- [ ] **Step 3: Run full suite (env unset → demo skips)**

Run: `poetry run python -m pytest -x -q`
Expected: PASS; the new demo skips without the env.

- [ ] **Step 4: Format, lint, commit**

```bash
poetry run python -m black tests/integration/cics/test_vsam_persistence.py
poetry run lint-imports
git add tests/integration/cics/test_vsam_persistence.py
git commit -m "test(cics): gated demo — real REWRITE/WRITE persists to the VSAM flat file"
```

---

## Self-review

**Spec coverage:**
- Configurable backend (in-memory default / file-backed) → Task 2 (backends) + Task 3 (engine `backend=` param) ✓
- Write-through every mutating op → Task 3 (`_persist` after write/rewrite/delete success) ✓
- `flush_to(dir)` snapshot regardless of backend → Task 3 ✓
- Raw flat-record format, round-trips with load → Task 1 codec; `load_all` uses it via backend ✓
- Atomic write / length validation / missing-file handling → Task 1 ✓
- Seeds never overwritten (backing dir separate) → Task 2 `FileBackend` ✓
- Zero behavior change on default path → Task 3 `test_default_engine_writes_no_files` + InMemoryBackend no-op persist ✓
- Demo: real REWRITE + WRITE → flat file, read back, assert → Task 4 ✓
- Dump CLI OUT OF SCOPE → not in any task (deferred, Beads issue filed) ✓

**Placeholder scan:** Task 4's body has an implementer note (factor/reuse the durable harness) rather than a full copy of the multi-turn driving — intentional (the flow is large and already exists/tested in `test_carddemo_signon_real.py`); the assertion code (read_flat_file + offset decode) is concrete. All other tasks have complete code.

**Type consistency:** `VsamBackend.load(name, cfg) -> list[bytes]` and `persist(name, cfg, records)` are used identically in Task 2 (defs), Task 3 (`load_all` calls `backend.load(name, cfg)`, `_persist` calls `backend.persist(canonical, cfg, list(...))`). `FileBackend(backing_dir)` ctor matches usage in Tasks 2–4. `read_flat_file(path, record_length)` / `write_flat_file(path, records, record_length)` signatures consistent across Tasks 1, 3, 4. `VsamEngine(config, backend=None)` matches Task 3 + 4.
