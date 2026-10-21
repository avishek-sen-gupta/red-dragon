# HLASM Frontend

> `interpreter/hlasm/hlasm_frontend.py` · Extends `Frontend` directly

## Overview

The HLASM frontend lowers an IBM High Level Assembler program to IR. Parsing and
assembly are the che4z language server's, through a forked bridge executable;
Python lowers what che4z has already resolved. The machine claims z17 problem
state and stays in AMODE 31. Lowered so far: SVC and the load and store, load
address and immediates, signed add and subtract, logical add and subtract, compare,
boolean, branch on condition, branch and link, and branch on count and index units (see
Opcode Units).
Any other opcode abends `S0C1` at run time.

## Architecture

```
HLASM source
  │
  ▼
hlasm_ast_bridge (che4z fork, C++ subprocess)
  │  assembles the source with its SYSLIB; writes the program as JSON
  │  exit 2 with diagnostics on any E/S diagnostic
  ▼
hlasm_asg (leaf package)
  │  HlasmBridgeParser — runs the bridge, reads JSON into HlasmProgram (Pydantic)
  ▼
HlasmFrontend
  │  start_up_ir(): GPR region, CC, program mask; one region per section with its
  │                 DC images; entry registers
  │  lower():       one IR function for the whole assembly, entered by dispatch
  ▼
compile_hlasm (interpreter/project/hlasm_compile.py)
     AST file → unit file → linked image, run with ProgramEntry(<entry name>)
```

che4z supplies symbol values, lengths, location counters and USING resolution.
Python computes only DC/DS byte images, section placement and runtime effective
addresses.

## Module Map

