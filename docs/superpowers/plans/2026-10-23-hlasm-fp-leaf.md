# HLASM Floating-Point Leaf Package — `zarch_float` (red-dragon-6uyp.21)

**Goal:** a top-level leaf package owning z/Architecture floating-point arithmetic,
rounding and exception conditions for BFP, HFP and DFP. No builtin adapters and no
`interpreter/` changes; those land with .50/.51.

**Binding:** ruling R40; spec `2026-10-21-hlasm-frontend-design.md` (floating-point
paragraph); ADR-148's `cobol_numeric` model. Semantics: the PoO (SA22-7832-14) chapters
9, 18, 19 and 20.

## Rules taken from the PoO

- Tininess is detected before rounding (9-23, note 3a), for BFP and DFP.
- Nontrap underflow is tiny and inexact; a trap-enabled underflow fires on tiny alone and
  delivers the scaled value Tw(g) (figures 19-9, 20-6). Overflow nontrap results per mode:
  nearest and away give infinity, toward 0 and prepare-for-shorter give Nmax, directed
  modes by sign. Scale exponents: BFP 192/1536/24576 (LOAD ROUNDED by source 512/8192),
  DFP 576/9216 (LOAD ROUNDED 192/3072).
- NaNs: the first SNaN in operand order wins, quieted, with invalid; otherwise the first
  QNaN. FMA order is op3, op2, op1, but 0 × ∞ gives the default NaN even with a NaN op1.
- RFS: BFP picks the candidate with an odd last bit; DFP picks toward zero unless that
  candidate's last digit is 0 or 5.
- HFP truncates (guard digit in add, subtract and compare; exact intermediates in multiply,
  divide, halve); LOAD ROUNDED adds half and truncates; square root rounds at the guard
  digit. Exponents are returned unbounded, so the caller wraps the characteristic (trap) or
  forces a true zero (masked), per the PSW masks.

## Module layout (flat, one class per module)

- `rounding_mode.py` — `RoundingMode` (8 methods) and the code tables `BFP_FPC_MODES`,
  `BFP_MODIFIER_MODES`, `DFP_FPC_MODES`, `DFP_MODIFIER_MODES`, `HFP_MODIFIER_MODES`.
- `condition.py` — `Condition`: INVALID, DIVISION_BY_ZERO, OVERFLOW, UNDERFLOW, TINY,
  INEXACT, INCREMENTED, QUANTUM, HFP_EXPONENT_OVERFLOW, HFP_EXPONENT_UNDERFLOW,
  HFP_SIGNIFICANCE, HFP_DIVIDE, HFP_SQUARE_ROOT, OUT_OF_RANGE.
- `float_kind.py` — `FloatKind`: ZERO, FINITE, INFINITY, QNAN, SNAN (BFP, DFP).
- `comparison.py` — `Comparison`: EQUAL 0, LOW 1, HIGH 2, UNORDERED 3 (the CC).
- `comparison_result.py`, `integer_result.py`, `integer_format.py` (SIGNED_32/64,
  UNSIGNED_32/64 with their ranges).
- `exact_rounding.py` — `round_ratio(numerator, denominator, mode, negative)` → `RoundedInteger`
  (`rounded_integer.py`): the one integer-rounding primitive BFP and HFP share.
- BFP: `bfp_format.py` (SHORT/LONG/EXTENDED), `bfp_value.py`, `bfp_result.py`,
  `bfp_rounding.py` (exact `Fraction` → format), `bfp_nan.py`, `bfp_arithmetic.py`,
  `bfp_compare.py`, `bfp_convert.py`.
- HFP: `hfp_format.py`, `hfp_value.py`, `hfp_result.py`, `hfp_arithmetic.py`,
  `hfp_convert.py`.
- DFP: `dfp_format.py`, `dfp_value.py`, `dfp_result.py`, `dfp_context.py` (the only
  `decimal` user), `dfp_arithmetic.py`, `dfp_convert.py`.

## Public API

Values: `BfpValue(format, negative, kind, significand, exponent)` — finite value is
significand × 2^exponent; NaN payload is the fraction without the quiet bit.
`HfpValue(format, negative, fraction, exponent)` — 0.fraction × 16^exponent, fraction of
`format.digits` hex digits. `DfpValue(format, negative, kind, significand, exponent)` —
right-units view; NaN payload is the trailing significand.

