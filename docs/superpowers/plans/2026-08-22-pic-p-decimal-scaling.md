# PIC P Decimal Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record the `P` decimal-scaling factor a COBOL PICTURE declares, and apply it when encoding and decoding values, so P-scaled fields store the correct magnitude.

**Architecture:** Add a `scale: int` field to `CobolTypeDescriptor`, populated by the Lark transformer (which currently parses `P` and discards it). Encode divides by `10**scale`; decode multiplies. Both sites are guarded by `if td.scale:` so every field without `P` takes a path byte-identical to today. No Java change — the bridge computes only widths and offsets, and already excludes `S`/`V`/`P`.

**Tech Stack:** Python 3.13, Lark (earley parser), pytest, `uv` for all commands.

**Spec:** `docs/superpowers/specs/2026-08-22-pic-p-decimal-scaling-design.md`

## Global Constraints

- Use `uv run python -m pytest`, never bare `pytest`. Use `uv run python -m black`, never `uv run black`.
- Integration tests require `PROLEAP_BRIDGE_JAR`. Prefix commands with
  `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar`, or run via `make test`.
- `git commit` triggers a pre-commit hook that runs the FULL suite (~3 minutes). Never use the default 2-minute Bash timeout; use a long timeout or run it in the background.
- Every `test_*` method needs a `@covers(CobolFeature.MEMBER)` decorator. Import from `tests.covers`.
- **Never assert a P-scaled round trip.** `MOVE 900 TO WS-HI` then reading `WS-HI` back displays `900` correctly even against the CURRENT broken code, because the same wrong scale applies both ways. Assert STORED BYTES.
- Byte widths must not move. `P` is already excluded from the width on both sides (red-dragon-ilb6 for the bridge, red-dragon-5f4g for `parse_edit_picture`).
- Scale convention, from the spec:
  - trailing `P`: `scale = +count(P)` — `999PP` → `+2`, `S9PP` → `+2`
  - leading `P`: `scale = -(count(P) + count(digits))` — `PP9` → `-3`, `PP999` → `-5`
  - `value = stored_digits / 10**decimal_digits * 10**scale`

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `interpreter/cobol/cobol_types.py` | `CobolTypeDescriptor` | add `scale: int = 0` |
| `interpreter/cobol/pic_parser.py` | Lark grammar + transformer | record the `P` count and side; put `scale` on the descriptor |
| `interpreter/cobol/edit_picture.py` | edit-picture parse + format | compute `scale` for edited pictures (`ZZZPP`); divide in `format_edited` |
| `interpreter/cobol/emit_context.py` | IR emission | divide on encode (`emit_encode_numeric`), multiply on decode (`emit_decode_field`) |
| `tests/unit/cobol/test_pic_scaling.py` | NEW — unit + NIST cases | create |
| `tests/integration/test_cobol_pic_scaling.py` | NEW — stored-byte + layout | create |

---

### Task 1: Record the scale on the descriptor

**Files:**
- Modify: `interpreter/cobol/cobol_types.py`
- Modify: `interpreter/cobol/pic_parser.py`
- Test: `tests/unit/cobol/test_pic_scaling.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `CobolTypeDescriptor.scale: int` (default `0`); `parse_pic(pic, ...)` populates it.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cobol/test_pic_scaling.py`:

```python
"""PIC P decimal scaling (red-dragon-qhtv).

P positions denote decimal scaling: they occupy no storage but shift the
assumed decimal point. The scale convention (see the design doc) is

    trailing P:  scale = +count(P)
    leading  P:  scale = -(count(P) + count(digits))

so `999PP` holding stored digits '009' is the value 900, and `PP9` holding
stored digit '1' is the value .001.
"""

from __future__ import annotations

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.pic_parser import parse_pic
from tests.covers import covers


class TestScaleIsRecorded:
    @covers(CobolFeature.PIC_CLAUSE)
    @pytest.mark.parametrize(
        ("pic", "scale"),
        [
            ("999PP", 2),
            ("S9PP", 2),
            ("9PP", 2),
            ("PP9", -3),
            ("PP999", -5),
            ("PPP9", -4),
        ],
    )
    def test_scale_from_picture(self, pic: str, scale: int):
        assert parse_pic(pic).scale == scale

    @covers(CobolFeature.PIC_CLAUSE)
    def test_pictures_without_p_have_zero_scale(self):
        for pic in ("9(5)", "S9(5)V99", "X(8)", "$$,$$$.99", "ZZZ.99"):
            assert parse_pic(pic).scale == 0

    @covers(CobolFeature.PIC_CLAUSE)
    def test_leading_and_trailing_p_are_distinguishable(self):
        """These two pictures differ by a factor of 10**7 and returned
        IDENTICAL descriptors before this change."""
        assert parse_pic("999PP") != parse_pic("PP999")

    @covers(CobolFeature.PIC_CLAUSE)
    def test_scaling_does_not_change_byte_width(self):
        """P occupies no storage. The bridge excludes S/V/P from its uniform
        width rule, so Python must agree or record layouts diverge."""
        assert parse_pic("999PP").byte_length == 3
        assert parse_pic("PP999").byte_length == 3
        assert parse_pic("S9PP").byte_length == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_pic_scaling.py -q`
