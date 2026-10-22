# HLASM Opcode Unit — Conditional Load and Store, Select, Population and Bit Counts (red-dragon-6uyp.41)

**Goal:** lower LOC, LOCG, LOCFH, LOCR, LOCGR, LOCFHR, LOCHI, LOCGHI, LOCHHI, STOC, STOCG,
STOCFH; SELR, SELGR, SELFHR; FLOGR, POPCNT, CLZG, CTZG, BDEPG, BEXTG. The bridge resolves
the extended mnemonics (LOCRE, STOCGNH, SELFHRO, ...) to the base mnemonic with M3 (M4 for
SELECT) filled in. che4z gives the negated suffixes (NE/NZ, NL/NM, NH/NP) of LOC, LOCG,
LOCR, LOCGR, STOC and STOCG masks 6, 10, 12 where Figure J-1 gives 7, 11, 13
(red-dragon-6uyp.82); the lowering takes M3 as given, and the mnemonics test xfails those.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14): LOAD ON CONDITION, LOAD HIGH ON CONDITION, LOAD
HALFWORD (HIGH) IMMEDIATE ON CONDITION, STORE (HIGH) ON CONDITION, SELECT, SELECT HIGH, FIND
LEFTMOST ONE, POPULATION COUNT, COUNT LEADING ZEROS, COUNT TRAILING ZEROS, BIT DEPOSIT, BIT
EXTRACT; Figure J-1 for the extended mnemonics.

## Semantics

- On condition (LOC*, STOC*): the mask bit `8 >> CC` of M3 picks whether the move happens. CC
  unchanged. Widths: LOC, LOCR, STOC low words; LOCFH, LOCFHR, LOCHHI, STOCFH high words;
  LOCG, LOCGR, LOCGHI, STOCG whole registers. I2 is a signed halfword. A storage operand's
  access exception when the condition is false is model dependent; we model none, so storage
  is touched only when the move happens.
- SELECT: R1 = R2 when M4 selects the CC, else R3; both read before R1 is written. SELR low
  words, SELGR whole registers, SELFHR high words; the other half of R1 kept. CC unchanged.
- FLOGR: R1 even (odd abends `S0C6`). R1 = position of R2's leftmost one, or 64; R1+1 = R2 with
  that bit cleared, or 0. CC 0 none found, 2 found. R2 read before either write.
- POPCNT: M3 bit 0 off: each byte of R1 = ones in that byte of R2; on: R1 = ones in R2. CC 0
  result zero, 1 not zero.
- CLZG, CTZG: R1 = leading or trailing zeros of R2 (64 for zero). CC unchanged.
- BEXTG: R2's bits under the R3 mask packed left-justified into R1, the rest zero. BDEPG: R2's
  leftmost n bits (n = ones in the mask) deposited, in order, at the mask's one bits; the rest
  zero. CC unchanged for both.

## IR shape (no new builtins)

- New `interpreter/hlasm/bit_counts.py`, branch-free: per-byte population (SWAR: subtract the
  halved pairs, add nibble pairs, add bytes, mask), total (per-byte times `0x0101...`, top
  byte), right smear (`x |= x >> 1, 2, 4, 8, 16, 32`), leading zeros (64 - total of the
  smear), trailing zeros (total of `(x AND -x) - 1` mod 2^64), the leftmost one bit
  (`smear XOR smear >> 1`).
- New `interpreter/hlasm/mask_bit_loop.py`: one IR loop over the mask's one bits, right to
  left, at most 64 iterations, state in three variables. Each iteration takes the lowest
  remaining bit, moves one bit between that mask position and a cursor that starts at
  `2^(64 - n)` and doubles. BEXTG reads at the mask bit and writes at the cursor; BDEPG the
  reverse. Chosen over an unrolled 64-step form (about 800 IR instructions) and the Hacker's
  Delight compress/expand (about 150, much harder to check).

## Shared pieces

- `branch_on_condition.mask_selects`, `conditional.emit_when` for the condition.
- `operand_sources`: WORD_STORAGE, DOUBLEWORD_STORAGE, HALFWORD_IMMEDIATE.
- `data_movement`: `move`, `from_gr32/64`, `to_gr32/64`, `to_storage`; new
  `from_gr_high32(index)` and `to_gr_high32` on a new `HlasmEmitter.load_gr_high32`.
- `even_odd` for FLOGR; `build_nonzero_ir` for POPCNT's CC.
- New `opcodes/conditional_select_count.py`, registered in `opcodes/__init__.py`.

## Tests

- Unit `test_conditional_select_count_lowering.py`: on-condition forms test the mask over
  `__hlasm_cc` before any operand is read and never store the CC; SELECT reads R2 and R3
  before writing R1; FLOGR odd R1 abends `S0C6`; the counts lower with no branch; BDEPG and
  BEXTG one loop; no SYMBOLIC. Bit-count IR checked on values through `straight_line_vm`.
- Integration `test_conditional_select_count_mnemonics.py`: every extended spelling reaches
  its base mnemonic and the Figure J-1 mask.
- Integration `test_conditional_select_count.py`, programs in
  `conditional_select_count_programs.py`: every base mnemonic, each extended suffix at least
  once across the family; condition met and not met, the kept half, negative immediates,
  SELECT with R1 = R2 or R3; FLOGR on 0, bit 0, bit 63, R2 = R1+1; POPCNT both forms;
  CLZG/CTZG on 0 and 1 and 2^63; BEXTG/BDEPG on empty, full and scattered masks.
- z390 `test_conditional_select_count_differential.py`: every case; differences pinned and
  noted on red-dragon-6uyp.74; cases z390 lacks use PoO-derived expectations, stated.

## Commits

1. This plan.
2. Helpers, lowering, tests, docs, bead snapshot.
