# HLASM Opcode Unit — Compare, Signed and Logical (red-dragon-6uyp.28)

**Goal:** lower the 43 base mnemonics of red-dragon-6uyp.28. None has extended mnemonics.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14) pages COMPARE, COMPARE IMMEDIATE, COMPARE RELATIVE
LONG, COMPARE HALFWORD, COMPARE HALFWORD IMMEDIATE, COMPARE HALFWORD RELATIVE LONG, COMPARE
LOGICAL, COMPARE LOGICAL IMMEDIATE, COMPARE LOGICAL RELATIVE LONG, COMPARE LOGICAL
CHARACTERS UNDER MASK.

## Semantics (from the PoO pages)

- CC 0 equal, 1 first operand low, 2 first operand high. Nothing is stored; no overflow.
- Signed, 32-bit: C, CY, CR, CFI (I2 32), CRL; CH, CHY, CHI (I2 16), CHRL, CHSI (first
  operand a storage word, I2 16) — halfword second operands are sign-extended.
- Signed, 64-bit: CG, CGR, CGRL; CGF, CGFR, CGFI, CGFRL (second operand 32-bit signed);
  CGH, CGHI, CGHRL, CGHSI (second operand 16-bit signed; CGHSI first operand a storage
  doubleword).
- Signed, 16-bit: CHHSI (storage halfword against I2).
- Logical, 32-bit: CL, CLY, CLR, CLFI, CLRL; CLHRL, CLFHSI (second operand 16 bits, zero
  extended).
- Logical, 64-bit: CLG, CLGR, CLGRL; CLGF, CLGFR, CLGFI, CLGFRL (second operand 32 bits,
  zero extended); CLGHRL, CLGHSI (16 bits, zero extended).
- Logical, 16-bit CLHHSI; 8-bit CLI, CLIY (storage byte against I2).
- CLM, CLMY: the low-word bytes selected by M3, as one contiguous field, against that many
  storage bytes; byte-by-byte left to right equals an unsigned compare of the two fields.
  Mask 0 → CC 0 with no storage read.
- Relative long: CRL, CGFRL, CLRL, CLGFRL need a word boundary, CGRL and CLGRL a doubleword
  boundary (specification exception, S0C6); halfword forms are aligned by construction.
  `data_movement.from_relative` already checks exactly this.

## Shared pieces

- New in `fixed_width_ir`: `build_compare_signed_cc_ir` and `build_compare_logical_cc_ir`
  (operands to signed / wrapped at the width, CC from the sign of the difference via the
  existing `_sign_cc` at width + 1). They return the CC alone.
- New `interpreter/hlasm/opcodes/compare.py`: table rows per mnemonic over `data_movement`
  sources (registers, storage, `signed_immediate`, `immediate`, `from_relative`, `signed`),
  a first-operand storage source for the SI/SIL forms, and a CLM lowering.
- `load_store`: the STCM byte gather becomes a public `register_bytes_under_mask` reused
  by CLM, with `selected_positions` public.

## Tests

- Unit `tests/unit/hlasm/test_fixed_width_ir.py`: both builders on equal/low/high vectors,
  sign boundaries (0x80000000 vs 1 signed low, logical high).
- Unit `tests/unit/hlasm/test_compare_lowering.py`: CGF, CR, CHHSI, CLI, CLGHSI, CRL, CLM
  (mask 0b1010 and 0) read their widths, write no register or storage, store only the CC,
  no SYMBOLIC; CRL carries the alignment branch.
- Integration `tests/integration/hlasm/test_compare.py`, programs in `compare_programs.py`:
  one case per mnemonic (body, declared registers unchanged, CC), every CC reached in each
  of signed and logical; plus misaligned CRL/CGRL/CLGFRL abend S0C6.
- z390 `tests/z390/test_compare_differential.py`: every case against z390; disagreements
  pinned and noted on red-dragon-6uyp.74.

## Commits

1. Plan.
2. Builders, lowering, tests, `docs/frontend-design/hlasm.md`; bead note; issues snapshot.
