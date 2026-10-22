# HLASM Opcode Unit — Storage-to-Storage Compares (red-dragon-6uyp.36)

**Goal:** lower CLC, CLCL, CLCLE, CLCLU, CLST, CUSE.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14), COMPARE LOGICAL (CLC), COMPARE LOGICAL LONG,
LONG EXTENDED, LONG UNICODE, COMPARE LOGICAL STRING, COMPARE UNTIL SUBSTRING EQUAL
(pages 7-167 to 7-185). None is lowered yet; the compare unit stopped at CLM.

## Semantics

All compares are unsigned, left to right: CC 0 equal, 1 first low, 2 first high. Storage
is never written.

- CLC: L bytes (written length, 0 means 1). One block compare of the two L-byte values
  gives the same CC as a byte loop. Registers unchanged.
- CLCL: even pairs, else S0C6. 24-bit lengths, pad in R2+1 bits 32-39; the shorter operand
  is extended with the pad. With k the offset of the first unequal byte (or the longer
  length when equal), each operand's length drops by min(k, its length) and its address
  advances by the same amount. That covers both PoO cases: an inequality against the pad
  zeroes the shorter length, and equality zeroes both. R1 and R2 lose bit 32; bits 32-39
  of the length registers and all high words are kept.
- CLCLE, CLCLU: as CLCL with 32-bit lengths and the pad from the D2(B2) address (one byte;
  two for CLCLU). CLCLU compares 2-byte characters and abends S0C6 on an odd length.
  Ruling R28: one execution, never CC 3.
- CLST: GR0 bits 32-55 nonzero is S0C6; the ending character is GR0 bits 56-63. Both end
  together: CC 0, R1 and R2 unchanged. Otherwise CC 1 when the first operand ends first or
  has the lower byte, else CC 2; R1 and R2 point at the last bytes processed. Never CC 3.
- CUSE: even pairs, else S0C6. Signed 32-bit lengths in R1+1 and R2+1 (negative counts as
  zero and stays unchanged); substring length GR0 bits 56-63, pad GR1 bits 56-63. The
  scan keeps `start`, the offset after the last unequal byte. CC 0 when the equal run
  reaches the substring length (length 0 is found at once); at the end of the longer
  operand CC 1 if the last bytes were equal (start < longer length), else CC 2. Each
  operand advances by min(start, its length). Never CC 3.

## Shared pieces

- `long_operands.py`: `LongOperands` fields renamed to first/second/shorter so a compare
  reads it as naturally as a move.
- `long_registers.py`: the pair reading, the smaller length, the address advance, the
  length count-down, both pads and the even-length check, moved out of `long_move.py`.
- `long_compare.py`: CLCL, CLCLE, CLCLU over one span walk: the common bytes, then the
  longer operand's tail against the pad; a body callback per byte.
- `compare_string.py` (CLST) and `compare_substring.py` (CUSE).
- `opcodes/ss_compare.py`: the unit table and CLC.

## Tests

- Unit `test_ss_compare_lowering.py`: CLC reads both L-byte blocks once and writes no
  storage; CLCL's loop reads one byte per operand per iteration; odd pairs in CLCL, CLCLE,
  CLCLU and CUSE abend S0C6 before reading a register; no SYMBOLIC.
- Integration `test_ss_compare.py`, programs in `ss_compare_programs.py`: every mnemonic,
  CC 0/1/2, registers after completion: CLC length 0 and 256; CLCL equal, unequal in the
  common part and against the pad, zero lengths; CLCLE and CLCLU pads; CLST equal, first
  ends first, unequal bytes; CUSE found, end with equal and unequal last bytes, zero
  substring length, negative length. S0C6: CLCLU odd length, CLST GR0 bits.
- z390 `test_ss_compare_differential.py`: every case against z390.

## Commits

1. This plan.
2. Shared pieces, lowering, tests, docs, bead snapshot.
