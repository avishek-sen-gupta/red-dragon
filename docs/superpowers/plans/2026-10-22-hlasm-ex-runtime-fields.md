# HLASM EX: data-field targets lowered once with a runtime field (red-dragon-6uyp.79, ruling R31)

## Problem

EX and EXRL expand the target once per byte-1 value R1 can make (R30). EX of an MVC lowers
to 13,324 IR instructions; 16 such sites take 40 s to compile. R31 keeps expansion only where
byte 1 selects registers or opcode bits. Where it is a pure data field (an SS length L or
L1/L2, an SI or SIY I2, the SVC number), the target is lowered once and the field is an IR
register: v = byte1 | (GR R1 bits 56-63); R1 = 0 lowers the plain statement.

## Facts that shape the design

- LOAD_REGION and WRITE_REGION take a compile-time length (`length: int` on the
  instruction, read as a literal by the handler). A runtime length must be a byte loop.
- Every data-field lowering except MVC and CLC already runs a byte loop (NC, OC, XC, TR, TRT,
  TRTR, MVN, MVZ, MVCIN); only the bound changes from a constant to a register.
- Unit tests build statements with `format=""`, so the written field cannot come from
  `byte_one_layout(statement)`; each data-field lowering names its layout instead.

## Design

- `DataField` (protocol): byte 1, or a part of it, as the lowering sees it.
  - `value` (a register), `part(shift, width)`, `length` (a length code plus one).
  - `loaded(address)`: the unsigned value of that many bytes; `copied(addresses)`: a
    left-to-right copy of that many bytes; `select(cases, otherwise)`: dispatch on the value.
- `WrittenField(value: int)`: the assembled byte. `loaded`/`copied` are one block
  LOAD_REGION/WRITE_REGION; `select` picks the case at compile time.
- `ExecutedField(register)`: EX's v. `loaded`/`copied` are byte loops; `select` is a chain
  of equality tests.
- These three methods are the only branch on "the field is a compile-time constant", and
  they sit in the shared layer, not in any instruction. Justification, to be measured:
  plain MVC/CLC steps (block vs loop) and plain SVC IR (one service vs all).
- `FieldLowering(layout, lower)`: a lowering taking `(emitter, statement, DataField)`.
  `written_lowerings` adapts a mapping of them into `StatementLowering`s that pass
  `WrittenField(layout.byte_of(statement))`; `OPCODE_LOWERINGS` keeps one entry per mnemonic.
  `DATA_FIELD_LOWERINGS` collects them for EX.
- `byte_one_layouts.py` names the four data-field layouts: `LENGTH_BYTE` (SS-a),
  `LENGTH_NIBBLES` (SS-b), `IMMEDIATE_BYTE` (SI, SIY), `NUMBER_BYTE` (I).
- `execute.py`: a target in `DATA_FIELD_LOWERINGS` with R1 != 0 computes v as now (opcode
  guard is a no-op, all bits are field bits) and calls its lowering once with
  `ExecutedField(v)`. Everything else is unchanged (R30 expansion).

## Units converted (one code path each)

| Family | Mnemonics | Field |
|---|---|---|
| storage moves | MVC, MVCIN, MVN, MVZ; MVO | L; L1/L2 |
| storage immediates | MVI, MVIY | I2 |
| storage compare | CLC | L |
| compare | CLI, CLIY | I2 |
| boolean | NC, OC, XC; NI, NIY, OI, OIY, XI, XIY | L; I2 |
| add/subtract | ASI, AGSI, ALSI, ALGSI | I2 (signed) |
| translate | TR, TRT, TRTR | L |
| test under mask | TM, TMY | I2 |
| SVC | SVC | I |

- MVC: overlap test on the length register; byte loop when destructive (unchanged), else
  `length.copied`. CLC: `length.loaded` on both operands, one logical compare at 2,048 bits
  (the widest field; the wrap is the identity below it).
- MVO: its compile-time unrolling becomes a right-to-left byte loop, the carry and the
  fetched source byte in variables; exhausted source bytes read as zero.
- TRT/TRTR: the last offset is the length code itself.
- SI immediates: `data_movement.storage_immediate` takes the field; the SI sources become
  the field's register (sign-extended where they were).
- SVC: `number.select(services, unknown)`; the written path logs as now.

## Tests

- Unit (`test_execute_lowering.py`): a data-field target lowers once: no `<` tree, no variant,
  the byte computed from GR R1 OR the written byte; MVC under EX uses only one-byte region
  accesses; IR size bounded. The expansion test keeps LHI/AR (register fields) and drops
  MVC/CLI, which no longer expand.
- Existing unit tests unchanged unless they assert an IR shape that changes (MVO, CLC's
  compare width); each listed in the report.
- Integration (`execute_programs.py`, shared with z390): one EX case per family with the field
  from R1: MVC, CLC, XC, TR, TRT, MVN, MVZ, MVCIN, CLI, MVI, TM, NI, OI, XI, SVC.

## Measurements (scratchpad script)

IR per EX site; compile time for 1, 4, 8, 16 `EX 2,MOVE` sites; VM steps for one EX of MVC
and one plain MVC (and CLC), before and after.

## Commits

1. Plan, the field layer, every unit on `FieldLowering`, EX using `ExecutedField`, the tests,
   `hlasm.md` (EX section R31, module map). Push.
2. Bead note and issues snapshot.
