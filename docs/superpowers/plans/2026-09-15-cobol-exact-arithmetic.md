# COBOL Exact Arithmetic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Python `float` in COBOL fixed-point arithmetic with exact values behind a single `cobol_numeric` boundary, following IBM `ARITH(COMPAT)` intermediate-precision rules.

**Architecture:** A new leaf package `cobol_numeric` owns the exact representation (`CobolNumber`, currently `Decimal`) and every conversion, scale rule and arithmetic operation; nothing else imports `decimal`. COBOL lowering computes IBM scales statically and emits boundary builtins (`__cobol_add/subtract/multiply/divide`, `__cobol_from_digits`, `__cobol_scale_by`, `__cobol_to_text`); decoders, literals and encoders switch to exact values; floating-point expressions (COMP-1/COMP-2, floating intrinsics) stay IEEE.

**Tech Stack:** Python 3.13, uv, pytest (xdist), import-linter, black, beads (`bd`).

**Spec:** `docs/superpowers/specs/2026-09-15-cobol-exact-arithmetic-design.md` (read it first; this plan argues from it).

## Global Constraints

- Work only in the worktree `/Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic` (branch `worktree-cobol-exact-arithmetic`). Use `/usr/bin/git -C <worktree>` if the shell hook refuses plain `git`.
- Every test command needs the bridge JAR: prefix `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar`.
- Targeted tests: `uv run python -m pytest <path> -q -n0`. Full suite: `make test` (≈5 min). Baseline before any change: 15198 passed, 66 skipped, 17 xfailed.
- `git commit` runs the full suite in a pre-commit hook: use a ≥10-minute timeout or run in the background.
- Format with `uv run python -m black .`; import contracts with `uv run lint-imports`.
- TDD: write the failing test first, run it, see it fail, then implement (TDD Guard is active).
- Every `test_*` function carries `@covers(...)` (`from tests.covers import covers, NotLanguageFeature`; COBOL features from `interpreter.cobol.features.CobolFeature`).
- COBOL-only: no behaviour change to `DefaultTypeConversionRules` existing pairs, `DefaultBinopCoercion`, `BINOP_TABLE`, or the generic `str` builtin.
- After Task 10, no module under `interpreter/`, `cobol_asg/`, `cobol_memory/`, `mcp_server/` other than `cobol_numeric/` imports `decimal` or constructs `Decimal`.
- `tests/unit/cobol/test_arithmetic_decimal_precision.py` must pass at every commit.
- ADRs in `docs/architectural-design-decisions.md` are append-only.
- Never name downstream/external codebases in tracked files.
- Division semantics are IBM, not GnuCOBOL: `2023 / 4 * 4` into `PIC 9(4)` must stay 2020.

## Task order (differs from spec step numbers — see spec "Ordering constraint")

| Task | Spec step | Deliverable |
|---|---|---|
| 0 | — | NIST-85 arithmetic baseline recorded on red-dragon-4q25.1 |
| 1 | 1 | `cobol_numeric` package + contract + unit tests |
| 2 | 2 | `Decimal` type, `Const.decimal_`, flat CONST branch, serialization |
| 3 | 3 | Unified encode digits (closes bqds), `__cobol_to_text`, IS NUMERIC contract |
| 4 | 6 | IBM scale analysis + exact arithmetic builtins; `force_division_float` deleted |
| 5 | 4+5 | Exact decode (closes 0dvs), PIC P, literals, lowering `float()` removal |
| 6 | 7+8 | Remaining builtins, intrinsics, COMP-1/COMP-2 boundary, edit pictures |
| 7 | 9 | Guard step removed (closes 5b93) |
| 8 | 10 | `decimal` boundary invariant test |
| 9 | docs | ADR-148, ADR-149, ADR-146 amendment, cobol.md, type-system.md |
| 10 | measure | NIST-85 after-measurement recorded |

## File Structure

| File | Responsibility |
|---|---|
| `cobol_numeric/__init__.py` (create) | Package docstring; re-exports |
| `cobol_numeric/number.py` (create) | `CobolNumber`, conversions, exact `add/subtract/multiply/divide`, truncation/rounding, encode digits, text |
| `cobol_numeric/scale.py` (create) | `Scale`, `add_scale`, `mul_scale`, `div_scale`, `carry`, `literal_scale` |
| `cobol_numeric/intrinsics.py` (create, Task 6) | Decimal math used by COBOL intrinsic builtins |
| `interpreter/cobol/arithmetic_scale.py` (create, Task 4) | Static per-expression `Scale`/`dmax` and floating-point classification |
| `interpreter/cobol/numeric_builtins.py` (create, Task 3/4/5) | Builtins backed by `cobol_numeric` (`__cobol_add` …, `__cobol_to_text`, `__cobol_from_digits`, `__cobol_scale_by`) |
| `.importlinter`, `pyproject.toml` (modify) | Root package, leaf contract, wheel packages |
| `interpreter/cobol/cobol_constants.py` (modify) | New `BuiltinName` members |
| `interpreter/cobol/byte_builtins.py` (modify) | Register numeric builtins; migrate Decimal code |
| `interpreter/cobol/pic_scale.py` (modify) | Thin wrapper over `digits_for_encode` |
| `interpreter/cobol/emit_context.py`, `ir_encoders.py`, `lower_arithmetic.py`, `condition_lowering.py` (modify) | Lowering changes |
| `interpreter/constants.py`, `types/type_graph.py`, `instructions.py`, `vm/vm_types.py` (modify) | Type plumbing |
| `cobol_asg/edit_picture.py` (modify) | Migrate Decimal parsing/digits |

---

### Task 0: Record the NIST-85 arithmetic baseline

**Files:** none (records to beads).

- [ ] **Step 1: Run the tracer on the arithmetic programs**

Run (from the worktree):
```bash
PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python scripts/nist_ccvs_tracer.py NC121M NC207A NC220M NC123A NC117A 2>&1 | tail -60 > /tmp/nist-arith-before.txt; cat /tmp/nist-arith-before.txt
```
Expected: a `=== N programs with traced failures, M failing assertions ===` block plus RE-MARK/FEATURE clusters.

- [ ] **Step 2: Append the baseline to the issue**

```bash
bd update red-dragon-4q25.1 --append-notes "NIST-85 arithmetic baseline (before, worktree base 96651c84): $(head -3 /tmp/nist-arith-before.txt | tr '\n' ' ')"
```
Keep `/tmp/nist-arith-before.txt` for Task 10.

---

### Task 1: `cobol_numeric` package

**Files:**
- Create: `cobol_numeric/__init__.py`, `cobol_numeric/number.py`, `cobol_numeric/scale.py`
- Modify: `.importlinter` (root_packages + new contract), `pyproject.toml` (`[tool.hatch.build.targets.wheel] packages`, `[tool.coverage.run] source`)
- Test: `tests/unit/cobol/test_cobol_numeric_number.py`, `tests/unit/cobol/test_cobol_numeric_scale.py`

**Interfaces:**
- Consumes: nothing.
- Produces (exact names used by later tasks):
  - `cobol_numeric.number`: `CobolNumber` (alias of `Decimal`), `NumberLike = int | CobolNumber`, `is_cobol_number(x: object) -> bool`, `to_number(x: int | float | str | CobolNumber) -> CobolNumber` (raises `ValueError` for non-numeric text/non-finite floats, `TypeError` otherwise), `from_digits(digits: int, decimal_digits: int) -> CobolNumber`, `scale_by(value: NumberLike, scale: int) -> CobolNumber`, `from_literal(text: str) -> CobolNumber` (raises `ValueError`), `from_float(value: float) -> CobolNumber` (raises `ValueError`), `to_float(value: NumberLike) -> float`, `truncate_to(value, decimal_places: int) -> CobolNumber`, `round_half_up(value, decimal_places: int) -> CobolNumber`, `add/subtract/multiply(a, b, result_decimals: int) -> CobolNumber`, `divide(dividend, divisor, quotient_decimals: int) -> CobolNumber` (raises `ZeroDivisionError`), `digits_for_encode(value, total_digits: int, decimal_digits: int, scale: int = 0) -> tuple[bool, str]`, `to_plain_str(value: NumberLike) -> str`, `as_whole_int(value: NumberLike) -> int | None`.
  - `cobol_numeric.scale`: `Scale(integer_places: int, decimal_places: int)` (frozen dataclass), `COMPAT_DIGIT_LIMIT = 30`, `add_scale(a, b)`, `mul_scale(a, b)`, `div_scale(dividend, divisor, dmax)`, `carry(scale, dmax, limit=COMPAT_DIGIT_LIMIT)`, `literal_scale(text: str) -> Scale`.

- [ ] **Step 1: Write the failing number tests**

Create `tests/unit/cobol/test_cobol_numeric_number.py`:

```python
"""cobol_numeric.number — the exact COBOL value boundary (red-dragon-4q25.1)."""

from __future__ import annotations

import pytest

from cobol_numeric.number import (
    add,
    as_whole_int,
    digits_for_encode,
    divide,
    from_digits,
    from_float,
    from_literal,
    is_cobol_number,
    multiply,
    round_half_up,
    scale_by,
    subtract,
    to_float,
    to_number,
    to_plain_str,
    truncate_to,
)
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_digits_places_the_implied_decimal_point():
    assert from_digits(12345, 2) == from_literal("123.45")
    assert to_plain_str(from_digits(12345, 2)) == "123.45"
    assert to_plain_str(from_digits(-5, 3)) == "-0.005"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_digits_keeps_trailing_zeros_of_the_scale():
    assert to_plain_str(from_digits(80, 2)) == "0.80"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_scale_by_shifts_without_rounding_beyond_28_digits():
    big = from_literal("123456789012345678901234567890.5")
    assert to_plain_str(scale_by(big, 2)) == "12345678901234567890123456789050"
    assert to_plain_str(scale_by(123, -3)) == "0.123"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_literal_accepts_cobol_fixed_point_literals():
    assert to_plain_str(from_literal("+0.007")) == "0.007"
    assert to_plain_str(from_literal("-12")) == "-12"
    assert to_plain_str(from_literal(".5")) == "0.5"


@pytest.mark.parametrize("text", ["", ".", "1.2.3", "1E5", "NaN", "ABC", "+-1", " "])
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_literal_rejects_non_literals(text):
    with pytest.raises(ValueError):
        from_literal(text)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_float_uses_the_shortest_round_trip_repr():
    assert to_plain_str(from_float(76.59999999999994)) == "76.59999999999994"
    assert to_plain_str(from_float(1e-05)) == "0.00001"
    with pytest.raises(ValueError):
        from_float(float("inf"))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_to_number_normalises_migration_inputs():
    assert to_number(7) == 7
    assert to_number(0.5) == from_literal("0.5")
    assert to_number(" 12.50 ") == from_literal("12.50")
    with pytest.raises(ValueError):
        to_number("SPACES")
    with pytest.raises(TypeError):
        to_number(True)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_is_cobol_number():
    assert is_cobol_number(3)
    assert is_cobol_number(from_literal("1.5"))
    assert not is_cobol_number(True)
    assert not is_cobol_number(1.5)
    assert not is_cobol_number("1")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_to_float():
    assert to_float(from_literal("0.25")) == 0.25


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_truncate_to_truncates_toward_zero():
    assert to_plain_str(truncate_to(from_literal("1.239"), 2)) == "1.23"
    assert to_plain_str(truncate_to(from_literal("-1.239"), 2)) == "-1.23"
    assert to_plain_str(truncate_to(from_literal("0.129999999"), 2)) == "0.12"
    assert to_plain_str(truncate_to(5, 2)) == "5.00"
    assert to_plain_str(truncate_to(from_literal("-0.001"), 2)) == "0.00"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_round_half_up_rounds_ties_away_from_zero():
    assert to_plain_str(round_half_up(from_literal("1.235"), 2)) == "1.24"
    assert to_plain_str(round_half_up(from_literal("1.234"), 2)) == "1.23"
    assert to_plain_str(round_half_up(from_literal("-1.235"), 2)) == "-1.24"
    assert to_plain_str(round_half_up(from_literal("2.7"), 0)) == "3"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_add_subtract_are_exact_and_truncate_to_result_decimals():
    assert to_plain_str(add(from_literal("0.1"), from_literal("0.7"), 2)) == "0.80"
    assert to_plain_str(add(from_literal("38.30"), from_literal("38.30"), 2)) == "76.60"
    assert to_plain_str(subtract(2023, 2020, 0)) == "3"
    thirty = from_literal("999999999999999999.999999999999")
    assert to_plain_str(add(thirty, from_literal("0.000000000001"), 12)) == (
        "1000000000000000000.000000000000"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_multiply_is_exact_beyond_28_significant_digits():
    a = from_literal("123456789.123456789")
    b = from_literal("987654321.987654321")
    assert to_plain_str(multiply(a, b, 18)) == "121932631356500531.347203169112635269"
    assert to_plain_str(multiply(from_literal("4.35"), 100, 2)) == "435.00"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_divide_truncates_to_quotient_decimals():
    assert to_plain_str(divide(2023, 4, 0)) == "505"
    assert to_plain_str(divide(7, 2, 1)) == "3.5"
    assert to_plain_str(divide(1, 3, 9)) == "0.333333333"
    assert to_plain_str(divide(-7, 2, 0)) == "-3"
    assert to_plain_str(divide(from_literal("0.99999999999999999999999999999999"), 1, 2)) == "0.99"
    with pytest.raises(ZeroDivisionError):
        divide(1, 0, 2)


@pytest.mark.parametrize(
    "value, total, decimals, scale, expected",
    [
        ("123.45", 5, 2, 0, (False, "12345")),
        ("-123.45", 5, 2, 0, (True, "12345")),
        ("1.237", 5, 2, 0, (False, "00123")),
        ("12.5", 3, 0, 0, (False, "012")),
        ("12300", 3, 0, 2, (False, "123")),
        ("123456", 3, 0, 0, (False, "456")),
        ("-0.001", 3, 2, 0, (True, "000")),
        ("0", 3, 0, 0, (False, "000")),
        ("0.00001", 6, 5, 0, (False, "000001")),
        ("0.000123", 3, 0, -3, (False, "123")),
        ("5", 0, 0, 0, (False, "")),
    ],
)
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_digits_for_encode(value, total, decimals, scale, expected):
    assert digits_for_encode(from_literal(value), total, decimals, scale) == expected


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_digits_for_encode_accepts_int():
    assert digits_for_encode(7, 3, 0) == (False, "007")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_to_plain_str_never_uses_exponent_notation():
    for value in [scale_by(1, -10), scale_by(123, 3), scale_by(-1, -5), from_digits(0, 2)]:
        rendered = to_plain_str(value)
        assert "E" not in rendered and "e" not in rendered
    assert to_plain_str(scale_by(1, -10)) == "0.0000000001"
    assert to_plain_str(scale_by(123, 3)) == "123000"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_as_whole_int():
    assert as_whole_int(from_literal("12.00")) == 12
    assert as_whole_int(from_literal("12.50")) is None
    assert as_whole_int(-4) == -4
```

- [ ] **Step 2: Write the failing scale tests**

Create `tests/unit/cobol/test_cobol_numeric_scale.py`:

