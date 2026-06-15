# COBOL File I/O — Design Spec

**Date:** 2026-06-16
**Status:** Approved (design); pending implementation plan
**Scope:** All three COBOL file organizations (SEQUENTIAL, INDEXED, RELATIVE) with real on-disk I/O, conditional clause execution (AT END / INVALID KEY), FILE STATUS write-back, and OPEN multi-mode fix. Verified against the NIST-85 SQ/IX/RL test suite (282 programs).

---

## Background

The COBOL I/O stack has a complete verb layer — OPEN/CLOSE/READ/WRITE/REWRITE/START/DELETE — all lowered to `__cobol_*` CALL_FUNCTION calls dispatched to a pluggable `CobolIOProvider`. The existing implementations (`NullIOProvider`, `StubIOProvider`) cover symbolic execution and in-memory testing.

Four concrete gaps block real-program execution:

1. **No real file access** — no provider reads or writes actual disk files.
2. **Conditional clauses unimplemented** — AT END / NOT AT END / INVALID KEY / NOT INVALID KEY are not serialized by the bridge, not present in statement dataclasses, and not lowered to branches.
3. **FILE STATUS not tracked** — `SELECT ... FILE STATUS IS ws-var` in the ENVIRONMENT DIVISION is not serialized or written after I/O operations.
4. **OPEN multi-mode bug** — `OPEN INPUT f1 OUTPUT f2` flattens all files into one list with the last-seen mode winning.
5. **File section has no runtime region** — `MaterialisedSectionedLayout` has no `.file` entry; FD record fields cannot be accessed after a READ.

---

## Enums

New file `interpreter/cobol/file_enums.py`. All use `str` mixin so they construct directly from bridge JSON strings.

```python
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

---

## IOResult

`IOResult` replaces the raw string / `UNCOMPUTABLE` return contract for all provider methods.

```python
@dataclass(frozen=True)
class IOResult:
    status: str        # COBOL file status code
    data: str | None   # populated on successful READ; None for all other verbs