Expected: FAIL — `AttributeError: 'CobolTypeDescriptor' object has no attribute 'scale'`

- [ ] **Step 3: Add the field**

In `interpreter/cobol/cobol_types.py`, add to `CobolTypeDescriptor` (after `blank_when_zero`, before `pic_string`):

```python
    # PIC P decimal scaling: the value is stored_digits * 10**scale. Positive
    # for trailing P (999PP -> +2), negative for leading P (PP9 -> -3). P
    # occupies no storage, so this never affects byte_length (red-dragon-qhtv).
    scale: int = 0
```

- [ ] **Step 4: Record the scale in the transformer**

In `interpreter/cobol/pic_parser.py`, `_PicTransformer` currently drops the
`scaling` occurrences. Replace the `scaling` rule handler and `fraction` /
`scaling_only` methods so the count and side survive.

Add a marker class near `_Count`:

```python
@dataclass(frozen=True)
class _Scale:
    """One P scaling position, preserved so `fraction` can count them."""
```

Change the `scaling` handler to return one:

```python
    def scaling(self, items: list) -> _Scale:
        return _Scale()
```

Rewrite `fraction` to count `_Scale` markers on each side of the body. Lark
passes children in source order, so the body's index separates leading from
trailing:

```python
    def fraction(self, items: list) -> dict:
        signed = any(getattr(t, "type", None) == "SIGN" for t in items)
        body_index = next(i for i, x in enumerate(items) if isinstance(x, tuple))
        integer_digits, decimal_digits = items[body_index]
        leading = sum(1 for x in items[:body_index] if isinstance(x, _Scale))
        trailing = sum(1 for x in items[body_index + 1 :] if isinstance(x, _Scale))
        if leading and trailing:
            raise ValueError(
                "PIC scaling positions must be contiguous on ONE side of the "
                "digits; got P both before and after."
            )
        # Trailing P multiplies; leading P places the digits that many places
        # to the RIGHT of the assumed point, so the rightmost digit lands at
        # 10**-(P count + digit count).
        if trailing:
            scale = trailing
        elif leading:
            scale = -(leading + integer_digits + decimal_digits)
        else:
            scale = 0
        return {
            "alphanumeric": False,
            "integer_digits": integer_digits,
            "decimal_digits": decimal_digits,
            "signed": signed,
            "scale": scale,
        }
```

Update `scaling_only` to carry the key too (a picture of only P has no digits,
so the scale is meaningless but the key must exist):

```python
    def scaling_only(self, items: list) -> dict:
        # A picture of only P scaling positions (e.g. "P", "PPP", "SPP"): no
        # stored digit positions, so no value can be held and no scale applies.
        signed = any(getattr(t, "type", None) == "SIGN" for t in items)
        return {
            "alphanumeric": False,
            "integer_digits": 0,
            "decimal_digits": 0,
            "signed": signed,
            "scale": 0,
        }
```

Update `pointer` the same way — add `"scale": 0` to its returned dict.

- [ ] **Step 5: Put the scale on the descriptor**

In `parse_pic`, the final numeric return currently reads:

```python
    return CobolTypeDescriptor(
        category=category,
        total_digits=total_digits,
        decimal_digits=facts["decimal_digits"],
        signed=facts["signed"],
        sign_separate=sign_separate,
        sign_leading=sign_leading,
        blank_when_zero=blank_when_zero,
    )
```

