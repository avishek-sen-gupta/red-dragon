# HLASM Opcode Unit — Load and Test, Complement, Negative, Positive (red-dragon-6uyp.40)

**Goal:** lower the 15 base mnemonics of red-dragon-6uyp.40. None has extended mnemonics.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14) pages LOAD AND TEST, LOAD COMPLEMENT, LOAD NEGATIVE,
LOAD POSITIVE.

## Semantics (from the PoO pages)

- LTR, LTGR, LTGFR (register), LT, LTG, LTGF (storage; the 32-bit operand of LTGF and
  LTGFR is sign-extended to 64 bits): load the operand, CC 0 zero, 1 negative, 2 positive.
  LT, LTR write only the low word of R1 (ruling R1).
- LCR, LCGR: the two's complement. LPR, LPGR: the absolute value. Both overflow only on
  the maximum negative number: the result is that number unchanged, CC 3, and with
  program-mask bit `1000` the run abends `S0C8`. Otherwise CC 0, 1, 2 by the result sign.
- LCGFR, LPGFR: sign-extend the low word of R2 to 64 bits first, so they never overflow.
- LNR, LNGR, LNGFR: minus the absolute value, never overflow, CC 0 or 1.

## Shared pieces

- `fixed_width_ir`: `build_load_test_cc_ir`, `build_negate_signed_cc_ir`,
  `build_absolute_signed_cc_ir`, `build_negative_absolute_cc_ir`; each takes `%p_value` and
  returns the (result, CC) pair, reusing the signed CC and overflow fragments.
- `result_and_cc.apply_result_and_cc` returns the CC register so the overflow trap can
  follow it.
- New `interpreter/hlasm/opcodes/load_sign.py`: table rows per mnemonic over the shared
  `operand_sources` (`WORD_STORAGE`, `DOUBLEWORD_STORAGE`, `SIGNED_WORD_STORAGE`,
  `SIGNED_LOW_WORD`) and `data_movement` sources; the trap wrapper for LC and LP forms.

## Tests

- Unit `test_fixed_width_ir.py`: each builder at 32 and 64 bits, the maximum negative
  number included.
- Unit `test_load_sign_lowering.py`: register and storage widths per form, the `S0C8` trap
  only on LCR, LCGR, LPR, LPGR, the trap taken only with the mask bit on, no SYMBOLIC.
- Integration `test_load_sign.py`, programs in `load_sign_programs.py`: every mnemonic,
  negative, zero and positive operands, the maximum negative number, high word kept.
- z390 `test_load_sign_differential.py`: every case against z390.

## Commits

1. Plan.
2. Builders, lowering, tests, `docs/frontend-design/hlasm.md`; bead note; issues snapshot.
