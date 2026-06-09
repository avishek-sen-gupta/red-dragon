# VSAM File Persistence — Design

**Date:** 2026-06-09
**Status:** Approved (design); pending implementation plan
**Scope:** `interpreter/cics/vsam/` only. No core-VM edits. Engine stays a pure bytes/int API.

## Goal

Let the in-memory VSAM engine persist its state to disk: a **configurable backend** chosen at engine instantiation — **in-memory** (default, unchanged) or **file-backed write-through** (every mutating operation persists) — plus an explicit `flush_to(dir)` snapshot. The on-disk format is the **raw fixed-length-record flat image** the engine's `load_all` already reads, so it round-trips losslessly and a flushed file is itself a valid seed.

## Background

`interpreter/cics/vsam/engine.py` is an in-memory VSAM KSDS engine: one `SortedDict` (full-record-bytes → record-bytes) per dataset. `load_all()` reads each `DatasetConfig.path` once as a flat file (`read_bytes()`, split into `record_length` chunks). `write`/`rewrite`/`delete` mutate the `SortedDict` only — **nothing is written back to disk**, so mutations live only for the engine instance's lifetime. The CardDemo update (REWRITE) and create (WRITE) flows therefore persist only in memory.

A real VSAM KSDS on z/OS is a proprietary block structure (Control Intervals/Areas + a separate index component) — NOT concatenated records. We model the **logical** KSDS (keyed record access), not VSAM's physical layout. The flat fixed-length-record image used here is the same shape `IDCAMS REPRO` produces when copying a fixed-length KSDS to a sequential dataset, and the same format the engine's seeds already use.

## Architecture

A small `VsamBackend` seam owns persistence. The engine keeps its in-memory `SortedDict` as the working set (reads stay in memory) and delegates **load** (seed/restore) and **persist** (durable write) to the backend. A single raw-format codec is shared by the backends and `flush_to`. This mirrors the recently-extracted terminal-channel protocol: an explicit, swappable boundary with `queue.Queue`-style default behavior preserved.

## Components

### 1. `interpreter/cics/vsam/format.py` — raw-format codec
The single source of the on-disk format (factored out of `load_all` + its inverse):
- `read_flat_file(path: Path, record_length: int) -> list[bytes]` — read the file, split into `record_length`-byte records. Raise `ValueError` if the file size is not a multiple of `record_length` (corrupt/wrong-length). Missing file → `[]`.
- `write_flat_file(path: Path, records: Iterable[bytes], record_length: int) -> None` — concatenate the records (each validated to be exactly `record_length` bytes; raise on mismatch) and write atomically (write to a temp file in the same dir, then `os.replace`) so a crash mid-write can't truncate the dataset.

### 2. `interpreter/cics/vsam/backend.py` — backend protocol + implementations
```python
class VsamBackend(Protocol):
    def load(self, name: str, cfg: DatasetConfig) -> list[bytes]: ...
    def persist(self, name: str, cfg: DatasetConfig, records: list[bytes]) -> None: ...
```
- `InMemoryBackend` (default): `load` reads the seed `cfg.path` via the codec (current behavior); `persist` is a no-op. Pure in-memory — existing flows/tests unchanged.
- `FileBackend(backing_dir: Path)`: `load` reads `<backing_dir>/<NAME>.dat` via the codec if it exists, else falls back to seeding from `cfg.path` (first run); `persist` writes `<backing_dir>/<NAME>.dat` via the codec. The durable copy is kept **separate from the read-only seeds** (`backing_dir`, not `cfg.path`), so seeds are never overwritten.

`name` is the dataset name; records are passed in key (SortedDict) order so the on-disk image is deterministic/diffable.

### 3. `interpreter/cics/vsam/engine.py` — wire the backend in
- `VsamEngine(config: FctConfig, backend: VsamBackend | None = None)` — default `InMemoryBackend()`.
- `load_all()` populates each dataset's `SortedDict` from `backend.load(name, cfg)` (instead of inlining the file read).
- `write` / `rewrite` / `delete` — after the in-memory mutation succeeds (RESP_NORMAL), call `self._backend.persist(name, cfg, list(ds.store.keys()))`. No-op for `InMemoryBackend`; write-through for `FileBackend`. Browse ops (STARTBR/READNEXT/READPREV/ENDBR) and READ don't mutate → no persist.
- `flush_to(dir: Path) -> None` — explicit snapshot: write every dataset's current `SortedDict` to `<dir>/<NAME>.dat` via the codec, **regardless of backend**. Covers the "flush to a temp file" use case independent of write-through.

### 4. (Demo / in-test inspection)
No production CLI in this project. The demo test proves persistence by reading the flat file back with the codec and asserting on it (see Testing).

## Data flow

- **First run, FileBackend:** `load_all` → `FileBackend.load` finds no `<NAME>.dat` → seeds from `cfg.path` → memory. A turn does REWRITE/WRITE → memory mutated → `persist` rewrites `<NAME>.dat`.
- **Restart, FileBackend:** `load_all` → `FileBackend.load` reads `<NAME>.dat` (the persisted state, not the seed). State survives the engine instance.
- **Snapshot (any backend):** `flush_to(tmp)` writes current memory to `<tmp>/<NAME>.dat`.

## Error handling
- File size not a multiple of `record_length` → `ValueError` (loud; corrupt/wrong-length), not a silent partial read.
- Records of the wrong byte length passed to `write_flat_file` → `ValueError`.
- Missing backing file on `FileBackend.load` → seed from `cfg.path`; missing seed too → empty dataset.
- Persist I/O failure → propagate (no silent swallow). Atomic write (temp + `os.replace`) prevents truncated datasets.

## Testing
- **Unit (`tests/unit/cics/`):**
  - codec round-trip: `write_flat_file` then `read_flat_file` returns the same records; size-mismatch raises; wrong-length record raises; missing file → `[]`.
  - `FileBackend`: load from `<dir>/<NAME>.dat`; first-run seed fallback to `cfg.path`; persist writes the expected bytes; `InMemoryBackend.persist` is a no-op.
  - engine write-through: a `VsamEngine(config, FileBackend(dir))` after `write`/`rewrite`/`delete` leaves `<NAME>.dat` reflecting the change; a **fresh** engine over the same `dir` loads the mutated state (persistence survives the instance).
  - `flush_to`: in-memory engine, mutate, `flush_to(tmp)`, read back → mutation present.
  - default path unchanged: `VsamEngine(config)` behaves exactly as today (InMemoryBackend, no files written).
- **Demo (gated, `tests/integration/cics/`):** drive one real CardDemo **update (REWRITE)** and one **create (WRITE)** via `CicsRegion` with a `FileBackend` (or `flush_to`) into a temp dir; then `read_flat_file` the relevant dataset and assert the mutated/new record is present (decode the changed field in-test to confirm). Gated on `CARDDEMO_HOME` + `BMS_TOOLS_HOME` like the other real flows.

## Out of scope (deferred — own brainstorm + spec later)
- **The dump / inspect CLI** (copybook-driven field decode, output format, copybook resolution). Tracked as a Beads follow-up; to be brainstormed heavily when picked up. The raw flat file is not plain-text readable (EBCDIC + binary fields); in-test inspection (codec read-back + field decode) suffices for this project.

## Constraints
- All changes in `interpreter/cics/vsam/` (+ tests). No edits to `interpreter/vm/**`, `ir.py`, `run.py`, `executor.py`, `cfg.py`.
- Engine remains pure bytes/int (no CICS/VM coupling); the backend is the only new dependency and stays filesystem-only.
- Zero behavior change for the default in-memory path — existing CICS flows and tests untouched.
