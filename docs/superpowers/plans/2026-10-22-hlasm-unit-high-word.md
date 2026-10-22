# HLASM Opcode Unit — High-word (red-dragon-6uyp.44)

**Goal:** lower the 34 high-word base mnemonics: AHHHR, AHHLR, AIH, ALHHHR, ALHHLR, ALSIH,
ALSIHN, BRCTH (JCTH), CHF, CHHR, CHLR, CIH, CLHF, CLHHR, CLHLR, CLIH, CLMH, ICMH, LBH, LFH,
LFHAT, LHH, LLCH, LLHH, LMH, SHHHR, SHHLR, SLHHHR, SLHHLR, STCH, STCMH, STFH, STHH, STMH.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14), pages 7-29 to 7-33, 7-48, 7-166 to 7-173, 7-300,
7-310 to 7-324, 7-444 to 7-457. Rulings: R1 (low-word writes at 8r+4), high words at 8r,
R29 (compares on ints), R31 (EX data fields; none here — byte 1 of every form is R1 with
an opcode, X2, R3 or M3 field, never a data field), R34 (checks before the first store).

## Semantics

- Register forms read the high word (bits 0-31) of R1, R2; `..HHR` reads R3's high word,
  `..HLR` (and CHLR, CLHLR) its low word. Results go to R1's high word; the low word is
  never written.
- AHHHR, AHHLR, SHHHR, SHHLR, AIH: 32-bit signed, CC 0-3, overflow CC 3 then `S0C8`
  under the program mask (the result is stored first: overflow completes).
- ALHHHR, ALHHLR, ALSIH: 32-bit logical add, carry CC. SLHHHR, SLHHLR: logical subtract,
  borrow CC. ALSIH adds a 32-bit signed immediate (wrapped, so a negative one sets the
  CC as a subtract would). ALSIHN: the same sum, CC unchanged.
- BRCTH: R1's high word minus one, wrapped; branch to the relative target when nonzero.
  The target is generated first; CC unchanged.
- CHHR, CHLR, CHF, CIH signed; CLHHR, CLHLR, CLHF, CLIH logical: first operand R1's high
  word. CC only.
- ICMH, STCMH, CLMH: ICM, STCM, CLM over bits 0-31.
- LBH, LHH sign-extend a byte or halfword; LLCH, LLHH zero-extend; LFH loads a word.
  LFHAT loads a word, then traps on zero with the compare-and-trap data exception: `S0C7`
  after the load, like LAT (load-and-trap completes; the DXC is not modelled).
- STCH, STHH, STFH store the high word's rightmost byte, halfword or all of it.
- LMH, STMH: LM and STM over high words, wrapping 15 to 0.

## Shared pieces

- `register_part.py`: `RegisterPart(load, store, bits)`, a register's low word, high word or
  whole value, with `merge` (insert bytes under a field mask). Constants in
  `register_parts.py`. `merge_low_word` becomes `LOW_WORD_PART.merge`.
- `load_store.py`: ICM/STCM and LM/STM factories take the part; `compare.py` likewise CLM.
- `loop_branch.py`: branch on count and index take a `RegisterPart` in place of the
  width-keyed load/store maps; `on_count` public for BRCTH.
- `compare_branch_trap.trapping_on_zero` public for LFHAT.
- `logical_add_subtract`: the sum and carried factories public for the high forms.
- `opcodes/high_word.py`: the unit table.

## Tests

- Unit `test_high_word_lowering.py`: per representative form the GPR offsets read and
  written (high word at 8r, low word of R3 for the HL forms, no low-word write), which set
  the CC, AIH's `S0C8` check, LFHAT's `S0C7` after the write, BRCTH target before the
  decrement; no SYMBOLIC.
- Integration `test_high_word.py`, programs in `high_word_programs.py`: every mnemonic on
  the VM with registers loaded with distinct high and low words: results, untouched low
  words, CCs (zero, negative, positive, overflow; carry, borrow), ALSIHN keeps a preset
  CC, ALSIH negative immediate, BRCTH/JCTH loop count, compares equal/low/high signed vs
  logical, ICMH/STCMH/CLMH masks incl. 0, LMH/STMH wrap, LFHAT trap and no trap.
- z390 `test_high_word_differential.py`: every case against z390. z390 lacks LFHAT; its
  cases pin z390's result and keep the PoO value here.

## Commits

1. This plan.
2. Shared-piece refactor, the unit, tests, `docs/frontend-design/hlasm.md`, issue snapshot.
