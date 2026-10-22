# HLASM Opcode Unit — Edit (red-dragon-6uyp.49)

**Goal:** lower ED and EDMK. No extended mnemonics.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: the PoO pages
8-8 to 8-12 (EDIT, EDIT AND MARK, Figure 8-3) and 8-5 (general-operand data exception).
Rulings R28, R29, R31, R34, R39.

## Semantics

- SS-a. The pattern (first operand, L+1 bytes) is processed left to right one byte at a
  time and each byte replaced. The fill byte is pattern byte 0, read before any store; if
  it is X'20' or X'21' it is then processed as one.
- X'20' and X'21' examine the next source digit. A pending right nibble (a digit left over
  from the last fetched byte) is used first; otherwise a new source byte is fetched, its
  left nibble is the digit, and its right nibble is pending when 0-9. A plus code (A, C,
  E, F) in the fetched byte's right nibble turns the significance indicator off after the
  left digit is processed; minus codes (B, D) do nothing.
- Digit result: the zoned digit (F0 | d) when the indicator is on or d is nonzero, else
  the fill. New indicator: off on a plus code, else on if it was on, d is nonzero or the
  byte is X'21'.
- X'22': fill byte, indicator off, starts a new field (last-field-nonzero reset).
- Message byte: kept when the indicator is on, else the fill.
- CC: 0 when the last field is zero or empty; else 1 with the indicator on, 2 with it off.
- S0C7: a left nibble A-F. The PoO (8-5) leaves ED/EDMK suppression or termination to the
  model; R34 picks suppression, so a checking sweep walks the pattern and source (no stores)
  first, then the editing sweep stores. Pattern, CC and GR1 unchanged. z390 also suppresses.
  Right nibbles are never invalid (PoO: an invalid sign code cannot occur).
- EDMK: the address of the rightmost result byte that is a zoned digit stored while the
  indicator was off before the examination goes to GR1 bits 33-63, bit 32 zero, bits 0-31
  kept (AMODE 31). No such byte (e.g. significance forced by X'21' with digit 0): GR1
  unchanged.
- Overlapping pattern and source: unpredictable per PoO; the lowering reads each source
  byte when it is needed and writes each pattern byte after reading it.
- EX (R31): `LENGTH_BYTE`, lowered once.

## Shared helpers

- `interpreter/hlasm/opcodes/edit.py`: ED and EDMK, registered in `OPCODE_LOWERINGS` and
  `DATA_FIELD_LOWERINGS`. Reuses `emit_counted_loop`/`emit_byte_loop`, `emit_either`,
  `emit_when`, `unit_reader`, `table_bit`, `emit_data_check`, `store_address`.
- `PLUS_SIGNS` beside `MINUS_SIGNS` in `packed_decimal.py`. Loop state in named vars in
  `hlasm_constants.py`.

## Tests

- Unit `test_edit_lowering.py`: ED and EDMK read, `S0C7`, then write, then CC; EDMK's GR1
  store after the CC; EX layout `LENGTH_BYTE`; no SYMBOLIC.
- Integration `test_edit.py` with `edit_programs.py`: amount mask with comma, point and CR
  (positive CC 2 drops CR, negative CC 1 keeps it); zero suppression with `*` fill (CC 0);
  multi-field with X'22' (CC from the last field, CC 0 after a nonzero first field);
  fill byte that is a digit selector; no digit selectors; alternate minus B; EDMK setting
  GR1 (bit 32 cleared, high word kept), EDMK leaving it unchanged after X'21' with digit 0,
  EDMK marking the rightmost field; EX of ED; `S0C7` with pattern and CC unchanged
  (storage checked).
- z390 `test_edit_differential.py`: every case. Disagreements pinned and noted on
  red-dragon-6uyp.74.

## Commits

1. This plan.
2. Feature: module, registration, tests, docs (hlasm.md, README unit count).
3. Issue snapshot with the bead note.
