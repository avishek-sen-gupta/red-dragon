# HLASM Opcode Unit — Test Under Mask (red-dragon-6uyp.38)

**Goal:** lower TM, TMY, TMH, TML, TMHH, TMHL, TMLH, TMLL.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14), TEST UNDER MASK and TEST UNDER MASK (TMHH, TMHL,
TMLH, TMLL).

## Semantics

- The selected bits are the bits of the first operand where the mask I2 has a one. Nothing
  is stored; only the CC is set.
- TM, TMY: one storage byte against the 8-bit I2. CC 0 all selected bits zero or mask zero,
  1 mixed, 3 all ones.
- TMHH bits 0-15, TMHL 16-31, TMLH 32-47, TMLL 48-63 of R1 against the 16-bit I2. CC 0 and 3
  as above; mixed gives CC 1 when the leftmost selected bit is zero, 2 when it is one.
- The bridge delivers TMH and TML as their own base mnemonics; they are TMLH and TMLL.

## Shared pieces

- `fixed_width_ir`: `build_test_under_mask_cc_ir` (mixed CC 1) and
  `build_test_under_mask_ranked_cc_ir` (mixed CC 1 or 2), arithmetic only. With S the
  selected bits and M the mask: S nonzero, M-S nonzero means mixed, and the leftmost
  selected bit is one exactly when 2S-M is positive.
- `data_movement`: `field_of` (register halfword) and `immediate`; `compare.from_first_storage`
  for the storage byte.
- New `opcodes/test_under_mask.py` with the table; registered in `opcodes/__init__.py`.

## Tests

- Unit `test_fixed_width_ir.py`: both builders over zero, mask zero, all ones, mixed with the
  leftmost bit one and zero.
- Unit `test_test_under_mask_lowering.py`: TM/TMY read one storage byte, the RI forms read
  eight bytes of the register at their halfword offsets, nothing is written, only the CC is
  set, no SYMBOLIC.
- Integration `test_test_under_mask.py`, programs in `test_under_mask_programs.py`: every
  mnemonic across CC 0, 1, 2, 3, mask zero, other halfwords ignored, registers unchanged.
- z390 `test_test_under_mask_differential.py`: every case against z390.

## Commits

1. This plan.
2. Builders, lowering, tests, docs, bead snapshot.
