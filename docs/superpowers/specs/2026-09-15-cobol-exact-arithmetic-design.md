# COBOL Exact Arithmetic — Design

**Status:** Draft for review
**Date:** 2026-09-15
**Issue:** red-dragon-4q25.1 (P0) under epic red-dragon-4q25; also closes red-dragon-0dvs (P1), red-dragon-bqds (P2) and red-dragon-5b93 (P2)
**Scope:** COBOL only. All other languages keep IEEE-754 float semantics.

## Context

COBOL fixed-point values are decoded, computed and re-encoded through Python `float`, so arithmetic silently loses precision. COBOL requires exact decimal fixed-point arithmetic.

Verified end-to-end through `run()`, before and after the temporary workaround described below:

| Probe | Expected | `7a9fac23` | `96651c84` (current) |
|---|---|---|---|
| A: `COMPUTE X = 0.1 + 0.7`, X `PIC 9V99` | 0.80 | **0.79** | 0.80 (masked by guard) |
| E: `COMPUTE X = 4.35 * 100`, X `PIC 999` | 435 | **434** | **434** |
| G: `PIC S9(9)V9(9) VALUE 123456789.123456788`, `ADD 0.000000001` | .123456789 | **.123456790** | **.123456790** |
| H: `COMPUTE X = 0.129999999`, X `PIC 9V99` | 0.12 | — | **0.13** (guard regression) |
| I: `MOVE 0.12 TO X`, `ADD A TO X`, A `PIC 9V9(9) VALUE 0.009999999` | 0.12 | — | **0.13** (guard regression) |
| D: `COMPUTE Q = -7 / 2` and `DIVIDE`, Q `PIC S9` | -3 | -3 | -3 |

### Temporary workaround already on main

- **`96651c84` — guard+truncate in `__cobol_prepare_digits`.** After descaling, when `decimal_digits > 0`, the value is first quantized to `decimal_digits + 6` places with `ROUND_HALF_UP` (collapsing float noise such as `76.59999999999994` → `76.60`), then to `decimal_digits` with `ROUND_DOWN`. It adds `tests/unit/cobol/test_arithmetic_decimal_precision.py` (38.30 + 38.30 = 76.60; a five-operand `COMPUTE` = 180,576.60), which pass. It masks probe A, does not help integer receivers (E, guard skipped at `decimal_digits == 0`) or digits the float never held (G), and introduces a regression: genuine values with nines beyond the receiver's scale are rounded up before truncation (H, I). Tracked as its own bug (see Decisions).
- **`8d3b4e54` — `IS NUMERIC` accepts sign and decimal point.** `_builtin_is_numeric` now accepts an optional leading `+`/`-`, digits, and at most one `.`, because it receives `emit_to_string` text of implied-decimal fields (e.g. `180038.30`). This makes the textual form of COBOL numbers load-bearing for class conditions.

The issue's original acceptance criteria were revised on 2026-09-15: `0.1 + 0.2` into `PIC 9V99` passes by luck (float `0.30000000000000004` truncates to 0.30), and a 20-digit `PIC 9(10)V9(10)` exceeds the 18-digit `ARITH(COMPAT)` PIC limit (`cobol_asg/picture.py:213`).

## How floats enter today

