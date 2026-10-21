# HLASM Opcode Unit — Branch on Condition (red-dragon-6uyp.32)

**Goal:** lower BC, BCR, BIC, BRC, BRCL, BPP and BPRP. The bridge resolves every extended
mnemonic (B, BE, BNER, BIL, J, JLNOP, BRUL, ...) to its base mnemonic with the mask filled
in, so the extended spellings need no lowering of their own; the tests prove the bridge
transforms by writing them.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14) pages BRANCH ON CONDITION, BRANCH INDIRECT ON
CONDITION, BRANCH RELATIVE ON CONDITION (LONG), BRANCH PREDICTION (RELATIVE) PRELOAD.

## Semantics (from the PoO pages)

- Branch when mask bit `8 >> CC` is one. Mask 0: no branch. Mask 15: unconditional. The CC
  is unchanged and no instruction here sets it.
- BC: target is the D2(X2,B2) effective address. BCR: target is R2; R2 = 0 performs no
  branch (BCR 15,0 and BCR 14,0 are serialization: no architected effect here).
- BRC (RI-c), BRCL (RIL-c): target is the RELOC_IMM address, section base + offset.
- BIC: target is the doubleword at D2(X2,B2), subject to the addressing mode, so AMODE 31
  keeps bits 33-63. The operand is read only when the branch is taken (model dependent).
- BPP, BPRP: hints only; "does not change the execution sequence". Lowered to nothing.
- Every target goes through `hl_dispatch`, which masks to 31 bits; a target that is not a
  machine statement abends `S0C1`.

## Static relative targets

Branching straight to a relative target's statement label would skip the dispatch chain,
but a lowering sees one statement, not the program, so it cannot tell whether the target
is a machine statement (and must abend `S0C1` when not). Threading the program into
`StatementLowering` touches every unit. Left as is; red-dragon-6uyp.62 tracks dispatch cost.

## Shared pieces

- New `interpreter/hlasm/opcodes/branch_on_condition.py`: one `on_condition(mask, target)`
  helper (nothing, unconditional, or a `BranchIf` on the mask bit around the taken path)
  and the seven lowerings. BCR moves here from `seed.py` unchanged in behaviour.

## Tests

- Unit `tests/unit/hlasm/test_branch_on_condition_lowering.py`: BC, BRC, BIC with a
  conditional mask test the CC, store the target and branch to `hl_dispatch` (BIC reads
  8 bytes, BRC adds the offset to the section base); mask 15 has no `BranchIf`; mask 0,
  BCR R2 = 0, BPP and BPRP lower to nothing.
- Integration `tests/integration/hlasm/test_branch_on_condition.py`, programs in
  `branch_on_condition_programs.py`: each case sets CC 0-3, branches, and R2 records the
  path (1 taken, 2 fall-through); CC asserted unchanged. Every base mnemonic, and an
  extended spread: B, BE, BNE, BH, BL, BNH, BNL, BO, BNO, BZ, BNZ, BM, BNM, BP, BNP, NOP;
  BR, BER, BNER, BHR, BOR, NOPR, BCR 15,0, BCR 14,0; BI, BIE, BINE, BIO, BIH, BINL;
  J, JE, JNE, JH, JL, JO, JNO, JNOP, JC, BRE, BRU, BRNZ; JLU, JLE, JLNE, JLH, JLNOP,
  JLC, BRUL, BRNEL, BRZL. BIC with a nonzero high word and bit 32 set still lands.
  A relative branch into data, BC to data, and BIC to data abend `S0C1`; BRC across
  sections lands.
- z390 `tests/z390/test_branch_on_condition_differential.py`: every case against z390;
  disagreements pinned and noted on red-dragon-6uyp.74.

## Commits

1. Plan.
2. Module, BCR move, tests, `docs/frontend-design/hlasm.md`; bead note; issues snapshot.
