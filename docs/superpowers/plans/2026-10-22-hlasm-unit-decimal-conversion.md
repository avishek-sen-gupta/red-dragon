# HLASM Opcode Unit — Decimal conversion (red-dragon-6uyp.48)

**Goal:** lower CVB, CVBY, CVBG, CVD, CVDY, CVDG, PACK, PKA, PKU, UNPK, UNPKA, UNPKU. No
extended mnemonics.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: the PoO pages
7-266 (CONVERT TO BINARY), 7-267 (CONVERT TO DECIMAL), 7-355 to 7-357 (PACK, PACK ASCII,
PACK UNICODE), 7-482 to 7-484 (UNPACK, UNPACK ASCII, UNPACK UNICODE) and 8-3/8-4 (which
instructions check codes). Rulings R1, R29, R31, R34, R39.

## Semantics

- CVB/CVBY: 8-byte packed second operand, read and checked with the unit .46 reader;
  invalid digit or sign → `S0C7`, suppressed. Value outside 32 bits: the low 32 bits go to
  bits 32-63 of R1 (completed), then `S0C9`. CVBG: 16 bytes, all 64 bits of R1; outside 64
  bits → `S0C9`, suppressed. -0 converts to 0. CC unchanged.
- CVD/CVDY: low word of R1 signed; CVDG: all 64 bits. 8 or 16 bytes stored with sign C or
  D; a binary zero is +0, so no negative zero. CC unchanged. No exception.
- PACK (SS-b): no code checks. Right to left, one result byte per step, fetching its
  source bytes just before storing it (the PoO's overlap rule): byte 0 swaps the rightmost
  source byte's nibbles; byte k takes the numerics of source bytes L2-2k (low) and L2-1-2k
  (high). Source bytes left of the operand read as zero; extra source digits are dropped.
- PKA/PKU (SS-f): 16-byte result, sign C, digits from the low nibble of each byte (PKA) or
  of each two-byte character (PKU). L2 code above 31 (PKA), or above 63 or even (PKU) →
  `S0C6` before any store. Same digit loop as PACK, with stride 1 or 2.
- UNPK (SS-b): byte 0 swaps the rightmost source nibbles; then per result byte, odd steps
  fetch the next source byte, store zone F with its low digit and keep its high digit for
  the even step (the PoO's one-fetch-two-stores rule). No checks.
- UNPKA/UNPKU (SS-a): 16-byte source, digits extended with 3 (ASCII) or 003 (Unicode);
  L1 code above 31 (UNPKA) or above 63 or even (UNPKU) → `S0C6`. A 32-character result
  has 0x30 leftmost (digit 31 is the zero beyond the source). CC 0 for sign A/C/E/F, 1 for
  B/D, 3 otherwise. The PoO (8-3) says the digits are not checked and an invalid sign sets
  CC 3 rather than a data exception, so there is no `S0C7` here.
- EX (R31): PACK/UNPK on `LENGTH_NIBBLES`, PKA/PKU on the SS-f L2 byte (named
  `SECOND_LENGTH_BYTE`), UNPKA/UNPKU on `LENGTH_BYTE`; each lowered once.

## Shared helpers

- `interpreter/hlasm/opcodes/decimal_conversion.py`: the twelve lowerings, registered in
  `OPCODE_LOWERINGS` and (the SS six) `DATA_FIELD_LOWERINGS`. Reuses `read_packed`,
  `signed_value`, `store_packed`, `negative_bit`, `emit_data_check`,
  `emit_specification_check`, `emit_fixed_point_divide_check`, `signed`, `emit_counted_loop`.
- A zero-beyond-the-operand byte read (clamped offset, value masked) for the digit loops.

## Tests

- Unit `test_decimal_conversion_lowering.py`: CVB reads, `S0C7`, writes R1, `S0C9`; CVBG
  `S0C9` before the write; PKA `S0C6` before the first store; UNPKA sets the CC and has no
  `S0C7`; EX layouts; no SYMBOLIC.
- Integration `test_decimal_conversion.py` with `decimal_conversion_programs.py`: every
  mnemonic; CVB limits, -0, negatives, `S0C7` (R1 unchanged), `S0C9` (low word stored);
  CVBG limits and suppressed `S0C9`; CVD/CVDG negatives, zero, extremes; PACK truncation,
  padding, nibble swap, overlap; UNPK truncation, padding, overlap; PKA/PKU 31 digits,
  32-byte/64-byte source, `S0C6`; UNPKA/UNPKU CCs 0/1/3, 32-character fill, `S0C6`; EX.
- z390 `test_decimal_conversion_differential.py`: every case z390 has; PKU and UNPKU are
  not in z390, so those expected values come from the PoO. Disagreements pinned and noted
  on red-dragon-6uyp.74.

## Commits

1. This plan.
2. Feature: module, registration, tests, docs (hlasm.md, README unit count).
3. Issue snapshot with the bead note.