```python
"""cobol_numeric.scale — IBM ARITH(COMPAT) places-carried rules."""

from __future__ import annotations

from cobol_numeric.scale import (
    COMPAT_DIGIT_LIMIT,
    Scale,
    add_scale,
    carry,
    div_scale,
    literal_scale,
    mul_scale,
)
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_add_scale():
    assert add_scale(Scale(3, 2), Scale(5, 0)) == Scale(6, 2)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_mul_scale():
    assert mul_scale(Scale(9, 9), Scale(9, 9)) == Scale(18, 18)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_div_scale_uses_dmax_when_larger():
    # 2023 / 4 into PIC 9(4): d = max(0 - 0, 0) = 0
    assert div_scale(Scale(4, 0), Scale(1, 0), dmax=0) == Scale(4, 0)
    # 7 / 2 into PIC 9V9: d = max(0 - 0, 1) = 1
    assert div_scale(Scale(1, 0), Scale(1, 0), dmax=1) == Scale(1, 1)
    # dividend decimals exceed divisor decimals
    assert div_scale(Scale(3, 4), Scale(2, 1), dmax=2) == Scale(4, 3)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_carry_within_limit_is_identity():
    assert carry(Scale(18, 12), dmax=2) == Scale(18, 12)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_carry_table_rows():
    assert COMPAT_DIGIT_LIMIT == 30
    # i + d > 30, d <= dmax -> 30 - d integer, d decimal
    assert carry(Scale(29, 3), dmax=3) == Scale(27, 3)
    # d > dmax, i + dmax <= 30 -> i integer, 30 - i decimal
    assert carry(Scale(18, 18), dmax=2) == Scale(18, 12)
    # d > dmax, i + dmax > 30 -> 30 - dmax integer, dmax decimal
    assert carry(Scale(29, 5), dmax=4) == Scale(26, 4)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_literal_scale():
    assert literal_scale("2023") == Scale(4, 0)
    assert literal_scale("-0.007") == Scale(1, 3)
    assert literal_scale(".5") == Scale(1, 1)
```

- [ ] **Step 3: Run both test files to verify they fail**

Run: `uv run python -m pytest tests/unit/cobol/test_cobol_numeric_number.py tests/unit/cobol/test_cobol_numeric_scale.py -q -n0`
Expected: collection errors `ModuleNotFoundError: No module named 'cobol_numeric'`.

- [ ] **Step 4: Create the package**

`cobol_numeric/__init__.py`:
```python
"""Exact COBOL numeric values, importable without the interpreter.

Every conversion between a COBOL representation (stored digits, literals,
text, IEEE floats) and the exact value, every IBM ARITH(COMPAT) scale rule,
and every exact arithmetic operation lives in this package. It is the only
code that imports ``decimal``; replacing the representation means editing this
package alone. It is a sibling of ``cobol_asg`` for the same reason as
``cobol_memory``: ``interpreter.anything`` loads the VM. See ``.importlinter``.
"""
```

`cobol_numeric/number.py`:
```python
# pyright: standard
"""CobolNumber — the exact representation of COBOL fixed-point values.

All arithmetic is done on exact integer ratios, never through the ``decimal``
context: the default context rounds results to 28 significant digits, while
IBM ARITH(COMPAT) intermediates carry up to 30.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import TypeAlias

CobolNumber: TypeAlias = Decimal
NumberLike: TypeAlias = int | Decimal

_ASCII_DIGITS = frozenset("0123456789")


def is_cobol_number(value: object) -> bool:
    """True for exact COBOL numeric values: ``int`` (not ``bool``) or ``CobolNumber``."""
    return not isinstance(value, bool) and isinstance(value, (int, Decimal))


def _exact(value: object) -> Decimal:
    if not is_cobol_number(value):
        raise TypeError(f"not a COBOL number: {value!r}")
    return Decimal(value)  # type: ignore[arg-type]


def _ratio(value: object) -> tuple[int, int]:
    """Exact (numerator, positive denominator)."""
    return _exact(value).as_integer_ratio()


def _from_scaled_int(unscaled: int, decimal_places: int) -> CobolNumber:
    """``unscaled × 10^-decimal_places``, built exactly (string construction is
    not subject to the context precision)."""
    return Decimal(f"{unscaled}E{-decimal_places}")


def _truncate_ratio(numerator: int, denominator: int, decimal_places: int) -> CobolNumber:
    """numerator/denominator truncated toward zero to ``decimal_places``."""
    if decimal_places < 0:
        raise ValueError(f"decimal_places must be >= 0, got {decimal_places}")
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    scaled = numerator * 10**decimal_places
    magnitude = abs(scaled) // denominator
    return _from_scaled_int(-magnitude if scaled < 0 else magnitude, decimal_places)


def from_digits(digits: int, decimal_digits: int) -> CobolNumber:
    """Stored digits (sign applied) with ``decimal_digits`` implied places."""
    if decimal_digits < 0:
        raise ValueError(f"decimal_digits must be >= 0, got {decimal_digits}")
    return _from_scaled_int(digits, decimal_digits)


def scale_by(value: NumberLike, scale: int) -> CobolNumber:
    """``value × 10^scale`` (PIC P scaling); an exponent shift, never rounded."""
    sign, digits, exponent = _exact(value).as_tuple()
    assert isinstance(exponent, int)
    return Decimal((sign, digits, exponent + scale))


def from_literal(text: str) -> CobolNumber:
    """Parse a COBOL fixed-point numeric literal: optional sign, digits, at most one '.'."""
    stripped = text.strip()
    body = stripped[1:] if stripped[:1] in ("+", "-") else stripped
    digits = body.replace(".", "", 1)
    if not digits or not set(digits) <= _ASCII_DIGITS:
        raise ValueError(f"not a COBOL fixed-point literal: {text!r}")
    return Decimal(stripped)


def from_float(value: float) -> CobolNumber:
    """The exact decimal of the float's shortest round-trip representation."""
    if not math.isfinite(value):
        raise ValueError(f"non-finite float: {value!r}")
    return Decimal(repr(value))


def to_number(value: object) -> CobolNumber:
    """Normalise an arithmetic operand: exact numbers, floats, or numeric text."""
    if isinstance(value, float):
        return from_float(value)
    if isinstance(value, str):
        return from_literal(value)
    return _exact(value)


def to_float(value: NumberLike) -> float:
    return float(_exact(value))


def truncate_to(value: NumberLike, decimal_places: int) -> CobolNumber:
    return _truncate_ratio(*_ratio(value), decimal_places)


def round_half_up(value: NumberLike, decimal_places: int) -> CobolNumber:
    """Round to ``decimal_places``, ties away from zero (COBOL ROUNDED)."""
    numerator, denominator = _ratio(value)
    magnitude = (2 * abs(numerator) * 10**decimal_places + denominator) // (2 * denominator)
    return _from_scaled_int(-magnitude if numerator < 0 else magnitude, decimal_places)


def add(a: NumberLike, b: NumberLike, result_decimals: int) -> CobolNumber:
    an, ad = _ratio(a)
    bn, bd = _ratio(b)
    return _truncate_ratio(an * bd + bn * ad, ad * bd, result_decimals)


def subtract(a: NumberLike, b: NumberLike, result_decimals: int) -> CobolNumber:
    an, ad = _ratio(a)
    bn, bd = _ratio(b)
    return _truncate_ratio(an * bd - bn * ad, ad * bd, result_decimals)


def multiply(a: NumberLike, b: NumberLike, result_decimals: int) -> CobolNumber:
    an, ad = _ratio(a)
    bn, bd = _ratio(b)
    return _truncate_ratio(an * bn, ad * bd, result_decimals)


def divide(dividend: NumberLike, divisor: NumberLike, quotient_decimals: int) -> CobolNumber:
    an, ad = _ratio(dividend)
    bn, bd = _ratio(divisor)
    if bn == 0:
        raise ZeroDivisionError("COBOL division by zero")
    return _truncate_ratio(an * bd, ad * bn, quotient_decimals)


def digits_for_encode(
    value: NumberLike, total_digits: int, decimal_digits: int, scale: int = 0
) -> tuple[bool, str]:
    """``(negative, digit_str)`` stored for ``value`` in a field of ``total_digits``
    with ``decimal_digits`` implied places and PIC P ``scale``.

    Divides by the scaling factor, truncates toward zero to ``decimal_digits``,
    and keeps the low-order ``total_digits`` (COBOL high-order truncation).
    ``negative`` is the sign of the value before truncation, matching the
    runtime sign-nibble builtin (a value like -0.001 keeps a negative sign).
    """
    exact = _exact(value)
    stored = truncate_to(scale_by(exact, -scale), decimal_digits)
    unscaled = abs(int(scale_by(stored, decimal_digits)))
    digit_str = str(unscaled).rjust(total_digits, "0")[-total_digits:] if total_digits else ""
    return exact < 0, digit_str


def to_plain_str(value: NumberLike) -> str:
    """Plain decimal text: optional '-', digits, optional '.' and digits; never an exponent."""
    return format(_exact(value), "f")


def as_whole_int(value: NumberLike) -> int | None:
    numerator, denominator = _ratio(value)
    return numerator if denominator == 1 else None
```

`cobol_numeric/scale.py`:
```python
# pyright: standard
"""IBM ARITH(COMPAT) places carried for fixed-point intermediate results.

Source: IBM COBOL reference "Fixed-point data and intermediate results"
(rpinr04) and "Terminology used for intermediate results" (rpinr03). In a
division, op1 is the divisor and op2 the dividend.
"""

from __future__ import annotations

from dataclasses import dataclass

COMPAT_DIGIT_LIMIT = 30


@dataclass(frozen=True)
class Scale:
    integer_places: int
    decimal_places: int


def add_scale(a: Scale, b: Scale) -> Scale:
    return Scale(
        max(a.integer_places, b.integer_places) + 1,
        max(a.decimal_places, b.decimal_places),
    )


def mul_scale(a: Scale, b: Scale) -> Scale:
    return Scale(a.integer_places + b.integer_places, a.decimal_places + b.decimal_places)


def div_scale(dividend: Scale, divisor: Scale, dmax: int) -> Scale:
    return Scale(
        dividend.integer_places + divisor.decimal_places,
        max(dividend.decimal_places - divisor.decimal_places, dmax),
    )


def carry(scale: Scale, dmax: int, limit: int = COMPAT_DIGIT_LIMIT) -> Scale:
    i, d = scale.integer_places, scale.decimal_places
    if i + d <= limit:
        return scale
    if d <= dmax:
        return Scale(limit - d, d)
    if i + dmax <= limit:
        return Scale(i, limit - i)
    return Scale(limit - dmax, dmax)


def literal_scale(text: str) -> Scale:
    body = text.strip().lstrip("+-")
    integer_part, _, fraction_part = body.partition(".")
    return Scale(max(len(integer_part), 1), len(fraction_part))
```

- [ ] **Step 5: Register the package**

In `.importlinter`, change `root_packages` to:
```
root_packages =
    interpreter
    cobol_asg
    cobol_memory
    cobol_numeric
```
and append after the `cobol-memory-is-a-leaf` contract:
```
[importlinter:contract:cobol-numeric-is-a-leaf]
name = The COBOL numeric boundary must not import the interpreter
type = forbidden
source_modules =
    cobol_numeric
forbidden_modules =
    interpreter
```
In `pyproject.toml`: `packages = ["interpreter", "cobol_asg", "cobol_memory", "cobol_numeric"]` and `source = ["interpreter", "cobol_asg", "cobol_numeric"]`.

Run: `uv sync && uv run python -c "import cobol_numeric.number, cobol_numeric.scale; print('ok')"`
Expected: `ok`.

- [ ] **Step 6: Run tests, contracts and formatter**

Run: `uv run python -m pytest tests/unit/cobol/test_cobol_numeric_number.py tests/unit/cobol/test_cobol_numeric_scale.py -q -n0 && uv run lint-imports && uv run python -m black cobol_numeric tests/unit/cobol/test_cobol_numeric_number.py tests/unit/cobol/test_cobol_numeric_scale.py`
Expected: all tests PASS; `Contracts: ... kept, 0 broken`.

- [ ] **Step 7: Commit**

