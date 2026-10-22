# zarch_float — z/Architecture Floating Point

> `zarch_float/` · top-level leaf package (`zarch-float-is-a-leaf`) · ADR-194

## Overview

Arithmetic, rounding and exception conditions for BFP (IEEE binary), HFP and DFP, per
the Principles of Operation chapters 9 and 18-20. HLASM lowering reaches it through
the builtins in `interpreter/hlasm/bfp_builtins.py` (red-dragon-6uyp.51).

- **No bytes.** Values are frozen records of sign, kind, significand and exponent. IR
  encodes and decodes the bit images.
- **Exact, then one rounding.** Results are computed as integers or `Fraction`s and
  rounded once into the target format. Host floats are test oracles only.
- **Conditions are data.** A result carries the `Condition`s it raised. The caller
  applies the FPC masks, the XiC/XxC/XqC controls and the PSW masks, and raises the
  data exception or program interruption.

## Shared modules

| Module | Purpose |
|---|---|
| `rounding_mode.py` | `RoundingMode` (eight methods); `BFP_FPC_MODES`, `BFP_MODIFIER_MODES` and the DFP and HFP tables map FPC and M-field codes to methods |
| `condition.py` | `Condition`; `raised(...)` builds a condition set |
| `float_kind.py` | `FloatKind`: ZERO, FINITE, INFINITY, QNAN, SNAN |
| `comparison.py`, `comparison_result.py` | `Comparison` (value = CC) with its conditions |
| `integer_format.py`, `integer_result.py` | `SIGNED_32/64`, `UNSIGNED_32/64`; a converted integer with its conditions |
| `exact_rounding.py` | `round_ratio`: an exact ratio to an integer under a method (binary RFS: odd last bit) |

## BFP

`BfpValue(format, negative, kind, significand, exponent)`: a finite value is
significand × 2^exponent, canonical with the significand in [2^(p-1), 2^p) or subnormal
at the minimum exponent. Zeros and infinities carry 0, 0. A NaN's significand is its
payload, the fraction without the quiet bit. Formats: `SHORT`, `LONG`, `EXTENDED`.

`BfpResult(value, conditions, scaled, scaled_conditions)`. `value` is the nontrap result.
`scaled` is what an enabled overflow or underflow trap delivers instead: the
precision-rounded value scaled by 2^∓192/1536/24576 (LOAD ROUNDED: by source, 512/8192,
in the source format), with its own inexact and incremented conditions.

| Function | Notes |
|---|---|
| `bfp_add`, `bfp_subtract`, `bfp_multiply`, `bfp_divide` | `(a, b, mode)` |
| `bfp_square_root` | `(a, mode)` |
| `bfp_multiply_add`, `bfp_multiply_subtract` | `(a, b, c, mode)` = a × b ± c, one rounding. MADBR passes op3, op2, op1 |
| `bfp_compare`, `bfp_compare_signaling` | `ComparisonResult` |
| `bfp_load_rounded`, `bfp_load_lengthened` | NaN payloads truncate on the right or extend with zeros |
| `bfp_round_to_integral` | LOAD FP INTEGER |
| `bfp_from_integer`, `bfp_to_integer` | Signed and unsigned alike: the caller reads the register. Out of range and NaN give an end of the `IntegerFormat` with INVALID and INEXACT |
| `bfp_divide_to_integer` | `(a, b, quotient_mode, remainder_mode)`: `BfpDivideToIntegerResult(remainder, quotient, partial, quotient_overflow)`. Final when \|q\| < 2^p or q is an integer; otherwise the quotient is truncated to p bits and the remainder is exact, without TINY. An overflowing quotient is scaled by 2^-192/-1536 |
| `bfp_widened` | Exact retag into a wider format; an SNaN stays signaling (the lengthening multiplies) |

Rules taken from the PoO:

- Tininess is detected before rounding. TINY is reported whenever the precise value is
  below Nmin; UNDERFLOW (the nontrap flag) only when it is also inexact.
- Overflow delivers infinity under the nearest modes and away-from-zero, Nmax under
  toward-zero and prepare-for-shorter, and depends on sign under the directed modes.
  Infinity counts as incremented.
