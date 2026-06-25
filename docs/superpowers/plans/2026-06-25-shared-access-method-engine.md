# Shared Access-Method Engine — First Piece — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make red-dragon's file drivers return a **neutral** access-method outcome (not COBOL FILE STATUS), refactor the COBOL I/O adapter to translate that outcome → FILE STATUS with *identical* VM-facing behaviour, and route jackal's IDCAMS through the same engine — so the mainframe stack shares one access layer.

**Architecture:** The three existing drivers (PS/KSDS/RRDS) stop baking COBOL FILE STATUS into their results and instead return a neutral `AccessResult{condition, data}`. A small factory selects a driver by organization. `RealFileIOProvider` (the COBOL adapter) maps the neutral `AccessCondition` → FILE STATUS and keeps returning the VM-facing `IOResult` unchanged — so COBOL execution is byte-for-byte identical (the full suite is the guard). Then jackal's IDCAMS (a direct driver consumer in another repo) is updated to the new API after a submodule bump.

**Tech Stack:** Python 3.13, frozen dataclasses, pytest, black. red-dragon (engine + COBOL adapter); jackal (IDCAMS routing, after a submodule bump).

## Global Constraints

- **Behavior-preserving:** no program's output may change. The full red-dragon suite (incl. COBOL file-I/O integration tests) and jackal's suite (incl. the gated CardDemo e2e) are the gate.
- **The neutral core knows NO consumer vocabulary** — `AccessResult`/`AccessCondition` contain **no** FILE STATUS strings and **no** EIBRESP ints. FILE STATUS mapping lives only in the COBOL adapter.
- **`IOResult` stays the VM-facing type** (`status: str`, `data: str | None`) — unchanged. `AccessResult` is the new driver/engine type. The COBOL adapter is the translation boundary.
- **Architecture-neutral Protocol:** `FileOrganizationDriver` dictates *operations*, never file-resident-vs-in-memory (a future cicada in-memory variant must be able to implement it).
- FP / frozen dataclasses; **no `None` defaults; no defensive guards (fail loud); no regex.**
- `AccessResult.data` is **`bytes | None`** (byte-faithful core); the COBOL adapter handles the bytes↔str (latin-1) boundary it relies on today.
- Tooling: `uv run --no-sync python -m pytest …`; `uv run --no-sync python -m black …` before commit. red-dragon's pre-commit runs the full suite — commits will be slow; that is expected and is the guard.

### The canonical neutral mapping (COBOL adapter owns this table)
| `AccessCondition` | FILE STATUS | meaning |
|---|---|---|
| `OK` | `"00"` | success |
| `END_OF_FILE` | `"10"` | AT END (sequential read past last) |
| `DUPLICATE_KEY` | `"22"` | WRITE of an existing key |
| `NOT_FOUND` | `"23"` | keyed read / start / delete: no such record |
| `FILE_NOT_FOUND` | `"35"` | OPEN INPUT of a missing file |
| `NOT_OPEN` | `"47"` | operation on a file that isn't open |
| `WRITE_NOT_PERMITTED` | `"48"` | WRITE in a non-write open mode |

---

## File Structure

- **Create `interpreter/cobol/access_result.py`** — `AccessCondition` (Enum) + `AccessResult` (frozen). The neutral vocabulary. No status strings.
- **Modify `interpreter/cobol/file_drivers.py`** — `FileOrganizationDriver` Protocol + the three drivers return `AccessResult`; add an `open_driver(...)` factory.
- **Modify `interpreter/cobol/real_file_provider.py`** — the COBOL adapter: map `AccessCondition` → FILE STATUS, use the factory, keep returning `IOResult`.
- **(jackal, after bump) Modify `jackal/idcams/executor.py`** — consume the factory + `AccessResult` instead of the drivers' old `IOResult`.

**Cross-repo note:** Tasks 1–4 are red-dragon. Task 5 is jackal, after bumping the red-dragon submodule. cicada/squall are **unaffected** by the bump — they consume COBOL I/O through `RealFileIOProvider`'s unchanged VM-facing `IOResult`, and do not import the drivers directly. Only jackal's IDCAMS imports drivers directly, so only jackal needs updating.

