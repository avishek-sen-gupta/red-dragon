# HLASM Opcode Unit — Shifts and Rotates, Including the RISBG Family (red-dragon-6uyp.31)

**Goal:** lower the 25 base mnemonics of red-dragon-6uyp.31.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14) pages ROTATE LEFT SINGLE LOGICAL, ROTATE THEN AND /
EXCLUSIVE OR / OR SELECTED BITS, ROTATE THEN INSERT SELECTED BITS (HIGH, LOW), SHIFT LEFT /
RIGHT SINGLE / DOUBLE (LOGICAL).

## Semantics (from the PoO pages)

- The shift or rotate amount is the low six bits of the second-operand address D2(B2); no
  storage is referenced.
- Logical, CC unchanged: SLL, SRL (R1 low word), SLLK, SRLK (R3 low word into R1 low word),
  SLLG, SRLG (64), RLL (32, amount mod 32), RLLG (64).
- Signed right: SRA, SRAK (32), SRAG (64); the sign fills from the left. CC 0 zero, 1
  negative, 2 positive.
- Signed left: SLA, SLAK (32), SLAG (64). The sign stays; the numeric bits shift; CC 3 when a
  bit unlike the sign leaves the numeric part (the exact product by 2^n does not fit), then
  fixed-point overflow abends `S0C8` only when program-mask bit `1000` is on.
- Double: SLDL, SRDL, SLDA, SRDA over the low words of the even-odd pair R1, R1+1 as one
  64-bit operand; the high words stay. An odd R1 is a specification exception (`S0C6`);
  che4z already refuses it at assembly, so only a built statement reaches it.
- RISBG, RISBGN: the 64-bit R2 rotated left by I5 (low six bits, absent = 0); the bits
  from I3 to I4 (bits 2-7, wrapping from 63 to 0) replace those of R1; Z (I4 bit 0) zeroes
  the rest. RISBG sets the CC from the 64-bit signed result; RISBGN leaves it.
- RISBHG, RISBLG: as RISBG, positions from bits 3-7 of I3 and I4 within bits 0-31 (HIGH)
  or 32-63 (LOW), wrapping within that word; Z zeroes the rest of that word only; the other
  word stays. CC unchanged.
- RNSBG, ROSBG, RXSBG: R1 combined with the rotated R2 over the selected bits; CC 0 if
  those bits of the result are zero, else 1; T (I3 bit 0) leaves R1 unchanged.
- Extended mnemonics arrive resolved: RISBGZ, RISBGNZ, RISBHGZ, RISBLGZ (I4 | X'80'),
  RNSBGT, ROSBGT, RXSBGT (I3 | X'80'), the high-word loads, logical and shift-logical forms
  (LHHR, SLLHH, NHHR and the rest) as RISBHG / RISBLG / RxSBG operands.

## Shared pieces

- `fixed_width_ir`: `build_shift_left_logical_ir`, `build_shift_right_logical_ir`,
  `build_rotate_left_ir` (value), `build_shift_left_signed_cc_ir`,
  `build_shift_right_signed_cc_ir` ((result, CC)); value in `%p_left`, amount in `%p_right`.
- New `interpreter/hlasm/register_span.py`: `RegisterSpan(origin, bits)`, the positions a
  RISBG-family field selects within; `selected(start, end)` and `word()` masks;
  `WHOLE_REGISTER`, `HIGH_WORD`, `LOW_WORD`.
- `operands.optional_imm_operand(statement, index, absent)` for I5.
- `data_movement`: `from_even_odd_pair`, `to_even_odd_pair` (low words of R1 and R1+1).
- New `interpreter/hlasm/opcodes/shift_rotate.py`: table rows per mnemonic.

## Tests

- Unit `test_fixed_width_ir.py`: the five builders on vectors (wrap, sign fill, overflow
  beyond the width, rotate by 0 and by more than 32).
- Unit `test_shift_rotate_lowering.py`: SLL, SLLG, SRAK, RLL, SLDL read and write their
  widths with no storage access, CC only for SRAK; SLA's overflow trap; odd SLDA abends
  `S0C6` with no register access; RISBG/RISBGN/RISBHG/RNSBG-T/ROSBG writes and CCs;
  `RegisterSpan` masks; no SYMBOLIC.
- Integration `test_shift_rotate.py`, programs in `shift_rotate_programs.py`: one case per
  base and extended mnemonic (registers, CC; CC 1 set beforehand where unchanged); SLA and
  SLDA overflow CC 3; amount from a base register; amount 33 in SLL and RLL.
- Integration `test_shift_rotate_mnemonics.py`: a sample of extended mnemonics reach
  their base mnemonic and operands through the bridge.
- z390 `test_shift_rotate_differential.py`: every case against z390; differences pinned,
  PoO values where z390 lacks an instruction.

## Commits

1. Plan.
2. Builders, span, lowering, tests, `docs/frontend-design/hlasm.md`; bead note; issues
   snapshot.
