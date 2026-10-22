# HLASM Opcode Unit — Compare and Branch, Compare and Trap, Load and Trap (red-dragon-6uyp.29)

**Goal:** lower CRB, CGRB, CLRB, CLGRB, CIB, CGIB, CLIB, CLGIB; CRJ, CGRJ, CLRJ, CLGRJ, CIJ,
CGIJ, CLIJ, CLGIJ; CRT, CGRT, CLRT, CLGRT, CIT, CGIT, CLFIT, CLGIT, CLT, CLGT; LAT, LGAT,
LLGFAT, LLGTAT. The bridge resolves every extended mnemonic (CRJE, CLGTNL, ...) to its base
mnemonic with M3 filled in (E 8, L 4, H 2, NE 6, NL 10, NH 12).

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14), COMPARE AND BRANCH, COMPARE LOGICAL AND BRANCH,
COMPARE AND TRAP, COMPARE LOGICAL AND TRAP, LOAD AND TRAP, LOAD LOGICAL AND TRAP, LOAD
LOGICAL THIRTY ONE BITS AND TRAP; Data Exception (6-25).

## Semantics

- None changes the CC. The comparison result picks an M3 bit: equal 8, first low 4, first
  high 2. Bit 3 (1) is reserved and never selected. M3 bits 0-2 zero: no comparison, no
  action. All three on (14 or 15): the action always happens.
- Branch forms (RRS, RIS) branch to D4(B4) through the dispatch; relative forms (RIE) to the
  RELOC_IMM target.
- Widths: CRB/CRJ/CRT 32 signed, CGRB/CGRJ/CGRT 64 signed; CIB/CIJ/CGIB/CGIJ a signed 8-bit
  I2; CLIB/CLIJ/CLGIB/CLGIJ an unsigned 8-bit I2; CIT/CGIT signed 16; CLFIT/CLGIT unsigned 16;
  CLRB/CLRJ/CLRT/CLT 32 logical, CLGRB/CLGRJ/CLGRT/CLGT 64 logical; CLT/CLGT read storage at
  D2(B2) (M3 is operand 1).
- Trap: a compare-and-trap data exception, DXC FF, operation completed: program interruption
  code 7, abend `S0C7`. The DXC is not modelled.
- LAT loads a word into the low word (high kept), LGAT a doubleword, LLGFAT a word zero
  extended, LLGTAT bits 1-31 of a word zero extended. The register is written, then a zero
  value traps (`S0C7`).

## Shared pieces

- `compare.py`: SIGNED_32/64, LOGICAL_32/64 CC builders; the comparison is spliced, its CC
  kept in a register and not stored.
- `branch_on_condition.py`: the mask test made public as `mask_selects(emitter, cc, mask)`
  and used by BC over `__hlasm_cc`.
- New `conditional.py`: `emit_when(emitter, condition, then)` — the taken/fall labels the
  branch-on-condition lowering uses, shared with the trap.
- `operand_sources.py`: LOGICAL_HALFWORD_IMMEDIATE moves here from `compare.py`.
- `data_movement`: `from_gr32/64`, `from_storage(_at)`, `storage_address_at`,
  `relative_target_at`, `signed_immediate`, `immediate`, `keep`, `move`, sinks.
- New `opcodes/compare_branch_trap.py`, registered in `opcodes/__init__.py`.
- `hlasm_constants.DATA_EXCEPTION_ABEND = "S0C7"`.

## Tests

- Unit `test_compare_branch_trap_lowering.py`: a conditional branch splices the compare,
  tests the mask bit, dispatches; CC never stored; relative and D4(B4) targets; mask 0 lowers
  to nothing, 14 branches or traps with no compare; trap abends `S0C7`; load and trap writes
  the register before the zero test; no SYMBOLIC.
- Integration `test_branch_extended_mnemonics.py` gains the compare-branch/trap spellings:
  base mnemonic and M3 through the bridge.
- Integration `test_compare_branch_trap.py`, programs in `compare_branch_trap_programs.py`:
  every base mnemonic and a spread of extended ones; equal/low/high, sign vs logical (e.g.
  -1 vs 1), immediate widths (CIJ -5, CLIJ 200, CLFIT 65535), masks 0 and 14, high words
  ignored by 32-bit forms; path register, CC unchanged; traps abend `S0C7` with registers
  as loaded; load and trap values, zero and non-zero, LLGTAT of X'80000000' traps.
- z390 `test_compare_branch_trap_differential.py`: every case; differences pinned and noted on
  red-dragon-6uyp.74. Cases z390 lacks use the PoO-derived expectation, stated in the test.

## Commits

1. This plan.
2. Shared pieces, lowering, tests, docs, bead snapshot.