- **Decode:** zoned, zoned-separate, binary and COMP-3 IR decoders divide accumulated digits by `float(10**d)` (`interpreter/cobol/ir_encoders.py:348,624,962`). The float divisor exists to dodge `DefaultTypeConversionRules` rewriting `(Int, Int) /` to `//`.
- **PIC P scaling:** `emit_context.py:861` multiplies by `float(10**td.scale)`.
- **Literals:** `parse_literal` (`emit_context.py:1255`) tries `int` then `float`; `const_to_reg` emits `Const.float_`.
- **Lowering:** stray `float()` calls in `lower_arithmetic.py` (ref-mod writeback, figurative constants); `force_division_float` in `condition_lowering.py:993` wraps ROUNDED divisors in `float()`.
- **Existing `Decimal` islands:** `pic_scale.py`, `__cobol_prepare_digits`, `__cobol_round`, intrinsic helpers in `byte_builtins.py` — each converts back to `float`/`str` at its edges.
- **Type system:** numeric foundation types are only `Int`, `Float`, `Number`. `runtime_type_name` returns `""` for unknown Python types, so `_coerce_typed_register` leaves such values untouched.
- **Builtins rejecting non-float numbers:** `byte_builtins.py:263,325,640,1145,1172` check `isinstance(x, (int, float))`.
- **Text:** `DISPLAY` uses `emit_to_string` → generic `str` builtin.
- **Serialization:** `_serialize_value` (`interpreter/vm/vm_types.py:131`) passes unknown values through unchanged.

## Decisions

| Question | Decision |
|---|---|
| Languages covered | COBOL only |
| Representation | Python `Decimal`, hidden behind the `cobol_numeric` boundary module |
| Intermediate precision | IBM `ARITH(COMPAT)` rules, computed statically at lowering time: `+ -` carry `max(d1, d2)` decimals, `*` carries `d1 + d2`, `/` carries `max(d2 − d1, dmax)` decimals truncated toward zero; the 30-digit carry table applies when an intermediate exceeds 30 digits; receiver truncation / `ROUNDED` unchanged. Chosen over GnuCOBOL-style 38-digit division because that breaks red-dragon-apoq (`2023 / 4 * 4` must be 2020) and the downstream programs target IBM |
| Floating-point expressions | IBM rule: a COMP-1/COMP-2 operand or receiver, a floating-point literal, an exponent with decimal places, or a floating-point intrinsic makes the whole expression floating point |
| PIC digit limit | Stays at 18 (`ARITH(COMPAT)`) |
| COMP-1 / COMP-2 | Stay binary floating point; converted at the boundary |
| Boundary | Every Decimal ↔ COBOL-representation calculation lives behind functions in one module, so the representation can change later without touching callers |
| `96651c84` guard workaround | Kept until decode, literals and division are exact, then removed (Section 3, step 9). Its regression (probes H, I) is tracked as red-dragon-5b93; its tests become permanent regression tests |
| `8d3b4e54` `IS NUMERIC` text parsing | Kept; `to_plain_str` is held to the grammar it accepts by a contract test |

Rejected representations: scaled integers with statically tracked scale (rewrites all COBOL arithmetic lowering; consumers see raw scaled ints) and `fractions.Fraction` (non-COBOL intermediate semantics; unbounded growth).

Research basis (IBM COBOL for AIX 5.1 reference pages `rpinr03` "Terminology used for intermediate results", `rpinr04` "Fixed-point data and intermediate results", `rpinr09` "Floating-point data and intermediate results"):

- **Terms.** In a generated operation, `op1` is the first operand (the divisor in division) and `op2` the second (the dividend); `i1`/`i2` and `d1`/`d2` are their integer and decimal places. `dmax` is the largest of: the decimal places needed for the final result field(s); the maximum decimal places of any operand except divisors and exponents; the outer-dmax of any function operand.
- **Places carried:**

  | Operation | Integer places | Decimal places |
  |---|---|---|
  | `+` or `-` | `max(i1, i2) + 1` | `max(d1, d2)` |
  | `*` | `i1 + i2` | `d1 + d2` |
  | `/` | `i2 + d1` | `max(d2 − d1, dmax)` |

- **30-digit carry (`ARITH(COMPAT)`):** if `i + d ≤ 30`, carry `i` and `d`. Otherwise: if `d ≤ dmax`, carry `30 − d` integer and `d` decimal places; if `d > dmax` and `i + dmax ≤ 30`, carry `i` integer and `30 − i` decimal places; if `d > dmax` and `i + dmax > 30`, carry `30 − dmax` integer and `dmax` decimal places.
- **Floating point:** the whole expression is computed in floating point if a receiver or operand is COMP-1, COMP-2, external floating point, or a floating-point literal; an exponent contains decimal places; an exponent is an expression containing `**` or `/` and `dmax > 0`; or an intrinsic function is a floating-point function.
- **Assumption to verify (not stated on the IBM pages):** a `ROUNDED` receiver contributes its decimal places **plus one** to `dmax`, so the extra digit exists to round from. Required by the existing test `COMPUTE X ROUNDED = 10 / 6` → 2. Verified against NIST-85 before implementation (Section 3, step 6).

