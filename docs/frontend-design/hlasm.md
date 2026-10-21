# HLASM Frontend

> `interpreter/hlasm/hlasm_frontend.py` · Extends `Frontend` directly

## Overview

The HLASM frontend lowers an IBM High Level Assembler program to IR. Parsing and
assembly are the che4z language server's, through a forked bridge executable;
Python lowers what che4z has already resolved. The machine claims z17 problem
state in AMODE 31. Only the seed opcodes are lowered so far: LA, LR, SR, BCR,
BASR, BALR, BRAS and SVC. Any other opcode abends `S0C1` at run time.

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
| `interpreter/hlasm/storage_layout.py` | One region per section (`__hlasm_sect_<NAME>`) and its DC images; DC registers carry a per-piece index |
| `interpreter/hlasm/dc_encoding.py` | DC images: C, X, B, F, H, P, Z, A, Y |
| `interpreter/hlasm/entry_state.py` | Entry resolution and entry registers (R14 = `0xFF0` return sentinel, R13 = 72-byte save area, R15 = entry address) |
| `interpreter/hlasm/branch_dispatch.py` | `hl_dispatch`: maps a branch address to a statement label; a miss abends `S0C1` |
| `interpreter/hlasm/operands.py` | `reg_operand`, `mask_operand`, `imm_operand`, `storage_operand`, `reloc_operand`: typed operand access; a mismatch raises `HlasmLoweringError` |
| `interpreter/hlasm/hlasm_lowering_error.py` | `HlasmLoweringError`: names the statement (mnemonic, section, offset, operand) and what was found |
| `interpreter/hlasm/opcodes/seed.py` | The seed opcode lowerings |
| `interpreter/hlasm/opcodes/svc.py` | SVC, by number |
| `interpreter/hlasm/write_to_operator.py` | SVC 35 in IR |
| `interpreter/hlasm/abend_completion.py` | SVC 13 in IR |
| `interpreter/hlasm/statement_location.py` | Each statement's source line, set on the IR it lowers to |
| `interpreter/hlasm/fixed_width_ir.py` | 32-bit signed add/subtract with condition code, built in IR |
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
`EZ390` messages and register dumps. Registers are not compared: z390 starts the
high words at `F4F4F4F4` and R1, R13 and R14 at its own addresses.
A run that leaves no `.LOG` raises `Z390AssemblyFailed` with asmlg's exit code
and the `.ERR` text. The machine starts with program mask `0110` (decimal overflow
and HFP exponent underflow on), as z390's initial PSW `07850600` does.

## Known Gaps

- Only the seed opcodes are lowered; the rest are tracked as opcode-unit beads under red-dragon-6uyp.
- DC types beyond C, X, B, F, H, P, Z, A, Y and V, and any type extension, raise `UnsupportedDataType` (red-dragon-6uyp.63; floating point E, D, L: red-dragon-6uyp.21).
- Falling through into DC/DS data or past a CSECT's end skips the data instead of executing it (red-dragon-6uyp.64).
- Emission is O(n²) in the number of IR instructions (red-dragon-6uyp.62).
- Logical shifts are to be built in IR, not on the VM's `>>>`, which is not width-aware (red-dragon-srvz).
- `EXTRN`, `ENTRY` and V-type constants are not resolved; V-constants hold zero (red-dragon-6uyp.8, red-dragon-6uyp.15).
- Machine-instruction bytes are not in section storage (a spec non-goal: self-modifying code), so `EX` targets and `CLC` against code do not see them.
- Bridge gaps: `*` in a later DC operand takes the statement address (red-dragon-6uyp.65); bit-length data reports byte length (red-dragon-6uyp.66); S-type constants are not USING-resolved (red-dragon-6uyp.67); complex-relocatable constants refuse the assembly (red-dragon-6uyp.68).
- `ABEND` takes only a self-defining code of 0-4095. Register notation (`ABEND (R2)`) and larger codes are not supported.

## Test Coverage

| Test file | Covers |
|---|---|
| `tests/unit/hlasm/test_program_model.py` | Bridge JSON models |
| `tests/unit/hlasm/test_bridge_exit_codes.py` | Parser exit-code handling |
| `tests/unit/hlasm/test_operands.py` | Typed operand access and its failures |
| `tests/unit/hlasm/test_machine.py` | Machine start-up state |
| `tests/unit/hlasm/test_dc_encoding.py` | DC images |
| `tests/unit/hlasm/test_fixed_width_ir.py` | Fixed-width arithmetic and condition codes |
| `tests/unit/hlasm/test_lowering_skeleton.py` | Labels, seed opcodes, dispatch, abends |
| `tests/integration/hlasm/test_bridge_parser.py` | The real bridge: macro origins, refused assemblies |
| `tests/integration/hlasm/test_storage_layout.py` | Section regions and address constants |
| `tests/integration/hlasm/test_svc.py` | `WTO`, `ABEND` user and system codes, unlowered SVCs, `run()` with our maclib then `copybook_dirs`, call-site spans |
| `tests/integration/hlasm/test_hlasm_compile.py` | Unit files, reuse, SYSLIB invalidation, `run()`, return code, default entry, BALR/BR, wild branch |
| `tests/integration/hlasm/test_instruction_table.py`, `test_opcode_unit_coverage.py` | Instruction table and opcode-unit coverage |
| `tests/z390/test_foundation_differential.py` | Return code, WTO, user abend and assembly failure against z390 (`-m z390`) |