Add `scale=facts.get("scale", 0),` as the last argument.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/cobol/test_pic_scaling.py -q`
Expected: PASS (4 test methods, 6 parametrised cases)

Then the whole COBOL unit suite:
Run: `uv run python -m pytest tests/unit/cobol/ -q`
Expected: PASS, no regressions

- [ ] **Step 7: Commit**

```bash
git add interpreter/cobol/cobol_types.py interpreter/cobol/pic_parser.py tests/unit/cobol/test_pic_scaling.py
git commit -m "feat: record PIC P decimal scaling on the type descriptor (red-dragon-qhtv)

The Lark grammar already parsed P as a scaling position and the transformer
threw it away, so 999PP and PP999 returned identical descriptors despite
differing by a factor of 10**7. The factor is now recorded; applying it is
the next commit."
```

---

### Task 2: Apply the scale when encoding

**Files:**
- Modify: `interpreter/cobol/emit_context.py` (`emit_encode_numeric`, near line 574)
- Test: `tests/unit/cobol/test_pic_scaling.py`

**Interfaces:**
- Consumes: `CobolTypeDescriptor.scale` from Task 1.
- Produces: encoding that divides the incoming value by `10**scale` before extracting digits.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/cobol/test_pic_scaling.py`:

```python
class TestEncodeAppliesScale:
    """Encoding divides by 10**scale, so the STORED digits are the value's
    significant digits, not the value itself.

    NIST-85 NC124A declares `01 WORK-AREA-30 PICTURE 999PP VALUE 00900.` and
    proves the stored content is '009' by moving it to ZZZPP and asserting
    '  9'.
    """

    @covers(CobolFeature.PIC_CLAUSE)
    @pytest.mark.parametrize(
        ("pic", "value", "stored"),
        [
            ("999PP", "900", "009"),
            ("999PP", "12300", "123"),
            ("999PP", "00900", "009"),
            ("999PP", "950", "009"),
            ("9PP", "200", "2"),
        ],
    )
    def test_stored_digits_are_scaled(self, pic: str, value: str, stored: str):
        assert encode_scaled_digits(value, parse_pic(pic)) == stored

    @covers(CobolFeature.PIC_CLAUSE)
    def test_unscaled_pictures_are_unchanged(self):
        """Regression guard: scale == 0 must leave the digits exactly as the
        pre-change code produced them."""
        assert encode_scaled_digits("12345", parse_pic("9(5)")) == "12345"
        assert encode_scaled_digits("123.45", parse_pic("9(3)V99")) == "12345"
```

Add the import at the top of the file:

```python
from interpreter.cobol.pic_scale import encode_scaled_digits
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_pic_scaling.py -q -k Encode`
Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.cobol.pic_scale'`

- [ ] **Step 3: Create the scaling helper**

Create `interpreter/cobol/pic_scale.py`. A separate module because both
`emit_context` (IR emission) and `edit_picture` (formatting) need the same
arithmetic, and neither should import the other:

```python
"""PIC P decimal scaling arithmetic (red-dragon-qhtv).

P positions occupy no storage but shift the assumed decimal point. The stored
digits are therefore the value divided by the scaling factor; reading the field
multiplies back. Both directions live here so the encode path (emit_context)
and the edit-picture formatter (edit_picture) share one implementation.
"""

from __future__ import annotations

from decimal import Decimal

from interpreter.cobol.cobol_types import CobolTypeDescriptor
from interpreter.cobol.data_filters import align_decimal, left_adjust


def descale(value: Decimal, scale: int) -> Decimal:
    """Value -> the number the digit positions actually hold.

    There is deliberately no `rescale` counterpart: decoding happens in emitted
    IR (a Binop multiply in emit_decode_field), not in Python, so a Python-side
    inverse would have no caller.
    """
    return value / (Decimal(10) ** scale) if scale else value


def encode_scaled_digits(value: str, td: CobolTypeDescriptor) -> str:
    """Return the digit characters stored for `value` in a field of type `td`.

    Divides by the scaling factor BEFORE truncating to the field's digit
    positions — order matters. 12300 into PIC 999PP is 123, not 300: dividing
    first keeps the significant digits, whereas truncating first keeps the
    low-order ones.
    """
    clean = value.lstrip("+-")
    if td.scale:
        scaled = descale(Decimal(clean), td.scale)
        # Truncate toward zero: COBOL does not round unless ROUNDED is given.
        clean = str(int(scaled)) if td.decimal_digits == 0 else str(scaled)
    integer_digits = td.total_digits - td.decimal_digits
    if td.decimal_digits > 0:
        return align_decimal(clean, integer_digits, td.decimal_digits)
    return left_adjust(clean.replace(".", ""), td.total_digits)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/cobol/test_pic_scaling.py -q -k Encode`
