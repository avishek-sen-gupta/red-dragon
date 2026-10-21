# HLASM Opcode Unit — Logical Add and Subtract (red-dragon-6uyp.26)

**Goal:** lower the 34 base mnemonics of red-dragon-6uyp.26.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14) pages ADD LOGICAL, ADD LOGICAL IMMEDIATE, ADD LOGICAL
WITH CARRY, ADD LOGICAL WITH SIGNED IMMEDIATE, SUBTRACT LOGICAL, SUBTRACT LOGICAL IMMEDIATE,
SUBTRACT LOGICAL WITH BORROW.

## Semantics (from the PoO pages)

- Unsigned arithmetic at the result width; the carry out of bit 0 sets CC bit 2.
  CC = 2 × carry + (result ≠ 0). No fixed-point-overflow interruption.
- Add logical: AL, ALY, ALR, ALRK (32); ALG, ALGR, ALGRK (64); ALGF, ALGFR (64, second
  operand 32-bit unsigned); ALFI (I2 32-bit); ALGFI (64, I2 32-bit unsigned).
- Subtract logical: x + ¬y + 1 (PoO programming note 1). SL, SLY, SLR, SLRK; SLG, SLGR,
  SLGRK; SLGF, SLGFR; SLFI; SLGFI. Carry = no borrow, so CC 1 nonzero/borrow, 2 zero/no
  borrow, 3 nonzero/no borrow; CC 0 cannot occur (a zero difference always carries).
- With carry: ALC, ALCR (32), ALCG, ALCGR (64) add the carry-in, which is CC bit 2 (CC 2 or 3).
- With borrow: SLB, SLBR (32), SLBG, SLBGR (64) compute x + ¬y + (CC bit 2); CC 0 or 1 means
  borrow, so the +1 is dropped. CC 0 is possible here (0 − (2^n − 1) − 1).
- Signed immediate: ALHSIK, ALGHSIK (R1 = R3 + I2, I2 16-bit signed); ALSI, ALGSI
  (D1(B1) += I2, I2 8-bit signed). The immediate is sign-extended to the width and added as
  an unsigned value; for a negative I2 that is x + (2^n − |I2|), exactly SUBTRACT LOGICAL of
  |I2|, which is the CC the PoO prescribes for a negative second operand.
- 32-bit forms write only the low word.

## Shared pieces

- `fixed_width_ir.build_add_logical_cc_ir` (existing) for the add-logical forms.
- New in `fixed_width_ir`: `build_add_logical_carry_cc_ir` (left + right + carry-in) and
  `build_sub_logical_borrow_cc_ir` (left + ones' complement of right + carry-in); the
  carry-in is a third input register. SL forms supply a constant 1, ALC/SLB supply
  CC >> 1.
- New `interpreter/hlasm/opcodes/logical_add_subtract.py`: one `logical_arithmetic` lowering
  plus a storage-and-immediate one, table rows per mnemonic over `data_movement` sources and
  sinks, following `signed_add_subtract.py`.

## Tests

- Unit `tests/unit/hlasm/test_fixed_width_ir.py`: the two new builders on vectors (carry-in,
  CC 0 for SLB 0 − max − borrow).
- Unit `tests/unit/hlasm/test_logical_add_subtract_lowering.py`: ALGF, ALRK, ALCR, SLBG, ALSI,
  ALGSI read and write their widths; ALC/SLB read `__hlasm_cc`; every form stores the CC; no
  `S0C8`, no branch, no SYMBOLIC.
- Integration `tests/integration/hlasm/test_logical_add_subtract.py`, programs in
  `logical_add_subtract_programs.py`: one case per mnemonic (body, declared registers, final
  CC), covering every reachable CC across the unit; ALC/SLB cases set the carry first with an
  AL/SL; vectors: 0xFFFFFFFF + 1 → 0 CC 2, SLR x,x → CC 2, 0 − 1 → CC 1, SLB 0 − max with
  borrow → CC 0, ALSI −1 on 0 → CC 1, ALGSI 255 adds −1.
- z390 `tests/z390/test_logical_add_subtract_differential.py`: every case against z390.

## Commits

1. Refactor: width constants consolidated in `hlasm_constants`.
2. Plan.
3. Builders, lowering, tests, `docs/frontend-design/hlasm.md`; bead note; issues snapshot.
