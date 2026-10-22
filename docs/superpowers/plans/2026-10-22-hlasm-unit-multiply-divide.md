# HLASM Opcode Unit — Multiply and Divide (red-dragon-6uyp.27)

**Goal:** lower the 37 base mnemonics of red-dragon-6uyp.27. None has extended mnemonics.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14) pages DIVIDE, DIVIDE LOGICAL, DIVIDE SINGLE,
MULTIPLY, MULTIPLY HALFWORD (IMMEDIATE), MULTIPLY LOGICAL, MULTIPLY SINGLE (IMMEDIATE).

## Semantics (from the PoO pages)

- Truncated products, CC unchanged, no overflow: MS, MSY, MSR, MSFI, MH, MHY, MHI (32-bit
  R1 low word times a signed word, halfword or immediate; low 32 bits kept); MSG, MSGR,
  MSGF, MSGFR, MSGFI, MGH, MGHI (64-bit R1 times a signed doubleword, word, halfword or
  immediate; low 64 bits kept).
- Truncated products with CC: MSC, MSRKC (32), MSGC, MSGRKC (64). CC 0 zero, 1 negative,
  2 positive, 3 when the exact product does not fit the width; CC 3 with program-mask bit
  `1000` on abends `S0C8`. The RRF-a forms multiply R3 by R2.
- Pair products, CC unchanged, R1 even or `S0C6`: M, MFY, MR (signed low word of R1+1
  times a signed word; 64-bit product into the low words of R1, R1+1); ML, MLR (the same,
  unsigned); MG, MGRK (signed 64 by 64; the 128-bit product into R1, R1+1; MGRK multiplies
  R3 by R2); MLG, MLGR (the same, unsigned).
- Divides, CC unchanged, R1 even or `S0C6`. Remainder into R1, quotient into R1+1. The
  quotient truncates toward zero; the remainder takes the dividend's sign. A zero divisor
  or a quotient out of range is a fixed-point-divide exception, `S0C9`, not masked by the
  program mask; the registers stay.
  - D, DR: the low words of R1, R1+1 as a signed 64-bit dividend, a signed word divisor,
    32-bit results in the low words.
  - DL, DLR: the same, unsigned.
  - DLG, DLGR: R1, R1+1 as an unsigned 128-bit dividend, an unsigned doubleword divisor,
    64-bit results.
  - DSG, DSGR (signed doubleword divisor), DSGF, DSGFR (signed word divisor): R1+1 as a
    signed 64-bit dividend, 64-bit results.
- The VM's `//` and `%` floor, so the quotient and remainder are built from magnitudes.

## Shared pieces

- `fixed_width_ir`: `build_multiply_signed_cc_ir` ((result, CC), as add with `MUL`; the
  overflow test takes the exact value's full width); `build_divide_truncating_ir`
  ((quotient, remainder) from the operands' magnitudes and signs).
- New `interpreter/hlasm/fixed_point_divide.py`: a raised condition abends `S0C9`.
- New `interpreter/hlasm/opcodes/even_odd.py`: the odd-R1 `S0C6` wrapper, moved from
  `shift_rotate.py`, which then imports it.
- `data_movement`: `from_doubleword_pair`, `to_doubleword_pair` (R1, R1+1 as 128 bits).
- New `interpreter/hlasm/opcodes/multiply_divide.py`: table rows per mnemonic, reusing
  `operand_sources` and `signed_add_subtract.signed_arithmetic`.

## Tests

- Unit `test_fixed_width_ir.py`: multiply CC and overflow at 32 and 64 bits (the minimum
  times -1); truncating divide on all four sign combinations and a 128-bit dividend.
- Unit `test_multiply_divide_lowering.py`: register and storage widths for MS, MSGF, M,
  MLGR, MGRK, D, DLG, DSGF; CC and `S0C8` only for MSC and MSGRKC; the divide checks abend
  `S0C9`; odd R1 abends `S0C6` with no register access for every pair form; no SYMBOLIC.
- Integration `test_multiply_divide.py`, programs in `multiply_divide_programs.py`: one
  case per mnemonic (registers, CC; CC 1 set beforehand where unchanged); negative
  operands, truncation, 128-bit products, MSC overflow CC 3; divide by zero and quotient
  overflow abend `S0C9` with the registers unchanged.
- z390 `test_multiply_divide_differential.py`: every case against z390. z390 does not
  assemble MG, MGH, MGRK, MSC, MSGC, MSRKC, MSGRKC: those run on the VM with
  PoO-derived values and z390's refusal is pinned.

## Commits

1. Plan.
2. Builders, checks, lowering, tests, `docs/frontend-design/hlasm.md`; bead note; issues
   snapshot.
