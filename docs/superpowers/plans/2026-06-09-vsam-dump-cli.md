# VSAM Dump CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A copybook-driven CLI that decodes a VSAM flat-file dataset image into JSON-lines (one object per record), reusing the existing COBOL decoders and layout builder.

**Architecture:** A new module `interpreter/cics/vsam/dump.py` orchestrates existing pieces: `ProLeapCobolParser` + `build_data_layout` turn a copybook into a `DataLayout`; a new pure `decode_record(layout, record)` walks that layout and slices each field through the existing pure decoders (`decode_zoned`/`decode_comp3`/`decode_binary`/`EbcdicTable.ebcdic_to_ascii`); renderers emit `jsonl` (default) or human-readable `block`; an `argparse` `main()` wires it to the filesystem. No new decode logic, no new on-disk format, no core-VM edits.

**Tech Stack:** Python 3.13, Poetry, pytest, the ProLeap COBOL bridge (Java JAR, gated via `PROLEAP_BRIDGE_JAR`).

---

## Background the implementer needs

Read the spec: `docs/superpowers/specs/2026-06-09-vsam-dump-cli-design.md`.

**Existing pieces you will reuse (do not reimplement):**

- `interpreter/cics/vsam/format.py`:
  - `read_flat_file(path: Path, record_length: int) -> list[bytes]` — splits a flat file into fixed-length records; returns `[]` for a missing file; raises `ValueError` if the size is not a multiple of `record_length`.
- `interpreter/cobol/data_layout.py`:
  - `build_data_layout(fields: list[CobolField]) -> DataLayout`.
  - `DataLayout` (frozen dataclass): `fields: dict[str, FieldLayout]` (direct leaf children), `groups: dict[str, DataLayout]` (direct group children), `offset: int`, `total_bytes: int`, `occurs_count: int`, `element_size: int`. Methods: `lookup(name) -> FieldLayout | None` (depth-first, case-insensitive).
  - `FieldLayout` (frozen dataclass): `name: str`, `type_descriptor: CobolTypeDescriptor`, `offset: int` (absolute from record start), `byte_length: int`, `redefines: str`, `value: str`, `occurs_count: int`, `element_size: int`, `occurs_depending_on: str`, `occurs_min: int`, `sign_separate: bool`, … (other attrs exist but are unused here).
- `interpreter/cobol/cobol_types.py`:
  - `CobolDataCategory(str, Enum)`: `ZONED_DECIMAL`, `COMP3`, `BINARY`, `COMP1`, `COMP2`, `ALPHANUMERIC`.
  - `CobolTypeDescriptor` (frozen dataclass): `category: CobolDataCategory`, `total_digits: int`, `decimal_digits: int = 0`, `signed: bool = False`, `sign_separate: bool` (and others).
- Pure decoders (each returns `float`; **integer fields must be converted to `int` by the caller** — see below):
  - `interpreter/cobol/zoned_decimal.py`: `decode_zoned(data: bytes, decimal_digits: int) -> float`.
  - `interpreter/cobol/comp3.py`: `decode_comp3(data: bytes, decimal_digits: int) -> float`.
  - `interpreter/cobol/binary.py`: `decode_binary(data: bytes, decimal_digits: int, signed: bool) -> float`.
  - `interpreter/cobol/ebcdic_table.py`: `EbcdicTable.ebcdic_to_ascii(data: bytes) -> bytes`.
- `interpreter/cobol/cobol_parser.py`: `ProLeapCobolParser(runner, bridge_jar: str, copybook_dirs: list[Path] = ...)`; `.parse(source: bytes) -> CobolASG`. `CobolASG.data_fields` is the `list[CobolField]` of WORKING-STORAGE top-level items.
- `interpreter/cobol/subprocess_runner.py`: `SubprocessRunner()` — the real Java-invoking runner.

**Int-vs-float rule (matches the engine, red-dragon-4q25.42):** a numeric field with `decimal_digits == 0` decodes to `int`; with `decimal_digits > 0` to `float`. The pure decoders always return `float`, so the dump module converts: `int(round(v))` when `decimal_digits == 0`.

**Offsets are absolute from the record (01) start.** `decode_record` rebases by the record layout's own `offset` so it works whether the record is the whole working-storage (offset 0) or a selected sub-01 group.