Expected: PASS

- [ ] **Step 5: Route emit_encode_numeric through the helper**

In `interpreter/cobol/emit_context.py`, `emit_encode_numeric` currently reads:

```python
        negative = value.startswith("-")
        clean = value.lstrip("+-")

        integer_digits = td.total_digits - td.decimal_digits
        if td.decimal_digits > 0:
            digit_str = align_decimal(clean, integer_digits, td.decimal_digits)
        else:
            digit_str = left_adjust(clean.replace(".", ""), td.total_digits)
```

Replace the four lines from `integer_digits = ...` through the `else` branch with:

```python
        digit_str = encode_scaled_digits(value, td)
```

Keep the `negative` line above it. Add the import:

```python
from interpreter.cobol.pic_scale import encode_scaled_digits
```

The `clean` local may now be unused — if so, delete that line too and let the
lint hook confirm.

- [ ] **Step 6: Run the suite**

Run: `uv run python -m pytest tests/unit/cobol/ -q`
Expected: PASS, no regressions. `encode_scaled_digits` reproduces the previous
behaviour exactly when `scale == 0`, which is every existing test.

- [ ] **Step 7: Commit**

```bash
git add interpreter/cobol/pic_scale.py interpreter/cobol/emit_context.py tests/unit/cobol/test_pic_scaling.py
git commit -m "feat: divide by the P scaling factor when encoding (red-dragon-qhtv)

PIC 999PP holding 12300 now stores '123' rather than '300' — dividing before
truncating keeps the significant digits instead of the low-order ones."
```

---

### Task 3: Apply the scale when decoding

**Files:**
- Modify: `interpreter/cobol/emit_context.py` (`emit_decode_field`, returns at line 691)
- Test: `tests/integration/test_cobol_pic_scaling.py` (create)