Results: `BfpResult(value, conditions, scaled, scaled_conditions)` and `DfpResult` alike
(`scaled` is Tw(g)); `HfpResult(value, conditions)`; `ComparisonResult(comparison,
conditions)`; `IntegerResult(value, conditions)`.

- BFP: `bfp_add/subtract/multiply/divide(a, b, mode)`, `bfp_square_root(a, mode)`,
  `bfp_multiply_add/subtract(a, b, c, mode)` (a × b ± c), `bfp_compare(a, b)`,
  `bfp_compare_signaling(a, b)`, `bfp_load_rounded(a, target, mode)`,
  `bfp_load_lengthened(a, target)`, `bfp_round_to_integral(a, mode)`,
  `bfp_from_integer(n, format, mode)`, `bfp_to_integer(a, integer_format, mode)`.
- HFP: `hfp_add/subtract(a, b, normalized)`, `hfp_multiply(a, b, target)`,
  `hfp_divide(a, b)`, `hfp_square_root(a)`, `hfp_halve(a)`, `hfp_compare(a, b)`,
  `hfp_load_rounded(a, target)`, `hfp_load_lengthened(a, target)`,
  `hfp_from_integer(n, format)`, `hfp_to_integer(a, integer_format, mode)`.
- DFP: `dfp_add/subtract/multiply/divide(a, b, mode)`, `dfp_quantize(value, quantum, mode)`,
  `dfp_reround(value, significance, mode)`, `dfp_compare`, `dfp_compare_signaling`,
  `dfp_load_rounded(a, target, mode)`, `dfp_load_lengthened(a, target)`,
  `dfp_round_to_integral(a, mode)`, `dfp_from_integer(n, format, mode)`,
  `dfp_to_integer(a, integer_format, mode)`.

## Trade-offs

- **Exact rationals, then one rounding** (chosen, R40) over host floats: host floats cover
  neither extended nor the directed and RFS modes, and never report tininess.
- **BFP and HFP on `Fraction` and ints; DFP on `decimal`** with explicit contexts
  (`prec` 7/16/34, `clamp=1`, traps off). `decimal` implements IEEE 754-2008 decimal:
  ideal exponents match the PoO's preferred quanta, Subnormal is tininess before rounding,
  and ROUND_05UP is RFS. Hand-rolling the cohort rules was the alternative; it duplicates
  a tested library. QUANTIZE's NaN order differs from `decimal`'s, so NaNs are chosen
  before calling it. `Fraction` gives the exact value for "incremented".
- **Conditions as a frozenset of one enum** over per-family flag records: one shape for the
  caller's FPC/PSW logic; XiC/XxC/XqC suppression and the masks stay with the caller.
- **Unbounded HFP exponents** over pre-wrapped characteristics: wrapping and true-zero
  forcing depend on PSW masks the leaf does not see.
- **NaN payloads as ints without the quiet bit** over raw fraction fields: quieting is a
  kind change, and narrowing is a shift.

## Tests (tests/unit/zarch_float/)

- BFP: host-oracle table (binary64, and binary32 via `ctypes.c_float`) for add, subtract,
  multiply, divide, square root (and long FMA via `math.fma`) under round-to-nearest:
  halfway cases, subnormals, overflow, signed zeros; PoO figure 9-11 binary column through
  `bfp_round_to_integral`; overflow, underflow and trap scaling per mode; NaN precedence;
  integer conversions; extended results.
- HFP: the PoO's SQER examples; guard-digit add/subtract, unnormalized add, compare;
  multiply/divide/halve truncation; exponent overflow, underflow, significance, divide;
  conversions and LOAD ROUNDED carry.
- DFP: figure 9-11 decimal column; figure 9-12 LOAD ROUNDED; figures 9-13/9-14 REROUND;
  preferred quanta and quantum conditions; overflow, tininess, NaN order; conversions.
- `test_decimal_boundary_invariant.py` widened to allow `decimal` in `zarch_float`.
- Mutation checks per family, two breakages each.

## Commits

1. This plan.
2. BFP + shared modules + `zarch-float-is-a-leaf` contract + packaging + living doc
   `docs/frontend-design/zarch-float.md` (linked from `hlasm.md`) + ADR-194.
3. HFP + docs.
4. DFP + decimal invariant + docs + bead snapshot.