---

## Task 1: Neutral outcome type (`AccessResult` / `AccessCondition`)

**Files:**
- Create: `interpreter/cobol/access_result.py`
- Test: `tests/unit/cobol/test_access_result.py`

**Interfaces:**
- Produces: `class AccessCondition(Enum)` with members `OK, END_OF_FILE, NOT_FOUND, DUPLICATE_KEY, FILE_NOT_FOUND, NOT_OPEN, WRITE_NOT_PERMITTED`; `@dataclass(frozen=True) class AccessResult` with `condition: AccessCondition` and `data: bytes | None = None`.

- [ ] **Step 1: Write the failing test** — `tests/unit/cobol/test_access_result.py`:
```python
from interpreter.cobol.access_result import AccessCondition, AccessResult


def test_access_result_holds_condition_and_bytes():
    r = AccessResult(condition=AccessCondition.OK, data=b"ABC")
    assert r.condition is AccessCondition.OK
    assert r.data == b"ABC"


def test_access_result_data_defaults_none():
    r = AccessResult(condition=AccessCondition.END_OF_FILE)
    assert r.data is None


def test_conditions_present():
    names = {c.name for c in AccessCondition}
    assert names == {
        "OK", "END_OF_FILE", "NOT_FOUND", "DUPLICATE_KEY",
        "FILE_NOT_FOUND", "NOT_OPEN", "WRITE_NOT_PERMITTED",
    }
```