Rejected: GnuCOBOL-style division (`cob_decimal_div` shifts the dividend by `COB_MAX_DIGITS`, 38, before dividing), because `2023 / 4 * 4` would store 2023, breaking red-dragon-apoq's mod idiom `A - (A / B) * B`.

Probes of today's division behaviour (main `96651c84`): `COMPUTE X = 2023 / 4 * 4` into `PIC 9(4)` stores 2020 (correct under IBM); `COMPUTE X = 7 / 2 * 2` into `PIC 9V9` stores 6.0 (IBM: `dmax = 1`, 3.5 × 2 = 7.0, so today is wrong).

## Section 1 — The `cobol_numeric` boundary

### Package and layering

New top-level package `cobol_numeric/`, a sibling of `cobol_asg/` and `cobol_memory/`, with an import-linter contract:

```ini
[importlinter:contract:cobol-numeric-is-a-leaf]
name = The COBOL numeric boundary must not import the interpreter
type = forbidden
source_modules =
    cobol_numeric
forbidden_modules =
    interpreter
```

`cobol_numeric` is added to `root_packages`. COBOL lowering, COBOL builtins, `interpreter.instructions` and `interpreter.vm.vm_types` may import it; no existing contract forbids that.

### The representation

`CobolNumber` is a type alias for the current representation (`Decimal`). `cobol_numeric` is the **only** module that imports `decimal`. Every other module treats a `CobolNumber` as opaque: it is passed around, stored in registers and compared (`==`, `<`, … are exact for `Decimal` at any precision), but never combined with Python arithmetic operators on the COBOL arithmetic path.

All four COBOL arithmetic operators lower to boundary builtins — `__cobol_add`, `__cobol_subtract`, `__cobol_multiply`, `__cobol_divide` — rather than `Binop`s. Reason: Python's default `Decimal` context rounds every arithmetic result to 28 significant digits (verified: `123456789.123456789 × 987654321.987654321` returns `121932631356500531.3472031691`, losing the last 8 digits of the exact `121932631356500531.347203169112635269`), while IBM intermediates carry up to 30 digits. The boundary functions compute with exact integer ratios, so no context precision and no global state is involved.

### Functions