```bash
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic add cobol_numeric .importlinter pyproject.toml uv.lock tests/unit/cobol/test_cobol_numeric_number.py tests/unit/cobol/test_cobol_numeric_scale.py docs/superpowers/specs/2026-09-15-cobol-exact-arithmetic-design.md docs/superpowers/plans/2026-09-15-cobol-exact-arithmetic.md
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic commit -m "feat(cobol-numeric): exact COBOL value boundary and IBM scale rules (red-dragon-4q25.1)"
```
(Add the session's Co-Authored-By trailer.)

---

### Task 2: `Decimal` type, `Const.decimal_`, flat CONST, serialization

**Files:**
- Modify: `interpreter/constants.py` (`FoundationTypeName`), `interpreter/types/type_graph.py` (`DEFAULT_TYPE_NODES`), `interpreter/instructions.py` (`Const` docstring + factory, `_const`), `interpreter/vm/vm_types.py` (`_serialize_value`)
- Test: `tests/unit/cobol/test_decimal_type_plumbing.py`

**Interfaces:**
- Consumes: `cobol_numeric.number.from_literal`, `is_cobol_number`, `to_plain_str`, `CobolNumber` (Task 1).
- Produces: `FoundationTypeName.DECIMAL` (`TypeName("Decimal")`); `Const.decimal_(result_reg: Register, value: CobolNumber, **kw) -> Const` typed `scalar(FoundationTypeName.DECIMAL)`; flat CONST `literal_type == "Decimal"`; `_serialize_value` renders `CobolNumber` via `to_plain_str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/cobol/test_decimal_type_plumbing.py`:

```python
"""Shared-code plumbing for exact COBOL values (red-dragon-4q25.1)."""

from __future__ import annotations

from types import SimpleNamespace

from cobol_numeric.number import from_literal
from interpreter.constants import FoundationTypeName
from interpreter.instructions import Const, _const
from interpreter.ir import NO_SOURCE_LOCATION
from interpreter.register import Register
from interpreter.types.type_expr import scalar
from interpreter.types.type_graph import DEFAULT_TYPE_NODES
from interpreter.types.typed_value import runtime_type_name, typed
from interpreter.vm.vm_types import _serialize_value
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decimal_is_a_number_in_the_type_graph():
    nodes = {node.name: node for node in DEFAULT_TYPE_NODES}
    assert str(FoundationTypeName.DECIMAL) == "Decimal"
    assert nodes[FoundationTypeName.DECIMAL].parents == (FoundationTypeName.NUMBER,)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_const_decimal_factory_is_typed_decimal():
    inst = Const.decimal_(Register("%0"), from_literal("0.80"))
    assert inst.type_expr == scalar(FoundationTypeName.DECIMAL)
    assert inst.value == from_literal("0.80")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_flat_const_with_decimal_literal_type():
    flat = SimpleNamespace(
        result_reg=Register("%0"),
        operands=["1.50"],
        source_location=NO_SOURCE_LOCATION,
        literal_type="Decimal",
    )
    inst = _const(flat)
    assert inst.type_expr == scalar(FoundationTypeName.DECIMAL)
    assert inst.value == from_literal("1.50")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cobol_number_is_never_coerced_by_runtime_type_name():
    assert runtime_type_name(from_literal("1.5")) == ""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cobol_number_serializes_as_plain_text():
    value = typed(from_literal("0.80"), scalar(FoundationTypeName.DECIMAL))
    assert _serialize_value(value) == "0.80"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/unit/cobol/test_decimal_type_plumbing.py -q -n0`
Expected: FAIL — `AttributeError: type object 'FoundationTypeName' has no attribute 'DECIMAL'` (collection or first test).

- [ ] **Step 3: Implement**

`interpreter/constants.py`, in `class FoundationTypeName`, after `FLOAT = TypeName("Float")`:
```python
    DECIMAL = TypeName("Decimal")
```

`interpreter/types/type_graph.py`, in `DEFAULT_TYPE_NODES`, after the `FLOAT` node:
```python
    TypeNode(name=FoundationTypeName.DECIMAL, parents=(FoundationTypeName.NUMBER,)),
```

`interpreter/instructions.py`:
- Add import near the other imports: `from cobol_numeric.number import CobolNumber, from_literal`
- In the `Const` class docstring, change the factory list to `(``Const.int_``, ``Const.float_``, ``Const.decimal_``, ``Const.string``, ``Const.bool_``, ``Const.null_``, ``Const.func_ref``, ``Const.class_ref``)`.
- After `float_`, add:
```python
    @classmethod
    def decimal_(cls, result_reg: Register, value: CobolNumber, **kw: Any) -> Const:
        """Create an exact COBOL fixed-point constant (COBOL lowering only)."""
        return cls(
            result_reg=result_reg,
            value=value,
            has_value=True,
            type_expr=scalar(FoundationTypeName.DECIMAL),
            **kw,
        )
```
- In `_const`, docstring list gains `"Decimal"`; after the `if lit == "Float":` branch add:
```python
    if lit == "Decimal":
        return Const.decimal_(reg, from_literal(str(raw)), source_location=sl)
```

`interpreter/vm/vm_types.py`:
- Add import: `from cobol_numeric.number import is_cobol_number, to_plain_str`
- In `_serialize_value`, before the final `return v`:
```python
    if is_cobol_number(v) and not isinstance(v, int):
        return to_plain_str(v)
```

- [ ] **Step 4: Run tests, contracts, and the type-system unit tests**

Run: `uv run python -m pytest tests/unit/cobol/test_decimal_type_plumbing.py tests/unit/test_type_graph.py -q -n0 && uv run lint-imports`
Expected: PASS; contracts kept. If `test_type_graph.py` asserts a node count (the docs say 12 nodes), update that assertion to include `Decimal` and state the new count in the assertion message — do not delete the assertion.

- [ ] **Step 5: Full suite**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar make test`
Expected: 15198 + new tests passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic add interpreter/constants.py interpreter/types/type_graph.py interpreter/instructions.py interpreter/vm/vm_types.py tests/unit/cobol/test_decimal_type_plumbing.py tests/unit/test_type_graph.py
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic commit -m "feat(types): Decimal foundation type and exact COBOL constants (red-dragon-4q25.1)"
```

---

### Task 3: One encode-digits implementation (closes red-dragon-bqds), `__cobol_to_text`, IS NUMERIC contract

**Files:**
- Modify: `interpreter/cobol/pic_scale.py` (replace contents), `interpreter/cobol/byte_builtins.py` (`_builtin_cobol_prepare_digits`, `_builtin_cobol_prepare_sign`, `BYTE_BUILTINS`), `interpreter/cobol/cobol_constants.py` (`BuiltinName`), `interpreter/cobol/emit_context.py` (`emit_encode_numeric`, `emit_to_string`)
- Create: `interpreter/cobol/numeric_builtins.py`
- Test: `tests/unit/cobol/test_encode_digits_parity.py`, `tests/integration/test_cobol_exact_arithmetic.py` (new file, grows in later tasks)

**Interfaces:**
- Consumes: `cobol_numeric.number.digits_for_encode`, `from_float`, `from_literal`, `is_cobol_number`, `round_half_up`, `scale_by`, `to_number`, `to_plain_str` (Task 1).
- Produces:
  - `interpreter.cobol.pic_scale.encode_digits(value: object, total_digits: int, decimal_digits: int, scale: int, float_noise_guard: bool = False) -> tuple[bool, str]` — the single encode-digits implementation for both paths.
  - `pic_scale.encode_scaled_digits(value: str, td) -> str` and `pic_scale.descale(value, scale)` kept as wrappers.
  - `BuiltinName.COBOL_TO_TEXT = "__cobol_to_text"`; `interpreter.cobol.numeric_builtins._builtin_cobol_to_text(args, vm) -> BuiltinResult`; `NUMERIC_BUILTINS: dict[FuncName, Any]` merged into `BYTE_BUILTINS`.
  - `EmitContext.emit_to_string` emits `__cobol_to_text` (COBOL only).

- [ ] **Step 1: Write the failing unit tests**

Create `tests/unit/cobol/test_encode_digits_parity.py`:

```python
"""Both numeric encode paths share one digits implementation (red-dragon-bqds),
and COBOL numeric text always satisfies IS NUMERIC (8d3b4e54 contract)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cobol_numeric.number import from_digits, from_literal, scale_by, to_plain_str
from interpreter.cobol.byte_builtins import (
    _builtin_cobol_prepare_digits,
    _builtin_cobol_prepare_sign,
    _builtin_is_numeric,
)
from interpreter.cobol.cobol_constants import BuiltinName, ByteConstants
from interpreter.cobol.byte_builtins import BYTE_BUILTINS
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.numeric_builtins import _builtin_cobol_to_text
from interpreter.cobol.pic_scale import encode_scaled_digits
from interpreter.func_name import FuncName
from interpreter.types.typed_value import typed_from_runtime
from tests.covers import NotLanguageFeature, covers

_CORPUS = [
    ("123.45", 5, 2, 0),
    ("-123.45", 5, 2, 0),
    ("1.237", 5, 2, 0),
    ("12.5", 3, 0, 0),
    ("12300", 3, 0, 2),
    ("123456", 3, 0, 0),
    ("0", 3, 0, 0),
    ("0.00001", 6, 5, 0),
    ("7", 4, 1, 0),
]


def _runtime_digits(value: str, total: int, decimals: int, scale: int) -> str:
    result = _builtin_cobol_prepare_digits(
        [
            typed_from_runtime(value),
            typed_from_runtime(total),
            typed_from_runtime(decimals),
            typed_from_runtime(True),
            typed_from_runtime(scale),
        ],
        None,
    )
    return "".join(str(d) for d in result.value)


@pytest.mark.parametrize("value, total, decimals, scale", _CORPUS)
@covers(CobolFeature.PIC_CLAUSE)
def test_value_clause_and_runtime_encode_paths_agree(value, total, decimals, scale):
    td = SimpleNamespace(total_digits=total, decimal_digits=decimals, scale=scale)
    assert encode_scaled_digits(value, td) == _runtime_digits(value, total, decimals, scale)


@covers(CobolFeature.PIC_CLAUSE)
def test_fraction_into_integer_field_truncates_on_the_value_clause_path():
    # red-dragon-bqds: the VALUE path used to store '125' (a 10x shift).
    td = SimpleNamespace(total_digits=3, decimal_digits=0, scale=0)
    assert encode_scaled_digits("12.5", td) == "012"


@covers(CobolFeature.PIC_CLAUSE)
def test_runtime_path_accepts_exact_and_float_values():
    number = from_literal("123.45")
    result = _builtin_cobol_prepare_digits(
        [typed_from_runtime(number), typed_from_runtime(5), typed_from_runtime(2), typed_from_runtime(True)],
        None,
    )
    assert result.value == [1, 2, 3, 4, 5]


@covers(CobolFeature.PIC_CLAUSE)
def test_runtime_path_tolerates_non_numeric_text():
    result = _builtin_cobol_prepare_digits(
        [typed_from_runtime("ABC"), typed_from_runtime(3), typed_from_runtime(0), typed_from_runtime(False)],
        None,
    )
    assert result.value == [0, 0, 0]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("-1.5", ByteConstants.SIGN_NIBBLE_NEGATIVE),
        ("-0.001", ByteConstants.SIGN_NIBBLE_NEGATIVE),
        ("-0", ByteConstants.SIGN_NIBBLE_POSITIVE),
        ("1.5", ByteConstants.SIGN_NIBBLE_POSITIVE),
    ],
)
@covers(CobolFeature.PIC_CLAUSE)
def test_sign_nibble_follows_the_pre_truncation_sign(value, expected):
    result = _builtin_cobol_prepare_sign([typed_from_runtime(value), typed_from_runtime(True)], None)
    assert result.value == expected


@covers(CobolFeature.DISPLAY)
def test_cobol_to_text_renders_numbers_plainly():
    def text(value):
        return _builtin_cobol_to_text([typed_from_runtime(value)], None).value

    assert text(1e-05) == "0.00001"
    assert text(from_digits(80, 2)) == "0.80"
    assert text(42) == "42"
    assert text("ABC") == "ABC"
    assert FuncName(BuiltinName.COBOL_TO_TEXT) in BYTE_BUILTINS


@pytest.mark.parametrize(
    "value",
    [
        from_digits(0, 0),
        from_digits(-5, 3),
        from_digits(18003830, 2),
        scale_by(1, -10),
        scale_by(123, 4),
        from_literal("999999999.999999999"),
        from_digits(-1, 0),
    ],
)
@covers(CobolFeature.CLASS_CONDITION)
def test_every_plain_number_text_is_numeric(value):
    rendered = to_plain_str(value)
    assert _builtin_is_numeric([typed_from_runtime(rendered)], None).value is True
```

Create `tests/integration/test_cobol_exact_arithmetic.py`:

```python
"""Exact COBOL fixed-point arithmetic end to end (red-dragon-4q25.1)."""

from __future__ import annotations

import pytest

from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401
from tests.integration.cobol_helpers import first_region, run_cobol


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Fails loudly when PROLEAP_BRIDGE_JAR is unset."""


def _program(working_storage: list[str], procedure: list[str], max_steps: int = 5000):
    return run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. EXACT.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            *working_storage,
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *procedure,
            "    STOP RUN.",
        ],
        max_steps=max_steps,
    )


class TestEncodePaths:
    @covers(CobolFeature.PIC_CLAUSE)
    def test_value_clause_fraction_into_integer_field_truncates(self):
        """red-dragon-bqds: VALUE 12.5 into PIC 999 stores 012, not 125."""
        vm = _program(["01 X PIC 999 VALUE 12.5."], ["    CONTINUE."])
        assert bytes(first_region(vm)[:3]).hex() == "f0f1f2"


class TestNumericText:
    @covers(CobolFeature.CLASS_CONDITION)
    def test_tiny_implied_decimal_value_is_numeric(self):
        """str(float) rendered 1e-05, which IS NUMERIC rejected."""
        vm = _program(
            ["01 T PIC 9V9(5) VALUE 0.00001.", "01 FLAG PIC 9 VALUE 0."],
            ["    IF T IS NUMERIC", "        MOVE 1 TO FLAG", "    END-IF."],
        )
        assert first_region(vm)[6] == 0xF1
```

- [ ] **Step 2: Run to verify failure**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/unit/cobol/test_encode_digits_parity.py tests/integration/test_cobol_exact_arithmetic.py -q -n0`
Expected: collection error `ModuleNotFoundError: interpreter.cobol.numeric_builtins`. After Step 3 creates only the module skeleton, re-run and expect `test_fraction_into_integer_field_truncates_on_the_value_clause_path` (gets `'125'`), `test_value_clause_fraction_into_integer_field_truncates` and `test_tiny_implied_decimal_value_is_numeric` to FAIL. If the IS NUMERIC integration test already passes, stop and report — the premise that `emit_to_string` feeds IS NUMERIC for this field is wrong and the test must be rewritten around the real path.

- [ ] **Step 3: Implement `numeric_builtins.py` and register it**

`interpreter/cobol/cobol_constants.py`, in `BuiltinName` after `COBOL_ROUND`:
```python
    COBOL_TO_TEXT = "__cobol_to_text"
```

Create `interpreter/cobol/numeric_builtins.py`:
```python
# pyright: standard
"""COBOL builtins backed by the cobol_numeric exact-value boundary (red-dragon-4q25.1)."""

from __future__ import annotations

import math
from typing import Any

from cobol_numeric.number import from_float, is_cobol_number, to_plain_str
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.func_name import FuncName
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm import Operators, VMState, _is_symbolic
from interpreter.vm.vm_types import BuiltinResult

_UNCOMPUTABLE = Operators.UNCOMPUTABLE


def _builtin_cobol_to_text(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Text of a COBOL value: numbers render plainly (never exponent notation),
    so IS NUMERIC, DISPLAY and the encode path all see ``-?digits(.digits)?``."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if isinstance(value, str):
        return BuiltinResult(value=value)
    if isinstance(value, float) and math.isfinite(value):
        return BuiltinResult(value=to_plain_str(from_float(value)))
    if is_cobol_number(value):
        return BuiltinResult(value=to_plain_str(value))
    return BuiltinResult(value=str(value))


NUMERIC_BUILTINS: dict[FuncName, Any] = (
    {  # Any: Callable[(list[TypedValue], VMState) -> BuiltinResult] — builtin boundary
        FuncName(BuiltinName.COBOL_TO_TEXT): _builtin_cobol_to_text,
    }
)
```

`interpreter/cobol/byte_builtins.py`: add `from interpreter.cobol.numeric_builtins import NUMERIC_BUILTINS` with the other imports, and as the last entry of the `BYTE_BUILTINS` dict literal (after `FuncName(BuiltinName.YEAR_TO_YYYY): _builtin_year_to_yyyy,`):
```python
        **NUMERIC_BUILTINS,
```

`interpreter/cobol/emit_context.py`, `emit_to_string` body: replace `func_name=FuncName("str"),` with `func_name=FuncName(BuiltinName.COBOL_TO_TEXT),` and the docstring with `"""Emit IR converting a COBOL value to its text (numbers rendered plainly)."""`.

- [ ] **Step 4: Replace `pic_scale.py` with the shared implementation**

```python
# pyright: standard
"""Digits stored for a COBOL numeric value — one implementation for every encode path.

The compile-time VALUE path (emit_context.emit_encode_numeric) and the runtime
path (__cobol_prepare_digits / __cobol_prepare_sign) both call ``encode_digits``,
so they cannot diverge again (red-dragon-qhtv, red-dragon-bqds). Exact
arithmetic lives in cobol_numeric; this module only adapts inputs and keeps the
historical tolerance for non-numeric text.
"""

from __future__ import annotations

from cobol_numeric.number import (
    CobolNumber,
    digits_for_encode,
    is_cobol_number,
    round_half_up,
    scale_by,
    to_number,
)
from cobol_asg.cobol_types import CobolTypeDescriptor
from interpreter.cobol.data_filters import align_decimal, left_adjust


def _parse(value: object) -> CobolNumber | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, float)) or is_cobol_number(value):
        try:
            return to_number(value)
        except ValueError:
            return None
    return None


def encode_digits(
    value: object,
    total_digits: int,
    decimal_digits: int,
    scale: int,
    float_noise_guard: bool = False,
) -> tuple[bool, str]:
    """``(negative, digit_str)`` for ``value`` in a field of the given shape.

    Non-numeric text (spaces, alphanumeric junk) keeps the historical tolerance:
    its characters are aligned as-is and non-digits later become 0.

    ``float_noise_guard`` is the temporary 96651c84 workaround (red-dragon-5b93):
    round to ``decimal_digits + 6`` places before truncating. Removed in Task 7.
    """
    number = _parse(value)
    if number is None:
        text = str(value)
        clean = text.lstrip("+-")
        negative = text.startswith("-") and any(ch.isdigit() and ch != "0" for ch in clean)
        if decimal_digits > 0:
            return negative, align_decimal(clean, total_digits - decimal_digits, decimal_digits)
        integer_part = clean.split(".")[0] if "." in clean else clean
        return negative, left_adjust(integer_part, total_digits)
    descaled = scale_by(number, -scale)
    if float_noise_guard and decimal_digits > 0:
        descaled = round_half_up(descaled, decimal_digits + 6)
    negative, digit_str = digits_for_encode(descaled, total_digits, decimal_digits)
    return negative, digit_str


def descale(value: object, scale: int) -> CobolNumber:
    """Value -> the number the digit positions hold (value / 10^scale)."""
    return scale_by(to_number(value), -scale)


def encode_scaled_digits(value: str, td: CobolTypeDescriptor) -> str:
    """Digit characters stored for ``value`` in a field of type ``td``."""
    _, digit_str = encode_digits(value, td.total_digits, td.decimal_digits, td.scale)
    return digit_str
