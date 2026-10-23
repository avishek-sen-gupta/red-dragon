# HLASM unit .54: HFP conversions

Bead red-dragon-6uyp.54. Rulings R34, R41, R43, R44, R46, R47. Twenty-seven base mnemonics, no
extended mnemonics. PoO SA22-7832-14: chapter 18 (18-11, 18-15, 18-17) and chapter 9 (9-27 to 9-29).

## Mnemonic groups

| Group | Mnemonics | Path | CC |
|---|---|---|---|
| HFP to fixed | CFER CFDR CFXR CGER CGDR CGXR | builtin | 0/1/2 by source, 3 out of range |
| HFP to BFP | TBEDR TBDR | builtin | 0/1/2 by source, 3 overflow |
| Fixed to HFP | CEFR CDFR CXFR CEGR CDGR CXGR | IR | unchanged |
| BFP to HFP | THDER THDR | IR | 0/1/2 by source, 3 special |
| Load lengthened | LDER LDE LXDR LXD LXER LXE | IR | unchanged |
| Load rounded | LEDR LRER LDXR LRDR LEXR | IR | unchanged |

## Why each path (R44, R47)

- **Builtins round.** CONVERT TO FIXED rounds by M3 to an integer (18-11); CONVERT HFP TO
  BFP rounds by M3 into a BFP format, with denormalization and overflow to infinity or
  Nmax by method (figure 9-20). Both are the exact-then-round arithmetic `zarch_float`
  already does; IR would repeat it. "Too cumbersome" clause.
- **IR for the rest.** None of them rounds by a method:
  - CONVERT FROM FIXED normalizes and truncates (18-11).
  - CONVERT BFP TO HFP is exact (figure 9-19).
  - LOAD LENGTHENED appends zeros (18-15).
  - LOAD ROUNDED adds one at the first dropped bit and shifts right on a carry (18-17).

  Each is a leading-zero count, shifts and selects.

## Rules pinned from the PoO

- CFxR/CGxR (18-11, 18-12): M3 0 or 5 truncates, 1 nearest away, 4 nearest even, 6 up, 7
  down. Any other M3 → `S0C6`. Out of range → the maximum of the source's sign, CC 3. CC
  comes from the source, so 0.3 rounded to 0 gives CC 2. A 32-bit result replaces bits
  32-63. No HFP underflow.
- CxFR/CxGR (18-11): normalized and truncated. Zero gives a positive true zero. CC
  unchanged.
- TBEDR/TBDR (9-29, figure 9-20): M3 0 truncates (not the FPC mode); 3 is valid
  (prepare for shorter); 2 or 8-15 → `S0C6`. No IEEE exceptions. Tiny values are
  denormalized and keep CC 1 or 2 even when the result is zero. Overflow gives infinity
  (nearest), Nmax (toward zero, prepare for shorter) or by sign (directed), CC 3. Sign of
  zero kept.
- THDER/THDR (9-27, figure 9-18): exact and normalized. A zero keeps its sign, CC 0. A
  characteristic below 0 gives a zero of the source's sign, CC 1 or 2. Above 127 gives
  Hmax (all ones) of the source's sign, CC 3. Infinity gives ±Hmax, CC 3. NaN gives +Hmax,
  CC 3.
- LOAD LENGTHENED (18-15): the fraction is extended with zeros. Long keeps the
  characteristic even for a zero fraction. Extended with a zero fraction is a true zero
  that keeps the sign (so LXDR of -0 is X'80..', X'80..'). Otherwise the low
  characteristic is the high one minus 14, modulo 128.
- LOAD ROUNDED (18-17): no normalization. Overflow stores the characteristic modulo 128,
  then `S0CC`. Short results replace bits 0-31; LDXR writes one FPR.
- Pairs: CFXR CGXR LDXR LRDR LEXR check R2; CXFR CXGR LXDR LXD LXER LXE check R1. An
  invalid pair → `S0C6` before any access.

## Shared pieces

- `fpr_images.py`: `signed_magnitude` (sign and magnitude of a signed integer), moved out
  of the BFP from-fixed lowering.
- `bfp_ir.py`: `finite_value` (BFP image to magnitude × 2^exponent), moved from
  `bfp_conversion._significand` for THDxR.
- `hfp_ir.py`: `normalized_fields` (sign, magnitude, binary exponent → characteristic and
  truncated fraction), used by CxFR/CxGR and THDxR.
- Reused as they are: `hfp_ir.image_of`, `true_zero_low`, `wrapped_low`, `fields_of`;
  `bfp_forms.checked`; `bfp_ir.image_at`; `floating_point_support.pairs`; `pick`.

## Leaf additions (own commit)

`zarch_float.hfp_convert.hfp_to_bfp(a, target, mode)`: zero keeps its sign, otherwise
`BfpRounding.round` (precision first, tininess before rounding, figure 19-9 overflow). Also
`HFP_TO_BFP_MODIFIER_MODES` (0 → toward zero, plus the BFP modifiers).

## Adapter

`hfp_builtins()` adds `__hlasm_hfp_to_fixed_32/64_<format>`, which takes `(m3, fields)` and
returns `[image, cc]`, and `__hlasm_hfp_to_bfp_short/long_long`, which takes `(m3, fields)`
and returns `[sign, biased, fraction, cc]`. Each takes two parameters.

## Tests

- `tests/unit/zarch_float/test_hfp.py`: one behaviour, `hfp_to_bfp` over each figure 9-20
  row.
- `tests/unit/hlasm/test_hfp_builtins.py`: one behaviour for the conversion builtins'
  fields and CC.
- `tests/unit/hlasm/test_hfp_conversion_lowering.py`:
  - builtin forms read, call, store and set the CC;
  - IR forms call nothing;
  - LOAD ROUNDED abends `S0CC` after the store;
  - invalid M3 and pairs abend `S0C6` first;
  - no SYMBOLIC in all 27.
- `tests/integration/hlasm/test_hfp_conversion.py`: every mnemonic on the VM.
  - Main vectors: CFER M3 0 of -2.5 → -2; CGDR of 2^63 → max, CC 3; CEFR 2^31-1 →
    X'487FFFFF'; THDR of 2^-300 → -0 sign kept, CC 1; THDR NaN → X'7FFF..', CC 3; LXDR of
    -0 → X'80..', X'80..'; LEDR X'7FFFFFFF80000000' → X'00100000' then `S0CC`; TBEDR of a
    huge HFP with M3 4 → +inf, CC 3.
- `tests/z390/test_hfp_conversion_differential.py`: every case against z390.
  Disagreements are pinned and noted on red-dragon-6uyp.74.

## Commits

1. This plan.
2. `zarch_float`: `hfp_to_bfp` and the modifier table, with tests and `zarch-float.md`.
3. HFP to fixed and HFP to BFP: adapter builtins and lowerings, tests, `hlasm.md`.
4. Fixed to HFP and BFP to HFP in IR (with the two moved helpers), tests, `hlasm.md`.
5. LOAD LENGTHENED and LOAD ROUNDED in IR, tests, `hlasm.md`; bead note and snapshot.