| Function | Purpose / replaces |
|---|---|
| `from_digits(digits: int, decimal_digits: int) -> CobolNumber` | Field decode (`digits × 10^-decimal_digits`), via `__cobol_from_digits` |
| `scale_by(n: int \| CobolNumber, scale: int) -> CobolNumber` | PIC P scaling (`n × 10^scale`, scale may be negative), via `__cobol_scale_by` |
| `from_literal(text: str) -> CobolNumber` | `parse_literal` non-integer branch; flat `CONST` `"Decimal"` branch |
| `from_float(x: float) -> CobolNumber` | COMP-1/COMP-2 decode; floating-point intrinsic results (`Decimal(repr(x))`) |
| `to_float(n: CobolNumber) -> float` | COMP-1/COMP-2 encode; floating-point intrinsic inputs |
| `add(a, b, result_decimals: int) -> CobolNumber` | `__cobol_add`: exact sum truncated toward zero to `result_decimals` places (the carried scale from `add_scale` + `carry`) |
| `subtract(a, b, result_decimals: int) -> CobolNumber` | `__cobol_subtract`: as `add` |
| `multiply(a, b, result_decimals: int) -> CobolNumber` | `__cobol_multiply`: exact product truncated toward zero to `result_decimals` places (`mul_scale` + `carry`) |
| `divide(dividend, divisor, quotient_decimals: int) -> CobolNumber` | `__cobol_divide`: exact quotient truncated toward zero to exactly `quotient_decimals` places (computed statically by `div_scale` + `carry`) |
| `to_number(value: int \| float \| str \| CobolNumber) -> CobolNumber` | Operand normalisation inside the arithmetic builtins during migration: `float` via `from_float`, numeric text via `from_literal` |
| `Scale(integer_places: int, decimal_places: int)` | Frozen dataclass: the places an operand or intermediate result carries |
| `add_scale(a: Scale, b: Scale) -> Scale` | `+`/`-` row of the IBM table |
| `mul_scale(a: Scale, b: Scale) -> Scale` | `*` row |
| `div_scale(dividend: Scale, divisor: Scale, dmax: int) -> Scale` | `/` row: integer `i2 + d1`, decimal `max(d2 − d1, dmax)` |
| `carry(scale: Scale, dmax: int, limit: int = 30) -> Scale` | The `ARITH(COMPAT)` 30-digit carry table |
| `truncate_to(n, decimals: int) -> CobolNumber` | Store truncation |
| `round_half_up(n, decimals: int) -> CobolNumber` | `__cobol_round` |
| `digits_for_encode(n, total_digits, decimal_digits, scale) -> tuple[bool, str]` | `(negative, digit_str)` for `__cobol_prepare_digits`, the sign-nibble builtin, and `pic_scale.encode_scaled_digits` |
| `to_plain_str(n) -> str` | `__cobol_numeric_str` (DISPLAY) and `_serialize_value`; never scientific notation |
| `as_whole_int(n) -> int \| None` | Integer-argument intrinsic helper; date intrinsics |
| `is_cobol_number(x) -> bool` | Replaces `isinstance(x, (int, float))` numeric checks in builtins |
| `sqrt`, `mean`, `variance`, `annuity`, `present_value`, `numval`, … | Decimal arithmetic currently inline in `byte_builtins.py` intrinsics |

Inputs may be `int` or `CobolNumber`; integers are exact already and remain `int` wherever they are produced today.

### Enforcement

An invariant test (modelled on `tests/unit/cobol/test_region_funnel_invariant.py`) walks `interpreter/`, `cobol_asg/`, `cobol_memory/` and `mcp_server/` and fails if any module other than `cobol_numeric` imports `decimal` or constructs a `Decimal`.

### Shared-code additions (additive only)

- `FoundationTypeName.DECIMAL = TypeName("Decimal")` — names the kind of value, not the Python implementation, so it survives a representation change.
- `Const.decimal_(result_reg, value: CobolNumber)`, typed `Decimal`.
- `_const` flat-format branch: `literal_type == "Decimal"` → `Const.decimal_(reg, from_literal(str(raw)))`.
- `_serialize_value`: `CobolNumber` → `to_plain_str`.

No change to `DefaultTypeConversionRules` for existing type pairs, to `DefaultBinopCoercion`, or to `BINOP_TABLE`. Pairs involving `Decimal` fall through to `IDENTITY_CONVERSION`, so operands are never coerced to float.

## Section 2 — Value flow on the COBOL path

### Where exact values originate

- **Decode:** the four fixed-point IR decoders keep accumulating digits as `int`, then call a new `__cobol_from_digits(accum, decimal_digits)` builtin backed by `from_digits`, replacing the float-divisor `Binop`. No decode division goes through `BINOP_TABLE`, so the float-divisor workaround and its `(Int, Int) → //` concern disappear. This also fixes red-dragon-0dvs: `build_decode_binary_ir` currently divides by an `int` `10**d`, which that rewrite turns into floor division, so every COMP/BINARY field with decimal places decodes without its fraction.
- **COMP/BINARY store (red-dragon-0dvs, store half):** `emit_encode_from_string`'s BINARY branch converts the value text with `int(float(text))` and never applies implied decimal places or PIC P scale (verified: `MOVE 123.45 TO` a `PIC S9(5)V99 COMP` field stores 123, not 12345). It calls a new `__cobol_binary_unscaled(value, decimal_digits, scale)` builtin backed by `scale_by`/`truncate_to`, returning the exact stored integer. The BINARY branch's deliberate absence of decimal-digit truncation (50000 into `PIC 9(4)` keeps 50000) is preserved.
- **PIC P:** `emit_context.py:861` calls a new `__cobol_scale_by(value, scale)` builtin backed by `scale_by`, replacing the float-factor `Binop`.
- **Literals:** `parse_literal` → `int` or `from_literal`; `const_to_reg` emits `Const.decimal_` for non-integers.
- **Lowering:** remaining `float()` calls in `lower_arithmetic.py` become `int` / `CobolNumber` via the boundary.