**Interfaces:**
- Consumes: `CobolTypeDescriptor.scale` from Task 1.
- Produces: decoded values multiplied by `10**scale`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_cobol_pic_scaling.py`:

```python
"""Integration: PIC P decimal scaling through the full pipeline.

Asserts STORED BYTES, never round trips. A round trip applies the same scale
in both directions and passes against the broken pre-fix code, so it proves
nothing (red-dragon-qhtv).

Expected values follow NIST-85 NC124A.CBL:
    01 WORK-AREA-27 PICTURE S9PP  VALUE 200    -> moved to X(3)   = "200"
    01 WORK-AREA-30 PICTURE 999PP VALUE 00900  -> moved to ZZZPP  = "  9"
    01 WORK-AREA-32 PICTURE PP9   VALUE .001   -> moved to V999   = .001
"""

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    run_cobol,
)
from tests.integration.cobol_helpers import (
    first_region as _first_region,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce PROLEAP_BRIDGE_JAR for run()-based tests."""


def _decode_chars(region, offset: int, length: int) -> str:
    return bytes(region[offset : offset + length]).decode("cp037")


def _run_scaled(pic: str, move_src: str):
    """A P-scaled field between PIC X(4) sentinels.

    Sentinels catch a width error at the same time: P occupies no storage, so
    the field must be exactly its digit count wide and the sentinels must not
    move (red-dragon-ilb6).
    """
    return run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. PSCALE.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-REC.",
            "   05 WS-BEFORE PIC X(4) VALUE 'AAAA'.",
            f"   05 WS-AMT PIC {pic}.",
            "   05 WS-AFTER PIC X(4) VALUE 'ZZZZ'.",
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            f"    MOVE {move_src} TO WS-AMT.",
            "    STOP RUN.",
        ],
        max_steps=20000,
    )


class TestScaledFieldStoresSignificantDigits:
    @covers(CobolFeature.PIC_CLAUSE, CobolFeature.MOVE)
    @pytest.mark.parametrize(
        ("pic", "value", "width", "stored"),
        [
            ("999PP", "900", 3, "009"),
            ("999PP", "12300", 3, "123"),
            ("9PP", "200", 1, "2"),
        ],
    )
    def test_stored_bytes(self, pic: str, value: str, width: int, stored: str):
        region = _first_region(_run_scaled(pic, value))
        assert _decode_chars(region, 0, 4) == "AAAA"
        assert _decode_chars(region, 4, width) == stored
        assert _decode_chars(region, 4 + width, 4) == "ZZZZ"

    @covers(CobolFeature.PIC_CLAUSE, CobolFeature.MOVE)
    def test_scaled_value_reads_back_at_full_magnitude(self):
        """NIST NC124A: 999PP holding 00900 moved to ZZZPP renders '  9' —
        three bytes of Z-suppressed STORED digits, P never displayed."""
        vm = run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. PSCALE2.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 WS-SRC PIC 999PP.",
                "01 WS-OUT PIC ZZZPP.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    MOVE 00900 TO WS-SRC.",
                "    MOVE WS-SRC TO WS-OUT.",
                "    STOP RUN.",
            ],
            max_steps=20000,
        )
        assert _decode_chars(_first_region(vm), 0, 3) == "009"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/integration/test_cobol_pic_scaling.py -q`
Expected: the `12300` case FAILS with stored `'300'` (Task 2 fixed the helper but
`emit_encode_numeric` only covers literal encoding; the MOVE path decodes and
re-encodes, so decode must apply the factor too).

- [ ] **Step 3: Multiply after the decode IR is inlined**

In `interpreter/cobol/emit_context.py`, `emit_decode_field` ends:

```python
        return self.inline_ir(ir, {"%p_data": data_reg})
```

Replace that single line with:

```python
        decoded = self.inline_ir(ir, {"%p_data": data_reg})
        if not td.scale:
            return decoded
        # PIC P: the stored digits are the value divided by the scaling factor,
        # so reading multiplies back. Applied HERE rather than inside the four
        # build_decode_*_ir builders — one site instead of four, and those
        # builders keep their existing signatures (red-dragon-qhtv).
        scaled = self.fresh_reg()
        factor_reg = self.const_to_reg(float(10**td.scale))
        self.emit_inst(
            Binop(
                result_reg=scaled,
                operator=resolve_binop("*"),
                left=decoded,
                right=factor_reg,
            )
        )
        return scaled
```

`Binop` is already imported (line 54) and `resolve_binop` is already imported
from `interpreter.operator_kind`. No new imports are needed for this step.

A float factor is deliberate: `10**-3` must not truncate to integer zero. The
existing decode sites use `float(10**decimal_digits)` for the same reason —
see the comment in `build_decode_zoned_ir`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/integration/test_cobol_pic_scaling.py -q`
Expected: PASS (4 cases)

- [ ] **Step 5: Prove the tests can fail**

They may pass on first run. Temporarily change `if not td.scale:` to
`if True:` in `emit_decode_field`, re-run the integration file, and confirm
failures. Then revert and confirm green again. Do NOT commit the perturbation.

- [ ] **Step 6: Run the full suite**

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest -q -p no:randomly`
Expected: PASS. Baseline before this work is 14906 passed, 66 skipped, 16 xfailed.

- [ ] **Step 7: Commit**

```bash
git add interpreter/cobol/emit_context.py tests/integration/test_cobol_pic_scaling.py
git commit -m "feat: multiply by the P scaling factor when decoding (red-dragon-qhtv)

Applied after the decode IR is inlined rather than threaded through all four
build_decode_*_ir builders — one site instead of four."
```

---

### Task 4: Scale edited pictures

**Files:**
- Modify: `interpreter/cobol/edit_picture.py`
- Test: `tests/unit/cobol/test_pic_scaling.py`

**Interfaces:**
- Consumes: `descale` from `interpreter/cobol/pic_scale.py` (Task 2).
- Produces: `parse_edit_picture(...).scale`; `format_edited` honouring it.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/cobol/test_pic_scaling.py`:

```python
class TestEditedPictureScaling:
    """P combines with EDITED pictures. NIST-85 NC124A declares
    `01 WORK-AREA-30A PICTURE ZZZPP` and asserts that 999PP holding 00900,
    moved into it, renders '  9' — three bytes, Z-suppressed STORED digits,
    with the P positions never displayed.
    """

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_edited_picture_records_scale(self):
        assert parse_edit_picture("ZZZPP").scale == 2

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_edited_picture_width_excludes_p(self):
        ep = parse_edit_picture("ZZZPP")
        assert ep.width == 3
        assert ep.int_digits == 3

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_nist_zzzpp_renders_stored_digits(self):
        assert format_edited("900", "ZZZPP") == "  9"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_unscaled_edited_pictures_unchanged(self):
        """Regression guard for every edited picture without P."""
        assert parse_edit_picture("ZZZ.99").scale == 0
        assert format_edited("1234", "$$,$$$.99") == "$1,234.00"
        assert format_edited("12.3", "**,***.99") == "****12.30"
```

Add to the imports at the top of the file:

```python
from interpreter.cobol.edit_picture import format_edited, parse_edit_picture
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_pic_scaling.py -q -k Edited`
Expected: FAIL — `EditPicture` has no attribute `scale`

- [ ] **Step 3: Compute the scale in parse_edit_picture**

In `interpreter/cobol/edit_picture.py`, `parse_edit_picture` currently begins:

```python
    template = [sym for sym in _expand(pic.upper()) if sym not in "SVP"]
```

That line drops the P positions before anything can count them. Replace it with:

```python
    raw_positions = _expand(pic.upper())
    scale = _scale_from_positions(raw_positions)
    template = [sym for sym in raw_positions if sym not in "SVP"]
```

Add the helper above `parse_edit_picture`:

```python
def _scale_from_positions(positions: list[str]) -> int:
    """PIC P scaling for an edited picture, using the same convention as
    pic_parser: trailing P multiplies, leading P divides (red-dragon-qhtv).
    """
    digits = sum(1 for c in positions if c in "9Z*")
    leading = 0
    for c in positions:
        if c == "P":
            leading += 1
        elif c in "9Z*":
            break
    trailing = 0
    for c in reversed(positions):
        if c == "P":
            trailing += 1
        elif c in "9Z*":
            break
    if leading and trailing:
        raise UnsupportedEditPictureError(
            f"PIC {''.join(positions)!r} has P scaling positions on BOTH sides "
            f"of its digits, which is not valid COBOL."
        )
    if trailing:
        return trailing
    if leading:
        return -(leading + digits)
    return 0
```

Add `scale: int = 0` to the `EditPicture` dataclass (after `trailing_sign`),
documenting it in the class docstring's Attributes list, and pass
`scale=scale` in the `EditPicture(...)` constructor call.

- [ ] **Step 4: Divide in format_edited**

In `format_edited`, immediately after the `Decimal` is built:

```python
    negative = dec < 0
    is_zero = dec == 0
```

insert before those two lines:

```python
    # PIC P: the field holds the value divided by the scaling factor, and the
    # P positions are never displayed. NIST NC124A: 999PP holding 900 moved to
    # ZZZPP renders '  9', not '900' (red-dragon-qhtv).
    dec = descale(dec, ep.scale)
```

Add the import at the top of `edit_picture.py`:

```python
from interpreter.cobol.pic_scale import descale
```

**Check for an import cycle first.** `pic_scale` imports `cobol_types` and
`data_filters`; `edit_picture` currently imports neither, and `cobol_types`
does not import `edit_picture`, so the direction should be clean. The
pre-commit `import-linter` hook is the authority — if it rejects the edge,
move `descale` into `edit_picture` and have `pic_scale` import it from there
rather than introducing a cycle.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/cobol/test_pic_scaling.py -q`
Expected: PASS

Run: `uv run python -m pytest tests/unit/cobol/ -q`
Expected: PASS — particularly `test_edit_picture_nist.py` (112 conformance
cases) and `test_currency_sign.py`, none of which use P.

- [ ] **Step 6: Commit**

```bash
git add interpreter/cobol/edit_picture.py tests/unit/cobol/test_pic_scaling.py
git commit -m "feat: apply P scaling to edited pictures (red-dragon-qhtv)

ZZZPP renders the Z-suppressed STORED digits with P never displayed, per
NIST-85 NC124A."
```

---

### Task 5: Verify parity and close out

**Files:**
- Modify: `interpreter/cobol/edit_picture.py` (module docstring only)
- Test: none new

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: nothing.

- [ ] **Step 1: Re-run the Python/Java width parity sweep**

`P` must still contribute zero bytes on both sides. Run:

```bash
uv run python - <<'PY'
import re, glob
pics=set()
files=[f for f in glob.glob('**/*.cbl',recursive=True)+glob.glob('**/*.cpy',recursive=True)
       if '.venv' not in f and 'worktrees' not in f]
pat=re.compile(r'\bPIC(?:TURE)?\s+(?:IS\s+)?([^\s.]+)',re.I)
for f in files:
    for line in open(f,encoding='utf-8',errors='replace'):
        if len(line)>6 and line[6:7] in ('*','/'): continue
        m=pat.search(line)
        if m: pics.add(m.group(1).upper().rstrip('.'))
pics |= {'999PP','PP999','S9PP','PP9','ZZZPP','9PP','PPP9'}
pics={p for p in pics if p and not re.search(r'[^0-9A-Z$*+\-,./()VSPZXA]', p)}
def java_uniform(p):
    out=[];i=0
    try:
        while i<len(p):
            if p[i]=='(':
                j=p.index(')',i); n=int(p[i+1:j]); out.extend([out[-1]]*(n-1)); i=j+1; continue
            out.append(p[i]); i+=1
    except Exception: return None
    return sum(1 for c in out if c not in 'SVP')
from interpreter.cobol.pic_parser import parse_pic
bad=[]
for p in sorted(pics):
    try: py=parse_pic(p).byte_length
    except Exception: continue
    jv=java_uniform(p)
    if jv is not None and py!=jv: bad.append((p,py,jv))
print(f"compared={len(pics)} mismatches={len(bad)}")
for b in bad: print("  ", b)
PY
```

Expected: `mismatches=0`.

- [ ] **Step 2: Update the edit_picture module docstring**

It currently says:

```
Still NOT supported: ``P`` scaling semantics (``P`` positions are correctly
excluded from the byte width, but the implied decimal-point shift they denote
is not applied to the value), and the ``CURRENCY SIGN IS`` /
``DECIMAL-POINT IS COMMA`` clauses (red-dragon-3o5f), so ``$`` and ``.`` are
hardcoded.
```

Replace with:

```
Still NOT supported: ``DECIMAL-POINT IS COMMA`` (red-dragon-j00c), so ``.``
is hardcoded as the decimal point and ``,`` as the grouping separator.
``P`` scaling is applied (red-dragon-qhtv) and ``CURRENCY SIGN IS`` is
honoured for a single-character symbol (red-dragon-3o5f).
```

- [ ] **Step 3: Run the full suite**

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest -q -p no:randomly`
Expected: PASS, count at or above the 14906 baseline.

- [ ] **Step 4: Format**

Run: `uv run python -m black interpreter/cobol/ tests/unit/cobol/test_pic_scaling.py tests/integration/test_cobol_pic_scaling.py`

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/edit_picture.py
git commit -m "docs: P scaling is implemented (red-dragon-qhtv)"
```

- [ ] **Step 6: Record the outcome on the issue**

```bash
bd update red-dragon-qhtv --append-notes "IMPLEMENTED <date>. scale field on CobolTypeDescriptor; encode divides, decode multiplies, edited pictures divide before formatting. Verified against the three NIST-85 NC124A cases, asserting STORED BYTES rather than round trips. Width parity with the bridge re-swept: zero mismatches. Full suite <count> passed."
```

---

## Notes for the executor

**The bug is invisible to round-trip tests.** `MOVE 900 TO WS-HI` followed by
`MOVE WS-HI TO WS-OUT` displays `900` correctly against the CURRENT broken
code, because the same wrong scale applies in both directions. If a test you
write passes before you have implemented anything, that is why — assert stored
bytes instead.

**Order matters in `encode_scaled_digits`.** Divide, then truncate. `12300`
into `PIC 999PP` is `123`; truncating first gives `300`.

**`P` never appears in output.** It occupies no storage and is not displayed.
`ZZZPP` is three bytes showing three Z-suppressed digits.

**Zero P-scaled pictures exist in the project corpus** (679 files, 79 distinct
pictures). Every test for this feature is one you write; there is no existing
coverage to lean on, and no existing program that will break if you get it
wrong — which also means no existing program will tell you that you did.
