# PIC P Decimal Scaling — Design

**Issue:** red-dragon-qhtv
**Date:** 2026-08-22
**Status:** approach approved; spec pending review; not yet implemented

## Problem

`P` positions in a PICTURE denote decimal scaling. RedDragon parses them,
correctly excludes them from the byte width, and then discards the scaling
factor. Nothing records it and nothing applies it, so a P-scaled field stores
and reads the wrong magnitude.

Verified on `main` (merge `adf40fa8`) by reading stored EBCDIC bytes:

| PIC | MOVE | stored | correct |
|-----|------|--------|---------|
| `999PP` | 900 | `'900'` | `'009'` |
| `999PP` | 12300 | `'300'` | `'123'` |
| `999PP` | 950 | `'950'` | `'009'` |

The `12300` case is the clearest: the field behaves as a plain `PIC 999`,
truncating high-order digits, instead of dividing by the scaling factor.

`parse_pic("999PP")` and `parse_pic("PP999")` currently return **identical**
descriptors — `total_digits=3, decimal_digits=0, byte_length=3` — despite the
two pictures differing by a factor of 10^7.

### Why it has gone unnoticed

It is invisible to a round-trip test. `MOVE 900 TO WS-HI` followed by
`MOVE WS-HI TO WS-OUT` displays `900` correctly, because the same wrong scale
is applied on the way in and on the way out. The corruption is only observable
in the stored bytes: file I/O, `REDEFINES`, group moves, comparison against a
literal, and `CALL ... BY REFERENCE`.

This is the same shape as red-dragon-ilb6 — correct-looking behaviour masking a
wrong stored representation.

### Root cause

`interpreter/cobol/pic_parser.py`'s Lark grammar parses `P` structurally:

```
SCALE: "P"i
scaling: SCALE
fraction: SIGN? scaling* body scaling*
        | SIGN? scaling+  -> scaling_only
```

but `_PicTransformer` discards it. `scaling_only` returns
`integer_digits=0, decimal_digits=0` with a comment acknowledging that "the
scaling shifts the implied decimal point" — and then does not record the shift.
The `scaling*` occurrences in the `fraction` rule are never consumed.

So the zero-storage half of `P` is correct and the scaling half was never
implemented.

## Semantics

Derived from NIST-85 `NC124A.CBL`, vendored at
`proleap-bridge/proleap-cobol-parser/src/test/resources/gov/nist/`.

```
trailing P:  scale = +count(P)                  999PP -> +2,  S9PP -> +2
leading  P:  scale = -(count(P) + count(digits)) PP9  -> -3,  PP999 -> -5

value = stored_digits / 10**decimal_digits * 10**scale
```

For a leading-`P` picture the assumed decimal point sits immediately left of the
leftmost `P`, so the rightmost digit lands at `10**-(P_count + digit_count)`.

Two edge cases, made explicit so the implementation does not have to guess:

- **`P` on both sides is not valid COBOL** — the scaling positions are
  contiguous on one side of the digits. The Lark grammar's
  `scaling* body scaling*` permits it syntactically, so the transformer should
  treat leading and trailing runs as mutually exclusive and, if both are
  somehow present, raise rather than silently pick one.
- **`V` with `P`** is redundant: the assumed decimal point is already fixed by
  the `P` run. Where both appear, `P` determines the scale and `V` contributes
  nothing, exactly as it contributes no storage today.

### Authoritative cases

`NC124A.CBL` declares these and asserts the results after a MOVE:

| source | PIC | VALUE | moved to | expected |
|--------|-----|-------|----------|----------|
| `WORK-AREA-27` | `S9PP` | 200 | `X(3)` | `"200"` |
| `WORK-AREA-30` | `999PP` | 00900 | `ZZZPP` | `"  9"` |
| `WORK-AREA-32` | `PP9` | .001 | `V999` | `.001` |

The middle case is the important one. `999PP` holding `00900` stores digits
`009`; moving it to `ZZZPP` renders `"  9"` — three bytes, Z-suppressed
**stored** digits, with the `P` positions never displayed. `P` changes the
value's magnitude but is invisible in output.