```

Standard status codes used throughout:

| Code | Meaning |
|------|---------|
| `"00"` | Success |
| `"10"` | AT END (sequential read exhausted) |
| `"22"` | Duplicate key on WRITE |
| `"23"` | Key not found (random access READ / DELETE / START) |
| `"35"` | File not found on OPEN |
| `"47"` | READ attempted on file not open INPUT or I-O |

`UNCOMPUTABLE` is retained for `NullIOProvider` (symbolic execution) — `_read_record` on `NullIOProvider` returns `UNCOMPUTABLE` since there is no data to return. All other provider abstract methods return `IOResult`.

Two thin helper builtins registered in `builtins.py`:

```python
"__cobol_io_status": lambda r, _vm: r.status if isinstance(r, IOResult) else UNCOMPUTABLE
"__cobol_io_data":   lambda r, _vm: r.data or "" if isinstance(r, IOResult) else UNCOMPUTABLE
```

---

## File Section Runtime Region

`MaterialisedSectionedLayout` gains a `file: tuple[DataLayout, Register]` field alongside the existing three sections. At program initialisation, an `ALLOC_REGION` is emitted for the file section if `SectionedLayout.file` is non-empty, exactly as for working-storage.

`resolve()` gains a fourth lookup tier — file section at lowest precedence (after linkage) — so working-storage fields shadow FD fields of the same name if they collide.

When `lower_read` processes a successful `IOResult`, it writes `data` as a raw byte string into the file region at offset 0 (the record root), making all FD sub-fields readable by their byte offsets. The existing `INTO` path then copies from the file region to the working-storage target.

---

## Bridge Changes (`StatementSerializer.java`, `AsgSerializer.java`)

### AT END / INVALID KEY phrase serialization

Each I/O statement gets its conditional phrases serialized using the same pattern as `SEARCH ... AT END`. Coverage per verb:

| Verb | `at_end` | `not_at_end` | `invalid_key` | `not_invalid_key` |
|------|:---:|:---:|:---:|:---:|
| READ | ✓ | ✓ | ✓ | ✓ |
| WRITE | — | — | ✓ | ✓ |
| REWRITE | — | — | ✓ | ✓ |
| START | — | — | ✓ | ✓ |
| DELETE | — | — | ✓ | ✓ |

`serializeRead` also captures the KEY IS clause (`stmt.getKey()`) as `"key"` — needed for random-access READ on INDEXED/RELATIVE files.

### OPEN multi-mode fix

Replace the single flat `mode` + `files` serialization with a `mode_groups` array:

```json
{ "type": "OPEN", "mode_groups": [
    { "mode": "INPUT",  "files": ["CUSTOMER-FILE"] },
    { "mode": "OUTPUT", "files": ["REPORT-FILE"]   }
]}
```

### FILE-CONTROL serialization

New method in `AsgSerializer.java` serializes `ENVIRONMENT DIVISION / INPUT-OUTPUT SECTION / FILE-CONTROL` entries via ProLeap's `getFileControlEntries()`. Each entry:

```json
{ "file_name": "CUSTOMER-FILE",
  "assign_to": "custfile.dat",
  "organization": "INDEXED",
  "access_mode": "DYNAMIC",
  "record_key": "CUST-ID",
  "relative_key": "",
  "file_status_var": "WS-CUST-STATUS"
}
```

Fields `record_key` (from `getRecordKeyClause().getRecordKeyCall()`), `relative_key` (from `getRelativeKeyClause().getRelativeKeyCall()`), and `file_status_var` are omitted if absent. Result lands in `asg["file_control"]` as a JSON array.

---

## Statement Layer (`cobol_statements.py`, `asg_types.py`)

### Conditional clause fields

`ReadStatement`, `WriteStatement`, `RewriteStatement`, `StartStatement`, `DeleteStatement` each gain the applicable fields (same `list[CobolStatementType]` pattern as `SearchStatement.at_end`). `ReadStatement` also gains `key: str = ""`.

```python
@dataclass(frozen=True)
class ReadStatement:
    file_name: str = ""
    into: str = ""
    key: str = ""
    at_end:          list[CobolStatementType] = field(default_factory=list)
    not_at_end:      list[CobolStatementType] = field(default_factory=list)
    invalid_key:     list[CobolStatementType] = field(default_factory=list)
    not_invalid_key: list[CobolStatementType] = field(default_factory=list)
```

`from_dict` / `to_dict` follow the `SearchStatement` pattern — omit empty lists.

### OPEN multi-mode

`OpenStatement.mode: str` and `OpenStatement.files: list[str]` become `mode_groups: list[tuple[OpenMode, list[str]]]`.

### FileControlEntry and CobolASG

```python
@dataclass(frozen=True)
class FileControlEntry:
    file_name: str
    assign_to: str = ""
    organization: FileOrganization = FileOrganization.SEQUENTIAL
    access_mode: AccessMode = AccessMode.SEQUENTIAL
    record_key: str = ""
    relative_key: str = ""
    file_status_var: str = ""
```

`CobolASG` gains `file_control: list[FileControlEntry] = field(default_factory=list)`, deserialized from `asg["file_control"]`.

---

## File Organization Drivers (`interpreter/cobol/file_drivers.py`)

All three organizations use flat fixed-length record files. The difference is the access pattern.

### Protocol

```python
class FileOrganizationDriver(Protocol):
    def open(self, path: Path, mode: OpenMode, record_length: int,
             key_offset: int, key_length: int) -> None: ...
    def close(self) -> None: ...
    def read_seq(self) -> IOResult: ...
    def read_key(self, key: bytes) -> IOResult: ...
    def start(self, key: bytes, relop: str) -> IOResult: ...
    def write(self, data: bytes) -> IOResult: ...
    def rewrite(self, data: bytes) -> IOResult: ...
    def delete(self) -> IOResult: ...
