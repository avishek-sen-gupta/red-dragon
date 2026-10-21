# HLASM Opcode Unit — Load and Store (red-dragon-6uyp.23)

**Goal:** lower the 71 load/store mnemonics of red-dragon-6uyp.23 (LR is seeded), and give the
z390 harness a register comparison every later unit uses.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation; LGG and LLGFSG with guarded storage not enabled.

## Harness: registers against z390

- `tests/integration/hlasm/hlasm_helpers.py`: `HlasmMachine(run, cc, gprs)` — the `HlasmRun`, the
  condition code, and the 64-bit GPRs; `restricted_to(registers)` keeps only the declared ones.
  `run_hlasm_machine(source)` reads all 16 GPRs from `__hlasm_gprs`. `HlasmRun` and `run_hlasm`
  are unchanged.
- `tests/z390/z390_runner.py`: `Z390Runner.run_machine` parses the abend dump: `R0-R3 …` lines
  (four 16-digit hex registers each) and the CC from `ABEND PSW=` (bits 18-19). Programs end in
  `ABEND n`, which both maclibs expand to `LA 1,n` / `SVC 13`. Only declared registers are
  compared, since the machines start with different register images.

## Machine support

- `HlasmEmitter.load_storage(address, width)` / `store_storage(address, width, value)`: flat-memory
  reads and writes, unsigned, stores wrap. `store_gr_high32` for LMD.
- `relative_address` moves from `opcodes/seed.py` to `effective_address.py`.
- `alignment_check.py`: `emit_alignment_check(address, boundary)` abends `S0C6` (specification).
  Sections are allocated in doubleword multiples so section bases stay doubleword aligned.
- `fixed_width_ir.build_signed_cc_ir(bits)`: CC 0 zero, 1 leftmost bit one, 2 otherwise.

## Mnemonic groups (`opcodes/load_store.py`, parts in `data_movement.py`)

A move is source → transforms → sink.

| Group | Mnemonics | Notes |
|---|---|---|
| Storage loads, 32-bit target | L LY LH LHY LB LLC LLH LZRF LRV | low word only (R1) |
| Storage loads, 64-bit target | LG LGF LGH LGB LLGC LLGH LLGF LLGT LZRG LLZRGF LRVG LGG LLGFSG | LGG doubleword, LLGFSG word aligned; both keep bits 33-63 (AMODE 31) |
| Partial inserts | IC ICY LRVH | IC: bits 56-63; LRVH: bits 48-63 |
| Register loads | LGR LBR LGBR LHR LGHR LGFR LLCR LLGCR LLHR LLGHR LLGFR LLGTR LRVR LRVGR | |
| Relative loads | LRL LGRL LGFRL LLGFRL LHRL LGHRL LLHRL LLGHRL | word/doubleword alignment → S0C6 |
| Stores | ST STY STG STH STHY STC STCY STRV STRVG STRVH | |
| Relative stores | STRL STGRL STHRL | |
| Multiples | LM LMY LMG STM STMY STMG LMD | R1..R3 wraps R15→R0; EA computed once |
| Masked | ICM ICMY STCM STCMY | ICM sets CC from inserted bits |

## Tests

- Unit `tests/unit/hlasm/test_load_store_lowering.py`: IR shape for L (LOAD_REGION 4 → low-word
  WRITE_REGION), LGRL (alignment branch + abend), ICM (CC store), STM (one WRITE_REGION per register);
  no SYMBOLIC.
- Integration `tests/integration/hlasm/test_load_store.py`, one test per family, table-driven:
  sign/zero extension with `X'80…'`/`X'7F…'` vectors and high word preserved for 32-bit targets;
  register forms; relative forms and misaligned LRL/LGRL/STRL/STGRL/LGG/LLGFSG → `S0C6`;
  stores (low bytes, high word ignored); reversals; LM/STM wrap 14→1 and LMG/STMG/LMD; ICM CC
  0/1/2 and mask 0; STCM.
- z390 `tests/z390/test_load_store_differential.py`: one program per family ending in `ABEND`,
  compared on declared registers and CC. LGG/LLGFSG/LZR*: expected values from the PoO.

## Commits

1. Plan.
2. Harness: `HlasmMachine`, `run_hlasm_machine`, `Z390Runner.run_machine`, a z390 test of it.
3. Load/store lowering, tests, `docs/frontend-design/hlasm.md`, bead note and snapshot.