| Module | Purpose |
|---|---|
| `hlasm_asg/hlasm_bridge_parser.py` | `make_hlasm_parser(syslib)`, `HlasmBridgeParser`; exit 2 → `HlasmParseError`, other failures → `HlasmBridgeFailure` |
| `interpreter/frontends/__init__.py` | `get_hlasm_parser(syslib)`: the bridge parser with `hlasm-bridge/maclib/` first on SYSLIB |
| `hlasm-bridge/maclib/` | Our macros: `WTO`, `ABEND` |
| `hlasm_asg/program/` | The bridge JSON models, one class per file |
| `interpreter/hlasm/hlasm_frontend.py` | `HlasmFrontend(program)`: `lower()`, `start_up_ir()`, `entry_name`, `entry_label` |
| `interpreter/hlasm/machine.py` | GPR region (`__hlasm_gprs`, 8 bytes per register), `__hlasm_cc`, `__hlasm_pm` |
| `interpreter/hlasm/storage_layout.py` | One region per section (`__hlasm_sect_<NAME>`) and its DC images; DC registers carry a per-piece index. Section bases are doubleword aligned: regions are allocated in order from address 4096, the 128-byte GPR region first, and each section is sized up to a doubleword multiple |
| `interpreter/hlasm/dc_encoding.py` | DC images: C, X, B, F, H, P, Z, A, Y |
| `interpreter/hlasm/entry_state.py` | Entry resolution and entry registers (R14 = `0xFF0` return sentinel, R13 = 72-byte save area, R15 = entry address) |
| `interpreter/hlasm/branch_dispatch.py` | `hl_dispatch`: maps a branch address to a statement label; a miss abends `S0C1` |
| `interpreter/hlasm/operands.py` | `reg_operand`, `mask_operand`, `imm_operand`, `storage_operand`, `reloc_operand`, `storage_length_operand`, `vec_reg_operand`: typed operand access; a mismatch raises `HlasmLoweringError` |
| `interpreter/hlasm/hlasm_lowering_error.py` | `HlasmLoweringError`: names the statement (mnemonic, section, offset, operand) and what was found |
| `interpreter/hlasm/opcodes/svc.py` | SVC, by number |
| `interpreter/hlasm/opcodes/load_store.py` | The load and store unit |
| `interpreter/hlasm/opcodes/load_address_immediate.py` | The load address and immediates unit |
| `interpreter/hlasm/opcodes/signed_add_subtract.py` | The signed add and subtract unit |
| `interpreter/hlasm/opcodes/logical_add_subtract.py` | The logical add and subtract unit |
| `interpreter/hlasm/opcodes/compare.py` | The compare unit, signed and logical |
| `interpreter/hlasm/opcodes/boolean.py` | The boolean unit: AND, OR, exclusive OR and the complemented connectives |
| `interpreter/hlasm/opcodes/branch_on_condition.py` | The branch on condition unit |
| `interpreter/hlasm/opcodes/branch_and_link.py` | The branch and link unit and the addressing-mode instructions |
| `interpreter/hlasm/opcodes/loop_branch.py` | The branch on count and branch on index unit |
| `interpreter/hlasm/opcodes/operand_sources.py` | Named second-operand sources shared by the arithmetic and compare units |
| `interpreter/hlasm/opcodes/result_and_cc.py` | Splices a (result, CC) builder over register, storage or immediate operands and stores both; its storage-immediate read-modify-write |
| `interpreter/hlasm/data_movement.py` | `move(source, transforms, sink)`: storage, relative-long, address, immediate and register sources and sinks, addressed by operand index; sign extension, `MOD 2^n` wrap, masks, shifts, byte reversal, bit fields (`field_of`, `into_field`); the storage-immediate read-modify-write |
| `interpreter/hlasm/effective_address.py` | `effective_address` (D(X,B), AMODE 31), `length_operand_address` (D(L,B)), `indexed_address` (index scaled by the element size), `relative_address` (RELOC_IMM) |
| `interpreter/hlasm/alignment_check.py` | An operand off its boundary abends `S0C6` |
| `interpreter/hlasm/fixed_point_overflow.py` | CC 3 with program-mask bit `1000` on abends `S0C8` |
| `interpreter/hlasm/write_to_operator.py` | SVC 35 in IR |
| `interpreter/hlasm/byte_loop.py` | An IR loop over the byte offsets of a compile-time length, the offset in `__hlasm_ss_at` |
| `interpreter/hlasm/boolean_connective.py` | A bitwise connective: the binop and whether the right operand or the result is complemented; the eight connectives |
| `interpreter/hlasm/abend_completion.py` | SVC 13 in IR |
| `interpreter/hlasm/statement_location.py` | Each statement's source line, set on the IR it lowers to |
| `interpreter/hlasm/fixed_width_ir.py` | Fixed-width signed add/subtract and logical add/subtract with carry-in, bitwise connectives, each with its condition code, and the sign CC (0 zero, 1 leftmost bit one, 2 other), built in IR |
| `interpreter/hlasm/inline_ir.py` | Splices a builder's IR under fresh registers; `inline_result_and_cc` splits its (result, CC) pair |
| `interpreter/hlasm/abend.py` | Stores the code in `__hlasm_abend`, then `Halt_` |

## Compilation Units

One assembly is one unit. `compile_hlasm(source, *, parser, work_dir)` writes
three files to the work directory, each skipped when it already exists:

| File | Holds |
|---|---|
| `__main__-<digest>.ast.json` | The bridge's program JSON |
| `__main__-<digest>.unit.json` | The lowered `ModuleUnit`; `program` is the entry name |
| `image-<digest>.linked.json` | The image: start-up module, then the unit |

`<digest>` covers the source bytes and the SYSLIB directories
(`HlasmLoweringSettings`), so a different SYSLIB gets new files. `lower_hlasm_program`
stops after the unit file.

The entry is the symbol `END` names, or the first CSECT at offset 0 when `END`
names none. The entry function is `func_<entry>_0`. It returns GR15's low word
when control branches to the return sentinel.

## Supervisor Calls and Our Maclib

`get_hlasm_parser` puts `hlasm-bridge/maclib/` ahead of any caller's SYSLIB.
`run()` and the tests assemble through it; `run(copybook_dirs=...)` supplies the
caller's SYSLIB directories, searched after ours. The macros follow the z/OS operand
conventions but expand only to lowered opcodes:

| Macro | Expansion |
|---|---|
| `WTO 'text'` | `BRAS 1` around an inline list (AL2 length including the 4-byte header, AL2 MCS flags, the text), then `SVC 35` |
| `ABEND code` | `LA 1,code` (user code, bits 20-31), then `SVC 13` |
| `ABEND code,,,SYSTEM` | `LA 1,code`, twelve `LA 1,0(1,1)` doublings into bits 8-19, then `SVC 13`. `DUMP` and `STEP` are accepted and ignored. |

SVCs are lowered in IR over existing builtins; no SVC has a builtin of its own.

- **SVC 35** reads the text length from the list at R1, copies the text a byte at a
  time, decodes it from EBCDIC and writes it as one line with `println`.
- **SVC 13** records `S` and three hex digits when bits 8-19 of R1 are non-zero,
  otherwise `U` and four decimal digits, in `__hlasm_abend`, then halts.
- **Any other SVC number** logs the number and abends `S0C1`. This is a project
  choice, not z/OS behaviour.

WTO costs about 15 VM steps per character, so `run()` needs `max_steps` well
above its default of 100.

Every IR instruction a statement lowers to carries that statement's line as its
source location. A macro-generated statement carries the line of the macro call
in the open-code source. Columns are 0: the bridge reports lines only.

## Differential Tests Against z390

`tests/z390/` runs each program in RedDragon and in z390 and compares the return
code, the abend code and the WTO lines. Under z390 the program assembles against
z390's own macro library. The tests carry the `z390` marker, which the default run
excludes. Build z390 (`javac` the sources into `z390.jar`, as its `bash/bldjar`
does), then:

```bash
Z390_HOME=/path/to/z390 uv run pytest -m z390 tests/z390 -n0
```

`Z390_HOME` unset fails the tests rather than skipping them. `Z390Runner` runs
`bash/asmlg` and reads the program's `.LOG`. The return code comes from the
`EZ390 ENDED RC=` line, or is 0 after an abend. The abend code comes from
`program aborting due to abend`. The WTO lines are the run's lines minus z390's
`EZ390` messages and register dumps.

Registers and the CC are compared through `HlasmMachine`: `run_hlasm_machine` reads
all 16 GPRs (64-bit) and `__hlasm_cc`; `Z390Runner.run_machine` reads them from the
dump z390 prints on an abend, the CC from the `ABEND PSW` (short, or 16 digits in AMODE 64). So a register test ends
in `ABEND n`, which both maclibs expand to `LA 1,n` and `SVC 13`. Compare only the
registers the test declares (`restricted_to`): z390 starts the high words at
`F4F4F4F4` and R0, R1, R13, R14 and R15 at its own values. A declared register that a
32-bit instruction writes needs its high word set first, by `LG` or `LMG`.
A run that leaves no `.LOG` raises `Z390AssemblyFailed` with asmlg's exit code
and the `.ERR` text. The machine starts with program mask `0110` (decimal overflow
and HFP exponent underflow on), as z390's initial PSW `07850600` does.

## Opcode Units

Storage is the VM's flat byte memory: `HlasmEmitter.load_storage` and
`store_storage` read and write a compile-time width at an address. A 32-bit
result writes only the GPR's low word.

**Load and store (red-dragon-6uyp.23).** L, LY, LG, LGF, LH, LHY, LGH, LB, LGB,
LLC, LLGC, LLH, LLGH, LLGF, LLGT, LZRF, LZRG, LLZRGF, LRV, LRVG, LRVH, IC, ICY,
LGG, LLGFSG; the register forms LR, LGR, LBR, LGBR, LHR, LGHR, LGFR, LLCR, LLGCR,
LLHR, LLGHR, LLGFR, LLGTR, LRVR, LRVGR; relative-long LRL, LGRL, LGFRL, LLGFRL,
LHRL, LGHRL, LLHRL, LLGHRL, STRL, STGRL, STHRL; ST, STY, STG, STH, STHY, STC,
STCY, STRV, STRVG, STRVH; LM, LMY, LMG, STM, STMY, STMG, LMD (R1 to R3 wraps from
R15 to R0); ICM, ICMY (CC from the inserted bits), STCM, STCMY.

