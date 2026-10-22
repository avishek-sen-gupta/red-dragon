# HLASM Opcode Unit — Miscellaneous and access registers (red-dragon-6uyp.45)

**Goal:** lower CKSM, CPYA, EAR, ECAG, ECTG, EPSW, IPM, LAM, LAMY, LCBB, MC, NIAI, PFD,
PFDRL, SAR, SPM, STAM, STAMY, STCK, STCKE, STCKF, STFLE, TRAP2, TRAP4. SVC is already
lowered (`opcodes/svc.py`, `test_svc.py`); confirm only.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: the PoO pages
7-50, 7-289, 7-295 to 7-303, 7-311, 7-329, 7-350, 7-424, 7-436 to 7-449, 10-189.
Rulings: R28 (CKSM one execution, no CC 3), R29, R31 (MC's I2 is a data field), R34,
R35 (access registers), R36 (clocks are run inputs), R37 (fixed z17), R38 (hints, MC,
TRAP).

## Semantics

- Access registers: a 64-byte region `__hlasm_ars`, 16 words, zero at start, allocated
  after the sections so section addresses do not move. CPYA AR←AR, EAR GR low word←AR,
  SAR AR←GR low word. LAM/LAMY/STAM/STAMY: R1 to R3 wrapping, word boundary else S0C6
  before any access; reuse `load_multiple`/`store_multiple` with an access-register part.
- SPM: CC ← R1 bits 34-35, program mask ← bits 36-39. IPM: R1 bits 32-33 ← 0, 34-35 CC,
  36-39 mask, the rest kept (PoO; the dispatch's "bits 2-7, others unchanged" reads as
  the same byte). EPSW: R1 low word ← PSW bits 0-31 with bit 12 zero: X'0785' (T, IO, EX,
  protection 8, M, P), CC at 18-19, mask at 20-23; then, if R2 ≠ 0, R2 low word ← X'80000000' (BA).
- Clocks (R36): the VM has no injectable run-time clock (COBOL's `CompileClock` is a
  compile-time datetime; CURRENT-DATE reads `datetime.now` directly). New `MachineClock`
  protocol: `tod_clock()` (104-bit TOD) and `cpu_timer()` (64-bit). Two thin builtins over
  it, `__hlasm_tod_clock` and `__hlasm_cpu_timer`, composed into `core_builtins(clock)`;
  `SystemMachineClock` reads the wall and process clocks it is given. Tests inject a fixed
  clock. STCK: bits 0-63, made unique in IR (`max(clock, last + 1)`, `__hlasm_tod_last`).
  STCKF: bits 0-63. STCKE: epoch 0, 104 clock bits with bit 103 forced on, zero
  programmable field. CC 0 (set state). ECTG: GR0 ← op1 − CPU timer, GR1 ← op2, R3 ←
  eight bytes at R3's address; all fetched first.
- STFLE (R37): a constant list, a bit on only when every problem-state instruction of the
  facility is lowered: 0-2, 7, 18, 19, 21, 22, 25, 26, 30-35, 45, 52, 53, 58, 61, 84, 87
  (two doublewords). Off: 16 and 24 (PKA, PKU, UNPKA, UNPKU unlowered), 49 (PPA), 129
  (vector), 133. Doubleword boundary else S0C6. Stores min(GR0 bits 56-63 + 1, 2)
  doublewords; GR0 bits 56-63 ← 1; CC 0 complete, 3 short.
- ECAG (R37): code = address bits 40-63. Reserved bits 40-53, reserved ASI/AI/LI → all
  ones. Cache set: topology summary X'04070B0B00000000' (L1 split private, L2 private
  unified, L3 and L4 shared unified), line 256, sizes 128 KiB / 36 MiB / 360 MiB /
  2,880 MiB, associativity 8/18/48/48; TI ignored (I and D alike). CPU set AI 0: 5,500
  cycles per microsecond, dynamic and static. A range dispatch over the 9-bit selector.
- LCBB: boundary 64 << M3 (M3 > 6 → S0C6 at lowering), R1 low word ← min(16, bytes to
  the boundary), CC 0 for 16 else 3.
- CKSM (R28): R2 even else S0C6; words at R2 for R2+1's 32-bit length, the tail padded
  with zeros; end-around carry into R1's low word; R2 advances (bit 32 cleared), R2+1 ← 0,
  CC 0. Use long_registers for the pair and `unit_reader` in a counted loop.
- MC: I2 bits 0-3 nonzero → S0C6; CR8 masks are 0, so nothing else. A data-field
  lowering (SI immediate) for EX. NIAI, PFD, PFDRL: nothing. TRAP2, TRAP4: DUCT trap bit
  off → special-operation exception, abend `S0D3` (interruption code 0013).

## Fixture moves

- `unknown_opcode.json` and the EX unlowered-target test move from SPM to PR (system set,
  never lowered).

## Tests

- Unit `test_miscellaneous_lowering.py`: PSW and mask reads and writes; access-register
  moves touch only the AR region; LAM's boundary check before any read; clock forms call
  their builtin; hints lower to nothing; TRAP abends S0D3; MC check; odd CKSM R2, M3 7 and
  STFLE boundary S0C6 before stores; ECAG's range dispatch; no SYMBOLIC. `test_machine.py`
  gains the AR region and `__hlasm_tod_last`. A clock-builtin test: the system clock's TOD
  for 1972-01-01 is the PoO's X'8126D60E46000000'.
- Integration `test_miscellaneous.py` with `miscellaneous_programs.py`: every mnemonic,
  registers, storage and CC, fixed clock values, wraps, boundary and spec abends; S0C8
  end to end: SPM with bit 20 on, then AR, AGR, LCR, LCGR, LPR, LPGR, MSC, MSRKC, MSGC,
  MSGRKC, SLA, SLAK, SLAG, SLDA, AHHHR, AIH, LAA, LAAG overflowing.
- z390 `test_miscellaneous_differential.py`: every case; pin z390's S0C1s (CKSM, EPSW,
  ECTG, MC, LCBB), its ECAG no-op, STFLE, STCK/STCKE CC, missing AR boundary checks.

## Commits

1. This plan.
2. Feature: machine state, clocks, unit module, docs (hlasm.md, notes-on-vm-design.md),
   tests, fixture moves.
3. Issue snapshot.