```

### SequentialDriver

Plain flat file of concatenated fixed-length records.

- `read_seq`: reads `record_length` bytes; EOF → `IOResult("10", None)`.
- `write`: appends record.
- `rewrite`: seeks back to last-read position and overwrites in place.
- `key_offset` / `key_length` unused.

### IndexedDriver

Flat file of fixed-length records **kept sorted by key at all times**. Key bytes are extracted as `data[key_offset:key_offset+key_length]` for every insert/lookup.

- `read_key(key)`: binary search over `file_size // record_length` slots using `seek(mid * record_length)`; compare key bytes at `[key_offset:key_offset+key_length]`; → `IOResult("23", None)` on miss.
- `read_seq`: forward scan from cursor position set by `start`.
- `start(key, relop)`: binary search to first record satisfying the key relation (`=`, `>`, `>=`, `<`, `<=`); sets cursor.
- `write`: binary search for insertion point; shift tail forward; write record; → `IOResult("22", None)` if key exists.
- `rewrite`: binary search to locate; overwrite in place (key unchanged, only data changes).
- `delete`: binary search to locate; shift tail backward (compact in place).

### RelativeDriver

Flat file of fixed-length slots. Each slot: `[1-byte flag | record_length bytes]` where `0x00` = empty, `0xFF` = active.

The relative record number is passed as `key: bytes` encoded as a 4-byte big-endian unsigned integer. The driver decodes it: `n = int.from_bytes(key, "big")`. The lowering encodes the WS relative-key field value the same way before calling `__cobol_read_record` / `__cobol_write_record` etc.

- `read_key(key)`: decode `n`; seek to `(n-1) * (1 + record_length)`; read flag; → `IOResult("23", None)` if `0x00`; else return data bytes.
- `read_seq`: advance slot by slot, skipping empty slots; → `IOResult("10", None)` at end of file.
- `start(key, relop)`: decode `n`; position sequential cursor at slot `n` (only `=` and `>=` are meaningful for RELATIVE).
- `write(key, data)`: decode `n`; check flag is `0x00` (else → `IOResult("22", None)`); write `0xFF` + data.
- `rewrite(key, data)`: decode `n`; check flag is `0xFF` (else → `IOResult("23", None)`); overwrite data bytes.
- `delete(key)`: decode `n`; write `0x00` at slot (zeroes the flag byte).

---

## RealFileIOProvider (`interpreter/cobol/real_file_provider.py`)

Constructed with:
- `base_dir: Path` — root for resolving relative paths
- `path_overrides: dict[str, Path] = {}` — test control; takes precedence over all other resolution

Path resolution for `assign_to`:
1. Check `path_overrides[file_name]` first.
2. If `assign_to` is a quoted string literal → use as-is, relative to `base_dir`.
3. If `assign_to` is an identifier → check env var of that name; fall back to `<base_dir>/<assign_to>`.

At `_open_file(filename, mode, record_length, organization, key_offset, key_length)`:
- Instantiate `SequentialDriver`, `IndexedDriver`, or `RelativeDriver` based on `organization`.
- Call `driver.open(resolved_path, mode, record_length, key_offset, key_length)`.
- Store driver in `self._drivers[filename]`.

All subsequent verb calls look up `self._drivers[filename]` and delegate, returning `IOResult`.

---

## Lowering Changes (`lower_io.py`, `emit_context.py`)

### `__cobol_open_file` extended signature

The lowering emits extra compile-time args from the FD layout and `FileControlEntry`:

```
CALL_FUNCTION __cobol_open_file "CUST-FILE" "I-O" 80 "INDEXED" 0 5
                                  filename   mode  rl  org    key_off key_len
```

Record length: root FD field `byte_length` from `SectionedLayout.file`. Key offset/length: resolve `FileControlEntry.record_key` in the FD layout. SEQUENTIAL/RELATIVE files pass `0 0` for key offset/length.

### OPEN multi-mode

Replace the single-mode loop with iteration over `stmt.mode_groups`:

```python
for mode, files in stmt.mode_groups:
    for filename in files:
        # emit __cobol_open_file(filename, mode, record_length, org, key_off, key_len)
        # emit FILE STATUS update
```

### FILE STATUS write-back helper

`EmitContext.emit_file_status_update(file_name, status_reg, materialised)`:
1. Looks up `FileControlEntry` for `file_name` in `CobolASG.file_control`.
2. If `file_status_var` is non-empty and resolvable, encodes `status_reg` into that WS field.
3. No-ops silently if no FILE STATUS was declared.

Called after every I/O verb emission.

### READ lowering pattern