### Division

Lowering computes each expression node's `Scale` statically: a field's `Scale` comes from its PIC (`total_digits − decimal_digits`, `decimal_digits`), a literal's from its digits, and each operator node applies `add_scale` / `mul_scale` / `div_scale` followed by `carry`. `dmax` for a `COMPUTE` is computed once per statement: the largest receiver decimal places (plus one for a `ROUNDED` receiver, see the assumption in Decisions) and the largest decimal places of any non-divisor, non-exponent operand.

- **Division** lowers to `__cobol_divide(dividend, divisor, quotient_decimals)` with `quotient_decimals` emitted as a constant, backed by `cobol_numeric.divide` (exact, truncated toward zero). This single rule reproduces both today's integer truncation (`2023 / 4 * 4` → 2020, because `dmax = 0`) and receiver-aware fractions (`7 / 2 * 2` into `PIC 9V9` → 7.0).
- **`+ - *`** lower to `__cobol_add` / `__cobol_subtract` / `__cobol_multiply(a, b, result_decimals)`, with `result_decimals` taken from the statically carried `Scale`, so the IBM carry truncation happens inside the same call. No separate truncation instruction is emitted. The high-order integer-place truncation in the 30-digit carry table is not emulated; with the 18-digit PIC limit, receivers overflow (and `ON SIZE ERROR` fires) long before an intermediate needs it.
- **Division by zero** keeps today's `UNCOMPUTABLE` / `ON SIZE ERROR` behaviour.
- **Deleted:** `force_division_float`, and the `(Int, Int)` `/` → `//` dependency for COBOL (COBOL arithmetic no longer goes through `BINOP_TABLE`).
- **Floating-point expressions** (Section 2, below) keep ordinary `Binop`s on `float` operands, because IEEE arithmetic is what IBM specifies for them.
- **`ADD`/`SUBTRACT`/`MULTIPLY`/`DIVIDE` verbs** use the same scale algebra, with the target(s) as receivers.

### Where exact values leave

- **Encode:** `__cobol_prepare_digits`, the sign-nibble builtin and `encode_scaled_digits` all call `digits_for_encode` — one implementation for both encode paths (closes red-dragon-bqds).
- **ROUNDED:** `__cobol_round` calls `round_half_up`.
- **Intrinsics:** Decimal-based intrinsics use boundary functions; trigonometric/logarithmic intrinsics stay floating point, converting via `to_float` / `from_float`.
- **Floating-point expressions (IBM rule):** lowering classifies each expression before emitting it. If any operand or receiver is COMP-1/COMP-2, any literal is floating point, an exponent has decimal places or is an expression containing `**` or `/` with `dmax > 0`, or any intrinsic is a floating-point function (SIN, COS, TAN, ASIN, ACOS, ATAN, EXP, EXP10, LOG, LOG10), the **whole** expression is computed in float: fixed-point operands are converted with `to_float`, the scale algebra is skipped, and the float result is converted with `from_float` only when stored into a fixed-point receiver (then truncated, or `ROUNDED`, as today).
- **COMP-1/COMP-2 decode and encode:** decode yields `float`; encode uses `to_float` (`struct.pack`). A COMP-1/COMP-2 field in an otherwise fixed-point expression makes that expression floating point per the rule above, so a float never meets a `CobolNumber` in a `Binop`.
- **Text:** COBOL `emit_to_string` on numeric values calls `__cobol_numeric_str` (`to_plain_str`). Trailing zeros of the field scale are kept (`0.80`). The generic `str` builtin is unchanged for other languages. Making DISPLAY emit the field's character representation (real COBOL behaviour) is out of scope.
- **Text contract with `IS NUMERIC`:** since `8d3b4e54`, `_builtin_is_numeric` parses this text. `to_plain_str` therefore guarantees the grammar `-?[0-9]+(\.[0-9]+)?` — optional leading `-`, never `+`, never an exponent, never a bare leading or trailing `.` — and a contract test asserts every `to_plain_str` output over a corpus (negatives, zero, tiny and 18-digit magnitudes, P-scaled values) is accepted by `_builtin_is_numeric`. This fixes today's latent failure where `str(float)` yields `1e-05` and `IS NUMERIC` returns false.