```

- [ ] **Step 5: Route both builtins through `encode_digits`**

In `byte_builtins.py`, replace the body of `_builtin_cobol_prepare_digits` after the docstring with:
```python
    if len(args) < 4 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value, total_digits, decimal_digits, signed = (
        args[0].value,
        args[1].value,
        args[2].value,
        args[3].value,
    )
    scale = args[4].value if len(args) > 4 else 0
    if not isinstance(total_digits, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not (isinstance(value, (str, float)) or is_cobol_number(value)):
        return BuiltinResult(value=_UNCOMPUTABLE)

    from interpreter.cobol.pic_scale import encode_digits

    _, digit_str = encode_digits(
        value, total_digits, int(decimal_digits), int(scale), float_noise_guard=True
    )
    return BuiltinResult(value=[int(ch) if ch.isdigit() else 0 for ch in digit_str])
```
and the body of `_builtin_cobol_prepare_sign` after the docstring with:
```python
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value, signed = args[0].value, args[1].value
    if not (isinstance(value, (str, float)) or is_cobol_number(value)):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if not signed:
        return BuiltinResult(value=ByteConstants.SIGN_NIBBLE_UNSIGNED)

    from interpreter.cobol.pic_scale import encode_digits

    negative, _ = encode_digits(value, 1, 0, 0)
    if negative:
        return BuiltinResult(value=ByteConstants.SIGN_NIBBLE_NEGATIVE)
    return BuiltinResult(value=ByteConstants.SIGN_NIBBLE_POSITIVE)
```
Add `from cobol_numeric.number import is_cobol_number` to the top-level imports. (The local import of `pic_scale` avoids a new import cycle; keep it local like the original.)

In `emit_context.py`, `emit_encode_numeric`: replace
```python
        negative = value.startswith("-")

        digit_str = encode_scaled_digits(value, td)
```
with
```python
        negative, digit_str = encode_digits(value, td.total_digits, td.decimal_digits, td.scale)
```
and change the import of `encode_scaled_digits` from `interpreter.cobol.pic_scale` to `encode_digits`. The existing post-truncation sign rule (`negative and any(d != 0 for d in digits)`) stays unchanged.

- [ ] **Step 6: Run the new tests, then the COBOL suites**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/unit/cobol/test_encode_digits_parity.py tests/integration/test_cobol_exact_arithmetic.py tests/unit/test_byte_builtins.py tests/unit/cobol/test_arithmetic_decimal_precision.py -q -n0`
Expected: PASS.

Then: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar make test`
Expected: 0 failed. If a pre-existing test asserted the old `'125'` VALUE-path digits or exponent text such as `'1e-05'`, it was pinning red-dragon-bqds or the `str(float)` bug: update its expectation to the corrected value and say so in the commit body. Any other failure: stop and report.

- [ ] **Step 7: Commit**

```bash
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic add interpreter/cobol/pic_scale.py interpreter/cobol/byte_builtins.py interpreter/cobol/numeric_builtins.py interpreter/cobol/cobol_constants.py interpreter/cobol/emit_context.py tests/unit/cobol/test_encode_digits_parity.py tests/integration/test_cobol_exact_arithmetic.py
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic commit -m "fix(cobol): one encode-digits implementation and plain numeric text (red-dragon-bqds, red-dragon-4q25.1)"
```

---

### Task 4: IBM scale analysis and exact arithmetic builtins

**Files:**
- Create: `interpreter/cobol/arithmetic_scale.py`
- Modify: `interpreter/cobol/numeric_builtins.py` (four exact builtins + `__cobol_to_float`), `interpreter/cobol/cobol_constants.py` (`BuiltinName`), `interpreter/cobol/condition_lowering.py` (`lower_expr_node`), `interpreter/cobol/lower_arithmetic.py` (`lower_arithmetic`, `lower_arithmetic_giving`, `lower_compute`)
- Test: `tests/unit/cobol/test_arithmetic_scale.py`, `tests/unit/cobol/test_exact_arithmetic_builtins.py`, `tests/integration/test_cobol_exact_arithmetic.py` (extend)

**Interfaces:**
- Consumes: Task 1 (`Scale`, `add_scale`, `mul_scale`, `div_scale`, `carry`, `literal_scale`, `add`, `subtract`, `multiply`, `divide`, `to_number`, `to_float`, `as_whole_int`, `from_literal`), Task 3 (`NUMERIC_BUILTINS`).
- Produces:
  - `BuiltinName.COBOL_ADD = "__cobol_add"`, `COBOL_SUBTRACT = "__cobol_subtract"`, `COBOL_MULTIPLY = "__cobol_multiply"`, `COBOL_DIVIDE = "__cobol_divide"`, `COBOL_TO_FLOAT = "__cobol_to_float"`. Exact builtins take `(left, right, result_decimals: int)`, accept `int | float | numeric str | CobolNumber`, return `int` when `result_decimals == 0` else `CobolNumber`, and `UNCOMPUTABLE` on division by zero or non-numeric input.
  - `arithmetic_scale`: `FieldTypes = Callable[[str], CobolTypeDescriptor | None]`; `FLOAT_INTRINSICS`, `INTEGER_INTRINSICS`, `ARGUMENT_SCALED_INTRINSICS` (frozensets of COBOL names); `field_scale(td) -> Scale`; `is_floating_type(td) -> bool`; `receiver_decimals(td, rounded: bool) -> int`; `expression_is_floating(node, field_types) -> bool`; `operand_dmax(node, field_types) -> int`; `node_scale(node, dmax, field_types) -> Scale`.
  - `lower_expr_node(ctx, node, materialised, receiver_decimals: int = 0, floating_receiver: bool = False) -> Register` — `force_division_float` removed.

- [ ] **Step 1: Verify the IBM rules against NIST-85 before writing code**

The NIST sources are only populated in the main checkout. Run:
```bash
rtk proxy grep -nE "(COMPUTE|DIVIDE).*ROUNDED" /Users/asgupta/code/red-dragon/proleap-bridge/proleap-cobol-parser/src/test/resources/gov/nist/NC1*.CBL /Users/asgupta/code/red-dragon/proleap-bridge/proleap-cobol-parser/src/test/resources/gov/nist/NC2*.CBL | head -40
```
For at least three hits whose receiver has decimal places (or is an integer receiver of a fractional quotient), read the surrounding test paragraph (the `MOVE ... TO CORRECT-...` / `IF ... = ...` lines within ~15 lines) and compute the expected value under this plan's rules: quotient decimals `max(d2 − d1, dmax)`, `dmax` = receiver decimals (+1 when `ROUNDED`) and non-divisor operand decimals. Record each (program, line, statement, NIST expected, rule result) in the task report. If any NIST expectation contradicts the rule — in particular the `ROUNDED` + 1 assumption — STOP and report to the user before continuing.

- [ ] **Step 2: Write the failing unit tests**

Create `tests/unit/cobol/test_arithmetic_scale.py`:

```python
"""Static IBM ARITH(COMPAT) scale analysis for COBOL expressions."""

from __future__ import annotations

from types import SimpleNamespace

from cobol_asg.cobol_expression import BinOpNode, FieldRefNode, FunctionNode, LiteralNode
from cobol_asg.cobol_types import CobolDataCategory
from cobol_numeric.scale import Scale
from interpreter.cobol.arithmetic_scale import (
    expression_is_floating,
    field_scale,
    node_scale,
    operand_dmax,
    receiver_decimals,
)
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


def _td(total: int, decimals: int, category=CobolDataCategory.ZONED_DECIMAL, scale: int = 0):
    return SimpleNamespace(total_digits=total, decimal_digits=decimals, category=category, scale=scale)


_FIELDS = {
    "Y": _td(4, 0),
    "A": _td(5, 2),
    "D": _td(8, 0, CobolDataCategory.COMP2),
}


def _types(name: str):
    return _FIELDS.get(name)


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_field_scale_includes_pic_p_scaling():
    assert field_scale(_td(5, 2)) == Scale(3, 2)
    assert field_scale(_td(3, 0, scale=2)) == Scale(5, 0)
    assert field_scale(_td(3, 0, scale=-3)) == Scale(1, 3)


@covers(CobolFeature.ROUNDED_CLAUSE)
def test_receiver_decimals_adds_one_for_rounded():
    assert receiver_decimals(_td(3, 0), rounded=False) == 0
    assert receiver_decimals(_td(3, 0), rounded=True) == 1
    assert receiver_decimals(_td(4, 2), rounded=True) == 3


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_mod_idiom_divides_with_zero_decimals():
    node = BinOpNode("*", BinOpNode("/", FieldRefNode("Y"), LiteralNode("4")), LiteralNode("4"))
    dmax = max(0, operand_dmax(node, _types))
    assert dmax == 0
    assert node_scale(node.left, dmax, _types) == Scale(4, 0)


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_receiver_decimals_widen_the_quotient():
    node = BinOpNode("/", LiteralNode("7"), LiteralNode("2"))
    assert node_scale(node, 1, _types) == Scale(1, 1)


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_divisor_decimals_do_not_contribute_to_dmax():
    node = BinOpNode("/", FieldRefNode("Y"), FieldRefNode("A"))
    assert operand_dmax(node, _types) == 0
    node2 = BinOpNode("/", FieldRefNode("A"), FieldRefNode("Y"))
    assert operand_dmax(node2, _types) == 2


@covers(CobolFeature.USAGE_COMP_2)
def test_comp2_operand_makes_the_expression_floating():
    assert expression_is_floating(BinOpNode("*", FieldRefNode("D"), LiteralNode("2")), _types)
    assert not expression_is_floating(BinOpNode("*", FieldRefNode("A"), LiteralNode("2")), _types)


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_floating_intrinsics_make_the_expression_floating():
    assert expression_is_floating(FunctionNode("SQRT", (LiteralNode("2"),)), _types)
    assert not expression_is_floating(FunctionNode("MAX", (FieldRefNode("A"),)), _types)


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_argument_scaled_intrinsics_carry_their_argument_decimals():
    assert node_scale(FunctionNode("MAX", (FieldRefNode("A"), LiteralNode("1"))), 0, _types) == Scale(18, 2)
    assert node_scale(FunctionNode("MOD", (FieldRefNode("A"), LiteralNode("3"))), 0, _types) == Scale(18, 0)
```

Create `tests/unit/cobol/test_exact_arithmetic_builtins.py`:

```python
"""__cobol_add/subtract/multiply/divide and __cobol_to_float builtins."""

from __future__ import annotations

from cobol_numeric.number import from_literal, to_plain_str
from interpreter.cobol.byte_builtins import BYTE_BUILTINS
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.features import CobolFeature
from interpreter.func_name import FuncName
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm import Operators
from tests.covers import covers


def _call(name: str, *values):
    builtin = BYTE_BUILTINS[FuncName(name)]
    return builtin([typed_from_runtime(v) for v in values], None).value


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_multiply_float_operand_is_converted_exactly():
    assert _call(BuiltinName.COBOL_MULTIPLY, 4.35, 100, 0) == 435


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_integer_results_come_back_as_int():
    result = _call(BuiltinName.COBOL_DIVIDE, 2023, 4, 0)
    assert result == 505 and isinstance(result, int)


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_fractional_results_are_exact():
    assert to_plain_str(_call(BuiltinName.COBOL_DIVIDE, 7, 2, 1)) == "3.5"
    assert to_plain_str(_call(BuiltinName.COBOL_ADD, "0.1", 0.7, 2)) == "0.80"
    assert to_plain_str(_call(BuiltinName.COBOL_SUBTRACT, from_literal("1.00"), 3, 2)) == "-2.00"


@covers(CobolFeature.ON_SIZE_ERROR)
def test_division_by_zero_is_uncomputable():
    assert _call(BuiltinName.COBOL_DIVIDE, 1, 0, 2) is Operators.UNCOMPUTABLE


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_non_numeric_operand_is_uncomputable():
    assert _call(BuiltinName.COBOL_ADD, " ", 1, 0) is Operators.UNCOMPUTABLE


@covers(CobolFeature.USAGE_COMP_2)
def test_to_float():
    assert _call(BuiltinName.COBOL_TO_FLOAT, from_literal("1.25")) == 1.25
    assert _call(BuiltinName.COBOL_TO_FLOAT, 1.5) == 1.5
    assert _call(BuiltinName.COBOL_TO_FLOAT, 3) == 3.0
```

- [ ] **Step 3: Write the failing integration tests**

Append to `tests/integration/test_cobol_exact_arithmetic.py`:

```python
class TestIbmDivision:
    @covers(CobolFeature.COMPUTE)
    def test_receiver_decimals_keep_the_quotient_fraction(self):
        """IBM dmax = 1: 7 / 2 = 3.5, * 2 = 7.0 (stored 6.0 before)."""
        vm = _program(["01 X PIC 9V9."], ["    COMPUTE X = 7 / 2 * 2."])
        assert bytes(first_region(vm)[:2]).hex() == "f7f0"

    @covers(CobolFeature.COMPUTE)
    def test_integer_mod_idiom_still_truncates(self):
        """red-dragon-apoq regression guard: 2023 / 4 * 4 = 2020."""
        vm = _program(["01 X PIC 9(4)."], ["    COMPUTE X = 2023 / 4 * 4."])
        assert bytes(first_region(vm)[:4]).hex() == "f2f0f2f0"

    @covers(CobolFeature.COMPUTE)
    def test_one_third_into_nine_decimals(self):
        vm = _program(["01 X PIC 9V9(9)."], ["    COMPUTE X = 1 / 3."])
        assert bytes(first_region(vm)[:10]).hex() == "f0f3f3f3f3f3f3f3f3f3"

    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_rounded_two_thirds(self):
        vm = _program(["01 X PIC 9V99."], ["    COMPUTE X ROUNDED = 2 / 3."])
        assert bytes(first_region(vm)[:3]).hex() == "f0f6f7"


class TestExactOperators:
    @covers(CobolFeature.COMPUTE)
    def test_multiply_into_integer_receiver_is_exact(self):
        """4.35 * 100 stored 434 through float."""
        vm = _program(["01 X PIC 999."], ["    COMPUTE X = 4.35 * 100."])
        assert bytes(first_region(vm)[:3]).hex() == "f4f3f5"

    @covers(CobolFeature.COMPUTE)
    def test_point_one_plus_point_seven(self):
        vm = _program(["01 X PIC 9V99."], ["    COMPUTE X = 0.1 + 0.7."])
        assert bytes(first_region(vm)[:3]).hex() == "f0f8f0"

    @covers(CobolFeature.USAGE_COMP_2, CobolFeature.COMPUTE)
    def test_comp2_expression_computes_in_floating_point(self):
        vm = _program(
            ["01 X PIC 9V9.", "01 D COMP-2 VALUE 1.5."],
            ["    COMPUTE X = D * 2."],
        )
        assert bytes(first_region(vm)[:2]).hex() == "f3f0"
```

- [ ] **Step 4: Run to verify failure**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/unit/cobol/test_arithmetic_scale.py tests/unit/cobol/test_exact_arithmetic_builtins.py tests/integration/test_cobol_exact_arithmetic.py -q -n0`
Expected: unit files fail on import (`arithmetic_scale` missing, `BuiltinName.COBOL_MULTIPLY` missing); `test_receiver_decimals_keep_the_quotient_fraction` (gets f6f0) and `test_multiply_into_integer_receiver_is_exact` (gets f4f3f4) fail; the mod-idiom, 1/3, ROUNDED, 0.1+0.7 and COMP-2 tests may already pass (regression guards).

- [ ] **Step 5: Add builtin names and the exact builtins**

`cobol_constants.py`, after `COBOL_TO_TEXT`:
```python
    COBOL_ADD = "__cobol_add"
    COBOL_SUBTRACT = "__cobol_subtract"
    COBOL_MULTIPLY = "__cobol_multiply"
    COBOL_DIVIDE = "__cobol_divide"
    COBOL_TO_FLOAT = "__cobol_to_float"
```

`numeric_builtins.py`: extend the `cobol_numeric.number` import to `add, as_whole_int, divide, from_float, from_literal, is_cobol_number, multiply, subtract, to_float, to_number, to_plain_str`, add `from collections.abc import Callable`, and add before `NUMERIC_BUILTINS`:
```python
def _exact_operation(
    operation: Callable[[Any, Any, int], Any],
) -> Callable[[list[TypedValue], VMState], BuiltinResult]:
    """Wrap an exact cobol_numeric operation as a builtin taking
    (left, right, result_decimals)."""

    def builtin(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
            return BuiltinResult(value=_UNCOMPUTABLE)
        if any(a.value is _UNCOMPUTABLE for a in args):
            return BuiltinResult(value=_UNCOMPUTABLE)
        decimals = args[2].value
        if isinstance(decimals, bool) or not isinstance(decimals, int):
            return BuiltinResult(value=_UNCOMPUTABLE)
        try:
            result = operation(to_number(args[0].value), to_number(args[1].value), decimals)
        except (ValueError, TypeError, ZeroDivisionError):
            return BuiltinResult(value=_UNCOMPUTABLE)
        whole = as_whole_int(result) if decimals == 0 else None
        return BuiltinResult(value=result if whole is None else whole)

    return builtin


def _builtin_cobol_to_float(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Operand of a floating-point expression (IBM rule) as an IEEE float."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    if isinstance(value, float):
        return BuiltinResult(value=value)
    try:
        return BuiltinResult(value=to_float(to_number(value)))
    except (ValueError, TypeError):
        return BuiltinResult(value=_UNCOMPUTABLE)
```
and extend `NUMERIC_BUILTINS`:
```python
        FuncName(BuiltinName.COBOL_ADD): _exact_operation(add),
        FuncName(BuiltinName.COBOL_SUBTRACT): _exact_operation(subtract),
        FuncName(BuiltinName.COBOL_MULTIPLY): _exact_operation(multiply),
        FuncName(BuiltinName.COBOL_DIVIDE): _exact_operation(divide),
        FuncName(BuiltinName.COBOL_TO_FLOAT): _builtin_cobol_to_float,
```

- [ ] **Step 6: Create `arithmetic_scale.py`**

```python
# pyright: standard
"""Static IBM ARITH(COMPAT) scale analysis for COBOL arithmetic expressions.

Before emitting an expression, lowering needs the decimal places each
intermediate carries (IBM "Fixed-point data and intermediate results") and
whether the whole expression is computed in floating point (IBM
"Floating-point data and intermediate results"). Both depend only on PIC
clauses, literals, intrinsic names and receivers, so they are computed here
without emitting IR.

Intrinsic classification is this project's reading of IBM's function types:
FLOAT_INTRINSICS keep today's floating behaviour; INTEGER_INTRINSICS are
integer-valued; ARGUMENT_SCALED_INTRINSICS carry their arguments' decimals.
"""

from __future__ import annotations

from collections.abc import Callable

from cobol_asg.cobol_expression import (
    BinOpNode,
    ExprNode,
    FieldRefNode,
    FunctionNode,
    LengthOfNode,
    LiteralNode,
    RefModNode,
)
from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_numeric.number import from_literal
from cobol_numeric.scale import Scale, add_scale, carry, div_scale, literal_scale, mul_scale

FieldTypes = Callable[[str], CobolTypeDescriptor | None]

FLOAT_INTRINSICS = frozenset(
    {
        "SIN", "COS", "TAN", "ASIN", "ACOS", "ATAN", "EXP", "EXP10", "LOG", "LOG10",
        "SQRT", "MEAN", "MEDIAN", "MIDRANGE", "VARIANCE", "ANNUITY", "PRESENT-VALUE",
        "RANDOM", "NUMVAL", "NUMVAL-C",
    }
)
INTEGER_INTRINSICS = frozenset(
    {
        "LENGTH", "INTEGER-OF-DATE", "DATE-OF-INTEGER", "MOD", "ORD-MAX", "ORD-MIN",
        "FACTORIAL", "INTEGER", "INTEGER-PART", "ORD", "DAY-OF-INTEGER", "INTEGER-OF-DAY",
        "DATE-TO-YYYYMMDD", "DAY-TO-YYYYDDD", "YEAR-TO-YYYY", "TEST-NUMVAL", "TEST-NUMVAL-C",
    }
)
ARGUMENT_SCALED_INTRINSICS = frozenset({"MAX", "MIN", "SUM", "ABS", "RANGE", "REM", "FRACTION-PART"})

_FLOATING_CATEGORIES = frozenset({CobolDataCategory.COMP1, CobolDataCategory.COMP2})
_FUNCTION_INTEGER_PLACES = 18


def field_scale(td: CobolTypeDescriptor) -> Scale:
    return Scale(
        max(td.total_digits - td.decimal_digits + max(td.scale, 0), 1),
        td.decimal_digits + max(-td.scale, 0),
    )


def is_floating_type(td: CobolTypeDescriptor) -> bool:
    return td.category in _FLOATING_CATEGORIES


def receiver_decimals(td: CobolTypeDescriptor, rounded: bool) -> int:
    """Decimal places a receiver contributes to dmax; ROUNDED needs one more digit."""
    return field_scale(td).decimal_places + (1 if rounded else 0)


def _numeric_literal_scale(text: str) -> Scale | None:
    try:
        from_literal(text)
    except ValueError:
        return None
    return literal_scale(text)


def expression_is_floating(node: ExprNode, field_types: FieldTypes) -> bool:
    if isinstance(node, (FieldRefNode, RefModNode)):
        td = field_types(node.name)
        return td is not None and is_floating_type(td)
    if isinstance(node, BinOpNode):
        return expression_is_floating(node.left, field_types) or expression_is_floating(
            node.right, field_types
        )
    if isinstance(node, FunctionNode):
        return node.name.upper() in FLOAT_INTRINSICS or any(
            expression_is_floating(arg, field_types) for arg in node.args
        )
    return False


def operand_dmax(node: ExprNode, field_types: FieldTypes) -> int:
    """Largest decimal places of any operand except divisors."""
    if isinstance(node, (FieldRefNode, RefModNode)):
        td = field_types(node.name)
        return field_scale(td).decimal_places if td is not None else 0
    if isinstance(node, LiteralNode):
        scale = _numeric_literal_scale(node.value)
        return scale.decimal_places if scale is not None else 0
    if isinstance(node, BinOpNode):
        right = 0 if node.op == "/" else operand_dmax(node.right, field_types)
        return max(operand_dmax(node.left, field_types), right)
    if isinstance(node, FunctionNode):
        return max((operand_dmax(arg, field_types) for arg in node.args), default=0)
    return 0


def node_scale(node: ExprNode, dmax: int, field_types: FieldTypes) -> Scale:
    if isinstance(node, (FieldRefNode, RefModNode)):
        td = field_types(node.name)
        return field_scale(td) if td is not None else Scale(1, 0)
    if isinstance(node, LiteralNode):
        return _numeric_literal_scale(node.value) or Scale(1, 0)
    if isinstance(node, LengthOfNode):
        return Scale(9, 0)
    if isinstance(node, BinOpNode):
        left = node_scale(node.left, dmax, field_types)
        right = node_scale(node.right, dmax, field_types)
        if node.op in ("+", "-"):
            combined = add_scale(left, right)
        elif node.op == "*":
            combined = mul_scale(left, right)
        else:
            combined = div_scale(left, right, dmax)
        return carry(combined, dmax)
    if isinstance(node, FunctionNode):
        name = node.name.upper()
        if name in ARGUMENT_SCALED_INTRINSICS:
            decimals = max(
                (node_scale(arg, dmax, field_types).decimal_places for arg in node.args),
                default=0,
            )
            return Scale(_FUNCTION_INTEGER_PLACES, decimals)
        return Scale(_FUNCTION_INTEGER_PLACES, 0)
    return Scale(1, 0)
```
(Run black afterwards; it will reflow the frozensets.)

- [ ] **Step 7: Lower COMPUTE / condition expressions through the builtins**

In `condition_lowering.py`:
- Imports: add `from interpreter.cobol.arithmetic_scale import expression_is_floating, node_scale, operand_dmax`.
- Add module constant:
```python
_EXACT_OPERATORS = {
    "+": BuiltinName.COBOL_ADD,
    "-": BuiltinName.COBOL_SUBTRACT,
    "*": BuiltinName.COBOL_MULTIPLY,
    "/": BuiltinName.COBOL_DIVIDE,
}
```
- Rename the existing `lower_expr_node` function to `_lower_expr_node_body(ctx, node, materialised, dmax: int, floating: bool, field_types)`, remove its `force_division_float` parameter, and make its recursive `BinOpNode` calls use `_lower_expr_node_body(ctx, node.left, materialised, dmax, floating, field_types)` / `node.right`. Leave the `RefModNode` start/length calls calling the public `lower_expr_node` (they are independent integer expressions).
- Replace the `BinOpNode` branch's body after computing `left_reg`/`right_reg` (delete the `force_division_float` block and the `Binop` emission) with:
```python
        result_reg = ctx.fresh_reg()
        if floating:
            ctx.emit_inst(
                Binop(
                    result_reg=result_reg,
                    operator=resolve_binop(node.op),
                    left=Register(str(left_reg)),
                    right=Register(str(right_reg)),
                )
            )
            return result_reg
        decimals_reg = ctx.const_to_reg(node_scale(node, dmax, field_types).decimal_places)
        ctx.emit_inst(
            CallFunction(
                result_reg=result_reg,
                func_name=FuncName(_EXACT_OPERATORS[node.op]),
                args=(Register(str(left_reg)), Register(str(right_reg)), decimals_reg),
            )
        )
        return result_reg
```
- In floating mode, every non-`BinOpNode` operand must be converted: at the end of each leaf branch (`LiteralNode`, `FieldRefNode`, `RefModNode`, `FunctionNode`, `FigurativeNode`, `LengthOfNode`), instead of returning the register directly, return `_float_operand(ctx, reg, floating)`, where:
```python
def _float_operand(ctx: EmitContext, reg: Register, floating: bool) -> Register:
    if not floating:
        return reg
    converted = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=converted,
            func_name=FuncName(BuiltinName.COBOL_TO_FLOAT),
            args=(Register(str(reg)),),
        )
    )
    return converted
```
- New public entry point (keeps the old name and docstring purpose):
```python
def lower_expr_node(
    ctx: EmitContext,
    node: ExprNode,
    materialised: MaterialisedSectionedLayout,
    receiver_decimals: int = 0,
    floating_receiver: bool = False,
) -> Register:
    """Walk an expression tree and emit IR. Returns the result register.

    Fixed-point expressions follow IBM ARITH(COMPAT): each operator lowers to an
    exact cobol_numeric builtin truncating to its statically carried decimal
    places, with dmax the larger of ``receiver_decimals`` and the non-divisor
    operand decimals. Integer-only division therefore truncates (the mod idiom
    ``A - (A / B) * B``, red-dragon-apoq) while receivers with decimal places
    keep the fraction. An expression with a COMP-1/COMP-2 operand or receiver,
    or a floating intrinsic, is computed in IEEE floating point.
    """

    def field_types(name: str):
        if not ctx.has_field(name, materialised):
            return None
        return materialised.resolve(name)[0].type_descriptor

    floating = floating_receiver or expression_is_floating(node, field_types)
    dmax = max(receiver_decimals, operand_dmax(node, field_types))
    return _lower_expr_node_body(ctx, node, materialised, dmax, floating, field_types)
```

In `lower_arithmetic.py`, `lower_compute`: replace
```python
    # Preserve division fractions only when a target is ROUNDED; otherwise COBOL
    # integer division truncates (the mod idiom A - (A / B) * B; red-dragon-apoq).
    rounded_target = any(t.rounded for t in stmt.targets)
    result_reg = lower_expr_node(
        ctx, stmt.expression, materialised, force_division_float=rounded_target
    )
```
with
```python
    # IBM ARITH(COMPAT): receivers (+1 for ROUNDED) size the division fraction.
    target_types = [
        (materialised.resolve(t.name)[0].type_descriptor, t.rounded)
        for t in stmt.targets
        if ctx.has_field(t.name, materialised)
    ]
    result_reg = lower_expr_node(
        ctx,
        stmt.expression,
        materialised,
        receiver_decimals=max(
            (receiver_decimals(td, rounded) for td, rounded in target_types), default=0
        ),
        floating_receiver=any(is_floating_type(td) for td, _ in target_types),
    )
```
and import `from interpreter.cobol.arithmetic_scale import is_floating_type, receiver_decimals` (check for a local-name clash with any existing `receiver_decimals` variable; rename the import `as _receiver_decimals` if needed).

- [ ] **Step 8: Lower the ADD/SUBTRACT/MULTIPLY/DIVIDE verbs through the builtins**

In `lower_arithmetic.py`, add after `ARITHMETIC_OPS`:
```python
_EXACT_VERB_BUILTINS = {
    "ADD": BuiltinName.COBOL_ADD,
    "SUBTRACT": BuiltinName.COBOL_SUBTRACT,
    "MULTIPLY": BuiltinName.COBOL_MULTIPLY,
    "DIVIDE": BuiltinName.COBOL_DIVIDE,
}


def _operand_type(ctx: EmitContext, name: str, materialised: MaterialisedSectionedLayout):
    if not ctx.has_field(name, materialised):
        return None
    return materialised.resolve(name)[0].type_descriptor


def _operand_scale(ctx: EmitContext, name: str, materialised: MaterialisedSectionedLayout) -> Scale:
    td = _operand_type(ctx, name, materialised)
    if td is not None:
        return field_scale(td)
    try:
        from_literal(translate_cobol_figurative(name))
    except ValueError:
        return Scale(1, 0)
    return literal_scale(translate_cobol_figurative(name))


def _emit_verb_operation(
    ctx: EmitContext,
    op: str,
    left_reg: Register,
    right_reg: Register,
    left_operand: RefModOperand,
    right_operand: RefModOperand,
    receivers: list[RefModOperand],
    materialised: MaterialisedSectionedLayout,
) -> Register:
    """Emit ``left <op> right`` for an arithmetic verb, exact unless IBM's
    floating-point rule applies (a COMP-1/COMP-2 operand or receiver)."""
    result_reg = ctx.fresh_reg()
    types = [
        _operand_type(ctx, operand.name, materialised)
        for operand in (left_operand, right_operand, *receivers)
    ]
    if any(td is not None and is_floating_type(td) for td in types):
        ctx.emit_inst(
            Binop(
                result_reg=result_reg,
                operator=resolve_binop(ARITHMETIC_OPS[op]),
                left=left_reg,
                right=right_reg,
            )
        )
        return result_reg
    left_scale = _operand_scale(ctx, left_operand.name, materialised)
    right_scale = _operand_scale(ctx, right_operand.name, materialised)
    receiver_places = max(
        (
            receiver_decimals(td, receiver.rounded)
            for receiver, td in zip(receivers, types[2:])
            if td is not None
        ),
        default=0,
    )
    operand_places = (
        left_scale.decimal_places
        if op == "DIVIDE"
        else max(left_scale.decimal_places, right_scale.decimal_places)
    )
    dmax = max(receiver_places, operand_places)
    if op in ("ADD", "SUBTRACT"):
        combined = add_scale(left_scale, right_scale)
    elif op == "MULTIPLY":
        combined = mul_scale(left_scale, right_scale)
    else:
        combined = div_scale(left_scale, right_scale, dmax)
    decimals_reg = ctx.const_to_reg(carry(combined, dmax).decimal_places)
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName(_EXACT_VERB_BUILTINS[op]),
            args=(left_reg, right_reg, decimals_reg),
        )
    )
    return result_reg
```
Imports to add: `from cobol_numeric.number import from_literal`, `from cobol_numeric.scale import Scale, add_scale, carry, div_scale, literal_scale, mul_scale`, `field_scale` from `arithmetic_scale`; `RefModOperand` from `cobol_asg.cobol_statements` if not already imported.

Replace the three verb `Binop` emissions (keep operand order exactly as today):
- `lower_arithmetic`, no-clause path (the `op = ARITHMETIC_OPS[stmt.op]` + `Binop(left=tgt_decoded, right=src_decoded)` block) and the ON SIZE ERROR path's identical block, each with:
```python
    result_reg = _emit_verb_operation(
        ctx, stmt.op, tgt_decoded, src_decoded, stmt.target, stmt.source, [stmt.target], materialised
    )
```
- `lower_arithmetic_giving` (`Binop(left=left_reg, right=right_reg)`) with:
```python
    result_reg = _emit_verb_operation(
        ctx, stmt.op, left_reg, right_reg, stmt.source, stmt.target, list(stmt.giving), materialised
    )
```
Leave the divide-by-zero `==` Binops, overflow checks and REMAINDER logic unchanged.

- [ ] **Step 9: Run the targeted tests**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/unit/cobol/test_arithmetic_scale.py tests/unit/cobol/test_exact_arithmetic_builtins.py tests/integration/test_cobol_exact_arithmetic.py tests/unit/cobol/test_arithmetic_decimal_precision.py "tests/integration/test_cobol_coverage_gaps.py::TestIntegerDivisionSemantics" "tests/integration/test_cobol_programs.py::TestRoundedClause" -q -n0`
Expected: PASS.

- [ ] **Step 10: Full suite, lint, format**

Run: `uv run python -m black . && uv run lint-imports && PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar make test`
Expected: 0 failed. Confirm `rtk proxy grep -rn "force_division_float" interpreter tests` prints nothing. Any failing pre-existing test: stop and report with the failing assertion; do not change its expectation unless it pinned a float artefact that the spec explicitly corrects (name the spec line in the commit body).

- [ ] **Step 11: Commit**

```bash
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic add interpreter/cobol tests/unit/cobol/test_arithmetic_scale.py tests/unit/cobol/test_exact_arithmetic_builtins.py tests/integration/test_cobol_exact_arithmetic.py
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic commit -m "feat(cobol): IBM ARITH(COMPAT) scale rules and exact arithmetic builtins (red-dragon-4q25.1)"
```

---

### Task 5: Exact operands — decode (closes red-dragon-0dvs), PIC P, literals, COMP store, lowering `float()` removal

Decode and literals switch in ONE commit: an exact field compared with a float literal (or the reverse) is unequal under Python (`Decimal("0.1") != 0.1`), so switching one without the other breaks `IF X = 0.1` between commits.

**Files:**
- Modify: `interpreter/cobol/ir_encoders.py` (four decoders + helper), `interpreter/cobol/emit_context.py` (`emit_decode_field` PIC P block, `parse_literal`, `const_to_reg`, `emit_encode_from_string` BINARY branch), `interpreter/cobol/lower_arithmetic.py` (lines ~809-818, ~930-940, ~1116-1127), `interpreter/cobol/condition_lowering.py` (RefModNode `float` call), `interpreter/cobol/numeric_builtins.py`, `interpreter/cobol/cobol_constants.py`
- Test: `tests/unit/test_ir_encoders.py` (`TestIntegerFieldsDecodeToInt`), `tests/unit/cobol/test_exact_arithmetic_builtins.py` (extend), `tests/integration/test_cobol_exact_arithmetic.py` (extend)

**Interfaces:**
- Consumes: Task 1 (`from_digits`, `scale_by`, `truncate_to`, `as_whole_int`, `from_literal`, `to_number`, `is_cobol_number`), Task 2 (`Const.decimal_`), Tasks 3–4 builtins.
- Produces: `BuiltinName.COBOL_FROM_DIGITS = "__cobol_from_digits"` `(digits: int, decimal_digits: int)`; `COBOL_SCALE_BY = "__cobol_scale_by"` `(value, scale: int)`; `COBOL_PARSE_NUMBER = "__cobol_parse_number"` `(text)` → `int` when integral text without a point, else `CobolNumber`, `UNCOMPUTABLE` for non-numeric text; `COBOL_BINARY_UNSCALED = "__cobol_binary_unscaled"` `(value, decimal_digits: int, scale: int)` → `int`. Decoded fixed-point values with decimal places are `CobolNumber`; integer fields stay `int`; numeric literals with a point are `CobolNumber`.

- [ ] **Step 1: Write the failing builtin tests**

Append to `tests/unit/cobol/test_exact_arithmetic_builtins.py`:

```python
@covers(CobolFeature.USAGE_COMP)
def test_from_digits_builtin():
    assert to_plain_str(_call(BuiltinName.COBOL_FROM_DIGITS, -12345, 2)) == "-123.45"
    assert _call(BuiltinName.COBOL_FROM_DIGITS, 42, 0) == 42


@covers(CobolFeature.PIC_CLAUSE)
def test_scale_by_builtin():
    assert _call(BuiltinName.COBOL_SCALE_BY, 123, 2) == 12300
    assert to_plain_str(_call(BuiltinName.COBOL_SCALE_BY, from_literal("1.2"), -2)) == "0.012"


@covers(CobolFeature.ARITHMETIC_REF_MOD)
def test_parse_number_builtin():
    assert _call(BuiltinName.COBOL_PARSE_NUMBER, "045") == 45
    assert to_plain_str(_call(BuiltinName.COBOL_PARSE_NUMBER, "4.50")) == "4.50"
    assert _call(BuiltinName.COBOL_PARSE_NUMBER, "A1") is Operators.UNCOMPUTABLE


@covers(CobolFeature.USAGE_COMP)
def test_binary_unscaled_builtin():
    assert _call(BuiltinName.COBOL_BINARY_UNSCALED, "123.45", 2, 0) == 12345
    assert _call(BuiltinName.COBOL_BINARY_UNSCALED, "-1.239", 2, 0) == -123
    assert _call(BuiltinName.COBOL_BINARY_UNSCALED, "50000", 0, 0) == 50000
    assert _call(BuiltinName.COBOL_BINARY_UNSCALED, "12300", 0, 2) == 123
```

- [ ] **Step 2: Update the decoder unit test (behaviour intentionally changes)**

In `tests/unit/test_ir_encoders.py`, `TestIntegerFieldsDecodeToInt`: change the class docstring's last sentence to `Decimal fields (decimal_digits > 0) decode to an exact CobolNumber (red-dragon-4q25.1).`, add `from cobol_numeric.number import from_literal`, and replace `test_zoned_decimal_still_float` with:

```python
    def test_zoned_decimal_decodes_exactly(self):
        data = [0xF1, 0xF2, 0xF3, 0xF4, 0xF5]
        ir = build_decode_zoned_ir("z", total_digits=5, decimal_digits=2)
        result = _execute_ir(ir, {"%p_data": data})
        assert not isinstance(result, float)
        assert result == from_literal("123.45")

    def test_binary_decimal_decodes_exactly(self):
        """red-dragon-0dvs: the int divisor floor-divided COMP fractions away."""
        data = list((12345).to_bytes(4, "big", signed=True))
        ir = build_decode_binary_ir("bin", byte_count=4, decimal_digits=2, signed=True)
        result = _execute_ir(ir, {"%p_data": data})
        assert result == from_literal("123.45")

    def test_comp3_negative_decimal_decodes_exactly(self):
        data = [0x12, 0x34, 0x5D]  # packed -123.45
        ir = build_decode_comp3_ir("c3", total_digits=5, decimal_digits=2)
        result = _execute_ir(ir, {"%p_data": data})
        assert result == from_literal("-123.45")
```
(Give each new method the same `@covers` decorator the neighbouring methods in that class use; if they have none, add `@covers(CobolFeature.NUMERIC_EXECUTION)` with the import.)

- [ ] **Step 3: Write the failing integration tests**

Append to `tests/integration/test_cobol_exact_arithmetic.py`:

```python
class TestExactOperands:
    @covers(CobolFeature.ADD)
    def test_eighteen_digit_add_keeps_the_last_digit(self):
        vm = _program(
            ["01 Y PIC S9(9)V9(9) VALUE 123456789.123456788."],
            ["    ADD 0.000000001 TO Y."],
        )
        assert bytes(first_region(vm)[:18]).hex() == "f1f2f3f4f5f6f7f8f9f1f2f3f4f5f6f7f8c9"

    @covers(CobolFeature.USAGE_COMP)
    def test_comp_decimal_field_decodes_its_fraction(self):
        """red-dragon-0dvs (decode half)."""
        vm = _program(
            ["01 C PIC S9(5)V99 COMP VALUE 123.45.", "01 D PIC 9(5)V99."],
            ["    MOVE C TO D."],
        )
        assert bytes(first_region(vm)[:11]).hex() == "00003039f0f0f1f2f3f4f5"

    @covers(CobolFeature.USAGE_COMP)
    def test_comp_decimal_field_stores_its_fraction(self):
        """red-dragon-0dvs (store half): MOVE 123.45 stored 123."""
        vm = _program(
            ["01 C PIC S9(5)V99 COMP.", "01 D PIC 9(5)V99."],
            ["    MOVE 123.45 TO C.", "    MOVE C TO D."],
        )
        assert bytes(first_region(vm)[:11]).hex() == "00003039f0f0f1f2f3f4f5"

    @covers(CobolFeature.PIC_CLAUSE)
    def test_pic_p_field_round_trips(self):
        vm = _program(["01 P PIC 999PP VALUE 12300.", "01 D PIC 9(5)."], ["    MOVE P TO D."])
        assert bytes(first_region(vm)[:8]).hex() == "f1f2f3f1f2f3f0f0"

    @covers(CobolFeature.ARITHMETIC_EXPRESSION)
    def test_decimal_field_equals_decimal_literal(self):
        vm = _program(
            ["01 X PIC 9V9 VALUE 0.1.", "01 FLAG PIC 9 VALUE 0."],
            ["    IF X = 0.1", "        MOVE 1 TO FLAG", "    END-IF."],
        )
        assert first_region(vm)[2] == 0xF1
```

- [ ] **Step 4: Run to verify failure**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/unit/cobol/test_exact_arithmetic_builtins.py tests/unit/test_ir_encoders.py::TestIntegerFieldsDecodeToInt tests/integration/test_cobol_exact_arithmetic.py::TestExactOperands -q -n0`
Expected: the four new builtin tests fail (`AttributeError: ... COBOL_FROM_DIGITS`); the three decoder tests fail (float / floor-divided results); `test_eighteen_digit_add_keeps_the_last_digit` (gets `...f7f9c0`), both COMP tests (get `...f0f0f0f0f1f0f0`-style values) fail. `test_pic_p_field_round_trips` and `test_decimal_field_equals_decimal_literal` may already pass (regression guards).

- [ ] **Step 5: Add the builtins**

`cobol_constants.py`, after `COBOL_TO_FLOAT`:
```python
    COBOL_FROM_DIGITS = "__cobol_from_digits"
    COBOL_SCALE_BY = "__cobol_scale_by"
    COBOL_PARSE_NUMBER = "__cobol_parse_number"
    COBOL_BINARY_UNSCALED = "__cobol_binary_unscaled"
```

`numeric_builtins.py` — extend the `cobol_numeric.number` import with `from_digits, scale_by, truncate_to`, then add:
```python
def _int_arg(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _builtin_cobol_from_digits(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Signed stored digits with implied decimal places, exactly."""
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    digits, decimals = _int_arg(args[0].value), _int_arg(args[1].value)
    if digits is None or decimals is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=digits if decimals == 0 else from_digits(digits, decimals))


def _builtin_cobol_scale_by(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """PIC P: value × 10^scale, exactly; integral results stay int."""
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    scale = _int_arg(args[1].value)
    if scale is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    try:
        scaled = scale_by(to_number(args[0].value), scale)
    except (ValueError, TypeError):
        return BuiltinResult(value=_UNCOMPUTABLE)
    whole = as_whole_int(scaled)
    return BuiltinResult(value=scaled if whole is None else whole)


def _builtin_cobol_parse_number(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Text (e.g. a reference-modified slice) as an exact number."""
    if len(args) < 1 or _is_symbolic(args[0].value):
        return BuiltinResult(value=_UNCOMPUTABLE)
    value = args[0].value
    try:
        number = to_number(value)
    except (ValueError, TypeError):
        return BuiltinResult(value=_UNCOMPUTABLE)
    if isinstance(value, str) and "." not in value:
        whole = as_whole_int(number)
        return BuiltinResult(value=number if whole is None else whole)
    return BuiltinResult(value=number)


def _builtin_cobol_binary_unscaled(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """Integer stored in a COMP/BINARY field: value × 10^(decimal_digits − scale),
    truncated toward zero. No digit-count truncation (byte width bounds BINARY)."""
    if len(args) < 3 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    decimals, scale = _int_arg(args[1].value), _int_arg(args[2].value)
    if decimals is None or scale is None:
        return BuiltinResult(value=_UNCOMPUTABLE)
    try:
        stored = truncate_to(scale_by(to_number(args[0].value), -scale), decimals)
    except (ValueError, TypeError):
        return BuiltinResult(value=_UNCOMPUTABLE)
    unscaled = as_whole_int(scale_by(stored, decimals))
    return BuiltinResult(value=_UNCOMPUTABLE if unscaled is None else unscaled)
```
and register all four in `NUMERIC_BUILTINS`.

- [ ] **Step 6: Exact decoders**

In `ir_encoders.py`, add after `_lit`:
```python
def _scale_decoded(
    rc: _RegCounter,
    instructions: list[InstructionBase],
    digits_reg: Register,
    decimal_digits: int,
) -> Register:
    """Apply implied decimal places to the signed integer digits, exactly
    (red-dragon-4q25.1). Integer fields keep their int."""
    if decimal_digits == 0:
        return digits_reg
    decimals_reg = _lit(rc, instructions, decimal_digits)
    scaled = rc.next()
    instructions.append(
        CallFunction(
            result_reg=scaled,
            func_name=FuncName(BuiltinName.COBOL_FROM_DIGITS),
            args=(digits_reg, decimals_reg),
        )
    )
    return scaled
```
Then in `build_decode_zoned_ir`, `build_decode_zoned_separate_ir` and `build_decode_comp3_ir`:
- delete the whole `# Apply decimal scaling` block (`if decimal_digits > 0:` … `accum = scaled`) and the comment lines under it about keeping integers as int;
- replace the final `instructions.append(Return_(value_reg=final_result))` with
```python
    instructions.append(
        Return_(value_reg=_scale_decoded(rc, instructions, final_result, decimal_digits))
    )
```
In `build_decode_binary_ir`, replace the `# Apply decimal scaling` block and the `Return_` with:
```python
    instructions.append(
        Return_(value_reg=_scale_decoded(rc, instructions, int_val, decimal_digits))
    )
```
Update the three docstrings' `Output:` lines to `Output: int when decimal_digits == 0, else CobolNumber`.

- [ ] **Step 7: PIC P, literals, constants, COMP store**

`emit_context.py`:
- `emit_decode_field` PIC P block — replace from `scaled = self.fresh_reg()` to the `Binop(...)` emission with:
```python
        scaled = self.fresh_reg()
        scale_reg = self.const_to_reg(td.scale)
        self.emit_inst(
            CallFunction(
                result_reg=scaled,
                func_name=FuncName(BuiltinName.COBOL_SCALE_BY),
                args=(decoded, scale_reg),
            )
        )
```
- `parse_literal`: replace the `float(stripped)` attempt with
```python
        try:
            return from_literal(stripped)
        except ValueError:
            pass
```
and change the docstring phrase `int→float→str` to `int→exact number→str`.
- `const_to_reg`: after the `float` branch add
```python
        elif is_cobol_number(value):
            inst = Const.decimal_(reg, value)
```
- BINARY branch of `emit_encode_from_string`: replace the `float_reg` and `int_reg` CallFunctions with
```python
            int_reg = self.fresh_reg()
            decimals_reg = self.const_to_reg(td.decimal_digits)
            scale_reg = self.const_to_reg(td.scale)
            self.emit_inst(
                CallFunction(
                    result_reg=int_reg,
                    func_name=FuncName(BuiltinName.COBOL_BINARY_UNSCALED),
                    args=(value_str_reg, decimals_reg, scale_reg),
                ),
            )
```
and extend its comment: `Implied decimal places and PIC P scale are applied exactly (red-dragon-0dvs).`
- Imports: `from cobol_numeric.number import from_literal, is_cobol_number`.

`lower_arithmetic.py`:
- In `_emit_arithmetic_writeback`, `lower_arithmetic` (ref-mod source) and `lower_arithmetic_giving._decode_operand` (ref-mod): change every `func_name=FuncName("float")` to `func_name=FuncName(BuiltinName.COBOL_PARSE_NUMBER)`, and the adjacent comments from "float" wording to "Parse the text as an exact number".
- Replace `src_decoded = ctx.const_to_reg(float(translate_cobol_figurative(stmt.source.name)))` (split over lines) with `src_decoded = ctx.const_to_reg(ctx.parse_literal(translate_cobol_figurative(stmt.source.name)))` and `return ctx.const_to_reg(float(translate_cobol_figurative(field_name)))` with `return ctx.const_to_reg(ctx.parse_literal(translate_cobol_figurative(field_name)))`.

`condition_lowering.py`, `RefModNode` branch: `func_name=FuncName("float")` → `func_name=FuncName(BuiltinName.COBOL_PARSE_NUMBER)`; comment → `# Parse the sliced text as an exact number`.

- [ ] **Step 8: Targeted tests, then full suite**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/unit/cobol/test_exact_arithmetic_builtins.py tests/unit/test_ir_encoders.py tests/integration/test_cobol_exact_arithmetic.py tests/unit/cobol/test_arithmetic_decimal_precision.py tests/unit/cobol/test_pic_scaling.py -q -n0`
Expected: PASS.

Run: `uv run python -m black . && uv run lint-imports && PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar make test`
Expected: 0 failed. Confirm `rtk proxy grep -rn 'FuncName("float")' interpreter/cobol` lists only the COMP-1/COMP-2 store in `emit_encode_from_string`. A pre-existing test asserting a decoded value `isinstance(..., float)` or a float-shaped text (`"1.5"` where the field scale now renders `"1.50"`) is pinning the old representation: update it to the exact value and list each such test in the commit body. Any other failure: stop and report.

- [ ] **Step 9: Commit**

```bash
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic add interpreter/cobol tests/unit/test_ir_encoders.py tests/unit/cobol/test_exact_arithmetic_builtins.py tests/integration/test_cobol_exact_arithmetic.py
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic commit -m "fix(cobol): exact decode, literals and COMP store (red-dragon-0dvs, red-dragon-4q25.1)"
```

---

### Task 6: Remaining builtins, intrinsics, COMP-1/COMP-2 packing, numeric-edited formatting

**Files:**
- Create: `cobol_numeric/intrinsics.py`
- Modify: `interpreter/cobol/byte_builtins.py` (intrinsic helpers and bodies, `_numval_to_number`, `_builtin_cobol_round`, `_builtin_cobol_blank_when_zero`, `_builtin_float_to_bytes`, `_builtin_integer_of_date`, `_coerce_intrinsic_int`, `_coerce_intrinsic_float`), `interpreter/cobol/emit_context.py` (`_is_zero_value`), `cobol_asg/edit_picture.py` (`_digit_strings`, `format_edited`, imports)
- Test: `tests/unit/cobol/test_numeric_boundary_builtins.py` (new), `tests/unit/test_byte_builtins.py` (`TestPresentValue.test_nonzero_rate` tightened), `tests/integration/test_cobol_exact_arithmetic.py` (extend)

**Interfaces:**
- Consumes: Task 1 (`round_half_up`, `to_number`, `to_plain_str`, `to_float`, `is_cobol_number`, `as_whole_int`, `digits_for_encode`, `from_literal`, `from_digits`, `CobolNumber`).
- Produces: `cobol_numeric.intrinsics`: `coerce_argument(raw: object) -> CobolNumber | None`, `to_result(value: CobolNumber) -> int | CobolNumber`, `is_integral(value) -> bool`, `total(values)`, `mean(values)`, `median(values)`, `midrange(values)`, `value_range(values)`, `variance(values)`, `square_root(value)`, `absolute(value)`, `floor_integer(value) -> int`, `integer_part(value) -> int`, `fraction_part(value)`, `remainder(x, y)`, `annuity(rate, periods: int)`, `present_value(rate, cashflows)`, `parse_numval_digits(text: str, negative: bool) -> int | CobolNumber | None`. Behaviour identical to the pre-move builtins (same `Decimal` coercion and default context).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/cobol/test_numeric_boundary_builtins.py`:

```python
"""Builtins that accept exact COBOL values after the boundary migration."""

from __future__ import annotations

from cobol_asg.edit_picture import format_edited
from cobol_numeric.number import from_digits, from_literal
from interpreter.cobol.byte_builtins import (
    _builtin_cobol_blank_when_zero,
    _builtin_cobol_round,
    _builtin_float_to_bytes,
    _builtin_integer_of_date,
    _coerce_intrinsic_int,
)
from interpreter.cobol.cobol_constants import ByteConstants
from interpreter.cobol.features import CobolFeature
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm import Operators
from tests.covers import covers


def _args(*values):
    return [typed_from_runtime(v) for v in values]


@covers(CobolFeature.ROUNDED_CLAUSE)
def test_round_accepts_exact_values_and_returns_plain_text():
    assert _builtin_cobol_round(_args(from_literal("0.665"), 2), None).value == "0.67"
    assert _builtin_cobol_round(_args(from_digits(1, 10), 2), None).value == "0.00"


@covers(CobolFeature.ROUNDED_CLAUSE)
def test_round_non_numeric_text_is_uncomputable():
    assert _builtin_cobol_round(_args("ABC", 2), None).value is Operators.UNCOMPUTABLE


@covers(CobolFeature.PIC_CLAUSE)
def test_blank_when_zero_recognises_exact_zero_text():
    encoded = [0xF0, 0xF0, 0xF0]
    assert _builtin_cobol_blank_when_zero(_args(encoded, "0.00", 3), None).value == [
        ByteConstants.EBCDIC_SPACE
    ] * 3
    assert _builtin_cobol_blank_when_zero(_args(encoded, "0.01", 3), None).value == encoded


@covers(CobolFeature.USAGE_COMP_2)
def test_float_to_bytes_accepts_exact_values():
    import struct

    assert _builtin_float_to_bytes(_args(from_literal("1.25"), 8), None).value == list(
        struct.pack(">d", 1.25)
    )


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_integer_of_date_accepts_exact_whole_values():
    assert _builtin_integer_of_date(_args(from_literal("20240101")), None).value == 154498


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_integer_argument_coercion_accepts_exact_whole_values():
    assert _coerce_intrinsic_int(from_literal("12")) == 12
    assert _coerce_intrinsic_int(from_literal("12.5")) is None


@covers(CobolFeature.NUMERIC_EDITED)
def test_edit_picture_formats_exact_value_text():
    assert format_edited("1.50", "ZZ9.99") == "  1.50"
    assert format_edited("0.50", ".99") == ".50"
```

Append to `tests/integration/test_cobol_exact_arithmetic.py`:

```python
class TestBoundaryBuiltins:
    @covers(CobolFeature.ROUNDED_CLAUSE)
    def test_rounded_division_of_an_exact_field(self):
        vm = _program(["01 X PIC 9V99.", "01 A PIC 9V99 VALUE 2.00."], ["    COMPUTE X ROUNDED = A / 3."])
        assert bytes(first_region(vm)[:3]).hex() == "f0f6f7"

    @covers(CobolFeature.NUMERIC_EDITED)
    def test_numeric_edited_move_of_an_exact_field(self):
        vm = _program(["01 E PIC ZZ9.99.", "01 A PIC 9(3)V99 VALUE 1.50."], ["    MOVE A TO E."])
        assert bytes(first_region(vm)[:6]).hex() == "4040f14bf5f0"

    @covers(CobolFeature.USAGE_COMP_2)
    def test_exact_field_round_trips_through_comp2(self):
        vm = _program(
            ["01 X PIC 9V99.", "01 A PIC 9V99 VALUE 1.25.", "01 D COMP-2."],
            ["    MOVE A TO D.", "    MOVE D TO X."],
        )
        assert bytes(first_region(vm)[:3]).hex() == "f1f2f5"
```

In `tests/unit/test_byte_builtins.py`, `TestPresentValue.test_nonzero_rate`: 110 discounted at 10% for one period is exactly 100, so replace `assert math.isclose(float(result), 100.0, rel_tol=1e-9)` with `assert result == 100`.

- [ ] **Step 2: Run to verify failure**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/unit/cobol/test_numeric_boundary_builtins.py tests/integration/test_cobol_exact_arithmetic.py::TestBoundaryBuiltins "tests/unit/test_byte_builtins.py::TestPresentValue" -q -n0`
Expected: FAIL for round-junk (raises `InvalidOperation`), float-to-bytes (`UNCOMPUTABLE`), integer-of-date (`UNCOMPUTABLE`), integer coercion (`None`). The integration tests and `test_round_accepts_exact_values_and_returns_plain_text` may already pass (regression guards); `TestPresentValue.test_nonzero_rate` should already pass with the tightened assertion — if it does not, report the actual value.

- [ ] **Step 3: Move the intrinsic Decimal math into `cobol_numeric/intrinsics.py`**

```python
# pyright: standard
"""Decimal math behind COBOL intrinsic functions (moved from byte_builtins, red-dragon-4q25.1).

Semantics are exactly those of the original builtins: arguments coerce through
Decimal (ints, floats via str(), Decimals, numeric text), and division, powers
and SQRT use the default decimal context, as before.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_DOWN, ROUND_FLOOR, Decimal, InvalidOperation

from cobol_numeric.number import CobolNumber


def coerce_argument(raw: object) -> CobolNumber | None:
    """ints, floats, Decimals and numeric strings -> Decimal; else None."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, Decimal)):
        return Decimal(raw)
    if isinstance(raw, float):
        return Decimal(str(raw))
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except InvalidOperation:
            return None
    return None


def is_integral(value: CobolNumber) -> bool:
    return value == value.to_integral_value()


def to_result(value: CobolNumber) -> int | CobolNumber:
    """int when integral, else the exact value (NUMVAL's convention)."""
    return int(value) if is_integral(value) else value


def total(values: Sequence[CobolNumber]) -> CobolNumber:
    return sum(values, Decimal(0))


def mean(values: Sequence[CobolNumber]) -> CobolNumber:
    return total(values) / len(values)


def median(values: Sequence[CobolNumber]) -> CobolNumber:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 == 1 else (ordered[mid - 1] + ordered[mid]) / 2


def midrange(values: Sequence[CobolNumber]) -> CobolNumber:
    return (max(values) + min(values)) / 2


def value_range(values: Sequence[CobolNumber]) -> CobolNumber:
    return max(values) - min(values)


def variance(values: Sequence[CobolNumber]) -> CobolNumber:
    """Sample variance (n - 1 divisor); callers handle n == 1."""
    n = len(values)
    average = total(values) / n
    return sum(((v - average) ** 2 for v in values), Decimal(0)) / (n - 1)


def square_root(value: CobolNumber) -> CobolNumber:
    return value.sqrt()


def absolute(value: CobolNumber) -> CobolNumber:
    return abs(value)


def floor_integer(value: CobolNumber) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def integer_part(value: CobolNumber) -> int:
    return int(value.to_integral_value(rounding=ROUND_DOWN))


def fraction_part(value: CobolNumber) -> CobolNumber:
    return value - value.to_integral_value(rounding=ROUND_DOWN)


def remainder(x: CobolNumber, y: CobolNumber) -> CobolNumber:
    return x - y * (x / y).to_integral_value(rounding=ROUND_DOWN)


def annuity(rate: CobolNumber, periods: int) -> CobolNumber:
    if rate == 0:
        return Decimal(1) / periods
    return rate / (1 - (1 + rate) ** (-periods))


def present_value(rate: CobolNumber, cashflows: Sequence[CobolNumber]) -> CobolNumber:
    return sum((cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cashflows)), Decimal(0))


