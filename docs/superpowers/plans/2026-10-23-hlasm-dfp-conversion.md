# HLASM unit .56: DFP conversions and PFPO

Bead red-dragon-6uyp.56. Rulings R34, R41, R43-R45, R48, R49, R51, R52. Forty base
mnemonics plus PFPO, no extended mnemonics. PoO SA22-7832-14: chapter 20 (20-24 to 20-36,
20-45, 20-46, figures 20-17 to 20-19, 20-24), chapter 9 (PFPO 9-35 to 9-45, figures 9-23 to
9-29).

## Mnemonic groups

| Group | Mnemonics | Path |
|---|---|---|
| From fixed | CDFTR CDGTR CDGTRA CDLFTR CDLGTR CXFTR CXGTR CXGTRA CXLFTR CXLGTR | builtin |
| To fixed | CFDTR CFXTR CGDTR CGDTRA CGXTR CGXTRA CLFDTR CLFXTR CLGDTR CLGXTR | builtin |
| Lengthen | LDETR LXDTR | IR |
| Round | LEDTR LDXTR | builtin |
| Register decimal | CDSTR CXSTR CDUTR CXUTR CSDTR CSXTR CUDTR CUXTR | IR |
| Storage decimal | CDPT CXPT CPDT CPXT CDZT CXZT CZDT CZXT | IR |
| PFPO | PFPO | IR decode, dispatch and encode; one builtin converts |

## Why each path (R52)

- **Fixed to and from DFP, LOAD ROUNDED: builtins** over `dfp_from_integer`,
  `dfp_to_integer`, `dfp_load_rounded`, which exist in `zarch_float` with only test
  callers today. Rounding to a preferred quantum by eight methods is the "too cumbersome"
  clause. Exact cases (32-bit sources, extended targets) take the same builtin.
- **LOAD LENGTHENED: IR.** Exact: the biased exponent moves by the bias difference, the
  digits stay. `dfp_load_lengthened` loses its last caller and is deleted (R48).
- **Packed, zoned, signed and unsigned packed: IR.** Digit movement. Digits pass through
  the DPD codec's `[negative, e, significand]` fields; the significand is turned into
  decimal lanes (4 bits packed, 8 bits zoned) by an IR function and back by a SWAR combine,
  both defined once per program (`IrFunction.call`). Sign codes reuse `packed_decimal`'s
  sign tables.
- **PFPO.** GR0 is decoded in IR. The test bit sets CC 0 or 3 and a zero return code.
  Otherwise an invalid function is `S0C6`. Each family's IR decodes the source image (BFP
  fields, HFP fields, DPD decode) under a dispatch on the source format code. One builtin
  converts the exact source value into the target format with rounding. A dispatch on the
  target format encodes and stores the delivered value.

## Rules pinned from the PoO

- From fixed (20-24, 20-25): M3 0 or 2 → FPC DFP mode; M3 0, 8-15 → XqC 1. M4 bit 1 (X'4')
  is XxC. CDGTR/CXGTR are M3 0. Exact results take quantum 1; inexact the smallest quantum.
  Only CDGTR(A) and CDLGTR can be inexact. CC unchanged.
- To fixed (figures 20-18, 20-19): rounding as above. Out of range or NaN: invalid with no
  inexact; masked → MN/MP (signed) or 0/MU (logical), flag, CC 3; unmasked → `S0C7` DXC 80,
  suppressed. Otherwise CC by the source's sign, 0 for a zero. A value rounding to MN, MP or
  0 is in range. M4 bit 1 is XxC. Extended sources check the R2 pair.
- LOAD LENGTHENED (20-45, figure 20-24): finite exact; M4 bit 0 (X'8') is XiC. XiC 0:
  SNaN → invalid, QNaN result; an infinity loses its digits. XiC 1: SNaN and infinity keep
  their digits, no exception.
- LOAD ROUNDED (20-46): M3 as LOAD FP INTEGER (0, 8-15 XqC 1); M4 bit 0 XiC, bit 1 XxC.
  Short or long result in the left of R1, the rest unchanged; a trapped overflow or
  underflow delivers the scaled value in the source format. XiC 1 keeps an SNaN and an
  infinity's trailing digits.
- CDSTR/CXSTR (20-28): 15 or 31 digits and a sign nibble in GR R2 or the even-odd pair; a
  bad digit or sign → data exception DXC 0, `S0C7`, suppressed. CDUTR/CXUTR: 16 or 32
  digits, plus. Quantum 1. R2 odd → `S0C6`.
