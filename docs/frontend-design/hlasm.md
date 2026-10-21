# HLASM Frontend

> `interpreter/hlasm/hlasm_frontend.py` · Extends `Frontend` directly

## Overview

The HLASM frontend lowers an IBM High Level Assembler program to IR. Parsing and
assembly are the che4z language server's, through a forked bridge executable;
Python lowers what che4z has already resolved. The machine claims z17 problem
state in AMODE 31. Only the seed opcodes are lowered so far: LA, LR, SR, BCR,
BASR and BALR. Any other opcode abends `S0C1` at run time.

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
| `hlasm_asg/program/` | The bridge JSON models, one class per file |
| `interpreter/hlasm/hlasm_frontend.py` | `HlasmFrontend(program)`: `lower()`, `start_up_ir()`, `entry_name`, `entry_label` |
| `interpreter/hlasm/machine.py` | GPR region (`__hlasm_gprs`, 8 bytes per register), `__hlasm_cc`, `__hlasm_pm` |
| `interpreter/hlasm/storage_layout.py` | One region per section (`__hlasm_sect_<NAME>`) and its DC images |
| `interpreter/hlasm/dc_encoding.py` | DC images: C, X, B, F, H, P, Z, A, Y |
| `interpreter/hlasm/entry_state.py` | Entry resolution and entry registers (R14 = `0xFF0` return sentinel, R13 = 72-byte save area, R15 = entry address) |
| `interpreter/hlasm/branch_dispatch.py` | `hl_dispatch`: maps a branch address to a statement label; a miss abends `S0C1` |
| `interpreter/hlasm/opcodes/seed.py` | The seed opcode lowerings |
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

## Known Gaps

- Only the seed opcodes are lowered; the rest are tracked as opcode-unit beads under red-dragon-6uyp.
- DC types beyond C, X, B, F, H, P, Z, A, Y and V, and any type extension, raise `UnsupportedDataType` (red-dragon-6uyp.63; floating point E, D, L: red-dragon-6uyp.21).
- Falling through into DC/DS data or past a CSECT's end skips the data instead of executing it (red-dragon-6uyp.64).
- Emission is O(n²) in the number of IR instructions (red-dragon-6uyp.62).
- Logical shifts are to be built in IR, not on the VM's `>>>`, which is not width-aware (red-dragon-srvz).
- `EXTRN`, `ENTRY` and V-type constants are not resolved; V-constants hold zero (red-dragon-6uyp.8, red-dragon-6uyp.15).
- `run()` passes no SYSLIB to the parser.

## Test Coverage

| Test file | Covers |
|---|---|
| `tests/unit/hlasm/test_program_model.py` | Bridge JSON models |
| `tests/unit/hlasm/test_bridge_exit_codes.py` | Parser exit-code handling |
| `tests/unit/hlasm/test_machine.py` | Machine start-up state |
| `tests/unit/hlasm/test_dc_encoding.py` | DC images |
| `tests/unit/hlasm/test_fixed_width_ir.py` | Fixed-width arithmetic and condition codes |
| `tests/unit/hlasm/test_lowering_skeleton.py` | Labels, seed opcodes, dispatch, abends |
| `tests/integration/hlasm/test_bridge_parser.py` | The real bridge: macro origins, refused assemblies |
| `tests/integration/hlasm/test_storage_layout.py` | Section regions and address constants |
| `tests/integration/hlasm/test_hlasm_compile.py` | Unit files, reuse, SYSLIB invalidation, `run()`, return code, default entry, BALR/BR, wild branch |
| `tests/integration/hlasm/test_instruction_table.py`, `test_opcode_unit_coverage.py` | Instruction table and opcode-unit coverage |
