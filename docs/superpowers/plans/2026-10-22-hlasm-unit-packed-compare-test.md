# HLASM Opcode Unit — Packed-decimal compare and test (red-dragon-6uyp.47)

**Goal:** lower CP and TP. No extended mnemonics.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: the PoO pages
8-7 (COMPARE DECIMAL) and 8-14 (TEST DECIMAL), and EXECUTE (bits 8-15 ORed). Rulings:
R29 (compares on ints), R31 (byte 1 is a data field), R34 (checks before any store; these
store nothing), R39 (decimal; invalid digit or sign → `S0C7`).

## Semantics

- CP (SS-b): both operands, lengths L1 and L2 of 1-16 bytes each, are read with the
  unit .46 reader and checked; any invalid digit or sign → `S0C7`, CC unchanged. The
  signed values are compared as ints: CC 0 equal, 1 first low, 2 first high. Signs B/D
  are minus, so -0 equals +0 and preferred and alternate signs compare alike. No
  specification exception.
- TP (RSL-a, opcode EB..C0): one operand, L1 of 1-16 bytes in byte-1 bits 8-11; bits
  12-15 are unused. CC = 2 × (any digit invalid) + (sign invalid). No data exception and
  no specification exception.
- EX: CP on `LENGTH_NIBBLES`. TP's L1 is byte 1's high nibble, so EX sets it; the low
  nibble is ignored (the existing RSL-a layout), now named `LENGTH_HIGH_NIBBLE`.

## Shared helpers

- `PackedValue` carries a bad-digits bit and a bad-sign bit instead of one invalid bit;
  `invalid(emitter)` ORs them for .46's checks. The reader keeps the digit flag in its
  loop variable and computes the sign check from the last byte.
- The SS-b operand reading in `packed_arithmetic.py` (first field, both fields, read both,
  either invalid) moves to `interpreter/hlasm/packed_operands.py` and is imported by both
  opcode modules.
- `interpreter/hlasm/opcodes/packed_compare_test.py`: CP and TP, registered in
  `OPCODE_LOWERINGS` and `DATA_FIELD_LOWERINGS`.

## Tests

- Unit `test_packed_compare_test_lowering.py`: CP reads both operands, abends `S0C7`
  before it sets the CC; TP reads one operand, sets the CC, has no abend; neither writes
  storage; no SYMBOLIC; EX layouts (`LENGTH_NIBBLES`, `LENGTH_HIGH_NIBBLE`) and TP's byte 1.
- Integration `test_packed_compare_test.py` with `packed_compare_test_programs.py`:
  CP equal at different lengths, -0 vs +0, alternate signs, low and high, 31-digit
  operands, invalid digit and invalid sign in either operand (`S0C7`, CC unchanged);
  TP CC 0-3, 1-byte and 16-byte fields, sign F valid; EX of CP and of TP with runtime
  lengths.
- z390 `test_packed_compare_test_differential.py`: every case; pin and report any
  disagreement on red-dragon-6uyp.74.

## Commits

1. This plan.
2. Feature: helpers move, modules, registration, tests, docs (hlasm.md, README unit count).
3. Issue snapshot with the bead note.
