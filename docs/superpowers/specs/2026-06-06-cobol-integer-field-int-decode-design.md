# COBOL Integer Fields Decode to `int` — Design

**Issue:** red-dragon-4q25.42 (child of epic red-dragon-4q25)
**Related:** red-dragon-4q25.1 (P0, broad float arithmetic — out of scope here), red-dragon-4q25.4 / .30 (`ROUNDED` — orthogonal)
**Date:** 2026-06-06

## Problem

COBOL operations on integer fields — `PIC 9(n)` / `S9(n)` with **zero decimal places** —
carry the value as a Python `float`, not an `int`. The decode pipeline does this
*deliberately*: each integer-capable decode builder ends its `decimal_digits == 0`
path with a `CallFunction("float", accum)` step (comment: "Convert to float for
consistency"). So `77 WX PIC 9(4) VALUE 5.` after `ADD 1 TO WX` holds `6.0`, and
`MOVE WX TO LK-OUT` stringifies it via the `str` builtin to `"6.0"`.

This has two consequences:

1. **Silent corruption of large integers.** A Python `float` represents integers
   exactly only up to 2^53 ≈ 9.007×10¹⁵ (≈ 15–16 digits). COBOL routinely uses
   `PIC 9(18)` / `S9(18) COMP-3` for account numbers, IDs, timestamps, and
   accumulators. Decoding an 18-digit field to `float` drops low-order digits and
   re-encodes a **different number** (e.g. `123456789012345678` →
   `123456789012345680`). This is blatantly wrong and common in real COBOL.

2. **Cosmetic float + a misleading warning.** `str(6.0)` → `"6.0"` (it round-trips
   only because `COBOL_PREPARE_DIGITS` tolerates the trailing `.0` when
   `decimal_digits == 0`). Worse, `_unwrap_builtin_result`
   (`interpreter/handlers/calls.py:65-75`) logs a spurious *"Builtin str returned
   bare heap address '6.0'"* warning, because `_heap_addr`
   (`interpreter/vm/vm.py:338-339`) returns `Address(val)` for **any** non-empty
   string. That false-positive warning previously sent a debugging session chasing
   a phantom bug.

## Scope

**In scope:** integer fields (`decimal_digits == 0`) decode to `int`; fix the
spurious `str`-result warning.

**Out of scope (→ red-dragon-4q25.1):** decimal/fixed-point precision (money),
large *decimal* fields (`PIC 9(16)V99`), truncation off-by-one from float
representation, decimal equality. These are all manifestations of binary float
being unable to represent decimal values exactly, and require a Decimal- or
scaled-integer numeric core (a separate architectural design).

**Orthogonal (→ red-dragon-4q25.4 / .30):** `ROUNDED` is a rounding-*mode*
semantic (round-half-up), not a precision artifact; unaffected by this change.

## Design

### Change 1 — The four integer-capable decode builders

In `interpreter/cobol/ir_encoders.py`, each builder's `decimal_digits == 0` path
currently appends a `CallFunction("float", accum)` step. Remove that conversion so
the path returns the **int** accumulator directly. The `decimal_digits > 0`
branches (which produce a float via division) are **untouched**.

- `build_decode_zoned_ir` (~line 347-355)
- `build_decode_zoned_separate_ir` (~line 629)
- `build_decode_comp3_ir` (~line 972)
- `build_decode_binary_ir` (~line 1155 — already integer; drop the trailing
  `float()` for the non-scaled case)

`build_encode_float_ir` / `build_decode_float_ir` (COMP-1 / COMP-2, IEEE float)
are **untouched** — those values are genuinely float.

Docstrings currently reading `Output: float` are corrected to
`Output: int when decimal_digits == 0, else float`.

### Change 2 — Tighten the bare-heap-address warning

In `_unwrap_builtin_result` (`interpreter/handlers/calls.py`), the guard
`isinstance(result.value, (Pointer, str)) and _heap_addr(result.value)` fires for
any non-empty string because `_heap_addr` accepts everything. Add a small local
predicate that recognizes only genuinely address-shaped strings — those starting
with the known heap/region prefixes (`OBJ_ADDR_PREFIX`, `ARR_ADDR_PREFIX`,
`mem_`, `REGION_ADDR_PREFIX` from `interpreter.constants`) — and gate the warning
on it. A plain `str()` result like `"7"` no longer warns. `_heap_addr` itself is
**not** changed (it has other callers that rely on its permissive behaviour).

### Why this is safe (data flow)

- **Encode is value-agnostic.** The write path is `str(value)` →
  `COBOL_PREPARE_DIGITS`; `str(7)` → `"7"` parses identically to `str(7.0)` →
  `"7.0"`. No encode changes needed.
- **Mixed arithmetic unchanged.** `int`(integer field) + `float`(decimal field)
  promotes to `float` in Python, exactly as today.
- **Conditions unchanged.** `7 == 7.0` is `True` in Python; relational lowering is
  unaffected.
- **Division unchanged.** COBOL division lowers to true-division (`/`), which still
  yields a float and truncates at encode as before.

### Error handling

No new failure modes. The `int` accumulator is the same value built from the same
nibble extraction; only the final wrapping changes (drop one `float()` call).

## Testing

1. **Unit, per decode builder:** an integer field (`decimal_digits == 0`) decodes
   to `int`; a decimal field (`decimal_digits > 0`) still decodes to `float`
   (guards against over-reach).
2. **Integration — the correctness win:** an 18-digit `PIC 9(18)` value
   `MOVE`d/round-tripped through the VM returns the **exact** value (today it
   corrupts via float). This is the concrete proof of the fix.
3. **Integration — cosmetics:** an integer-field `ADD` / `MOVE` round-trips with
   the correct value and no `float` in the path.
4. **Warning-guard unit test:** `_unwrap_builtin_result` with `"7"` emits **no**
   warning; with `"obj_Point_1"` it **still** warns.
5. **Regression:** the full COBOL suite. Because encode is string-based, existing
   decimal-field tests should be unaffected.

## Acceptance Criteria

- Integer COBOL fields (`decimal_digits == 0`) decode and compute as `int`; the
  encode path sees `str(value) == "7"`, not `"7.0"`.
- An 18-digit integer field survives a decode/encode round-trip exactly.
- `_unwrap_builtin_result` no longer warns for plain numeric strings returned by
  the `str` builtin; it still warns for address-shaped strings.
- Full COBOL test suite passes; decimal-field behaviour is unchanged.
