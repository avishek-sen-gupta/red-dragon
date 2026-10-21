# HLASM Opcode Unit — Signed Add and Subtract (red-dragon-6uyp.25)

**Goal:** lower the 32 base mnemonics of red-dragon-6uyp.25. SR moves here from
`opcodes/seed.py`; it gains the fixed-point-overflow interruption, otherwise unchanged.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14) pages ADD, ADD IMMEDIATE, ADD HALFWORD, ADD HALFWORD
IMMEDIATE, SUBTRACT, SUBTRACT HALFWORD; Fixed-Point-Overflow Exception.

## Semantics (from the PoO pages)

- Result = first op ± second op, two's complement at the result width, carry out of the sign
  bit ignored. CC 0 zero, 1 negative, 2 positive, 3 overflow.
- 32-bit (low word written, high word kept): A, AY, AR, S, SY, SR (word storage / register);
  AH, AHY, SH, SHY (halfword storage, sign extended); AHI (I2 16-bit signed); AFI (I2 32-bit).
- 64-bit: AG, AGR, SG, SGR; AGF, AGFR, SGF, SGFR (second operand 32-bit signed); AGH, SGH
  (halfword signed); AGHI (16-bit); AGFI (32-bit).
- Distinct operands: ARK/AGRK R1 = R2 + R3; SRK/SGRK R1 = R2 − R3; AHIK/AGHIK R1 = R3 + I2
  (16-bit signed).
- Storage-and-immediate: ASI (word), AGSI (doubleword) at D1(B1) += I2 (8-bit signed); the
  sum is stored back, CC from the sum. Interlocked update is not observable here.
- Overflow: "the operation is completed" (result stored, CC 3); if PSW bit 20 — program-mask
  bit `0b1000` of `__hlasm_pm` — is one, a fixed-point-overflow interruption follows: abend
  `S0C8`. The initial mask `0110` has it off, so runs set CC 3 and continue.
- The bridge hands an immediate signed or unsigned (`AGSI X,255`), so each lowering takes the
  field-width bit image and sign-extends it.

## Shared pieces

- `fixed_width_ir.build_add_signed_cc_ir` / `build_sub_signed_cc_ir` at 32 and 64 bits
  (existing), spliced with `inline_ir`; the operands are sign-extended to the second operand's
  width first with `data_movement.signed`.
- New `interpreter/hlasm/fixed_point_overflow.py`: `emit_fixed_point_overflow_check(emitter, cc)`
  — CC 3 and PM bit `0b1000` both set → abend `S0C8` (pattern of `alignment_check.py`).
- New module `interpreter/hlasm/opcodes/signed_add_subtract.py`: one
  `signed_arithmetic(ir, left, right, sink)` lowering, rows per mnemonic; operand sources for a
  register, storage or immediate at a given operand index.

## Tests

- Unit `tests/unit/hlasm/test_signed_add_subtract_lowering.py`:
  - AGF reads its storage word and writes the full R1; AH writes only the low word; ARK reads
    R2 and R3 low words; ASI reads and writes the word at D1(B1); every form stores the CC and
    has one `S0C8` branch; no SYMBOLIC.
  - Overflow trap condition on the VM (straight-line): AR of 0x7FFFFFFF + 1 with the PM set to
    `1110` makes the trap condition true; with the initial `0110`, false; without overflow,
    false. End-to-end S0C8 needs SPM (red-dragon-6uyp.45); a note goes on that bead.
- Integration `tests/integration/hlasm/test_signed_add_subtract.py`, programs in
  `signed_add_subtract_programs.py`: one case per mnemonic (body, declared registers, final CC),
  rotating the final CC across 0/1/2/3 so each mnemonic's sign and overflow paths run; the high
  word kept for 32-bit forms; ASI/AGSI read back with L/LG; key vectors 0x7FFFFFFF + 1 → CC 3,
  0x80000000 − 1 → CC 3, −2^63 − 1 (SG) → CC 3, AGSI 255 adds −1.
- z390 `tests/z390/test_signed_add_subtract_differential.py`: every case against z390 registers
  and CC (programs end in `ABEND`). Where z390 lacks an instruction, its expected value stays
  PoO-derived and the test says so.

## Commits

1. Plan.
2. Lowering, SR move, overflow check, tests, `docs/frontend-design/hlasm.md`; bead notes
   (.25 commits, .45 end-to-end S0C8 test); issues snapshot.