def parse_numval_digits(text: str, negative: bool) -> int | CobolNumber | None:
    """NUMVAL's cleaned digit text -> int when integral, else exact; None if invalid."""
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None
    return to_result(-parsed if negative else parsed)
```

- [ ] **Step 4: Point `byte_builtins.py` at the boundary**

Top-level imports: add
```python
from cobol_numeric.intrinsics import (
    absolute,
    annuity,
    coerce_argument as _coerce_intrinsic_decimal,
    floor_integer,
    fraction_part,
    integer_part,
    is_integral,
    mean,
    median,
    midrange,
    parse_numval_digits,
    present_value,
    remainder,
    square_root,
    to_result as _decimal_to_intrinsic,
    total,
    value_range,
    variance,
)
from cobol_numeric.number import (
    as_whole_int,
    is_cobol_number,
    round_half_up,
    to_float,
    to_number,
    to_plain_str,
)
```
(merge with the `is_cobol_number` import added in Task 3). Delete the old `_coerce_intrinsic_decimal` and `_decimal_to_intrinsic` function definitions — the aliases above replace them, so their callers are unchanged. Then make these exact replacements (remove every local `from decimal import ...` line in the touched functions):

| Function | Old expression | New expression |
|---|---|---|
| `_numval_to_number` | `try: dec = Decimal(s) except InvalidOperation: return None` … `if negative: dec = -dec` … `if dec == dec.to_integral_value(): return int(dec)` / `return dec` | `return parse_numval_digits(s, negative)` |
| `_coerce_intrinsic_float` | `float(d)` | `to_float(d)` |
| `_builtin_sum` | `sum(values, Decimal(0))` | `total(values)` |
| `_builtin_abs` | `abs(d)` | `absolute(d)` |
| `_builtin_sqrt` | `d.sqrt()` | `square_root(d)` |
| `_builtin_range` | `max(values) - min(values)` | `value_range(values)` |
| `_builtin_mean` | `sum(values, Decimal(0)) / len(values)` | `mean(values)` |
| `_builtin_median` | the `ordered`/`n`/`mid`/`result` lines | `result = median(values)` |
| `_builtin_midrange` | `(max(values) + min(values)) / 2` | `midrange(values)` |
| `_builtin_variance` | `mean = ...` / `sq_dev = ...` / `sq_dev / (n - 1)` (keep the `n == 1` early return) | `variance(values)` |
| `_builtin_factorial` | `d != d.to_integral_value()` | `not is_integral(d)` |
| `_builtin_integer` | `int(d.to_integral_value(rounding=ROUND_FLOOR))` | `floor_integer(d)` |
| `_builtin_integer_part` | `int(d.to_integral_value(rounding=ROUND_DOWN))` | `integer_part(d)` |
| `_builtin_fraction_part` | `trunc = ...` / `d - trunc` | `fraction_part(d)` |
| `_builtin_rem` | `trunc = ...` / `x - y * trunc` | `remainder(x, y)` |
| `_builtin_annuity` | both `Decimal(1) / periods` and `rate / denominator` branches | `annuity(rate, periods)` |
| `_builtin_present_value` | `total = sum(...)` | `present_value(rate, cashflows)` |

`_builtin_cobol_round` — replace from `from decimal import ...` to the end with:
```python
    try:
        decimal_digits = int(args[1].value)
        rounded = round_half_up(to_number(args[0].value), decimal_digits)
    except (ValueError, TypeError):
        return BuiltinResult(value=_UNCOMPUTABLE)
    return BuiltinResult(value=to_plain_str(rounded))