- Guarded storage is never enabled, so LGG and LLGFSG never raise a guarded-storage
  event. In AMODE 31 they keep bits 33-63 of the loaded value; LLGFSG's shift is 0.
- Word and doubleword relative-long operands, LGG and LLGFSG check alignment and
  abend `S0C6`. z390 does not check relative-long alignment; the z390 test pins
  that difference.
- z390 refuses a relative-long operand in another CSECT, so the z390 tests keep
  relative operands in the same section; the VM tests cross sections.

**Load address and immediates (red-dragon-6uyp.24).** LA, LAY, LAE, LAEY, LARL;
LXAB, LXAH, LXAF, LXAG, LXAQ, LLXAB, LLXAH, LLXAF, LLXAG, LLXAQ; LHI, LGHI, LGFI;
LLIHF, LLIHH, LLIHL, LLILF (LLGFI), LLILH, LLILL (LLGHI); IIHF, IIHH, IIHL, IILF
(LFI), IILH, IILL. None changes the CC.

- Addresses go into bits 33-63 with bit 32 zero; the high word is kept.
- LXA* and LLXA*: (low word of X2 + DX2) shifted left 0-4, plus B2. In AMODE 31
  only bits 33-63 are kept, and they depend only on the low 31 bits of each term,
  so the signed and logical forms agree. che4z types their R1 as a mask operand.
  z390 does not execute them (`S0C1`); their tests use values from the Principles
  of Operation.
- The bridge hands an immediate signed or unsigned (`LLILF X'FFFFFFFF'` arrives as
  -1), so each lowering takes its field-width bit image first.
- z390 raises `S0C5` for LAE and LAEY at an address beyond its storage; the
  Principles of Operation make no storage reference. The z390 test pins that difference.

**Signed add and subtract (red-dragon-6uyp.25).** A, AY, AR, ARK, AH, AHY, AHI,
AFI, AHIK, ASI, AG, AGR, AGRK, AGF, AGFR, AGH, AGHI, AGFI, AGHIK, AGSI; S, SY, SR,
SRK, SH, SHY, SG, SGR, SGRK, SGF, SGFR, SGH. CC 0 zero, 1 negative, 2 positive,
3 overflow.

- Overflow keeps the wrapped result and sets CC 3. When program-mask bit `1000`
  (fixed-point overflow) is on, the run then abends `S0C8`. The initial mask has it
  off.
- AGF, AGFR, SGF, SGFR sign-extend a 32-bit second operand; AH, AHY, AGH, SH, SHY,
  SGH a halfword; AHI, AGHI, AHIK, AGHIK a 16-bit immediate; ASI, AGSI an 8-bit one.
- ASI and AGSI read, add and write back the storage operand.
- SR moved here from the seed module and gained the `S0C8` check.

**Logical add and subtract (red-dragon-6uyp.26).** AL, ALY, ALR, ALRK, ALFI, ALHSIK,
ALSI, ALG, ALGR, ALGRK, ALGF, ALGFR, ALGFI, ALGHSIK, ALGSI, ALC, ALCR, ALCG, ALCGR; SL,
SLY, SLR, SLRK, SLFI, SLG, SLGR, SLGRK, SLGF, SLGFR, SLGFI, SLB, SLBR, SLBG, SLBGR.
CC = 2 × carry + (result ≠ 0). No overflow interruption.

- Subtraction is first + ones' complement of second + carry-in: 1 for SL forms, CC bit 2
  (CC 2 or 3) for SLB forms. A borrow is no carry, so SL sets CC 1, 2 or 3; SLB can set
  CC 0. ALC forms add CC bit 2.