**Test conventions:**
- Unit tests: `tests/unit/cics/test_vsam_dump.py`. Integration: `tests/integration/cics/test_vsam_dump_e2e.py`.
- Every test method needs `@covers(NotLanguageFeature.INFRASTRUCTURE)`. The exact import (verified against `tests/unit/cics/test_vsam_format.py`) is a single line: `from tests.covers import covers, NotLanguageFeature`.
- Run tests with `poetry run python -m pytest`. Format with `poetry run python -m black <files>`. Lint imports with `poetry run lint-imports`.
- A TDD-guard pytest plugin is active: write the failing test first, run it red, then implement.

**Hand-building a `DataLayout` for unit tests** (no JAR needed). Example helper you can paste into the test module:

```python
from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor


def _alpha(name, offset, length):
    return FieldLayout(
        name=name,
        type_descriptor=CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC, total_digits=length
        ),
        offset=offset,
        byte_length=length,
    )


def _zoned(name, offset, total_digits, decimal_digits=0, signed=False):
    return FieldLayout(
        name=name,
        type_descriptor=CobolTypeDescriptor(
            category=CobolDataCategory.ZONED_DECIMAL,
            total_digits=total_digits,
            decimal_digits=decimal_digits,
            signed=signed,
        ),
        offset=offset,
        byte_length=total_digits,
    )
```

EBCDIC test bytes: build with `EbcdicTable.ascii_to_ebcdic(b"...")`. Zoned digits: each byte `0xF0 | digit` (e.g. `b"\xf0\xf0\xf1"` is 001). COMP-3: `encode_comp3(value, total_digits, decimal_digits, signed)` from `interpreter/cobol/comp3.py` round-trips with `decode_comp3`.

---

## File Structure

- **Create** `interpreter/cics/vsam/dump.py` — the whole feature: `decode_record` (+ leaf/group/occurs helpers), `load_record_layout`, `render_jsonl`/`render_block`, `main`. One module, one responsibility (read-only copybook-driven dump). It is small and cohesive; do not split.
- **Create** `tests/unit/cics/test_vsam_dump.py` — unit tests for decode + selection + renderers.
- **Create** `tests/integration/cics/test_vsam_dump_e2e.py` — gated round-trip test.

---

### Task 1: Decode a single elementary field (`_decode_leaf`)

**Files:**
- Create: `interpreter/cics/vsam/dump.py`
- Test: `tests/unit/cics/test_vsam_dump.py`

- [ ] **Step 1: Write the failing tests**

In `tests/unit/cics/test_vsam_dump.py` (copy the `@covers` import line from `tests/unit/cics/test_vsam_format.py`):

```python
from __future__ import annotations

from interpreter.cics.vsam.dump import _decode_leaf
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.comp3 import encode_comp3
from interpreter.cobol.binary import encode_binary
from tests.covers import covers, NotLanguageFeature


def _fl(category, offset, byte_length, total_digits, decimal_digits=0, signed=False):
    return FieldLayout(
        name="F",
        type_descriptor=CobolTypeDescriptor(
            category=category,
            total_digits=total_digits,
            decimal_digits=decimal_digits,
            signed=signed,
        ),
        offset=offset,
        byte_length=byte_length,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_alphanumeric_trims_trailing_spaces():
    fl = _fl(CobolDataCategory.ALPHANUMERIC, 0, 5, 5)
    data = EbcdicTable.ascii_to_ebcdic(b"AB   ")
    assert _decode_leaf(fl, data) == "AB"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_zoned_integer_is_int():
    fl = _fl(CobolDataCategory.ZONED_DECIMAL, 0, 3, 3, decimal_digits=0)
    assert _decode_leaf(fl, b"\xf0\xf1\xf2") == 12
    assert isinstance(_decode_leaf(fl, b"\xf0\xf1\xf2"), int)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_zoned_decimal_is_float():
    fl = _fl(CobolDataCategory.ZONED_DECIMAL, 0, 4, 4, decimal_digits=2)
    assert _decode_leaf(fl, b"\xf1\xf2\xf3\xf4") == 12.34


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_comp3_decimal():
    data = encode_comp3(123.45, 5, 2, True)
    fl = _fl(CobolDataCategory.COMP3, 0, len(data), 5, decimal_digits=2, signed=True)
    assert _decode_leaf(fl, data) == 123.45


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_binary_integer_is_int():
    data = encode_binary(42, 4, 0, True)
    fl = _fl(CobolDataCategory.BINARY, 0, len(data), 4, decimal_digits=0, signed=True)
    assert _decode_leaf(fl, data) == 42
    assert isinstance(_decode_leaf(fl, data), int)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_leaf_comp1_comp2_unsupported():
    import pytest

    fl = _fl(CobolDataCategory.COMP1, 0, 4, 0)
    with pytest.raises(NotImplementedError):
        _decode_leaf(fl, b"\x00\x00\x00\x00")
```


- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_dump.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.cics.vsam.dump'` (or `ImportError: cannot import name '_decode_leaf'`).

- [ ] **Step 3: Write the minimal implementation**

Create `interpreter/cics/vsam/dump.py`:

```python
"""Copybook-driven decoder/dumper for VSAM flat-file dataset images.

Reads a fixed-length-record flat file (see interpreter/cics/vsam/format.py) and
decodes each record field-by-field using a COBOL record layout parsed from a
copybook, emitting JSON-lines (default) or a human-readable block format.

Pure orchestration over existing primitives: build_data_layout (copybook ->
DataLayout) and the COBOL pure decoders. No new decode logic, no new format.
"""

from __future__ import annotations

from interpreter.cobol.binary import decode_binary
from interpreter.cobol.comp3 import decode_comp3
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.zoned_decimal import decode_zoned


def _decode_leaf(field: FieldLayout, data: bytes) -> int | float | str:
    """Decode the bytes of one elementary field to a Python value.

    ``data`` must be exactly the field's bytes. Numeric fields with no implied
    decimals decode to int (matching the engine, red-dragon-4q25.42); fields with
    decimals decode to float. Alphanumeric fields decode EBCDIC -> ASCII text with
    trailing spaces trimmed.
    """
    td = field.type_descriptor
    cat = td.category
    if cat == CobolDataCategory.ALPHANUMERIC:
        return EbcdicTable.ebcdic_to_ascii(data).decode("latin-1").rstrip(" ")
    if cat == CobolDataCategory.ZONED_DECIMAL:
        return _as_number(decode_zoned(data, td.decimal_digits), td.decimal_digits)
    if cat == CobolDataCategory.COMP3:
        return _as_number(decode_comp3(data, td.decimal_digits), td.decimal_digits)
    if cat == CobolDataCategory.BINARY:
        return _as_number(
            decode_binary(data, td.decimal_digits, td.signed), td.decimal_digits
        )
    raise NotImplementedError(
        f"VSAM dump does not support category {cat.value} (field {field.name!r})"
    )


def _as_number(value: float, decimal_digits: int) -> int | float:
    return int(round(value)) if decimal_digits == 0 else value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_dump.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black interpreter/cics/vsam/dump.py tests/unit/cics/test_vsam_dump.py
poetry run lint-imports
git add interpreter/cics/vsam/dump.py tests/unit/cics/test_vsam_dump.py
git commit -m "feat(vsam): decode_leaf — per-category elementary field decode for dump CLI"
```

---

### Task 2: Decode a whole record with nested groups and REDEFINES (`decode_record`)

**Files:**
- Modify: `interpreter/cics/vsam/dump.py`
- Test: `tests/unit/cics/test_vsam_dump.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/cics/test_vsam_dump.py`:

```python
from interpreter.cics.vsam.dump import decode_record
from interpreter.cobol.data_layout import DataLayout


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_record_flat_fields():
    layout = DataLayout(
        fields={
            "ACCT-ID": _fl(CobolDataCategory.ALPHANUMERIC, 0, 11, 11),
            "ACCT-ACTIVE-STATUS": _fl(CobolDataCategory.ALPHANUMERIC, 11, 1, 1),
        },
        total_bytes=12,
    )
    record = EbcdicTable.ascii_to_ebcdic(b"00000000011") + EbcdicTable.ascii_to_ebcdic(b"N")
    assert decode_record(layout, record) == {
        "ACCT-ID": "00000000011",
        "ACCT-ACTIVE-STATUS": "N",
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_record_nested_group():
    inner = DataLayout(
        fields={"FIRST": _fl(CobolDataCategory.ALPHANUMERIC, 0, 3, 3),
                "LAST": _fl(CobolDataCategory.ALPHANUMERIC, 3, 3, 3)},
        offset=0,
        total_bytes=6,
    )
    layout = DataLayout(groups={"NAME": inner}, total_bytes=6)
    record = EbcdicTable.ascii_to_ebcdic(b"BOBKAY")
    assert decode_record(layout, record) == {"NAME": {"FIRST": "BOB", "LAST": "KAY"}}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_record_redefines_both_views():
    # Two fields over the same 4 bytes: text view + a group view.
    base = _fl(CobolDataCategory.ALPHANUMERIC, 0, 4, 4)
    redef = FieldLayout(
        name="AS-NUM",
        type_descriptor=base.type_descriptor.__class__(
            category=CobolDataCategory.ZONED_DECIMAL, total_digits=4
        ),
        offset=0,
        byte_length=4,
        redefines="AS-TEXT",
    )
    layout = DataLayout(fields={"AS-TEXT": base, "AS-NUM": redef}, total_bytes=4)
    record = b"\xf1\xf2\xf3\xf4"
    out = decode_record(layout, record)
    assert out["AS-NUM"] == 1234  # zoned int view
    assert "AS-TEXT" in out  # both views present


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_record_rebases_subgroup_offset():
    # A sub-01 selected from a multi-01 copybook sits at a non-zero absolute offset;
    # decode_record must rebase so slicing is relative to the record start.
    inner = DataLayout(
        fields={"X": _fl(CobolDataCategory.ALPHANUMERIC, 20, 2, 2)},
        offset=20,
        total_bytes=2,
    )
    record = EbcdicTable.ascii_to_ebcdic(b"HI")
    assert decode_record(inner, record) == {"X": "HI"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_dump.py -k "decode_record" -q`