```
`_builtin_cobol_blank_when_zero` — replace `is_zero = float(str(value_str)) == 0.0` with `is_zero = to_number(value_str) == 0`.
`_builtin_float_to_bytes` — before the `isinstance` check add:
```python
    if is_cobol_number(value) and not isinstance(value, int):
        value = to_float(value)
```
`_builtin_integer_of_date` — after `if isinstance(raw, float): raw = int(raw)` add:
```python
    if is_cobol_number(raw) and not isinstance(raw, int):
        whole = as_whole_int(raw)
        if whole is None:
            return BuiltinResult(value=_UNCOMPUTABLE)
        raw = whole
```
`_coerce_intrinsic_int` — after the `isinstance(raw, int)` branch add:
```python
    if is_cobol_number(raw):
        return as_whole_int(raw)
```

- [ ] **Step 5: `emit_context._is_zero_value` and `edit_picture`**

`emit_context.py` `_is_zero_value`:
```python
    def _is_zero_value(self, value: str) -> bool:
        """Check if a literal value is numerically zero."""
        try:
            return from_literal(value) == 0
        except ValueError:
            return False
```
`cobol_asg/edit_picture.py`: replace `from decimal import Decimal, InvalidOperation` with `from cobol_numeric.number import CobolNumber, digits_for_encode, from_digits, from_literal`; replace `_digit_strings` with
```python
def _digit_strings(value: CobolNumber, ep: EditPicture) -> tuple[str, str]:
    """Return (integer_digits, fraction_digits) zero-padded/truncated to the
    picture's digit-position counts. Truncates toward zero (no ROUNDED); on
    overflow the low-order integer digits win (COBOL high-order truncation)."""
    _, digits = digits_for_encode(value, ep.int_digits + ep.frac_digits, ep.frac_digits)
    return digits[: ep.int_digits], digits[ep.int_digits :]
