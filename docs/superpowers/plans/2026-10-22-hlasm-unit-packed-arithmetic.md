# HLASM Opcode Unit — Packed-decimal arithmetic (red-dragon-6uyp.46)

**Goal:** lower AP, SP, ZAP, MP, DP and SRP. No extended mnemonics.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: the PoO pages
8-1 to 8-5 (formats, codes, overlap, general-operand data exception), 8-6, 8-7, 8-12 to
8-14, 6-26 and 6-27 (decimal-divide suppressed, decimal-overflow completed). Rulings:
R29 (compares on ints), R31 (byte 1 is a data field), R34 (checks before any store),
R39 (decimal).

## Semantics

- Read a packed field (address, runtime length) in one IR loop into a magnitude (an
  int), a negative bit (sign B or D) and an invalid bit (a digit A-F, a sign 0-9). The
  last byte holds a digit and the sign. Everything stays an int: the bits come from
  constant 16-bit tables shifted by the nibble.
- Store a magnitude and negative bit right to left in one IR loop; the sign is C or D.
  Overflow: magnitude ≥ 10^(2L−1). The stored digits are the magnitude modulo that.
- AP, SP, ZAP, SRP: the signed true result T; negative iff T < 0 (SRP: the original sign
  and a nonzero shifted magnitude), so a zero without overflow is positive and an
  overflowed zero keeps the true sign. CC 0/1/2, or 3 on overflow; store, set the CC,
  then program-mask bit `0100` on abends `S0CA` (completed).
- MP: L2 code > 7 or L2 ≥ L1 → `S0C6`. Multiplicand ≥ 10^(2(L1−L2)−1) (too few leading
  zero bytes) → `S0C7`. Product sign by algebra, negative zero kept. CC unchanged.
- DP: the same `S0C6`. Divisor × 10^(2(L1−L2)−1) ≤ dividend (magnitudes, the PoO trial
  comparison; covers a zero divisor) → `S0CB`, suppressed. Quotient (L1−L2 bytes, sign
  by algebra) and remainder (L2 bytes, the dividend's sign). CC unchanged.
- SRP: shift = EA bits 58-63 signed. Left: magnitude × 10^s. Right n: (magnitude +
  I3 × 10^(n−1)) // 10^n, written branch-free. I3 > 9 → `S0C7` even with no rounding.
- Order: `S0C6`, then `S0C7` (every operand checked; ZAP only the second), then `S0CB`;
  all before the first store.
- Overlap: AP, SP, MP, DP overlapping other than at coincident rightmost bytes → `S0C7`.
  ZAP never: fetching the whole second operand first is one of the two PoO choices, and
  it equals right-to-left processing for the proper overlaps.
- EX (R31): AP, SP, ZAP, MP, DP on `LENGTH_NIBBLES`; SRP on the SS-c layout (L1 and I3
  are both byte 1, bits 8-15), named `LENGTH_AND_IMMEDIATE`. One lowering each.

## Modules

- `interpreter/hlasm/packed_decimal.py`: read, store, sign and overflow helpers.
- `interpreter/hlasm/decimal_exceptions.py`: `S0C7`, `S0CA` under the mask, `S0CB`.
- `interpreter/hlasm/opcodes/packed_arithmetic.py`: the six lowerings, registered in
  `OPCODE_LOWERINGS` and `DATA_FIELD_LOWERINGS`.
- No reuse of `interpreter.cobol` (forbidden by `hlasm-not-cobol`); `cobol_numeric`
  works on Python values, not IR.

## Tests

- Unit `test_packed_arithmetic_lowering.py`: AP reads both operands before its one
  store loop and checks S0C7 first; MP and DP check S0C6 before any storage access; DP's
  S0CB precedes the stores; SRP reads no second operand; no SYMBOLIC.
- Integration `test_packed_arithmetic.py` with `packed_arithmetic_programs.py`, results
  loaded into registers: AP/SP/ZAP sign, zero sign, alternate signs in, CC 0-2;
  overflow CC 3 and S0CA with the truncated result stored; S0C7 invalid digit and
  sign (operand unchanged), improper overlap; coincident overlap (AP X,X); ZAP overlap;
  MP sign, negative zero, S0C6, too few zeros; DP quotient and remainder signs, S0CB on
  zero and on a large quotient, S0C6; SRP left, right with and without rounding,
  negative rounding, overflow, invalid I3; EX of AP and SRP with runtime fields.
- z390 `test_packed_arithmetic_differential.py`: every case; pin z390's differences
  (signed-long rounding in SRP, lost negative zero, no overlap check) on red-dragon-6uyp.74.

## Commits

1. This plan.
2. Feature: modules, registration, tests, docs (hlasm.md, README count if it changes).
3. Issue snapshot with the bead note.