## Design

### `scale` is a distinct field, not folded into `decimal_digits`

Every P case is expressible as a negative `decimal_digits` (`999PP` = -2) or one
exceeding the digit count (`PP9` = 3), and the existing
`value = digits / 10**decimal_digits` would then do the arithmetic with no new
code. This was considered and **rejected**.

Nine sites across five files compute `integer_digits = total_digits -
decimal_digits`, each guarded by `if decimal_digits > 0`
(`zoned_decimal.py:39`, `binary.py:55`, `byte_builtins.py:265`, `comp3.py:40`,
`emit_context.py:581`, and the four `ir_encoders.py` decode builders). All of
them are on the hot path for **every** numeric COBOL field. Overloading
`decimal_digits` changes an invariant all nine depend on, to fix a construct
that appears **zero times** in the project corpus (679 files, 79 distinct
pictures, no P-scaled ones).

A separate `scale` field keeps the blast radius inside P-scaled pictures: every
other field has `scale == 0` and takes a path byte-identical to today.

### Components

**`interpreter/cobol/cobol_types.py`** — add `scale: int = 0` to
`CobolTypeDescriptor`. Positive for trailing `P`, negative for leading `P`.

**`interpreter/cobol/pic_parser.py`** — `_PicTransformer` consumes the
`scaling` occurrences it currently drops, recording the count and which side of
the body they fall on, and `parse_pic` puts the result on the descriptor.

**`interpreter/cobol/edit_picture.py`** — `parse_edit_picture` computes the same
scale for edited pictures such as `ZZZPP`, and `format_edited` divides by
`10**scale` before formatting. Width is unaffected: `S`/`V`/`P` are already
dropped from the template.

**`interpreter/cobol/emit_context.py`** — two sites, both guarded by
`if td.scale:`:
- encode: `emit_encode_numeric` divides by `10**scale` before digit extraction
- decode: multiplies by `10**scale` **after** the decode IR is inlined

Applying the decode factor after inlining, rather than threading a `scale`
parameter through all four `build_decode_*_ir` builders, keeps this to one site
instead of four and leaves `ir_encoders.py` untouched.

**No Java change.** The bridge computes offsets and widths only and already
excludes `S`/`V`/`P` from its uniform width rule (red-dragon-ilb6). It never
computes values.

### Behaviour change beyond magnitude

`12300` moved into `PIC 999PP` currently stores `300` (low-order truncation).
Correct is `123` — divide **first**, then truncate. So the fix changes which
digits survive an oversized move, not only the magnitude.

## Testing

**Assert stored bytes, never round trips.** A round trip applies the same wrong
scale both ways and passes against the current broken code. Any test that moves
a value into a P-scaled field and reads it back out of the same field proves
nothing.

- The three NIST cases above as the acceptance basis.
- `parse_pic("999PP").scale == 2` and `parse_pic("PP999").scale == -5` — the two
  descriptors must stop being equal.
- Width guard: `parse_pic("ZZZPP").byte_length == 3`, matching the bridge.
- Regression guard: a picture with no `P` produces a descriptor identical to
  today, including `scale == 0`.
- Integration tests using the sentinel record-layout pattern from
  `tests/integration/test_cobol_numeric_edited.py::TestEditedFieldInARecordLayout`
  — the edited field between two `PIC X(4)` fields, asserting exact offsets, so
  a width regression surfaces at the same time.
- Re-run the Python/Java width parity sweep (95 pictures, currently zero
  mismatches).

## Out of scope

- `CURRENCY SIGN IS` multi-character form — separate, width-affecting.
- `DECIMAL-POINT IS COMMA` — red-dragon-j00c.
- Any change to the bridge.

## Related

- red-dragon-ilb6 (closed) — excluded `S`/`V`/`P` from the bridge's width rule;
  this is the value half of the same symbol. Its fix is what exposed the Python
  side of the width half, corrected in red-dragon-5f4g.
- red-dragon-5f4g (closed) — established NIST-85 as the acceptance oracle for
  edit-picture semantics, and dropped `S`/`V`/`P` from `parse_edit_picture`'s
  template.
