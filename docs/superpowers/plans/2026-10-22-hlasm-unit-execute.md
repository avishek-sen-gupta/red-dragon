# HLASM Opcode Unit — Execute (red-dragon-6uyp.39)

**Goal:** lower EX and EXRL.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14), page 7-294. Ruling R30: compile-time variant
expansion over a statically resolved target.

## Semantics

- The target is the machine statement at the second-operand address. When R1 is not 0,
  v = target byte 1 OR GR R1 bits 56-63; R1 = 0 executes the target unchanged.
- The target runs as if fetched in sequence, except the instruction address: link
  information (BAL, BAS, BRAS) points after the EX. Relative operands stay relative to
  the target. A taken branch leaves; otherwise execution continues after the EX. The CC
  is the target's.
- Target EX, EXRL, TBEGIN, TBEGINC, TEND or TABORT: execute exception, `S0C3`.
- EX with an odd target address: specification, `S0C6`. EXRL's target is always even.

## Resolution

- EXRL: the RELOC_IMM operand names the target section and offset.
- EX: the bridge exports a storage operand's address as written (`written`: ABS value or
  RELOC section and offset, before USING resolution). Bridge change on the che4z fork,
  then a submodule bump. RELOC with X2 = 0 resolves; anything else (explicit base, an
  index, no machine statement there) abends `S0C1` with a lowering warning, gap bead.

## Variant expansion

- Byte 1 layout per instruction format (`MachineStatement.format`, che4z's names),
  chosen by format and operand count: fields at a shift and width mapped to an operand
  value (R, M, I), a storage index (X2) or a length code (L, L1, L2: written length =
  code + 1); bits mapped to nothing are ignored or opcode bits.
- Runtime: m = GR R1 low byte. If m sets an opcode bit the target lacks, abend `S0C1`
  (opcode modification not modelled; gap bead). v = (target byte | m) masked to operand
  fields. A binary decision tree over the supersets of the target's field bits selects
  one inline copy per value, each lowered through OPCODE_LOWERINGS with the operands
  rewritten from v and positioned at the EX (section, offset, length) so link addresses
  follow the PoO. Every copy falls through to one join label.
- `lower_statement` takes the program's machine statements by location; EX and EXRL
  are dispatched there, not through OPCODE_LOWERINGS (they need the program).

## Modules

- `hlasm_asg/program/written_address.py`; `StorageOperand.written`.
- `interpreter/hlasm/byte_one_layout.py` (the per-format table and decode),
  `interpreter/hlasm/execute.py` (resolution, checks, tree, copies),
  `interpreter/hlasm/machine_statements.py` (statements by location).

## Tests

- Unit `test_execute_lowering.py`: R1 = 0 lowers one copy and reads no register; MVC
  length 0 under R2 has 256 copies and an 8-deep tree; CLI's I2 field; RR R1/R2 fields;
  RI opcode-bit guard; targets EX/EXRL abend `S0C3`; odd EX target `S0C6`; unresolved
  `S0C1` with a warning; no SYMBOLIC. Layout table decode for SS-a, SS-b, RX-a, RI-a.
- Integration `test_execute.py`: EX MVC with register length (0, 4, 255), EX CLI with
  the immediate from a register (CC), EX SVC 13 from a register, EX BAL (link after
  the EX), EXRL BRAS and EXRL J (relative target), EX of a BC mask, EX R0 (no
  modification), EX of EX `S0C3`, odd target `S0C6`, indexed target `S0C1`.
- z390 `test_execute_differential.py`: MVC length, CLI immediate, SVC number, BAL link,
  EXRL relative branch, EX of EX.
- Measure IR size of `EX 2,MOVE` / `MOVE MVC 0(0,3),0(4)` and VM steps per execution;
  record both in hlasm.md.

## Commits

1. This plan.
2. che4z fork: `written` on STORAGE operands (pushed), then the submodule bump with the
   model field and test updates.
3. EX and EXRL lowering, tests, hlasm.md, beads.