- ALGF, ALGFR, ALGFI, SLGF, SLGFR, SLGFI zero-extend a 32-bit second operand.
- ALHSIK, ALGHSIK (16-bit) and ALSI, ALGSI (8-bit) sign-extend the immediate and add it
  unsigned. For a negative immediate that is SUBTRACT LOGICAL of its magnitude, the CC the
  Principles of Operation prescribe.
- z390 sets a different CC for ALGRK and SLGRK (its CC helper reads stale operands) and
  for the signed-immediate forms (it reports a borrow as a carry). The z390 test pins
  each difference.

**Compare (red-dragon-6uyp.28).** Signed C, CY, CR, CFI, CRL, CH, CHY, CHI, CHRL, CHSI,
CHHSI, CG, CGR, CGRL, CGF, CGFR, CGFI, CGFRL, CGH, CGHI, CGHRL, CGHSI; logical CL, CLY,
CLR, CLFI, CLRL, CLHRL, CLFHSI, CLHHSI, CLI, CLIY, CLG, CLGR, CLGRL, CLGF, CLGFR, CLGFI,
CLGFRL, CLGHRL, CLGHSI, CLM, CLMY. CC 0 equal, 1 first operand low, 2 high; nothing is
stored.

- The CC is the sign of first − second, each taken signed or unsigned at the compare width.
- Signed forms sign-extend a shorter second operand; logical forms zero-extend it. CHHSI and
  CLHHSI compare 16 bits, CLI and CLIY 8.
- CLM and CLMY compare the low-word bytes the mask selects with that many storage bytes.
  Mask 0 sets CC 0 and reads no storage.
- Word and doubleword relative-long operands check alignment and abend `S0C6`; z390 does
  not, and the z390 test pins that difference.

**Boolean (red-dragon-6uyp.30).** N, NY, NR, NRK, NG, NGR, NGRK, NI, NIY, NC, NIHF, NIHH,
NIHL, NILF, NILH, NILL; O, OY, OR, ORK, OG, OGR, OGRK, OI, OIY, OC, OIHF, OIHH, OIHL, OILF,
OILH, OILL; X, XY, XR, XRK, XG, XGR, XGRK, XI, XIY, XC, XIHF, XILF; NCRK, NCGRK (AND with
complement), OCRK, OCGRK (OR with complement), NNRK, NNGRK (NAND), NORK (NOTR), NOGRK
(NOTGR) (NOR), NXRK, NXGRK (NOT exclusive OR). CC 0 result zero, 1 nonzero.

- The register-immediate forms combine I2 with one field of R1 (NIHH bits 0-15 ... NILF
  32-63) and replace only that field. The CC reflects that field alone.
- NC, OC and XC run one IR loop over the L bytes, left to right, storing each result byte
  before the next is fetched, so overlapping operands follow the Principles of Operation
  (`XC A,A` clears; `OC A+1(n),A` propagates the first byte). The loop is not unrolled.
- z390 leaves the CC unchanged for NIHF, NILF, OIHF, OILF, XIHF and XILF, sets it from the
  whole 32-bit word for the halfword forms, sign-extends the byte in XI (a zero result with
  both bytes over `X'7F'` sets CC 1), and runs OC in 8-, 4-, 2- and 1-byte pieces, so overlap
  differs. The z390 test pins each difference.

**Branch on condition (red-dragon-6uyp.32).** BC, BCR, BIC, BRC, BRCL, BPP, BPRP. The
bridge hands every extended mnemonic (B, BE, BNER, BIL, J, JLNOP, BRUL, ...) over as its
base mnemonic with the mask filled in. The branch is taken when mask bit `8 >> CC` is one;
the CC is unchanged.

- Mask 0 lowers to nothing; mask 15 branches without testing the CC.
- BC branches to the D2(X2,B2) address, BCR to R2, BRC and BRCL to the relative target.
  BCR with R2 = 0 does not branch, so BCR 15,0 and BCR 14,0 (serialization) are no-ops.
- BIC branches to the doubleword stored at D2(X2,B2), read only when the branch is taken.
  AMODE 31 keeps its bits 33-63.
