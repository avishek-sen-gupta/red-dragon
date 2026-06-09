# VSAM Dump CLI — Design

**Date:** 2026-06-09
**Status:** Approved (design); pending implementation plan
**Scope:** `interpreter/cics/vsam/` + tests only. No core-VM edits. Pure orchestration over existing parts.

## Goal

A copybook-driven CLI that decodes a VSAM flat-file dataset (the raw fixed-length-record image written by `interpreter/cics/vsam/format.py`) into **JSON-lines**, one object per record. Built primarily to debug the CardDemo end-to-end flows (confirm a REWRITE/WRITE landed and decodes correctly), and reusable as a general inspector for any fixed-length flat file given its COBOL record copybook.

## Background

`VsamEngine` persists datasets as a concatenation of fixed-length records (`format.py`, IDCAMS-REPRO-style). That image is **not** plain-text readable: fields are EBCDIC text, zoned-decimal (DISPLAY) numbers, COMP-3 packed decimals, and COMP binary. A raw hexdump is therefore useless. To inspect meaningfully you need the **record layout** (field names, byte offsets, types), which lives in the program's COBOL copybook — not in the engine (the engine is pure bytes/int and knows only `record_length` + key offset).

The project already has every decode primitive: `EbcdicTable.ebcdic_to_ascii`, `decode_zoned`, `decode_comp3`, `decode_binary` (all pure functions in `interpreter/cobol/`), `build_sectioned_layout`/`build_data_layout` (copybook → `DataLayout` with per-field offset/length/`type_descriptor`), `read_flat_file` (the codec), and `ProLeapCobolParser` (copybook → ASG via the Java bridge). This CLI is pure orchestration of those parts — no new decode logic, no new format.

## Decisions (resolved in brainstorming)

- **Use case:** debug CardDemo e2e dumps first; general copybook-driven inspector ultimately. Decode-only (no encode/seed authoring).
- **Layout source:** a COBOL copybook parsed via the existing ProLeap bridge at dump time. No new serialized-layout format. The Java JAR is required to run the CLI — the same gate as the e2e tests (`PROLEAP_BRIDGE_JAR`).
- **Default output:** JSON-lines (scriptable, jq-friendly). A secondary human-readable `block` format (with per-field raw hex) is included for deep encoding-bug debugging.
- **Record length is derived from the copybook layout** (`DataLayout.total_bytes`), not a CLI argument.
- **Filtering is out of scope** — pipe to `jq`/`grep`.

## Invocation

```
poetry run python -m interpreter.cics.vsam.dump \
    --data ACCTDAT.dat --copybook CVACT01Y.cpy [--record ACCOUNT-RECORD] \
    [--format jsonl|block] [--copybook-dir DIR ...] [--jar PATH]
```

- `--data` (required): path to the flat-file dataset image.
- `--copybook` (required): path to the COBOL record copybook.
- `--record` (optional): 01-level record name to decode when the copybook declares more than one. If the copybook has exactly one 01, it is the default. If it has multiple and `--record` is absent, the CLI errors listing the available 01 names.
- `--format` (optional, default `jsonl`): `jsonl` or `block`.
- `--copybook-dir` (optional, repeatable): extra directories for nested `COPY` resolution. The copybook's own directory is always included.
- `--jar` (optional): path to the ProLeap bridge JAR. Defaults from the `PROLEAP_BRIDGE_JAR` environment variable.

## Components