### Builtins accepting `CobolNumber`

`byte_builtins.py:263` (prepare digits), `:325` (sign nibble), `:640` (float packing), `:1145` (date intrinsic), `:1172` (integer-argument helper) replace float-only checks with `is_cobol_number` / `as_whole_int` / `to_float`.

### Comparisons, typing, size errors, state

- `CobolNumber` compares exactly with `int` and `CobolNumber`; no floats remain on the COBOL path except at the COMP-1/2 and floating intrinsic boundaries, which convert first.
- `DefaultBinopCoercion.result_type` returns `UNKNOWN` for `Decimal` pairs (as for any unrecognised type); `_coerce_typed_register` leaves the value untouched.
- `ON SIZE ERROR` digit-capacity checks become exact.
- `Decimal` pickles natively, so `ExecutionState` stays picklable; `VMState.to_dict` and MCP JSON use `to_plain_str`.

## Section 3 — Implementation order and testing

Each step is a separate commit with the full suite green.

**Ordering constraint.** Python raises `TypeError` when a `Decimal` meets a `float` in an arithmetic operator. If decoders or literals produced `CobolNumber` values while arithmetic was still ordinary `Binop`s fed by float literals and `float()` calls, the suite would break between commits. The implementation plan therefore lands the arithmetic builtins (step 6's lowering work, which accept `int`, `float`, numeric text and `CobolNumber` operands via `to_number`) **before** decode (step 4) and literals (step 5). The numbered steps below describe content; the plan orders them 1, 2, 3, 6, 4, 5, 7, 8, 9, 10.

1. **`cobol_numeric` package** — `CobolNumber`, all boundary functions, import-linter contract, unit tests per function (38-digit truncation toward zero, half-up on exact halves, `to_plain_str` never scientific, `from_float` on COMP-2 values). No callers yet.
2. **Type and serialization plumbing** — `FoundationTypeName.DECIMAL`, `Const.decimal_`, flat `CONST` branch, `_serialize_value`.
3. **Encode paths (closes red-dragon-bqds)** — both encode paths call `digits_for_encode`; a parity test drives both paths over a shared corpus (fractions into integer fields, P-scaled fields, negatives, tiny magnitudes) and asserts identical bytes. Encoders accept `CobolNumber` before decode starts producing it.
4. **Decode** — fixed-point decoders call `__cobol_from_digits` (`from_digits`); PIC P scaling calls `__cobol_scale_by` (`scale_by`).
5. **Literals** — `parse_literal`, `const_to_reg`, remaining `float()` in `lower_arithmetic.py`.
6. **Division and intermediate scale** — first, verify the IBM rules and the `ROUNDED` + 1 assumption against the NIST-85 arithmetic programs (`NC121M`, `NC207A`, `NC220M`, `NC123A`, `NC117A`: their inline expected values for `COMPUTE`/`DIVIDE` with fractional and `ROUNDED` receivers) and record the findings in the task; stop and raise with the user if any contradicts the rules. Then compute `Scale`/`dmax` in lowering; emit `__cobol_add`, `__cobol_subtract`, `__cobol_multiply` and `__cobol_divide` for every COBOL arithmetic operator (expressions and the ADD/SUBTRACT/MULTIPLY/DIVIDE verbs); delete `force_division_float`. (`Scale`, the scale functions and the exact arithmetic functions themselves are pure and land in step 1.) Existing tests `test_mod_idiom_integer_division_truncates`, `test_compute_without_rounded_truncates` (10/6 → 1) and `test_compute_rounded_integer` (10/6 `ROUNDED` → 2) must stay green.
   Floating-point expression classification is part of this step.
7. **Remaining builtins** — rounding/truncation, `__cobol_numeric_str`, integer-argument helper, date intrinsics, Decimal intrinsics moved behind the boundary.
8. **COMP-1/COMP-2 and floating intrinsics** — `from_float` / `to_float`.
9. **Remove the `96651c84` guard step** — delete the `decimal_digits + 6` `ROUND_HALF_UP` quantize from `__cobol_prepare_digits`, leaving plain truncation via `digits_for_encode`. Only safe after steps 4–6, when no float noise can reach the encoder; removing it earlier regresses `test_arithmetic_decimal_precision.py`. Probes H and I turn green here.
10. **Invariant test enabled** — no `decimal` outside `cobol_numeric` (the guard's inline `from decimal import ROUND_DOWN, ROUND_HALF_UP` is gone after step 9).

Throughout every step, `tests/unit/cobol/test_arithmetic_decimal_precision.py` (from `96651c84`) must stay green.

### Existing tests that change (assertions tightened, never loosened or renamed)

- `tests/unit/test_ir_encoders.py:777,782` — "decodes to float" / `pytest.approx(123.45)` become exact `CobolNumber` equality.
- `tests/unit/test_byte_builtins.py:2540,2613,2656,2935,2957,3371,3417` — `math.isclose` becomes exact equality for fixed-point results; stays approximate only for floating-point intrinsics.

### New integration tests (`tests/integration/`, via `run()`)

- `COMPUTE X = 4.35 * 100` → `PIC 999` stores 435 (probe E; fails today despite the guard).
- `COMPUTE X = 0.129999999` → `PIC 9V99` stores 0.12, and `MOVE 0.12 TO X` / `ADD A TO X` with `A PIC 9V9(9) VALUE 0.009999999` stores 0.12 (probes H, I; fail today because of the guard — green only after step 9).
- `COMPUTE X = 0.1 + 0.7` → `PIC 9V99` stores 0.80 (probe A; passes today via the guard, kept as a regression test).
- `to_plain_str` / `IS NUMERIC` contract test (Section 2).
- 18-digit `PIC S9(9)V9(9)` keeps its last digit through `ADD`.
- `COMPUTE Q = -7 / 2` → `PIC S9` stores -3; `COMPUTE X = 1 / 3` → `PIC 9V9(9)` stores .333333333; `COMPUTE X ROUNDED = 2 / 3` → `PIC 9V99` stores .67.
- `COMPUTE X = 2023 / 4 * 4` → `PIC 9(4)` stores 2020 (IBM `dmax = 0`; red-dragon-apoq must not regress).
- `COMPUTE X = 7 / 2 * 2` → `PIC 9V9` stores 7.0 (IBM `dmax = 1`; stores 6.0 today).
- `COMPUTE X = 10 / 6` → `PIC 9` stores 1, and with `ROUNDED` stores 2.
- `PIC S9(5)V99 COMP VALUE 123.45`, `MOVE` to `PIC 9(5)V99`, stores 123.45 (red-dragon-0dvs; stores 123.00 today).
- A COMP-2 field in a `COMPUTE` with a fixed-point field computes in floating point, and the result stored into a fixed-point receiver is truncated as today.
- PIC P-scaled field round-trips exactly.
- COMP-1/COMP-2 operands mixed with fixed-point fields still compute.
- `ON SIZE ERROR` fires on an overflow only exact arithmetic detects.
- `DISPLAY` of a `PIC 9V99` holding 0.80 prints `0.80`; a tiny value never prints in scientific notation.

Other languages: every existing test passes unchanged; the invariant test and untouched conversion-rule cases guard isolation.

### Measurement

Run the NIST-85 suite (`-m nist`) and the arithmetic-heavy programs `NC121M`, `NC207A`, `NC220M`, `NC123A`, `NC117A` before and after; record both counts in the closing notes of red-dragon-4q25.1. No improvement is promised, since most NIST failures halt before arithmetic.

## Documentation updates

ADRs in `docs/architectural-design-decisions.md` are append-only: existing entries are not rewritten.

- **ADR-148: COBOL exact fixed-point arithmetic behind a `cobol_numeric` boundary (2026-09-15)** — Context: float precision loss (probes above). Decision: `CobolNumber` (currently `Decimal`) created and consumed only through `cobol_numeric` functions; COBOL-scoped; new `Decimal` foundation type; rejected scaled integers and `Fraction`. Consequences: other languages unchanged; invariant test and import-linter contract enforce the boundary; representation swappable by editing one module; the temporary `96651c84` guard+truncate step is removed; closes red-dragon-4q25.1, red-dragon-0dvs, red-dragon-bqds and red-dragon-5b93.
- **ADR-149: COBOL intermediate precision — IBM `ARITH(COMPAT)` scale rules, computed at lowering time (2026-09-15)** — Context: division semantics differ between compilers (IBM sizes quotients from `dmax`; GnuCOBOL carries 38 extra digits); RedDragon's existing mod-idiom behaviour (red-dragon-apoq) and its downstream programs follow IBM. Decision: IBM places-carried table and 30-digit carry table implemented as pure `Scale` functions in `cobol_numeric`; lowering computes each node's `Scale` and each statement's `dmax` from PICs, literals and receivers (`ROUNDED` receivers + 1); `__cobol_add`/`__cobol_subtract`/`__cobol_multiply`/`__cobol_divide` compute exactly with integer ratios and truncate to the static carried scale (Python's default 28-digit `Decimal` context would otherwise round 30-digit intermediates); IBM floating-point expression rule for COMP-1/COMP-2, floating literals, fractional exponents and floating intrinsics; `force_division_float` and COBOL's reliance on `(Int, Int) /` → `//` removed; 18-digit PIC limit retained. Consequences: integer-only expressions truncate exactly as before; receivers with decimal places now keep division fractions IBM keeps (`7 / 2 * 2` into `PIC 9V9` = 7.0); GnuCOBOL-targeted programs relying on 38-digit division are out of scope; `ARITH(EXTEND)` (31 digits) is a one-parameter extension of `carry`.
- **ADR-146 (ROUNDED) — dated amendment note appended beneath the entry:** "Amended 2026-09-15 by ADR-148/ADR-149: `__cobol_round` receives a `CobolNumber` and delegates to `cobol_numeric.round_half_up`; its `decimal` import moved into `cobol_numeric`."
- `docs/frontend-design/cobol.md:241` — remove the P0 float-arithmetic gap; describe exact arithmetic and the boundary module.
- `docs/type-system.md` — add the `Decimal` foundation type and its COBOL-only scope.

## Out of scope

- `ARITH(EXTEND)` / 31-digit PICs.
- `ARITH(EXTEND)` 31-digit carry table (only the `ARITH(COMPAT)` 30-digit table is implemented; `carry`'s `limit` parameter leaves room for it).
- GnuCOBOL-style 38-digit division.
- Exponentiation (`**`), which the expression model does not parse or lower yet (red-dragon-wxur); the IBM floating-point triggers for exponents become reachable once it exists.
- DISPLAY emitting a numeric field's character representation.
- Exact arithmetic for other languages' decimal types (Java `BigDecimal`, C# `decimal`, Python `Decimal`).
