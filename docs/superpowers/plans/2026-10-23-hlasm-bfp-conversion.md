# HLASM unit .52: BFP conversions

Bead red-dragon-6uyp.52. Rulings R31, R34, R40, R41 (amended: invalid FPC values give
S0C6), R43, R44, R45. Forty-eight base mnemonics; no extended mnemonics.

## Mnemonic groups

| Group | Mnemonics | Path | CC |
|---|---|---|---|
| To fixed | CFEBR(A) CFDBR(A) CFXBR(A) CGEBR(A) CGDBR(A) CGXBR(A) | builtin `to_fixed_32/64` | Figure 19-19 |
| To logical | CLFEBR CLFDBR CLFXBR CLGEBR CLGDBR CLGXBR | builtin `to_logical_32/64` | Figure 19-20 |
| From fixed, rounding | CEFBR(A) CEGBR(A) CDGBR(A) CELFBR CELGBR CDLGBR | builtin `from_fixed` (short, long) | unchanged |
| From fixed, exact | CDFBR(A) CXFBR(A) CXGBR(A) CDLFBR CXLFBR CXLGBR | IR | unchanged |
| Lengthen | LDEBR LDEB LXDBR LXDB LXEBR LXEB | IR | unchanged |
| Round | LEDBR(A) LDXBR(A) LEXBR(A) | builtin `rounded_to_short/long` (by source) | unchanged |

## Why each path (R44, R45)

- **Builtins round.** BFP to fixed rounds to an integer under M3; fixed to a narrower BFP
  and LOAD ROUNDED round to the target precision with overflow and underflow. Exact
  rounding in IR would dwarf the program, so the "too cumbersome" clause applies.
- **IR when exact.** Lengthening and a fixed operand that fits the target significand
  need no rounding: sign, a rebased exponent and a left-justified fraction. One IR helper
  encodes magnitude x 2^exponent exactly, using `bit_counts.leading_zeros` to normalise a
  subnormal source or an integer. NaNs and infinities keep their fraction shifted left; an
  SNaN is quieted and signals invalid through the ladder, as LOAD AND TEST does.

## Design

- **Reuse .51.** Same builtin adapter, `BfpOperation`, slots and `emit_ieee_ladder`; no
  second ladder. Each builtin takes a rounding code and one operand (≤ 4 parameters).
- **To fixed result list.** Same eleven slots: the integer's two's-complement image in the
  value slot, trap and flag bits from `bfp_to_integer`'s conditions (INVALID, INEXACT,
  INCREMENTED for the DXC), and the CC: 3 when invalid, else 0, 1, 2 by the source.
  The lowering stores bits 32-63 or the whole GR, then the CC. Invalid enabled suppresses
  (R34); masked delivers MN/MP (signed) or 0/MU (logical) with CC 3, SFi, and SFx or the
  08 inexact trap, as the figures give.
- **M3 and M4.** M3 of 2 or 8-15 abends S0C6 at compile time; 0 reads the FPC mode. M4
  bit 1 (XxC) on the A and logical forms clears inexact from trap and flags (.51's
  `without`). Non-A forms have no M4.
- **LOAD ROUNDED delivery.** An enabled overflow or underflow delivers the scaled result in
  the source format. The ladder delivers once from a runtime slot, so the lowering always
  writes the source-format image: the scaled image, or the target image placed over the
  register's old bits (short over bits 0-31, long over the even register of the pair).
- **Pairs.** Extended R1 (from fixed, lengthen) or R2 (to fixed), and both for LDXBR and
  LEXBR, must be valid pairs; else S0C6 (R41).

## Tests

- `tests/unit/hlasm/test_bfp_builtins.py`: conversion builtins' result lists (integer
  image and CC, NaN and out of range, inexact; from fixed inexact; LOAD ROUNDED scaled in
  the source format).
- `tests/unit/hlasm/test_bfp_conversion_lowering.py`: traces (builtin forms call then
  ladder; exact forms and lengthening call nothing), static S0C6 before any access, no
  SYMBOLIC in all 48.
- `tests/integration/hlasm/bfp_conversion_programs.py` + `test_bfp_conversion.py`: every
  mnemonic with concrete GR/FPR images, CC and FPC; MN/MP/0/MU boundaries; traps (invalid
  suppresses, masked invalid with the inexact trap, inexact 08/0C, lengthening SNaN, LOAD
  ROUNDED scaled overflow and underflow).
- `tests/z390/test_bfp_conversion_differential.py`: the same against z390; disagreements
  pinned and noted on red-dragon-6uyp.74, PoO-derived values where z390 lacks a mnemonic.

## Commits

1. Plan.
2. Builtins for to fixed, from fixed and LOAD ROUNDED ("too cumbersome" in the message).
3. To fixed and to logical.
4. From fixed (rounding and exact).
5. Lengthen and round. hlasm.md updated with each behaviour; bead notes and snapshot last.