- [ ] **Step 2: Run → fail.** `uv run --no-sync python -m pytest tests/unit/cobol/test_access_result.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement** — `interpreter/cobol/access_result.py`:
```python
"""Neutral access-method outcome — the engine's shared, consumer-agnostic result.

Carries the underlying access-method *condition*, NOT any consumer's status
vocabulary (no COBOL FILE STATUS, no CICS EIBRESP). Each consumer adapter maps
AccessCondition to its own vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AccessCondition(Enum):
    OK = "OK"
    END_OF_FILE = "END_OF_FILE"
    NOT_FOUND = "NOT_FOUND"
    DUPLICATE_KEY = "DUPLICATE_KEY"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    NOT_OPEN = "NOT_OPEN"
    WRITE_NOT_PERMITTED = "WRITE_NOT_PERMITTED"


@dataclass(frozen=True)
class AccessResult:
    condition: AccessCondition
    data: bytes | None = None
```

- [ ] **Step 4: Run → pass.** `uv run --no-sync python -m pytest tests/unit/cobol/test_access_result.py -v` → 3 passed.

- [ ] **Step 5: Commit.**
```bash
uv run --no-sync python -m black interpreter/cobol/access_result.py tests/unit/cobol/test_access_result.py
git add interpreter/cobol/access_result.py tests/unit/cobol/test_access_result.py
git commit -m "feat(cobol): neutral AccessResult/AccessCondition for the shared access engine (red-dragon-mc6u)"
```

---

## Task 2: Drivers return `AccessResult` (the behavior-preserving core refactor)

**Files:**
- Modify: `interpreter/cobol/file_drivers.py`
- Test: locate existing driver unit tests first — `grep -rln "SequentialDriver\|IndexedDriver\|RelativeDriver" tests/` — and update their expectations to `AccessResult`; add the new-behaviour assertions below.

**Interfaces:**
- Consumes: `AccessResult`, `AccessCondition` (Task 1).
- Produces: `FileOrganizationDriver` Protocol methods (`read_seq/read_key/start/write/rewrite/delete`) now return `AccessResult` (was `IOResult`). `open`/`close` unchanged. The three drivers return `AccessResult` with `data: bytes | None`.

**Mapping the drivers' current internal FILE STATUS → condition** (preserve the exact behaviour — same condition wherever a status was returned):
`"00"→OK`, `"10"→END_OF_FILE`, `"22"→DUPLICATE_KEY`, `"23"→NOT_FOUND`, `"48"→WRITE_NOT_PERMITTED`. (The drivers do not emit `35`/`47` — those are adapter-level; see Task 4.)

- [ ] **Step 1: Write/адjust the failing test** — in the driver test module (or create `tests/unit/cobol/test_file_drivers_neutral.py`):
```python
from pathlib import Path

from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.file_drivers import SequentialDriver, IndexedDriver
from interpreter.cobol.file_enums import OpenMode


def test_sequential_read_past_end_is_end_of_file(tmp_path: Path):
    p = tmp_path / "f"
    p.write_bytes(b"AAAAA")  # one 5-byte record
    drv = SequentialDriver()
    drv.open(p, OpenMode.INPUT, 5, 0, 0)
    assert drv.read_seq().condition is AccessCondition.OK
    assert drv.read_seq().condition is AccessCondition.END_OF_FILE
    drv.close()


def test_indexed_read_key_miss_is_not_found(tmp_path: Path):
    p = tmp_path / "k"
    drv = IndexedDriver()
    drv.open(p, OpenMode.OUTPUT, 8, 0, 3)  # 8-byte record, 3-byte key at offset 0
    drv.write(b"AAArec01")
    assert drv.read_key(b"AAA").condition is AccessCondition.OK
    assert drv.read_key(b"ZZZ").condition is AccessCondition.NOT_FOUND
    drv.close()


def test_indexed_duplicate_write_is_duplicate_key(tmp_path: Path):
    p = tmp_path / "k2"
    drv = IndexedDriver()
    drv.open(p, OpenMode.OUTPUT, 8, 0, 3)
    assert drv.write(b"AAArec01").condition is AccessCondition.OK
    assert drv.write(b"AAArec02").condition is AccessCondition.DUPLICATE_KEY
    drv.close()
```

- [ ] **Step 2: Run → fail.** `uv run --no-sync python -m pytest tests/unit/cobol/test_file_drivers_neutral.py -v` → FAIL (`.condition` AttributeError — still `IOResult`).

- [ ] **Step 3: Implement.** In `interpreter/cobol/file_drivers.py`:
  - Replace the `IOResult` import with `from interpreter.cobol.access_result import AccessCondition, AccessResult`.
  - Change the `FileOrganizationDriver` Protocol return types: `read_seq/read_key/start/write/rewrite/delete -> AccessResult`.
  - In each of `SequentialDriver`, `IndexedDriver`, `RelativeDriver`, replace every `return IOResult("XX", data)` with `return AccessResult(condition=<MAP XX>, data=<bytes-or-None>)` using the mapping above. The record bytes that were placed in `IOResult.data` go into `AccessResult.data` as **bytes** (the drivers already read `self._fh.read(...)` as bytes — pass them through unchanged; do NOT decode here).
  - Leave `open`/`close` and all seek/binary-search logic untouched — only the *return type* changes, not the I/O logic. This is what makes it behaviour-preserving.

- [ ] **Step 4: Run → pass (driver tests).** `uv run --no-sync python -m pytest tests/unit/cobol/test_file_drivers_neutral.py -v` → 3 passed. (The COBOL integration suite will be red until Task 4 — that is expected; do not run the full suite as the gate for this task.)

- [ ] **Step 5: Commit.**
```bash
uv run --no-sync python -m black interpreter/cobol/file_drivers.py tests/unit/cobol/test_file_drivers_neutral.py
git add interpreter/cobol/file_drivers.py tests/unit/cobol/test_file_drivers_neutral.py
# (+ any existing driver test file you updated)
git commit -m "refactor(cobol): drivers return neutral AccessResult, not COBOL FILE STATUS (red-dragon-mc6u)"
```

---

## Task 3: `open_driver` factory (org → driver, one door)

**Files:**
- Modify: `interpreter/cobol/file_drivers.py`
- Test: `tests/unit/cobol/test_open_driver.py`

**Interfaces:**
- Consumes: the three drivers; `FileOrganization` (`interpreter/cobol/file_enums.py`), `OpenMode`.
- Produces: `def open_driver(org: FileOrganization, path: Path, mode: OpenMode, record_length: int, key_offset: int, key_length: int) -> FileOrganizationDriver` — returns an **opened** driver chosen by organization.

- [ ] **Step 1: Write the failing test** — `tests/unit/cobol/test_open_driver.py`:
```python
from pathlib import Path

from interpreter.cobol.file_drivers import (
    open_driver, SequentialDriver, IndexedDriver, RelativeDriver,
)
from interpreter.cobol.file_enums import FileOrganization, OpenMode


def test_open_driver_selects_by_org(tmp_path: Path):
    seq = open_driver(FileOrganization.SEQUENTIAL, tmp_path / "s", OpenMode.OUTPUT, 5, 0, 0)
    idx = open_driver(FileOrganization.INDEXED, tmp_path / "i", OpenMode.OUTPUT, 8, 0, 3)
    rel = open_driver(FileOrganization.RELATIVE, tmp_path / "r", OpenMode.OUTPUT, 8, 0, 0)
    assert isinstance(seq, SequentialDriver)
    assert isinstance(idx, IndexedDriver)
    assert isinstance(rel, RelativeDriver)
    for d in (seq, idx, rel):
        d.close()
```

- [ ] **Step 2: Run → fail.** `uv run --no-sync python -m pytest tests/unit/cobol/test_open_driver.py -v` → FAIL (`open_driver` undefined).

- [ ] **Step 3: Implement** — add to `interpreter/cobol/file_drivers.py` (import `FileOrganization` from `file_enums`):
```python
def open_driver(
    org: FileOrganization,
    path: Path,
    mode: OpenMode,
    record_length: int,
    key_offset: int,
    key_length: int,
) -> FileOrganizationDriver:
    """Select and open the driver for a file organization. The one door
    every consumer (COBOL adapter, IDCAMS, …) uses to reach a dataset."""
    if org == FileOrganization.INDEXED:
        drv: FileOrganizationDriver = IndexedDriver()
    elif org == FileOrganization.RELATIVE:
        drv = RelativeDriver()
    else:
        drv = SequentialDriver()
    drv.open(path, mode, record_length, key_offset, key_length)
    return drv
```

- [ ] **Step 4: Run → pass.** `uv run --no-sync python -m pytest tests/unit/cobol/test_open_driver.py -v` → 1 passed.

- [ ] **Step 5: Commit.**
```bash
uv run --no-sync python -m black interpreter/cobol/file_drivers.py tests/unit/cobol/test_open_driver.py
git add interpreter/cobol/file_drivers.py tests/unit/cobol/test_open_driver.py
git commit -m "feat(cobol): open_driver factory — select driver by organization (red-dragon-mc6u)"
```

---

## Task 4: COBOL adapter translates neutral → FILE STATUS (behaviour-preserving)

**Files:**
- Modify: `interpreter/cobol/real_file_provider.py`
- Test: the **full red-dragon suite** is the guard (COBOL file-I/O integration tests). Add one focused mapping unit test.

**Interfaces:**
- Consumes: `AccessResult`/`AccessCondition` (Task 1), `open_driver` (Task 3).
- Produces: `RealFileIOProvider` methods still return `IOResult` to the VM; internally they call drivers (which now return `AccessResult`) and map `AccessCondition → FILE STATUS`.

- [ ] **Step 1: Write the failing mapping test** — `tests/unit/cobol/test_file_status_mapping.py`:
```python
from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.real_file_provider import _file_status  # the mapping fn (Task 4)


def test_condition_to_file_status():
    assert _file_status(AccessCondition.OK) == "00"
    assert _file_status(AccessCondition.END_OF_FILE) == "10"
    assert _file_status(AccessCondition.DUPLICATE_KEY) == "22"
    assert _file_status(AccessCondition.NOT_FOUND) == "23"
    assert _file_status(AccessCondition.FILE_NOT_FOUND) == "35"
    assert _file_status(AccessCondition.NOT_OPEN) == "47"
    assert _file_status(AccessCondition.WRITE_NOT_PERMITTED) == "48"
```

- [ ] **Step 2: Run → fail.** `uv run --no-sync python -m pytest tests/unit/cobol/test_file_status_mapping.py -v` → FAIL (`_file_status` undefined).

- [ ] **Step 3: Implement.** In `interpreter/cobol/real_file_provider.py`:
  - Add the mapping table + function:
```python
from interpreter.cobol.access_result import AccessCondition, AccessResult

_FILE_STATUS: dict[AccessCondition, str] = {
    AccessCondition.OK: "00",
    AccessCondition.END_OF_FILE: "10",
    AccessCondition.DUPLICATE_KEY: "22",
    AccessCondition.NOT_FOUND: "23",
    AccessCondition.FILE_NOT_FOUND: "35",
    AccessCondition.NOT_OPEN: "47",
    AccessCondition.WRITE_NOT_PERMITTED: "48",
}


def _file_status(condition: AccessCondition) -> str:
    return _FILE_STATUS[condition]


def _to_ioresult(result: AccessResult) -> IOResult:
    # Bytes→str at the VM boundary, exactly as before (latin-1, byte-faithful).
    data = result.data.decode("latin-1") if result.data is not None else None
    return IOResult(_file_status(result.condition), data)
```
  - Replace the inline driver selection (the `if org == INDEXED … else SequentialDriver()` block) with `drv = open_driver(org, path, open_mode, record_length, key_offset, key_length)` and drop the now-duplicated `drv.open(...)` call.
  - In each record method (`_read_record`, `_write_record`, `_rewrite_record`, `_start_file`, `_delete_record`): the driver now returns `AccessResult`; wrap it with `_to_ioresult(...)` before returning. The methods' own pre-checks that already build `IOResult` directly — the missing-driver `IOResult("47", None)` and OPEN's `IOResult("35", None)`/`IOResult("00", None)` — convert to building from a condition: `_to_ioresult(AccessResult(AccessCondition.NOT_OPEN))`, `…FILE_NOT_FOUND`, `…OK`. (Keep behaviour identical; just express the status via the condition table so there is one source of truth.)
  - Encode keys/data to bytes for the driver exactly as today (`key.encode("latin-1")`, `data.encode("latin-1")`).

- [ ] **Step 4: Run → pass + the full behaviour guard.**
```bash
uv run --no-sync python -m pytest tests/unit/cobol/test_file_status_mapping.py -v
PROLEAP_BRIDGE_JAR="$(pwd)/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar" uv run --no-sync python -m pytest -q
```
Expected: the mapping test passes AND the **entire red-dragon suite is green** — this is the proof the refactor changed nothing observable. Investigate any diff against prior behaviour as a mapping bug; do NOT weaken a test.

- [ ] **Step 5: Commit** (through the real pre-commit hooks — the full suite runs).
```bash
uv run --no-sync python -m black interpreter/cobol/real_file_provider.py tests/unit/cobol/test_file_status_mapping.py
git add interpreter/cobol/real_file_provider.py tests/unit/cobol/test_file_status_mapping.py
git commit -m "refactor(cobol): COBOL adapter maps neutral AccessCondition -> FILE STATUS (red-dragon-mc6u)"
```

---

## Task 5: Route jackal IDCAMS through the engine (cross-repo, after submodule bump)

**Repo:** jackal (`~/code/jackal`). This task is done **after** Tasks 1–4 are merged to red-dragon `main`, by bumping jackal's vendored red-dragon submodule. The bump is a breaking change for jackal's IDCAMS (the drivers no longer return `IOResult`), so the bump and the IDCAMS update land together.

**Files:**
- Modify: `jackal/idcams/executor.py`
- Bump: `vendor/red-dragon` → the commit containing Tasks 1–4.

**Interfaces:**
- Consumes: `open_driver` + `AccessResult`/`AccessCondition` from red-dragon (`interpreter.cobol.file_drivers` / `interpreter.cobol.access_result`).
- The IDCAMS REPRO currently does `in_drv = SequentialDriver(); in_drv.open(...)`, loops on `result.status == "10"`, reads `result.data`; and `out_drv = IndexedDriver()`. Update to: build drivers via `open_driver(...)`, loop while `result.condition is not AccessCondition.END_OF_FILE`, and write `result.data` (already bytes — drop the `.encode("latin-1")` since `AccessResult.data` is bytes).

- [ ] **Step 1: Bump the submodule.**
```bash
cd ~/code/jackal/vendor/red-dragon && git fetch origin && git checkout <red-dragon main SHA with Tasks 1-4> && cd -
git add vendor/red-dragon
./build.sh   # rebuild the bridge JARs against the bumped engine
```

- [ ] **Step 2: Run the IDCAMS executor test to see it fail against the new API.**
```bash
export PROLEAP_BRIDGE_JAR="$(pwd)/vendor/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar"
export JCL_BRIDGE_JAR="$(pwd)/jcl-bridge/target/jcl-bridge-0.1.0-shaded.jar"
export CARDDEMO_HOME="$HOME/code/aws-mainframe-carddemo/app"
uv run --no-sync python -m pytest tests/unit/test_idcams_executor.py -v
```
Expected: FAIL — `result.status` / `IOResult` no longer exist; the drivers return `AccessResult`.

- [ ] **Step 3: Update `jackal/idcams/executor.py`.** In `_handle_repro`:
  - Import: `from interpreter.cobol.file_drivers import open_driver` and `from interpreter.cobol.access_result import AccessCondition`; drop the direct `SequentialDriver`/`IndexedDriver` imports if now unused.
  - Build the input driver: `in_drv = open_driver(FileOrganization.SEQUENTIAL, in_ds.path, OpenMode.INPUT, record_size, 0, 0)` and the output: `out_drv = open_driver(FileOrganization.INDEXED, out_ds.path, OpenMode.OUTPUT, record_size, out_ds.key_offset, out_ds.key_length)` (import `FileOrganization`/`OpenMode` from `interpreter.cobol.file_enums`).
  - Replace the read loop:
```python
    while True:
        result = in_drv.read_seq()
        if result.condition is AccessCondition.END_OF_FILE:
            break
        if result.data is None:
            raise ValueError("driver returned non-EOF with no data")
        out_drv.write(result.data)  # already bytes — no .encode()
```

- [ ] **Step 4: Run → pass + full jackal suite + the gated e2e.**
```bash
uv run --no-sync python -m pytest tests/unit/test_idcams_executor.py -v
uv run --no-sync python -m pytest -q   # full jackal suite incl. CardDemo e2e (env vars exported)
```
Expected: green — IDCAMS REPRO produces byte-identical output through the engine; the CardDemo e2e (ACCTFILE→READACCT, which exercises REPRO PS→KSDS) passes unchanged.

- [ ] **Step 5: Commit** (through jackal's real pre-commit hooks; export the JAR env vars first).
```bash
git add vendor/red-dragon jackal/idcams/executor.py
git commit -m "refactor(idcams): route REPRO through the shared engine (open_driver + AccessResult); bump red-dragon (red-dragon-mc6u)"
```

---

## Self-Review

**Spec coverage:**
- Neutral `AccessResult`/`AccessCondition` (no consumer vocabulary) → Task 1 ✓
- Architecture-neutral `FileOrganizationDriver` returning neutral results, over PS/KSDS/RRDS → Task 2 ✓
- Factory (org → driver) → Task 3 ✓
- COBOL adapter maps neutral → FILE STATUS, VM-facing `IOResult` unchanged, behaviour-preserving (full suite guard) → Task 4 ✓
- Route jackal IDCAMS through the engine after a submodule bump (jackal suite + CardDemo e2e guard) → Task 5 ✓
- `IOResult` stays VM-facing; `AccessResult` is the engine type (the deferred "replace vs beside" decision, resolved: *beside*, adapter is the boundary) → Tasks 1/2/4 ✓
- Deferred items (tracing, fidelity-hardening, cicada merge, jackal catalog, ESDS/AIX/PDS) → not in any task ✓

**Placeholder scan:** No TBD/"handle edge cases"/"similar to". The one discovery step (locating existing driver tests in Task 2) is an explicit `grep`, not a guess. The Task-5 submodule SHA is a real value the executor fills at bump time (it cannot be known before Tasks 1–4 merge) — flagged as `<red-dragon main SHA with Tasks 1-4>`.

**Type consistency:** `AccessCondition` members and the `_FILE_STATUS` table agree (7 conditions, 7 codes — 00/10/22/23/35/47/48). `AccessResult.data: bytes | None` flows drivers→adapter→`IOResult` (str via latin-1) and drivers→IDCAMS (bytes, no encode). `open_driver(org, path, mode, record_length, key_offset, key_length) -> FileOrganizationDriver` is used identically in Task 4 and Task 5.