- CSDTR/CSXTR (20-35): the rightmost 15 or 31 trailing-significand digits and a sign: D
  minus, C plus, F plus when M4 bit 3. CUDTR/CUXTR: 16 or 32 digits. Specials convert
  their trailing digits. No exception, CC unchanged. R1 odd → `S0C6` for the X forms.
- CDPT/CXPT (20-26, 20-27, figure 20-17): L2 bytes; M3 bit 0 S, bit 3 I. S 0: all nibbles
  digits, plus. S 1: rightmost nibble a sign, ignored when I. Unused digits (beyond 16 or
  34) must be zero. Any bad digit or sign → DXC 0, `S0C7`. L2 > 8 (CDPT), > 17 (CXPT) →
  `S0C6`.
- CDZT/CXZT (20-29): one digit per byte, zones ignored; S 1: the rightmost zone is the sign.
  L2 ≥ 16 / ≥ 34 → `S0C6`.
- CPDT/CPXT (20-33, 20-34): the rightmost L2 bytes of digits (and a sign when S), P selects F
  for plus, F forces a plus sign on a zero result. A special converts its trailing digits
  with CC 3. Lost nonzero digits: CC 3 and, with PSW mask bit X'4', `S0CA` after the store.
  CC 0 zero, 1 minus, 2 plus.
- CZDT/CZXT (20-36, 20-37): one digit per byte; zones F (Z 0) or 3 (Z 1); S puts the sign
  in the rightmost zone (C/F by P, D minus); F as above. CC and overflow as CPDT.
- PFPO (9-35 to 9-45): GR0 bits 33-39 operation 01, bits 40-47 / 48-55 target and source
  format (figure 9-25), bit 56 IS, 57 AE, 58-59 target controls, 60-63 method (figure
  9-27: 0 DFP mode, 1 BFP mode, 8-15). Valid functions are the cross-radix pairs of figure
  9-28; a BFP target needs bits 58-59 zero. Operands FPR 4(6) → FPR 0(2). Return code in GR1
  bits 32-63: 0, or the scaling exponent on a trapped overflow or underflow. CC 0, 1
  nontrap exception, 2 trap with alternate action. NaN to HFP: +Hmax; infinity to HFP:
  ±Hmax, invalid. HFP overflow (bit 58) and underflow (bit 59) controls. DFP target: DQPC
  (bit 58) enables the quantum exception, DPQC (bit 59) picks the exact result's quantum
  (figure 9-29).
- Pairs (R41): every extended FPR operand is checked before any access → `S0C6`.

## Shared pieces

- `dfp_ir` (decode, encode, store, quantum step), `bfp_forms.ieee_call`, the BFP ladder,
  `bfp_forms.inexact_control`, `floating_point_support.pairs`, `bfp_forms.checked`.
- BFP's integer result layout and its CC move to a neutral module the DFP to-fixed
  builtins share (refactor commit, no behaviour change).
- The short DFP encoder joins the codec (LEDTR's result).

## Tests

- Unit: lowering traces (decode, builtin, ladder, encode, store) per group; pair and even-GR
  checks abend before any access; all 41 mnemonics without SYMBOLIC; decimal-lane IR
  functions against every digit position; builtin field mapping.
- Integration: one programs module (`dfp_conversion_programs.py`) shared with z390: every
  mnemonic's images, GRs, storage, CC and FPC; traps: to-fixed invalid, inexact, quantum,
  LEDTR overflow scaled delivery, LDETR invalid, data exceptions, decimal overflow; PFPO
  test bit, each radix pair, alternate action and return code.
- z390: `test_dfp_conversion_differential.py`, a case per mnemonic; disagreements pinned
  to the PoO and noted on red-dragon-6uyp.74.

## Commits

1. This plan.
2. Refactor: the integer conversion result shared by BFP and DFP builtins.
3. Fixed to and from DFP (20); builtins; hlasm.md.
4. LOAD LENGTHENED (IR) and LOAD ROUNDED (builtin), short encoder; R48 deletion; docs.
5. Decimal lanes IR functions; register forms (8); hlasm.md.
6. Storage forms (8); hlasm.md.
7. PFPO: `zarch_float` radix conversion, builtin, lowering; zarch-float.md, hlasm.md.
8. z390 differential tests; .74 notes; issues snapshot.
