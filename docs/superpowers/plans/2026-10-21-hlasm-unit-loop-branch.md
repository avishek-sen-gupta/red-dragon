# HLASM Opcode Unit — Branch on Count and Branch on Index (red-dragon-6uyp.34)

**Goal:** lower BCT, BCTR, BCTG, BCTGR, BRCT (JCT), BRCTG (JCTG), BXH, BXHG, BXLE, BXLEG,
BRXH (JXH), BRXHG (JXHG), BRXLE (JXLE), BRXLG (JXLEG). BRCTH belongs to the high-word unit.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: the PoO pages
BRANCH ON COUNT, BRANCH ON INDEX HIGH / LOW OR EQUAL, BRANCH RELATIVE ON COUNT, BRANCH
RELATIVE ON INDEX HIGH / LOW OR EQUAL.

## Semantics (from the PoO pages)

- Count: R1 − 1, wrapped to 32 bits (low word only; high word kept) or 64 bits, replaces R1.
  Branch when the result is nonzero. The branch address is generated before R1 changes.
  BCT, BCTG: D2(X2,B2). BCTR, BCTGR: R2; R2 = 0 decrements without branching.
  BRCT, BRCTG: the relative target.
- Index: R3 even names the pair R3 (increment), R3 + 1 (compare value); R3 odd names one
  register used as both. Increment and compare value are read before R1 is written (the PoO:
  "the original contents of the compare-value register are used ... even when that register
  is also ... the first-operand location"). Sum = R1 + increment, wrapped; overflow ignored.
  Comparison is signed at 32 bits (BXH, BXLE, BRXH, BRXLE) or 64 bits (the G forms).
  High forms branch when sum > compare; low-or-equal forms when sum <= compare. The sum
  replaces R1 whether or not the branch is taken. BXH, BXLE: D2(B2) is the target, generated
  before R1 changes; BRX*: the relative target.
- CC unchanged by all of them. No program interruptions beyond transaction constraint.

## Shared pieces

- `interpreter/hlasm/opcodes/loop_branch.py`: `_on_count(width, target)` and
  `_on_index(width, comparison, target)` over a `Width` value (load, store, bits). A local
  `_branch_when(condition, target)` emits `BranchIf` to a taken label that dispatches via
  `emit_branch`. Signedness via `data_movement.signed`. Targets: `storage_address`,
  `relative_target` (operand 1), register R2, and operand-2 storage/relative for the index forms.

## Tests

- Unit `tests/unit/hlasm/test_loop_branch_lowering.py`: BCT target address computed before
  the R1 read; decrement `- 1`, `% 2^32`, low-word write, `!= 0`, `BranchIf`, dispatch.
  BCTR 4,0 has no BranchIf. BCTGR uses 64-bit offsets. BXH reads increment R6 and compare
  R7 before R4, `>`; BXLEG `<=` with 64-bit offsets; R3 odd reads one register twice.
  No `Symbolic`.
- Integration `tests/integration/hlasm/test_loop_branch.py`, programs in
  `loop_branch_programs.py` (CC preset 2; R2 records the path, R3 accumulates):
  - Counting loops for BCT, BCTR, BCTG, BCTGR, BRCT, JCT, BRCTG, JCTG summing 5..1 into R3
    (R3 = 15, R4 = 0, high word kept for 32-bit forms).
  - BCTR 4,0 decrements without branching; count 0 wraps to all ones and branches;
    BCTR 5,5 branches to the original R5.
  - Index loops for BXLE, BXLEG, BRXLE, JXLE, BRXLG, JXLEG (index 0..5 by 1, R3 = 15,
    R4 = 6) and BXH, BXHG, BRXH, JXH, BRXHG, JXHG (5 down to 1 by −1, R3 = 15, R4 = 0).
  - Overlaps: R1 = R3 + 1 (BXH 7,6: original compare value), R1 = R3 odd (BXLE 5,5, BXH 5,5),
    R1 = R3 even (BXLE 6,6). Signed and wrapping: 0x7FFFFFFF + 1 is −2^31, not high
    (BXH falls through, BXLE branches); the 64-bit analogue for BXHG.
- z390 `tests/z390/test_loop_branch_differential.py`: every integration case against z390.

## Commits

1. Plan.
2. Module, registration, tests, `docs/frontend-design/hlasm.md`; bead note; issues snapshot.