- BPP and BPRP are hints with no architected effect and lower to nothing.
- Every target, relative ones included, goes through `hl_dispatch`; a target that is not a
  machine statement abends `S0C1`. Branching straight to a static relative target's label
  is deferred as a performance item (red-dragon-6uyp.62).
- z390 branches BIC to the operand address instead of the doubleword stored there, and
  abends `S0C1` on BPP and BPRP. A branch into data runs the data bytes in z390 (J, BC
  and BRCL to FILL end `S0C2`); here it abends `S0C1`. The z390 test pins all three.

**Branch and link (red-dragon-6uyp.33).** BAL, BALR, BAS, BASR, BRAS (JAS), BRASL (JASL),
BASSM, BSM, SAM24, SAM31, SAM64, TAM. None changes the CC except TAM.

- The machine is fixed in AMODE 31. The link word is bit 32 one and the updated
  instruction address, in R1's low word; the high word is kept. BAL and BALR use this
  format too: their ILC, CC and program-mask format is AMODE 24 only.
- The branch address is read before R1 is written. BALR, BASR and BASSM with R2 = 0
  link without branching.
- BSM sets bit 32 of R1 (when R1 is not 0), then branches to R2 (when R2 is not 0).
- BASSM and BSM branch only into AMODE 31: R2 bit 32 one and bit 63 zero. A target
  selecting AMODE 24 or 64 abends `S0C1` after R1 is written; SAM24 and SAM64 abend
  `S0C1` too (red-dragon-6uyp.75). SAM31 does nothing. TAM sets CC 1.
- The entry R14 (`0xFF0`) has bit 32 off, as in z390, so `BSM 0,14` selects AMODE 24.
  A BASSM or BSM whose target is the return address returns before the mode test:
  nothing runs after it.
- BASR, BALR and BRAS moved here from the seed module; LR moved to load and store.
- z390 models AMODE 24 and 64; its test pins that difference.

**Branch on count and branch on index (red-dragon-6uyp.34).** BCT, BCTR, BCTG, BCTGR,
BRCT (JCT), BRCTG (JCTG); BXH, BXHG, BXLE, BXLEG, BRXH (JXH), BRXHG (JXHG), BRXLE (JXLE),
BRXLG (JXLEG). None changes the CC. BRCTH belongs to the high-word unit.

- The branch address is generated first, then R1 is replaced, wrapped to 32 bits (low word
  only) or 64.
- Count forms subtract one and branch when the result is nonzero. BCTR and BCTGR with R2 = 0
  count without branching.
- Index forms add the increment (R3) and compare the sum, signed, with the compare value
  (R3 + 1 when R3 is even, else R3): BXH forms branch when high, BXLE forms when low or equal.
  Both are read before R1 is written, so R1 = R3 + 1 compares the original value.
- z390 reads BCTR's and BCTGR's R2, and every index form's compare value, after writing R1.
  The z390 test pins BCTR 5,5, BXH 7,6 and BXHG 7,6.

## Known Gaps

- Only SVC and the load and store, load address and immediates, signed add and subtract, logical add and subtract, compare, boolean, branch on condition, branch and link, and branch on count and index units are lowered; the rest are tracked as opcode-unit beads under red-dragon-6uyp.
- DC types beyond C, X, B, F, H, P, Z, A, Y and V, and any type extension, raise `UnsupportedDataType` (red-dragon-6uyp.63; floating point E, D, L: red-dragon-6uyp.21).
- Falling through into DC/DS data or past a CSECT's end skips the data instead of executing it, and a branch into data abends `S0C1` (red-dragon-6uyp.64).
- Emission is O(n²) in the number of IR instructions, and every branch, even to a static relative target, walks the dispatch chain (red-dragon-6uyp.62).
- Logical shifts are to be built in IR, not on the VM's `>>>`, which is not width-aware (red-dragon-srvz).
- `EXTRN`, `ENTRY` and V-type constants are not resolved; V-constants hold zero (red-dragon-6uyp.8, red-dragon-6uyp.15).
- Machine-instruction bytes are not in section storage (a spec non-goal: self-modifying code), so `EX` targets and `CLC` against code do not see them.
- Bridge gaps: `*` in a later DC operand takes the statement address (red-dragon-6uyp.65); bit-length data reports byte length (red-dragon-6uyp.66); S-type constants are not USING-resolved (red-dragon-6uyp.67); complex-relocatable constants refuse the assembly (red-dragon-6uyp.68).
- AMODE 24 and 64 are not modelled: SAM24, SAM64 and BASSM or BSM into those modes
  abend `S0C1` (red-dragon-6uyp.75). A BASSM or BSM to the return address returns
  whatever mode it selects.