### 1. Layout sourcing
Wrap the copybook in a minimal program skeleton (IDENTIFICATION DIVISION / PROGRAM-ID / DATA DIVISION / WORKING-STORAGE SECTION + `COPY <book>.`) and parse it with `ProLeapCobolParser(SubprocessRunner(), jar, copybook_dirs=[copybook_dir, *extra_dirs])`. Take `build_sectioned_layout(asg).working_storage` to obtain the `DataLayout`. Select the 01 record: if exactly one top-level group, use it; if `--record` is given, select that group by name (case-insensitive, matching the project's identifier rules); if multiple and none specified, raise an error listing the names.

### 2. Record decoder (pure, reusable core)
`decode_record(layout: DataLayout, record: bytes) -> dict` — independent of argparse and the filesystem, directly unit-testable. Walks the `DataLayout` tree:
- **Leaf field** (`FieldLayout`): slice `record[offset : offset + byte_length]` and dispatch on the field's `type_descriptor` category to the existing pure decoder:
  - alphanumeric / display text → `EbcdicTable.ebcdic_to_ascii`, decoded to `str`, trailing spaces trimmed.
  - DISPLAY numeric (zoned) → `decode_zoned(slice, decimal_digits)`.
  - COMP-3 packed → `decode_comp3(slice, decimal_digits)`.
  - COMP binary → `decode_binary(slice, decimal_digits, signed)`.
- **Group** (`DataLayout` child): nested `dict` mirroring the record tree.
- **OCCURS** group/field: a JSON array of the element shape, one entry per occurrence. **OCCURS DEPENDING ON honors the counter:** decode the counter field (named by `FieldLayout.occurs_depending_on`) from the same record bytes, then emit exactly that many occurrences, clamped to `[occurs_min, occurs_count]`. This yields the logical view the program sees — decoding the fixed max width would present leftover bytes in the unused trailing slots as if they were real data and could trigger spurious decode errors on non-conforming garbage. If the decoded counter falls outside `[occurs_min, occurs_count]` it is clamped, and the raw out-of-range counter value is surfaced (in `block` format as a note; it remains visible as the counter field's own value in `jsonl`) since that signals record corruption.
- **REDEFINES**: both the base field and the redefining field are emitted (alternate readings of the same bytes — informative).

Numeric values decode to `int`/`float` per PIC scale; the decoders already return the correctly-scaled value.

### 3. Renderer
- `jsonl` (default): `json.dumps(decode_record(layout, rec))` per record, newline-separated, in record order.
- `block`: per record, a header line plus one line per leaf field showing `@<offset>  <NAME>  <decoded value>  0x<raw hex>` — the format that makes EBCDIC/COMP-3/leading-zero bugs visible.

## Data flow

1. Resolve JAR (arg or `PROLEAP_BRIDGE_JAR`).
2. Parse the copybook (skeleton-wrapped) → `DataLayout`; select the 01 record; `record_length = layout.total_bytes`.
3. `read_flat_file(data_path, record_length)` → `list[bytes]` (raises if the file size is not a multiple of the derived length).
4. For each record: `decode_record` → render per `--format` → write to stdout.

## Error handling

- File size not a multiple of the derived record length → `read_flat_file` raises `ValueError`; the CLI reports it including the derived record length (the loud "wrong copybook or wrong file" signal). Exit non-zero.
- Missing JAR or parse failure → the CLI surfaces `CobolParseError` (with the bridge's enriched message) and exits non-zero.
- Ambiguous record selection (multiple 01s, no `--record`) or an unknown `--record` name → error listing the available 01 names. Exit non-zero.
- Missing `--data` file → `read_flat_file` returns `[]` (no records); the CLI prints nothing and exits zero (an empty dataset is valid).

## Testing

### Unit (`tests/unit/cics/vsam/`)
- `decode_record` against hand-built `DataLayout`s:
  - EBCDIC alphanumeric text (trailing-space trim).
  - zoned DISPLAY numeric, signed and unsigned.
  - COMP-3 packed decimal.
  - COMP binary.
  - a nested group → nested dict.
  - a fixed OCCURS field → JSON array of the declared count.
  - an OCCURS DEPENDING ON field → array length equals the decoded counter (not max); trailing junk bytes are not decoded; an out-of-range counter clamps to `[occurs_min, occurs_count]`.
  - a REDEFINES pair → both views present.
- Renderers: `jsonl` emits one JSON object per record in order; `block` emits offset/name/value/hex lines.
- Record-length mismatch → the CLI path raises/reports the `ValueError`.
- Multiple-01 copybook without `--record` → error listing names (using a stubbed/handbuilt multi-group layout, no JAR needed).

### Gated integration (`tests/integration/cics/`)
Round-trip with the real flow: run the CardDemo account-update REWRITE through a `FileBackend` into a temp dir (reuse the durable harness driver), then invoke the dump CLI's programmatic entry point on the backing `ACCTDAT.dat` with the real CardDemo account copybook, and assert the decoded JSON shows `ACCT-ACTIVE-STATUS == "N"`. Gated on `CARDDEMO_HOME` + `BMS_TOOLS_HOME` + JAR like the other real flows; skips otherwise.

## Out of scope (YAGNI)

- Encode / seed-data authoring (decode only).
- Built-in filtering or queries (pipe to `jq`/`grep`).
- A sidecar-layout-JSON pure-Python path (we chose copybook-via-ProLeap; the JAR gate is accepted).
- A no-copybook raw hexdump mode.

## Constraints

- All changes in `interpreter/cics/vsam/` (+ tests). No edits to `interpreter/vm/**`, `ir.py`, `run.py`, `executor.py`, `cfg.py`.
- No new decode logic or record format — pure orchestration of existing primitives.
- `decode_record` stays a pure function (`DataLayout` + `bytes` → `dict`), independent of argparse and the filesystem.
- `@covers(...)` on every test; `black` + `lint-imports` + full suite green before commit.