- NaNs: the first SNaN in operand order, quieted, with INVALID; else the first QNaN.
  For fused multiply-add, 0 × ∞ gives the default NaN even when op1 is a NaN.
- An exact zero sum of opposite signs is +0, or −0 under round toward −∞.

## HFP

`HfpValue(format, negative, fraction, exponent)`: 0.fraction × 16^exponent, the fraction
`format.digits` hex digits (6, 14, 28), the exponent the characteristic − 64 and unbounded.
`HfpResult(value, conditions)`. The caller wraps the characteristic modulo 128 when the
interruption is taken, or forces a true zero when HFP_EXPONENT_UNDERFLOW or
HFP_SIGNIFICANCE is masked. HFP_DIVIDE and HFP_SQUARE_ROOT return the operand unchanged:
the operation is suppressed.

| Function | Notes |
|---|---|
| `hfp_add`, `hfp_subtract` | `(a, b, normalize)`: one guard digit; unnormalized results keep leading zeros and test zero without the guard digit |
| `hfp_compare` | The normalized-subtraction difference with its guard digit, so digits beyond it are lost |
| `hfp_multiply` | `(a, b, target)`: the exact product truncated; `target` LONG from SHORT operands gives MDER, EXTENDED from LONG gives MXDR |
| `hfp_divide`, `hfp_halve` | Exact quotient, normalized and truncated |
| `hfp_square_root` | Truncated to one guard digit, then a half is added at it (SQER, SQDR, SQXR) |
| `hfp_load_rounded`, `hfp_load_lengthened` | LOAD ROUNDED adds a half at the first dropped bit; a carry shifts right |
| `hfp_from_integer`, `hfp_to_integer` | From: normalized, truncated. To: under the M3 method; out of range gives an end of the range with OUT_OF_RANGE (CC 3) |

Zero fractions give a positive true zero from multiply, divide, halve, square root and
CONVERT FROM FIXED, as figure 18-1 states.

## DFP

`DfpValue(format, negative, kind, significand, exponent)`: right-units view, significand ×
10^exponent; a zero keeps its exponent (its quantum). A NaN's significand is its payload.
Formats: `SHORT` (7 digits, only for LOAD LENGTHENED and LOAD ROUNDED), `LONG`, `EXTENDED`.
`DfpResult` mirrors `BfpResult`; the trap scale is 10^∓576/9216 (LOAD ROUNDED by source,
192/3072).

`dfp_context.py` is the only `decimal` boundary besides `dfp_arithmetic.py`'s operation
types: contexts with the format's precision and exponent range, `clamp=1`, traps off.
`decimal` follows IEEE 754-2008 decimal, so its ideal exponents are the preferred quanta,
Subnormal is tininess before rounding (TINY), and ROUND_05UP is round to prepare for
shorter precision. INCREMENTED compares with the exact `Fraction`.

| Function | Notes |
|---|---|
| `dfp_add`, `dfp_subtract`, `dfp_multiply`, `dfp_divide` | `(a, b, mode)`, `a` the second operand of the instruction |
| `dfp_quantize` | `(value, quantum, mode)`: NaNs are chosen in the PoO's order (quantum operand first), which is not `decimal`'s |
| `dfp_reround` | `(value, significance, mode)` |
| `dfp_compare`, `dfp_compare_signaling` | `ComparisonResult` |
| `dfp_load_rounded`, `dfp_load_lengthened` | NaN payloads lose leftmost digits or keep them |
| `dfp_round_to_integral` | LOAD FP INTEGER |
| `dfp_from_integer`, `dfp_to_integer` | Out of range and NaN raise INVALID without INEXACT, unlike BFP |

QUANTUM is raised as the PoO defines the quantum-exception condition: inexact, or an exact
finite result off the preferred quantum; DIVIDE's own four cases; and, for LOAD FP INTEGER,
QUANTIZE and REROUND, a delivered quantum other than the source's. QUANTIZE, REROUND and
LOAD FP INTEGER report only INVALID, INEXACT, INCREMENTED and QUANTUM.
