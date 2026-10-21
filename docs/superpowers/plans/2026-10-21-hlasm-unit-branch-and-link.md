# HLASM Opcode Unit — Branch and Link, Branch and Save, Addressing Mode (red-dragon-6uyp.33)

**Goal:** lower BAL, BALR, BAS, BASR, BRAS (JAS), BRASL (JASL), BASSM, BSM, SAM24, SAM31,
SAM64 and TAM. BASR, BALR and BRAS move out of `seed.py`, behaviour unchanged.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: the PoO pages
BRANCH AND LINK, BRANCH AND SAVE, BRANCH AND SAVE AND SET MODE, BRANCH AND SET MODE,
BRANCH RELATIVE AND SAVE (LONG), SET ADDRESSING MODE, TEST ADDRESSING MODE.

## The machine stays in AMODE 31

Every effective address and the dispatch mask bits 33-63 at compile time. Modelling AMODE 24
or 64 would make every unit's address computation depend on a runtime mode. Out of scope:
any transition out of AMODE 31 abends `S0C1` (the project's "not modelled" code), tracked
by a new bead. So TAM always sees AMODE 31.

## Semantics (from the PoO pages, in AMODE 31)

- Link information: bit 32 one, bits 33-63 the updated instruction address, into the low
  word of R1; bits 0-31 unchanged. BAL and BALR use this format in AMODE 31 (their ILC/CC/
  program-mask format is AMODE 24 only). BAS, BASR, BRAS, BRASL, BASSM the same.
- The branch address is computed before R1 is written.
- BAL, BAS: target is the D2(X2,B2) address. BALR, BASR: R2; R2 = 0 links without branching.
  BRAS, BRASL: the relative target. CC unchanged.
- BASSM: link as BASR. R2 = 0: no branch, no mode change. Otherwise R2 bit 63 one selects
  AMODE 64, else bit 32 selects 31 (one) or 24 (zero): only bit 32 one with bit 63 zero
  stays in the model and branches; the others abend `S0C1` after R1 is written.
- BSM: R1 nonzero gets bit 32 set (the current basic-mode bit, one), the rest unchanged.
  R2 as BASSM. Both fields zero: nothing.
- SAM31: no effect (the instruction address is always below 2 GiB, so no specification
  exception). SAM24, SAM64: abend `S0C1`.
- TAM: CC 1.

## Shared pieces

- `interpreter/hlasm/opcodes/branch_and_link.py`: `_link` (AMODE 31 link word), the
  register, storage and relative targets (`storage_address`, `relative_target` from
  `data_movement.py`), `_set_mode_and_branch` (one `BranchIf` on `R2 & 0x80000001 ==
  0x80000000`, abend path, dispatch path). `seed.py` keeps LR only.

## Tests

- Unit `tests/unit/hlasm/test_branch_and_link_lowering.py`: link forms read the target
  before writing the link, link = section base + next offset | `0x80000000`, then dispatch;
  R2 = 0 has no dispatch; BASSM/BSM test the mode bits and abend or dispatch; BSM R1 ORs
  bit 32; SAM24/SAM64 abend, SAM31 is empty, TAM sets CC 1.
- Integration `tests/integration/hlasm/test_branch_and_link.py`, programs in
  `branch_and_link_programs.py`: CC preset to 2; R2 records the path; the target computes
  R5 = link − base (base from `LA`, bit 32 clear), so R5 = high fill | `0x80000000` |
  offset. Cases: BAL, BAL indexed, BALR, BALR 5,0, BAS, BASR, BASR 5,0, BRAS, JAS, BRASL,
  JASL, BASSM, BASSM 5,0, BASSM 5,5, BSM 5,4, BSM 0,4, BSM 5,0, BSM 0,0, SAM31, TAM.
  An xfail test (new bead) holds the PoO results of SAM24, SAM64, BSM/BASSM into
  AMODE 24 and 64 followed by TAM.
- z390 `tests/z390/test_branch_and_link_differential.py`: every case against z390; the
  mode-switch programs assert z390 gives the PoO values while RedDragon abends `S0C1`.
- The existing seed tests in `test_lowering_skeleton.py` stay as they are.

## Commits

1. Plan.
2. Module, seed move, tests, `docs/frontend-design/hlasm.md`; new bead; bead note;
   issues snapshot.
