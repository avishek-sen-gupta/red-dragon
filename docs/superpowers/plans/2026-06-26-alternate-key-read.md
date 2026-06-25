# Alternate-Key Read Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `AlternateKeyDriver` that reads a flat fixed-length dataset by a key it is NOT sorted by (linear scan), plus an `open_alternate_key_driver` factory — unblocking the cicada VsamEngine integration's alternate-key reads (CXACAIX).

**Architecture:** A new `FileOrganizationDriver` implementation in `interpreter/cobol/file_drivers.py` whose `read_key` linearly scans the flat file and returns the first record whose `record[key_offset:key_offset+key_length]` equals the search key. Read-only: every other operation raises (fail loud). `IndexedDriver` (binary search, primary key) is untouched.

**Tech Stack:** Python 3.13, frozen `AccessResult`, pytest, black.

## Global Constraints

- Reuse the existing neutral outcome: `AccessResult` / `AccessCondition` from `interpreter/cobol/access_result.py` — `OK` (with `data=record`) and `NOT_FOUND`. No new conditions.
- Read-only: `read_seq`/`start`/`write`/`rewrite`/`delete` **raise `NotImplementedError`** (fail loud — never a silent no-op or a fabricated status).
- Selection is a **factory function**, NOT a new `FileOrganization` enum value (that enum is COBOL's `ORGANIZATION`; "alternate key" is not a COBOL org).
- Purely additive: `IndexedDriver` and all existing code untouched; the full red-dragon suite stays green.
- FP / imperative shell; no `None` defaults; no defensive guards beyond the explicit fail-loud raises; no regex.
- Tooling: `uv run --no-sync python -m pytest …`; `uv run --no-sync python -m black …` before commit. The repo pre-commit runs the full suite (slow) — let it run.

---

## Task 1: AlternateKeyDriver + open_alternate_key_driver factory

**Files:**
- Modify: `interpreter/cobol/file_drivers.py` (add the class + factory; do not touch `IndexedDriver`/`SequentialDriver`/`RelativeDriver`/`open_driver`)
- Test: `tests/unit/cobol/test_alternate_key_driver.py`

**Interfaces:**
- Consumes: `AccessResult`, `AccessCondition` (`interpreter/cobol/access_result.py`); `OpenMode`, `FileOrganizationDriver` (`interpreter/cobol/file_drivers.py` / `file_enums.py`).
- Produces: `class AlternateKeyDriver` (implements `FileOrganizationDriver`); `def open_alternate_key_driver(path: Path, mode: OpenMode, record_length: int, key_offset: int, key_length: int) -> FileOrganizationDriver` (returns an opened driver).

- [ ] **Step 1: Write the failing tests** — create `tests/unit/cobol/test_alternate_key_driver.py`. (Match the `@covers` import style of `tests/unit/cobol/test_open_driver.py` — same `covers` / `NotLanguageFeature` import it uses.)

```python
from pathlib import Path

import pytest

from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.file_drivers import (
    AlternateKeyDriver,
    open_alternate_key_driver,
)
from interpreter.cobol.file_enums import OpenMode
from tests.covers import covers, NotLanguageFeature


# 8-byte records. Primary key at offset 0 (file IS sorted by it: AAA<BBB<CCC).
# Alternate key at offset 3, length 2 — its values (xz, yw, ab) are NOT in
# sorted order, so only a linear scan (not binary search) can find them.
_RECS = [b"AAAxz123", b"BBByw456", b"CCCab789"]


def _seed(path: Path) -> None:
    path.write_bytes(b"".join(_RECS))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_key_finds_out_of_sort_order_key(tmp_path: Path):
    p = tmp_path / "aix"
    _seed(p)
    drv = open_alternate_key_driver(p, OpenMode.INPUT, 8, 3, 2)
    # "ab" is the alt key of the LAST record, out of alt-key sort order.
    r = drv.read_key(b"ab")
    assert r.condition is AccessCondition.OK
    assert r.data == b"CCCab789"
    drv.close()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_key_finds_middle_record(tmp_path: Path):
    p = tmp_path / "aix"
    _seed(p)
    drv = open_alternate_key_driver(p, OpenMode.INPUT, 8, 3, 2)
    r = drv.read_key(b"yw")
    assert r.condition is AccessCondition.OK
    assert r.data == b"BBByw456"
    drv.close()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_read_key_miss_is_not_found(tmp_path: Path):
    p = tmp_path / "aix"
    _seed(p)
    drv = open_alternate_key_driver(p, OpenMode.INPUT, 8, 3, 2)
    assert drv.read_key(b"zz").condition is AccessCondition.NOT_FOUND
    drv.close()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_factory_returns_opened_alternate_key_driver(tmp_path: Path):
    p = tmp_path / "aix"
    _seed(p)
    drv = open_alternate_key_driver(p, OpenMode.INPUT, 8, 3, 2)
    assert isinstance(drv, AlternateKeyDriver)
    drv.close()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_unsupported_ops_raise(tmp_path: Path):
    p = tmp_path / "aix"
    _seed(p)
    drv = open_alternate_key_driver(p, OpenMode.INPUT, 8, 3, 2)
    with pytest.raises(NotImplementedError):
        drv.read_seq()
    with pytest.raises(NotImplementedError):
        drv.start(b"AA", ">=")
    with pytest.raises(NotImplementedError):
        drv.write(b"AAAxz999")
    with pytest.raises(NotImplementedError):
        drv.rewrite(b"AAAxz999")
    with pytest.raises(NotImplementedError):
        drv.delete()
    drv.close()
```

- [ ] **Step 2: Run → fail.** `uv run --no-sync python -m pytest tests/unit/cobol/test_alternate_key_driver.py -v` → FAIL (`AlternateKeyDriver` / `open_alternate_key_driver` not defined). If the `covers`/`NotLanguageFeature` import paths differ from `test_open_driver.py`, copy that file's exact import lines.

- [ ] **Step 3: Implement.** Append to `interpreter/cobol/file_drivers.py` (after the existing drivers; `Path`, `BinaryIO`, `OpenMode`, `AccessResult`, `AccessCondition`, `FileOrganizationDriver` are already imported at the top of the file):

```python
class AlternateKeyDriver:
    """Read a flat fixed-length dataset by a key it is NOT sorted by, via linear scan.

    Read-only. Used for alternate-key access (e.g. a CICS alternate index flattened
    to a standalone dataset): the search key sits at ``key_offset`` inside each
    record, but the file is sorted by a different (primary) key, so binary search
    cannot apply. Every operation other than ``read_key`` raises.
    """

    def __init__(self) -> None:
        self._fh: BinaryIO | None = None
        self._rl = 0
        self._koff = 0
        self._klen = 0

    def open(
        self,
        path: Path,
        mode: OpenMode,
        record_length: int,
        key_offset: int,
        key_length: int,
    ) -> None:
        self._rl = record_length
        self._koff = key_offset
        self._klen = key_length
        # Read-only by construction; mode is accepted for FileOrganizationDriver
        # uniformity. Write-side verbs raise regardless of mode.
        self._fh = open(path, "rb")

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def read_key(self, key: bytes) -> AccessResult:
        assert self._fh is not None
        self._fh.seek(0)
        while True:
            record = self._fh.read(self._rl)
            if len(record) < self._rl:
                return AccessResult(condition=AccessCondition.NOT_FOUND)
            if record[self._koff : self._koff + self._klen] == key:
                return AccessResult(condition=AccessCondition.OK, data=record)

    def read_seq(self) -> AccessResult:
        raise NotImplementedError("alternate-key datasets are read-only point lookups")

    def start(self, key: bytes, relop: str) -> AccessResult:
        raise NotImplementedError("alternate-key datasets are read-only point lookups")

    def write(self, data: bytes, key: bytes = b"") -> AccessResult:
        raise NotImplementedError("alternate-key datasets are read-only point lookups")

    def rewrite(self, data: bytes, key: bytes = b"") -> AccessResult:
        raise NotImplementedError("alternate-key datasets are read-only point lookups")

    def delete(self, key: bytes = b"") -> AccessResult:
        raise NotImplementedError("alternate-key datasets are read-only point lookups")


def open_alternate_key_driver(
    path: Path,
    mode: OpenMode,
    record_length: int,
    key_offset: int,
    key_length: int,
) -> FileOrganizationDriver:
    """Open an AlternateKeyDriver for read-by-a-non-sort-key (linear scan, read-only)."""
    drv = AlternateKeyDriver()
    drv.open(path, mode, record_length, key_offset, key_length)
    return drv
```

- [ ] **Step 4: Run → pass + full suite (additive proof).**
```bash
uv run --no-sync python -m pytest tests/unit/cobol/test_alternate_key_driver.py -v
PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar" uv run --no-sync python -m pytest -q
```
Expected: the 5 new tests pass AND the full red-dragon suite is green (nothing else changed).

- [ ] **Step 5: Commit** (through the real pre-commit hooks).
```bash
uv run --no-sync python -m black interpreter/cobol/file_drivers.py tests/unit/cobol/test_alternate_key_driver.py
git add interpreter/cobol/file_drivers.py tests/unit/cobol/test_alternate_key_driver.py
git commit -m "feat(cobol): AlternateKeyDriver — read a flat dataset by a non-sort key via linear scan (red-dragon-0wzv)"
```

---

## Self-Review

**Spec coverage:** `read_key` linear scan by key at `key_offset` → Step 3 + `test_read_key_finds_out_of_sort_order_key`/`test_read_key_finds_middle_record` ✓. Miss → `NOT_FOUND` → `test_read_key_miss_is_not_found` ✓. Read-only (unsupported ops raise) → Step 3 raises + `test_unsupported_ops_raise` ✓. Factory (not a new enum value) → `open_alternate_key_driver` + `test_factory_returns_opened_alternate_key_driver` ✓. `IndexedDriver` untouched / additive → only-append instruction + full-suite gate ✓. Reuse `AccessResult`/`AccessCondition` (`OK`/`NOT_FOUND`) → imports + return values ✓.

**Placeholder scan:** none — complete code, exact commands, real test bodies. The one discovery instruction (match `test_open_driver.py`'s `covers` import) is a concrete file reference, not a guess.

**Type consistency:** `AlternateKeyDriver`, `open_alternate_key_driver(path, mode, record_length, key_offset, key_length) -> FileOrganizationDriver`, `AccessResult(condition=…, data=…)`, `AccessCondition.OK`/`.NOT_FOUND` used identically in Step 1 and Step 3.