```
%raw    = CALL_FUNCTION __cobol_read_record "FILE-NAME" [key_bytes_reg_or_empty]
%status = CALL_FUNCTION __cobol_io_status %raw
emit_file_status_update("FILE-NAME", %status, materialised)

%data   = CALL_FUNCTION __cobol_io_data %raw
# write %data into file section region at offset 0
# if INTO present: copy from file region to WS target

%is_at_end   = BINOP == %status "10"
%is_inv_key  = BINOP == %status "23"
BRANCH_IF %is_at_end at_end_label not_at_end_label

LABEL not_at_end_label:
  <lower not_at_end statements>
BRANCH after_label

LABEL at_end_label:
  <lower at_end statements>
LABEL after_label:
```

For random-access READ (INDEXED/RELATIVE): `stmt.key` field value is resolved from the FD region and passed as the second arg to `__cobol_read_record`. Sequential READ passes an empty string.

### WRITE / REWRITE / START / DELETE lowering

Same structure but without AT END: call verb → extract status → FILE STATUS update → branch on `%status == "23"` for INVALID KEY / NOT INVALID KEY clause bodies.

---

## Testing

### Unit tests (existing dirs)

**`tests/unit/cobol/test_file_enums.py`** — round-trip construction from strings for all three enums; invalid strings raise `ValueError`.

**`tests/unit/cobol/test_io_statements.py`** — `from_dict` / `to_dict` round-trips for all five I/O statements with conditional clause fields; `OpenStatement` single-mode and multi-mode; `FileControlEntry` all fields present and absent.

**`tests/unit/cobol/test_file_drivers.py`** — each driver tested against `tmp_path`:
- `SequentialDriver`: write three records, read in order, fourth read → `IOResult("10", None)`; EXTEND appends.
- `IndexedDriver`: write out of key order, read back in key order; `read_key` hit and miss; duplicate key → `"22"`; `rewrite` updates in place; `delete` compacts; `start` with `>=` positions correctly.
- `RelativeDriver`: write slot 3 with slots 1–2 empty; `read_key(3)` returns it; `read_key(1)` → `"23"`; delete slot 3; `read_key(3)` → `"23"`.

**`tests/unit/cobol/test_real_file_provider.py`** — `RealFileIOProvider` against `tmp_path`: path resolution (literal, env var, override dict); correct driver instantiated per organization; `IOResult` returned correctly.

**`tests/unit/test_cobol_io_integration.py`** — extend existing class:
- READ AT END fires when sequential exhausted; NOT AT END fires on success.
- INVALID KEY fires when key absent; NOT INVALID KEY fires on success.
- FILE STATUS variable updated in working-storage after READ.
- OPEN multi-mode opens files with correct `OpenMode`.
- Random-access READ passes key bytes to driver.
- File section region populated after READ; FD sub-fields readable.

### NIST-85 suite (`tests/nist/`)

```
tests/nist/
  conftest.py     # X-card substitution, SUBPRG chain ordering,
                  # RealFileIOProvider construction, PASS/FAIL counter extraction
  test_sq.py      # 170 sequential programs
  test_ix.py      # 42 indexed programs
  test_rl.py      # 70 relative programs
```

`conftest.py` responsibilities:
- Parse HEADER line to resolve SUBPRG chains; guarantee parent runs before dependents.
- Provide a shared `tmp_path` per chain so files written by the parent are visible to dependents.
- Map X-card placeholders (e.g. `X-21`) to `<tmp_path>/<name>.dat` using the NIST substitution table.
- Construct `RealFileIOProvider(base_dir=tmp_path, path_overrides=x_card_map)`.
- Capture PRINT-FILE output; extract `PASS-COUNTER` and `ERROR-COUNTER`; fail the pytest test if `ERROR-COUNTER > 0`.

Gated with `@pytest.mark.nist` — excluded from CI by default, same pattern as `carddemo_e2e`.

---

## Out of Scope

- Variable-length records (RECORD IS VARYING) — fixed-length only for now.
- Alternate record keys on INDEXED files.
- VSAM physical format (CI/CA) — logical KSDS model only, same as the CICS VSAM engine.
- JCL DD name resolution beyond env-var lookup.
- COBOL sort/merge verbs (SORT, MERGE).