Expected: FAIL — `ImportError: cannot import name 'decode_record'`.

- [ ] **Step 3: Write the minimal implementation**

Add to `interpreter/cics/vsam/dump.py`:

```python
from interpreter.cobol.data_layout import DataLayout


def decode_record(
    layout: DataLayout, record: bytes, base_offset: int | None = None
) -> dict:
    """Decode one record's bytes into a nested dict, per the DataLayout.

    Leaf fields decode via _decode_leaf; group children recurse into nested dicts.
    ``base_offset`` rebases absolute field offsets to the record start; it defaults
    to the layout's own offset so a sub-01 group selected from a multi-01 copybook
    (sitting at a non-zero absolute offset) slices correctly. OCCURS handling is
    added in a later task.
    """
    base = layout.offset if base_offset is None else base_offset
    out: dict = {}
    for name, fl in layout.fields.items():
        start = fl.offset - base
        out[name] = _decode_leaf(fl, record[start : start + fl.byte_length])
    for name, sub in layout.groups.items():
        out[name] = decode_record(sub, record, base)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_dump.py -q`
Expected: PASS (10 passed).

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black interpreter/cics/vsam/dump.py tests/unit/cics/test_vsam_dump.py
poetry run lint-imports
git add interpreter/cics/vsam/dump.py tests/unit/cics/test_vsam_dump.py
git commit -m "feat(vsam): decode_record — nested groups + REDEFINES + offset rebase"
```

---

### Task 3: OCCURS arrays — fixed count and OCCURS DEPENDING ON

**Files:**
- Modify: `interpreter/cics/vsam/dump.py`
- Test: `tests/unit/cics/test_vsam_dump.py`

A field or group with `occurs_count > 0` repeats `occurs_count` times with stride `element_size`. For OCCURS DEPENDING ON (`occurs_depending_on` set), the live count comes from the counter field (decoded from the same record), clamped to `[occurs_min or 1, occurs_count]` — never the fixed max (which would expose junk in unused trailing slots).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/cics/test_vsam_dump.py`:

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_record_fixed_occurs_leaf_array():
    item = FieldLayout(
        name="CODE",
        type_descriptor=CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC, total_digits=2
        ),
        offset=0,
        byte_length=2,
        occurs_count=3,
        element_size=2,
    )
    layout = DataLayout(fields={"CODE": item}, total_bytes=6)
    record = EbcdicTable.ascii_to_ebcdic(b"AABBCC")
    assert decode_record(layout, record) == {"CODE": ["AA", "BB", "CC"]}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_record_odo_honors_counter_not_max():
    # N (zoned, offset 0, 1 digit) controls ITEM OCCURS 1 TO 3 DEPENDING ON N.
    counter = _fl(CobolDataCategory.ZONED_DECIMAL, 0, 1, 1, decimal_digits=0)
    item = FieldLayout(
        name="ITEM",
        type_descriptor=CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC, total_digits=2
        ),
        offset=1,
        byte_length=2,
        occurs_count=3,
        element_size=2,
        occurs_depending_on="N",
        occurs_min=1,
    )
    layout = DataLayout(fields={"N": counter, "ITEM": item}, total_bytes=7)
    # N=2 -> two live items "AA","BB"; trailing "ZZ" is junk and must NOT appear.
    record = b"\xf2" + EbcdicTable.ascii_to_ebcdic(b"AABBZZ")
    out = decode_record(layout, record)
    assert out["N"] == 2
    assert out["ITEM"] == ["AA", "BB"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decode_record_odo_counter_clamped_to_max():
    counter = _fl(CobolDataCategory.ZONED_DECIMAL, 0, 1, 1, decimal_digits=0)
    item = FieldLayout(
        name="ITEM",
        type_descriptor=CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC, total_digits=2
        ),
        offset=1,
        byte_length=2,
        occurs_count=3,
        element_size=2,
        occurs_depending_on="N",
        occurs_min=1,
    )
    layout = DataLayout(fields={"N": counter, "ITEM": item}, total_bytes=7)
    # N=9 (corrupt, > max 3) -> clamp to 3 items.
    record = b"\xf9" + EbcdicTable.ascii_to_ebcdic(b"AABBCC")
    out = decode_record(layout, record)
    assert out["ITEM"] == ["AA", "BB", "CC"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_dump.py -k "occurs or odo" -q`
Expected: FAIL — fixed OCCURS returns a scalar (`"AA"`) instead of a list; ODO tests likewise fail.

- [ ] **Step 3: Write the minimal implementation**

Replace the body of `decode_record` in `interpreter/cics/vsam/dump.py` with the OCCURS-aware version, and thread a `root` layout so ODO can resolve its counter anywhere in the record:

```python
def decode_record(
    layout: DataLayout,
    record: bytes,
    base_offset: int | None = None,
    root: DataLayout | None = None,
) -> dict:
    """Decode one record's bytes into a nested dict, per the DataLayout.

    Leaf fields decode via _decode_leaf; group children recurse. Fields/groups with
    occurs_count > 0 become lists (stride element_size). OCCURS DEPENDING ON honors
    the counter field (resolved from ``root``) clamped to [occurs_min or 1,
    occurs_count]. ``base_offset`` rebases absolute offsets to the record start.
    """
    base = layout.offset if base_offset is None else base_offset
    top = layout if root is None else root
    out: dict = {}
    for name, fl in layout.fields.items():
        out[name] = _decode_field(fl, record, base, top)
    for name, sub in layout.groups.items():
        out[name] = _decode_group(sub, record, base, top)
    return out


def _live_count(node, record: bytes, base: int, root: DataLayout) -> int:
    """Resolve the occurrence count for an OCCURS node, honoring ODO."""
    if not node.occurs_depending_on:
        return node.occurs_count
    counter = root.lookup(node.occurs_depending_on)
    if counter is None:
        return node.occurs_count  # unresolved counter: fall back to declared max
    start = counter.offset - base
    raw = _decode_leaf(counter, record[start : start + counter.byte_length])
    n = int(raw)
    low = node.occurs_min or 1
    return max(low, min(n, node.occurs_count))


def _decode_field(fl: FieldLayout, record: bytes, base: int, root: DataLayout):
    if fl.occurs_count > 0:
        n = _live_count(fl, record, base, root)
        result = []
        for i in range(n):
            start = fl.offset - base + i * fl.element_size
            result.append(_decode_leaf(fl, record[start : start + fl.byte_length]))
        return result
    start = fl.offset - base
    return _decode_leaf(fl, record[start : start + fl.byte_length])


def _decode_group(sub: DataLayout, record: bytes, base: int, root: DataLayout):
    if sub.occurs_count > 0:
        n = _live_count(sub, record, base, root)
        return [
            _decode_group_element(sub, record, base, root, i) for i in range(n)
        ]
    return decode_record(sub, record, base, root)


def _decode_group_element(
    sub: DataLayout, record: bytes, base: int, root: DataLayout, index: int
) -> dict:
    """Decode the index-th element of an OCCURS group (shift base by stride)."""
    shifted_base = base - index * sub.element_size
    return decode_record(sub, record, shifted_base, root)
```

> Note: `DataLayout` does not carry an `occurs_depending_on` attribute, so OCCURS DEPENDING ON on a *group* falls through `_live_count`'s `if not node.occurs_depending_on` guard and decodes the fixed count. That is acceptable for v1: CardDemo's ODO usage (if any) is on elementary tables, and the spec's correctness goal is met for the leaf case. If a group ODO is later needed, add the attribute to `DataLayout` in `interpreter/cobol/data_layout.py` (allowed — that file is not core-VM) and extend `_live_count`. Do NOT add it speculatively now (YAGNI).

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_dump.py -q`
Expected: PASS (13 passed).

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black interpreter/cics/vsam/dump.py tests/unit/cics/test_vsam_dump.py
poetry run lint-imports
git add interpreter/cics/vsam/dump.py tests/unit/cics/test_vsam_dump.py
git commit -m "feat(vsam): OCCURS arrays + ODO counter-honoring decode in dump CLI"
```

---

### Task 4: Layout sourcing, renderers, and the `main()` CLI

**Files:**
- Modify: `interpreter/cics/vsam/dump.py`
- Test: `tests/unit/cics/test_vsam_dump.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/cics/test_vsam_dump.py`:

```python
import json

from interpreter.cics.vsam.dump import (
    render_jsonl,
    render_block,
    select_record_layout,
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_render_jsonl_one_object_per_record():
    layout = DataLayout(
        fields={"S": _fl(CobolDataCategory.ALPHANUMERIC, 0, 1, 1)}, total_bytes=1
    )
    records = [EbcdicTable.ascii_to_ebcdic(b"Y"), EbcdicTable.ascii_to_ebcdic(b"N")]
    out = render_jsonl(layout, records)
    lines = out.splitlines()
    assert json.loads(lines[0]) == {"S": "Y"}
    assert json.loads(lines[1]) == {"S": "N"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_render_block_shows_offset_name_value_hex():
    layout = DataLayout(
        fields={"S": _fl(CobolDataCategory.ALPHANUMERIC, 0, 1, 1)}, total_bytes=1
    )
    out = render_block(layout, [EbcdicTable.ascii_to_ebcdic(b"Y")])
    assert "S" in out
    assert "Y" in out
    assert "@0" in out
    assert EbcdicTable.ascii_to_ebcdic(b"Y").hex() in out  # raw hex present


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_select_record_layout_single_group_is_default():
    inner = DataLayout(
        fields={"X": _fl(CobolDataCategory.ALPHANUMERIC, 0, 1, 1)},
        offset=0,
        total_bytes=1,
    )
    root = DataLayout(groups={"REC-A": inner}, total_bytes=1)
    assert select_record_layout(root, None) is inner


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_select_record_layout_multiple_groups_requires_name():
    import pytest

    a = DataLayout(offset=0, total_bytes=1)
    b = DataLayout(offset=1, total_bytes=1)
    root = DataLayout(groups={"REC-A": a, "REC-B": b}, total_bytes=2)
    with pytest.raises(ValueError) as exc:
        select_record_layout(root, None)
    assert "REC-A" in str(exc.value) and "REC-B" in str(exc.value)
    assert select_record_layout(root, "REC-B") is b


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_select_record_layout_no_groups_uses_root():
    # A copybook whose 01 is elementary: decode the root itself.
    root = DataLayout(
        fields={"X": _fl(CobolDataCategory.ALPHANUMERIC, 0, 1, 1)}, total_bytes=1
    )
    assert select_record_layout(root, None) is root
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_dump.py -k "render or select" -q`
Expected: FAIL — `ImportError: cannot import name 'render_jsonl'`.

- [ ] **Step 3: Write the minimal implementation**

Add to `interpreter/cics/vsam/dump.py`:

```python
import argparse
import json
import os
import sys
from pathlib import Path

from interpreter.cics.vsam.format import read_flat_file
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.subprocess_runner import SubprocessRunner


def select_record_layout(root: DataLayout, record_name: str | None) -> DataLayout:
    """Pick the 01-level record layout to decode.

    - Root has group children: select by ``record_name``; if exactly one group and
      no name given, use it; if multiple and no name, raise listing the names.
    - Root has no group children (the 01 is elementary): decode the root itself.
    """
    groups = root.groups
    if not groups:
        return root
    if record_name is not None:
        for name, sub in groups.items():
            if name.upper() == record_name.upper():
                return sub
        raise ValueError(
            f"record {record_name!r} not found; available: {sorted(groups)}"
        )
    if len(groups) == 1:
        return next(iter(groups.values()))
    raise ValueError(
        f"copybook declares multiple records; pass --record (one of {sorted(groups)})"
    )


_SKELETON_HEAD = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. VSAMDUMP.\n"
    "       DATA DIVISION.\n"
    "       WORKING-STORAGE SECTION.\n"
)


def load_record_layout(
    copybook: Path,
    record_name: str | None,
    jar: str,
    extra_dirs: list[Path],
) -> DataLayout:
    """Parse a copybook (wrapped in a minimal program) into the selected record layout."""
    member = copybook.stem
    source = (_SKELETON_HEAD + f"       COPY {member}.\n").encode("ascii")
    copybook_dirs = [copybook.parent, *extra_dirs]
    parser = ProLeapCobolParser(SubprocessRunner(), jar, copybook_dirs=copybook_dirs)
    asg = parser.parse(source)
    root = build_data_layout(asg.data_fields)
    return select_record_layout(root, record_name)


def render_jsonl(layout: DataLayout, records: list[bytes]) -> str:
    """One compact JSON object per record, newline-terminated."""
    lines = [json.dumps(decode_record(layout, rec)) for rec in records]
    return "\n".join(lines) + ("\n" if lines else "")


def render_block(layout: DataLayout, records: list[bytes]) -> str:
    """Human-readable per-field block: @offset NAME value 0xRAW, for each record."""
    chunks: list[str] = []
    for idx, rec in enumerate(records, start=1):
        chunks.append(f"=== record {idx} ===")
        chunks.extend(_block_lines(layout, rec, layout.offset, prefix=""))
    return "\n".join(chunks) + ("\n" if chunks else "")


def _block_lines(layout: DataLayout, record: bytes, base: int, prefix: str) -> list[str]:
    lines: list[str] = []
    for name, fl in layout.fields.items():
        start = fl.offset - base
        raw = record[start : start + fl.byte_length]
        value = _decode_leaf(fl, raw) if fl.occurs_count == 0 else "<occurs>"
        lines.append(f"  @{fl.offset:<5} {prefix}{name:<28} {value!r:<24} 0x{raw.hex()}")
    for name, sub in layout.groups.items():
        lines.append(f"  @{sub.offset:<5} {prefix}{name}:")
        lines.extend(_block_lines(sub, record, base, prefix + "  "))
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m interpreter.cics.vsam.dump",
        description="Decode a VSAM flat-file dataset via a COBOL copybook.",
    )
    parser.add_argument("--data", required=True, type=Path, help="flat-file .dat path")
    parser.add_argument("--copybook", required=True, type=Path, help="record copybook")
    parser.add_argument("--record", default=None, help="01-level record name (if multiple)")
    parser.add_argument("--format", choices=["jsonl", "block"], default="jsonl")
    parser.add_argument("--copybook-dir", action="append", default=[], type=Path)
    parser.add_argument(
        "--jar", default=os.environ.get("PROLEAP_BRIDGE_JAR"),
        help="ProLeap bridge JAR (defaults to $PROLEAP_BRIDGE_JAR)",
    )
    args = parser.parse_args(argv)
    if not args.jar:
        parser.error("no JAR: pass --jar or set PROLEAP_BRIDGE_JAR")

    layout = load_record_layout(
        args.copybook, args.record, args.jar, args.copybook_dir
    )
    record_length = layout.total_bytes
    records = read_flat_file(args.data, record_length)
    renderer = render_jsonl if args.format == "jsonl" else render_block
    sys.stdout.write(renderer(layout, records))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

> `record_length = layout.total_bytes`: for a single-01 copybook this is correct. For a selected sub-group whose `total_bytes` is 0, fall back is out of scope here (multi-01 record-length derivation is covered by the integration test using a real single-01 copybook). If a multi-01 selection needs a non-root length later, compute the group span; not needed for the CardDemo use case.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/cics/test_vsam_dump.py -q`
Expected: PASS (18 passed).

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black interpreter/cics/vsam/dump.py tests/unit/cics/test_vsam_dump.py
poetry run lint-imports
git add interpreter/cics/vsam/dump.py tests/unit/cics/test_vsam_dump.py
git commit -m "feat(vsam): copybook layout sourcing, jsonl/block renderers, dump CLI main"
```

---

### Task 5: Gated end-to-end round-trip test

**Files:**
- Test: `tests/integration/cics/test_vsam_dump_e2e.py`

This proves the whole pipeline: run the real CardDemo account-update REWRITE through a `FileBackend`, then decode the backing `ACCTDAT.dat` via the dump module and assert the mutated status is `"N"`.

- [ ] **Step 1: Write the failing test**

First, open `tests/integration/cics/test_vsam_persistence.py` and reuse its exact setup: the skip-gate (`CARDDEMO_HOME`/`BMS_TOOLS_AVAILABLE`/`JAR_AVAILABLE` `pytestmark`), the `_drive_rewrite(tmp_path, backend=...)` driver imported from `test_carddemo_signon_real.py`, the `FileBackend` import, and the ACCTDAT constants (record length, the account copybook path under `CARDDEMO_HOME`, the ACCT-ID of the rewritten record). Mirror those imports.

Create `tests/integration/cics/test_vsam_dump_e2e.py`:

```python
"""Gated e2e: a real CardDemo REWRITE, then decode the backing .dat via the dump CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

# Reuse the persistence test's gate + driver + constants. Copy the exact import
# lines and pytestmark from tests/integration/cics/test_vsam_persistence.py:
from tests.integration.cics.test_vsam_persistence import (  # noqa: F401
    pytestmark,  # the skipif gate
)
from tests.integration.cics.test_carddemo_signon_real import _drive_rewrite
from interpreter.cics.vsam.backend import FileBackend
from interpreter.cics.vsam.dump import load_record_layout, decode_record
from interpreter.cics.vsam.format import read_flat_file
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dump_decodes_rewritten_acctdat_status_n(tmp_path):
    import os

    backing = tmp_path / "store"
    _drive_rewrite(tmp_path, backend=FileBackend(backing))

    # Locate the real CardDemo account copybook (the one ACCTDAT records use).
    carddemo = Path(os.environ["CARDDEMO_HOME"])
    copybook = next(carddemo.rglob("CVACT01Y.cpy"))
    jar = os.environ["PROLEAP_BRIDGE_JAR"]

    layout = load_record_layout(copybook, None, jar, [])
    records = read_flat_file(backing / "ACCTDAT.dat", layout.total_bytes)
    decoded = [decode_record(layout, r) for r in records]

    target = [d for d in decoded if str(d["ACCT-ID"]).strip() == "00000000011"]
    assert target, "rewritten account not found in dumped records"
    assert target[0]["ACCT-ACTIVE-STATUS"] == "N"
```

> Adjust the field names (`ACCT-ID`, `ACCT-ACTIVE-STATUS`) to the actual names in `CVACT01Y.cpy` if they differ — open the copybook to confirm. The copybook member/file name (`CVACT01Y.cpy`) and the ACCT-ID value must match what `_drive_rewrite` seeds and rewrites (cross-check against `test_vsam_persistence.py`, which already asserts ACCT-ACTIVE-STATUS at offset 11 == "N" on disk).

- [ ] **Step 2: Run the test gated to verify it passes (env set)**

Run:
```bash
BMS_TOOLS_HOME=~/code/bms-tools CARDDEMO_HOME=/Users/asgupta/code/aws-mainframe-carddemo/app \
  poetry run python -m pytest tests/integration/cics/test_vsam_dump_e2e.py -v
```
Expected: PASS (1 passed). If field names differ, fix them per the copybook and re-run. This is the only way to verify (it needs the JAR + CardDemo + bms-tools).

- [ ] **Step 3: Run the full suite with env UNSET to verify it skips**

Run: `poetry run python -m pytest tests/integration/cics/test_vsam_dump_e2e.py -q`
Expected: `1 skipped` (gate not satisfied).

- [ ] **Step 4: Format, lint, commit**

```bash
poetry run python -m black tests/integration/cics/test_vsam_dump_e2e.py
poetry run lint-imports
git add tests/integration/cics/test_vsam_dump_e2e.py
git commit -m "test(vsam): gated e2e — dump CLI decodes a real REWRITE from the flat file"
```

---

## Final verification (after all tasks)

- [ ] Full suite green with env unset (e2e skips):
  `poetry run python -m pytest -q` — expect all pass, the new e2e skipped.
- [ ] `poetry run python -m black interpreter/cics/vsam/dump.py tests/unit/cics/test_vsam_dump.py tests/integration/cics/test_vsam_dump_e2e.py`
- [ ] `poetry run lint-imports` — 0 broken.
- [ ] Manual smoke (env set), confirm JSON-lines output:
  ```bash
  PROLEAP_BRIDGE_JAR=<jar> poetry run python -m interpreter.cics.vsam.dump \
    --data <some>.dat --copybook <CVACT01Y.cpy>
  ```
- [ ] Tree clean.

## Notes / out of scope (do not implement)

- COMP-1/COMP-2 (IEEE float) decode — `_decode_leaf` raises `NotImplementedError`; CardDemo does not use them.
- Sign-separate zoned decimal — `decode_zoned` handles embedded sign only; separate-sign fields will include the sign byte. Document as a known limitation; do not special-case (CardDemo uses embedded/unsigned).
- Built-in filtering/queries (use `jq`), encode/seed authoring, sidecar-layout JSON, no-copybook hexdump — all out of scope per the spec.
- Group-level OCCURS DEPENDING ON — decodes the fixed count (DataLayout has no `occurs_depending_on`); acceptable for v1.