- Access registers are not modelled: LAE and LAEY set only the general register.
- In AMODE 31, LM, STM, LMD, NC, OC and XC do not wrap EA + offset at 2 GiB.
- NC, OC and XC take the length as written; an explicit length of 0, which HLASM assembles as one byte, is not handled.
- ICM and CLM with mask 0 raise no access exception for their operand.
- Section bases are doubleword aligned only by allocation order. The VM's bump allocator
  starts at 4096 and does not align, so the GPR region (128 bytes) comes first and each
  section is sized up to a doubleword multiple. Addresses differ from z390's load point.
- Nothing sets the program mask until SPM lands (red-dragon-6uyp.45), so `S0C8` is tested only on the VM with the mask set directly, not end to end.
- `ABEND` takes only a self-defining code of 0-4095. Register notation (`ABEND (R2)`) and larger codes are not supported.

## Test Coverage

| Test file | Covers |
|---|---|
| `tests/unit/hlasm/test_program_model.py` | Bridge JSON models |
| `tests/unit/hlasm/test_bridge_exit_codes.py` | Parser exit-code handling |
| `tests/unit/hlasm/test_operands.py` | Typed operand access and its failures |
| `tests/unit/hlasm/test_machine.py` | Machine start-up state |
| `tests/unit/hlasm/test_dc_encoding.py` | DC images |
| `tests/unit/hlasm/test_fixed_width_ir.py` | Fixed-width arithmetic, bitwise connectives and condition codes |
| `tests/unit/hlasm/test_lowering_skeleton.py` | Labels, LR, BASR, BALR, BRAS and BCR, dispatch, abends |
| `tests/unit/hlasm/test_load_store_lowering.py` | Load and store IR: GPR and storage accesses, alignment branch, CC, no SYMBOLIC |
| `tests/integration/hlasm/test_load_store.py` | Every load and store mnemonic on the VM: registers, run status and CC; alignment abends |
| `tests/unit/hlasm/test_load_address_immediate_lowering.py` | Load address and immediate IR: GPR widths read and written, index sum shifted before the base is added, no CC |
| `tests/integration/hlasm/test_load_address_immediate.py` | Every load address and immediate mnemonic on the VM, CC unchanged |
| `tests/unit/hlasm/test_signed_add_subtract_lowering.py` | Signed add and subtract IR: operand widths, CC, the `S0C8` trap and its program-mask condition |
| `tests/integration/hlasm/test_signed_add_subtract.py` | Every signed add and subtract mnemonic on the VM: result, CC 0-3 |
| `tests/unit/hlasm/test_logical_add_subtract_lowering.py` | Logical add and subtract IR: operand widths, carry-in read, CC, no trap |
| `tests/integration/hlasm/test_logical_add_subtract.py` | Every logical add and subtract mnemonic on the VM: result, CC with carry and borrow |
| `tests/unit/hlasm/test_compare_lowering.py` | Compare IR: operand widths read, nothing written, only the CC set, relative-long alignment |
| `tests/integration/hlasm/test_compare.py` | Every compare mnemonic on the VM: CC, operands unchanged, alignment abends |
| `tests/unit/hlasm/test_boolean_lowering.py` | Boolean IR: operand widths, the field read and replaced, the CC; NC/OC/XC as one byte loop of fixed size |
| `tests/integration/hlasm/test_boolean.py` | Every boolean mnemonic, NOTR and NOTGR on the VM: result, CC 0 and 1, field CCs, overlapping storage operands |
| `tests/unit/hlasm/test_branch_on_condition_lowering.py` | Branch on condition IR: the CC mask test, each form's target, the forms that lower to nothing |
| `tests/integration/hlasm/test_branch_extended_mnemonics.py` | Every branch on condition extended spelling reaches its base mnemonic and mask through the bridge; JCT, JCTG, the JX spellings, JAS and JASL reach theirs with R1 |
| `tests/integration/hlasm/test_branch_on_condition.py` | Every branch on condition mnemonic and a spread of extended mnemonics on the VM: path taken, CC unchanged, branches into data abend `S0C1` |
| `tests/unit/hlasm/test_branch_and_link_lowering.py` | Branch and link IR: target read before the link is written, the AMODE 31 link word, the BASSM and BSM mode test, SAM and TAM |
| `tests/integration/hlasm/test_branch_and_link.py` | Every branch and link mnemonic, JAS and JASL on the VM: link relative to the next instruction, path, CC; BSM 0,14 and BASSM 14,14 return to the caller; SAM24, SAM64 and switches into AMODE 24 or 64 abend `S0C1`, entering those modes xfailed (red-dragon-6uyp.75) |
| `tests/unit/hlasm/test_loop_branch_lowering.py` | Branch on count and index IR: target first, operands read before R1 is written, wrap, nonzero or signed test |
| `tests/integration/hlasm/test_loop_branch.py` | Every branch on count and index mnemonic, JCT, JCTG and the JX spellings on the VM: counting loops, register overlaps, signed wrap, CC unchanged |
| `tests/integration/hlasm/test_bridge_parser.py` | The real bridge: macro origins, refused assemblies |
| `tests/integration/hlasm/test_storage_layout.py` | Section regions and address constants |
| `tests/integration/hlasm/test_svc.py` | `WTO`, `ABEND` user and system codes, unlowered SVCs, `run()` with our maclib then `copybook_dirs`, call-site spans |
| `tests/integration/hlasm/test_hlasm_compile.py` | Unit files, reuse, SYSLIB invalidation, `run()`, return code, default entry, BALR/BR, wild branch |
| `tests/integration/hlasm/test_instruction_table.py`, `test_opcode_unit_coverage.py` | Instruction table and opcode-unit coverage |
| `tests/z390/test_foundation_differential.py` | Return code, WTO, user abend and assembly failure against z390 (`-m z390`) |
| `tests/z390/test_z390_log.py` | Registers and CC from a z390 abend dump (default run) |
| `tests/z390/test_load_store_differential.py` | Load and store families, ICM CC, and the alignment difference against z390 (`-m z390`) |
| `tests/z390/test_load_address_immediate_differential.py` | Address and immediate families against z390; the LAE `S0C5` and LXA `S0C1` differences (`-m z390`) |
| `tests/z390/test_signed_add_subtract_differential.py` | Every signed add and subtract mnemonic against z390 (`-m z390`) |
| `tests/z390/test_logical_add_subtract_differential.py` | Every logical add and subtract mnemonic against z390; six z390 CC differences pinned (`-m z390`) |
| `tests/z390/test_boolean_differential.py` | Every boolean mnemonic, NOTR and NOTGR against z390; nine z390 differences (field CCs, XI, OC overlap) pinned (`-m z390`) |
| `tests/z390/test_compare_differential.py` | Every compare mnemonic against z390; the relative-long alignment difference pinned (`-m z390`) |
| `tests/z390/test_branch_on_condition_differential.py` | Every branch on condition case against z390; the BIC, BPP and BPRP differences and branches into data pinned (`-m z390`) |
| `tests/z390/test_branch_and_link_differential.py` | Every branch and link case and the mode-setting returns against z390; z390's AMODE 24 and 64 switches pinned (`-m z390`) |
| `tests/z390/test_loop_branch_differential.py` | Every branch on count and index case against z390; z390's late reads of R2 and the compare value pinned (`-m z390`) |