```
and in `format_edited` replace the `try`/`except` that builds `dec` with
```python
    try:
        dec = from_literal(str(value).strip() or "0")
    except ValueError:
        dec = from_digits(0, 0)
```

- [ ] **Step 6: Run the targeted tests and the full suite**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/unit/cobol/test_numeric_boundary_builtins.py tests/unit/test_byte_builtins.py tests/integration/test_cobol_exact_arithmetic.py -q -n0`
Then: `uv run python -m black . && uv run lint-imports && PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar make test`
Expected: 0 failed. `rtk proxy grep -rnE "^\s*(from decimal import|import decimal)" interpreter cobol_asg cobol_memory mcp_server` prints nothing. Edit-picture unit tests (NIST NC124A cases) must stay green unchanged; if one fails, stop and report — the `digits_for_encode` split must reproduce `_digit_strings` exactly.

- [ ] **Step 7: Commit**

```bash
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic add cobol_numeric/intrinsics.py interpreter/cobol/byte_builtins.py interpreter/cobol/emit_context.py cobol_asg/edit_picture.py tests/unit/cobol/test_numeric_boundary_builtins.py tests/unit/test_byte_builtins.py tests/integration/test_cobol_exact_arithmetic.py
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic commit -m "refactor(cobol): route remaining numeric builtins through cobol_numeric (red-dragon-4q25.1)"
```

---

### Task 7: Remove the 96651c84 guard step (closes red-dragon-5b93)

**Files:**
- Modify: `interpreter/cobol/pic_scale.py` (`encode_digits`), `interpreter/cobol/byte_builtins.py` (`_builtin_cobol_prepare_digits` call)
- Test: `tests/unit/cobol/test_encode_digits_parity.py` (extend), `tests/integration/test_cobol_exact_arithmetic.py` (extend)

**Interfaces:**
- Consumes: Tasks 3–6 (all fixed-point operands, literals and arithmetic are exact, so no float noise reaches the encoder).
- Produces: `encode_digits(value, total_digits, decimal_digits, scale) -> tuple[bool, str]` — the `float_noise_guard` parameter is removed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/cobol/test_encode_digits_parity.py`:
```python
@covers(CobolFeature.PIC_CLAUSE)
def test_genuine_nines_beyond_the_scale_truncate():
    """red-dragon-5b93: the guard rounded 0.129999999 up to 0.13."""
    assert _runtime_digits("0.129999999", 3, 2, 0) == "012"
```
Append to `tests/integration/test_cobol_exact_arithmetic.py`:
```python
class TestGuardRegression:
    @covers(CobolFeature.COMPUTE)
    def test_compute_of_genuine_nines_truncates(self):
        vm = _program(["01 X PIC 9V99."], ["    COMPUTE X = 0.129999999."])
        assert bytes(first_region(vm)[:3]).hex() == "f0f1f2"

    @covers(CobolFeature.ADD)
    def test_add_of_genuine_nines_truncates(self):
        vm = _program(
            ["01 X PIC 9V99.", "01 A PIC 9V9(9) VALUE 0.009999999."],
            ["    MOVE 0.12 TO X.", "    ADD A TO X."],
        )
        assert bytes(first_region(vm)[:3]).hex() == "f0f1f2"
```

- [ ] **Step 2: Run to verify failure**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/unit/cobol/test_encode_digits_parity.py::test_genuine_nines_beyond_the_scale_truncate tests/integration/test_cobol_exact_arithmetic.py::TestGuardRegression -q -n0`
Expected: FAIL — `'013' != '012'` and `f0f1f3` stored.

- [ ] **Step 3: Delete the guard**

In `pic_scale.py`, `encode_digits`: remove the `float_noise_guard: bool = False` parameter, the docstring paragraph about it, and the two lines
```python
    if float_noise_guard and decimal_digits > 0:
        descaled = round_half_up(descaled, decimal_digits + 6)
```
and drop `round_half_up` from the import. In `byte_builtins.py`, `_builtin_cobol_prepare_digits`: remove `, float_noise_guard=True` from the `encode_digits` call.

- [ ] **Step 4: Run the guard's own tests, the new tests, and the full suite**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/unit/cobol/test_arithmetic_decimal_precision.py tests/unit/cobol/test_encode_digits_parity.py tests/integration/test_cobol_exact_arithmetic.py -q -n0`
Expected: PASS — including 96651c84's 76.60 and 180,576.60 tests, now exact without the guard.
Then `uv run python -m black . && PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar make test` → 0 failed. If `test_arithmetic_decimal_precision.py` fails, a float still reaches the encoder: stop and report which path (do not restore the guard).

- [ ] **Step 5: Commit**

```bash
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic add interpreter/cobol/pic_scale.py interpreter/cobol/byte_builtins.py tests/unit/cobol/test_encode_digits_parity.py tests/integration/test_cobol_exact_arithmetic.py
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic commit -m "fix(cobol): remove float-noise guard now that arithmetic is exact (red-dragon-5b93)"
```

---

### Task 8: Boundary invariants

**Files:**
- Test: `tests/unit/cobol/test_decimal_boundary_invariant.py` (create), `tests/integration/test_cobol_exact_arithmetic.py` (extend)

**Interfaces:**
- Consumes: Tasks 1–7.
- Produces: guards only.

- [ ] **Step 1: Write the invariant tests**

Create `tests/unit/cobol/test_decimal_boundary_invariant.py`:
```python
"""Only cobol_numeric may touch ``decimal`` (red-dragon-4q25.1).

The silent failure mode this guards: a module that quietly builds a Decimal or
calls a Decimal method spreads representation-specific handling outside the
boundary, so a future representation change misses it.
"""

import re
from pathlib import Path

from tests.covers import NotLanguageFeature, covers

REPO_ROOT = Path(__file__).resolve().parents[3]

# A deliberate regex rather than ast-grep, for the same reason as
# test_region_funnel_invariant.py: the tokens are single-line and unambiguous,
# and over-matching only names an extra file for a human to clear.
DECIMAL_USE = re.compile(
    r"^\s*(from\s+decimal\s+import|import\s+decimal)\b|\bDecimal\(", re.MULTILINE
)
SCANNED_ROOTS = ("interpreter", "cobol_asg", "cobol_memory", "mcp_server")


def _decimal_users() -> set[str]:
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for root in SCANNED_ROOTS
        for path in (REPO_ROOT / root).rglob("*.py")
        if DECIMAL_USE.search(path.read_text())
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_decimal_is_used_only_inside_cobol_numeric():
    offenders = sorted(_decimal_users())
    assert offenders == [], (
        f"decimal used outside cobol_numeric: {offenders}. Route the calculation "
        "through a cobol_numeric function so the representation stays swappable."
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_boundary_itself_still_uses_decimal():
    """Guards against the invariant passing vacuously."""
    assert DECIMAL_USE.search((REPO_ROOT / "cobol_numeric/number.py").read_text())
```
Append to `tests/integration/test_cobol_exact_arithmetic.py`:
```python
class TestExactLowering:
    @covers(CobolFeature.COMPUTE, CobolFeature.ARITHMETIC_EXPRESSION)
    def test_fixed_point_operators_lower_to_exact_builtins(self):
        from interpreter.frontend import make_cobol_parser
        from interpreter.instructions import CallFunction
        from interpreter.project.cobol_compile import compile_cobol
        from tests.integration.cobol_helpers import to_fixed

        source = to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. LOWER.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "01 A PIC 9V99 VALUE 1.25.",
                "01 X PIC 9(3)V99.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    COMPUTE X = A * 2 + A / 3 - 1.",
                "    STOP RUN.",
            ]
        )
        _, linked = compile_cobol(source.encode("utf-8"), parser=make_cobol_parser())
        called = {str(i.func_name) for i in linked.merged_ir if isinstance(i, CallFunction)}
        assert {"__cobol_multiply", "__cobol_add", "__cobol_divide", "__cobol_subtract"} <= called
```

- [ ] **Step 2: Run**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python -m pytest tests/unit/cobol/test_decimal_boundary_invariant.py tests/integration/test_cobol_exact_arithmetic.py::TestExactLowering -q -n0`
Expected: PASS. If the invariant lists offenders, migrate each through `cobol_numeric` (Tasks 3–6 patterns) — never add an allowlist.

- [ ] **Step 3: Full suite and commit**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar make test` → 0 failed.
```bash
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic add tests/unit/cobol/test_decimal_boundary_invariant.py tests/integration/test_cobol_exact_arithmetic.py
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic commit -m "test(cobol): enforce the cobol_numeric decimal boundary (red-dragon-4q25.1)"
```

---

### Task 9: Documentation — ADRs, COBOL design doc, type system

**Files:**
- Modify: `docs/architectural-design-decisions.md` (append ADR-148, ADR-149; append an amendment line under ADR-146), `docs/frontend-design/cobol.md` (Known Gaps), `docs/type-system.md` (Type Hierarchy)

- [ ] **Step 1: Append the amendment under ADR-146**

Immediately after ADR-146's `**Consequences:** ...` paragraph (before the `---` that precedes ADR-147), add a new paragraph:
```markdown
**Amendment (2026-09-15, ADR-148/ADR-149):** `__cobol_round` now receives an exact `CobolNumber` (or numeric text) and delegates to `cobol_numeric.round_half_up`; its `decimal` import moved into `cobol_numeric`. `force_division_float` is gone — ROUNDED division keeps its extra digit through IBM `dmax` (a ROUNDED receiver contributes its decimal places + 1).
```

- [ ] **Step 2: Append ADR-148 and ADR-149 at the end of the file**

```markdown

---

### ADR-148: COBOL exact fixed-point arithmetic behind a `cobol_numeric` boundary (2026-09-15)

**Context:** COBOL fixed-point values were decoded, computed and re-encoded through Python `float` (red-dragon-4q25.1). Verified losses: `COMPUTE X = 4.35 * 100` into `PIC 999` stored 434; an 18-digit `ADD` lost its last digit; COMP/BINARY fields with decimal places lost their fraction on decode and their scaling on store (red-dragon-0dvs). A temporary guard-and-truncate step (96651c84) masked some float noise but rounded genuine values up (red-dragon-5b93). The two numeric encode paths also truncated fractions differently (red-dragon-bqds).

**Decision:** A new top-level leaf package `cobol_numeric` owns the exact representation (`CobolNumber`, currently Python `Decimal`) and every conversion between it and COBOL representations: stored digits (`from_digits`, `digits_for_encode`), PIC P scaling (`scale_by`), literals (`from_literal`), IEEE floats (`from_float`/`to_float`), text (`to_plain_str`, whose `-?digits(.digits)?` grammar IS NUMERIC relies on), truncation and ROUNDED, and intrinsic-function math. Arithmetic uses exact integer ratios, never the `decimal` context (whose default 28-digit precision would round IBM's 30-digit intermediates). COBOL lowering emits boundary builtins (`__cobol_add/subtract/multiply/divide`, `__cobol_from_digits`, `__cobol_scale_by`, `__cobol_parse_number`, `__cobol_binary_unscaled`, `__cobol_to_text`, `__cobol_to_float`). A new `Decimal` foundation type and `Const.decimal_` are the only shared-code additions. Scope is COBOL only. Rejected: scaled integers with statically tracked scale (rewrites all COBOL lowering; consumers see raw scaled ints) and `fractions.Fraction` (non-COBOL intermediate semantics, unbounded growth).

**Consequences:** Other languages' conversion rules, binop coercion, `BINOP_TABLE` and `str` builtin are unchanged. An import-linter contract (`cobol-numeric-is-a-leaf`) and an invariant test (no `decimal` outside `cobol_numeric`) keep the boundary; replacing the representation means editing one package. Closes red-dragon-4q25.1, red-dragon-0dvs, red-dragon-bqds and red-dragon-5b93. The 96651c84 guard step is removed. Exponentiation (`**`) remains unsupported (red-dragon-wxur).

---

### ADR-149: COBOL intermediate precision — IBM `ARITH(COMPAT)` scale rules computed at lowering time (2026-09-15)

**Context:** Compilers disagree on division: IBM sizes a quotient's decimal places from `dmax`; GnuCOBOL carries 38 extra digits. RedDragon's mod idiom `A - (A / B) * B` (red-dragon-apoq) and its downstream programs follow IBM: `2023 / 4 * 4` must be 2020, which GnuCOBOL-style division would make 2023.

**Decision:** Implement IBM's places-carried table as pure `Scale` functions in `cobol_numeric.scale` (`+ -`: `max(i1, i2) + 1` / `max(d1, d2)`; `*`: `i1 + i2` / `d1 + d2`; `/`: `i2 + d1` / `max(d2 − d1, dmax)`) and the 30-digit carry table (`carry`). Lowering computes each node's `Scale` and each statement's `dmax` (largest of receiver decimals — plus one for a ROUNDED receiver — and non-divisor operand decimals) from PICs, literals and receivers, and passes the carried decimal places as a constant to the exact builtin. IBM's floating-point rule applies per expression: a COMP-1/COMP-2 operand or receiver, or a floating intrinsic, makes the whole expression IEEE floating point. `force_division_float` and COBOL's reliance on `(Int, Int) /` → `//` are removed. The 18-digit PIC limit is retained.

**Consequences:** Integer-only expressions truncate exactly as before; receivers with decimal places keep fractions IBM keeps (`7 / 2 * 2` into `PIC 9V9` = 7.0, previously 6.0). The high-order integer truncation rows of the carry table are not emulated (receivers overflow first under the 18-digit PIC limit). The ROUNDED + 1 contribution and the intrinsic classification (floating / integer / argument-scaled) are this project's reading of IBM behaviour, verified against NIST-85 during implementation. `ARITH(EXTEND)` is a `limit=31` extension of `carry`; GnuCOBOL-style division is out of scope.
```
If Task 4 Step 1's NIST verification recorded any nuance, add one sentence citing the programs checked to ADR-149's Consequences.

- [ ] **Step 3: COBOL design doc**

In `docs/frontend-design/cobol.md`, Known Gaps, replace the bullet
`- **All arithmetic routes through Python `float`** for decimal/fixed-point fields, not true fixed-point/decimal arithmetic (red-dragon-4q25.1, P0 — the largest remaining gap).`
with
`- **Exponentiation (`**`) is not parsed or lowered** (red-dragon-wxur). Fixed-point arithmetic is exact (IBM `ARITH(COMPAT)` rules, `cobol_numeric` boundary — see ADR-148/ADR-149); only COMP-1/COMP-2 and floating intrinsic expressions use IEEE floats.`

- [ ] **Step 4: Type-system doc**

In `docs/type-system.md`, Type Hierarchy: change "12 nodes" to "13 nodes"; add `DECIMAL["Decimal"]` to the mermaid node list and `NUMBER --> DECIMAL` to the edges; add `DECIMAL = "Decimal"` to the TypeName listing with the note `(COBOL fixed-point values only; ADR-148)`. Under "CONST — Literal and Function Reference Typing", after `Float literals → Float`, add `   - COBOL fixed-point literals with a decimal point → `Decimal``.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic add docs/architectural-design-decisions.md docs/frontend-design/cobol.md docs/type-system.md
/usr/bin/git -C /Users/asgupta/code/red-dragon/.claude/worktrees/cobol-exact-arithmetic commit -m "docs: ADR-148/149 exact COBOL arithmetic and IBM intermediate precision"
```

---

### Task 10: NIST-85 after-measurement and issue notes

**Files:** none tracked.

- [ ] **Step 1: Re-run the tracer**

```bash
PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar uv run python scripts/nist_ccvs_tracer.py NC121M NC207A NC220M NC123A NC117A 2>&1 | tail -60 > /tmp/nist-arith-after.txt; diff /tmp/nist-arith-before.txt /tmp/nist-arith-after.txt; true
```
Expected: the diff shows the change in failing assertions. Any NEW failure cluster that did not exist before is a regression: stop and report it with the RE-MARK/FEATURE lines.

- [ ] **Step 2: Record results**

```bash
bd update red-dragon-4q25.1 --append-notes "NIST-85 arithmetic after (branch worktree-cobol-exact-arithmetic): $(head -3 /tmp/nist-arith-after.txt | tr '\n' ' ') | full suite: <paste the final 'N passed' line from the last make test>"
```
(Replace the angle-bracket text with the actual summary line before running.) Do not close issues here; closing happens when the branch is merged (superpowers:finishing-a-development-branch).

