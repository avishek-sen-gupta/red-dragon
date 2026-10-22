# HLASM Opcode Unit — Translate (red-dragon-6uyp.37)

**Goal:** lower TR, TRT, TRTR, TRE, TROO, TROT, TRTO, TRTT, TRTE, TRTRE.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14), pages 7-468 to 7-481. Rulings: R28 (interruptible
forms finish in one execution, never CC 3), R29 (compares on ints, never on byte images).
The machine claims z17, so the ETF2-enhancement facility is installed.

## Semantics

- TR: L bytes left to right; each byte is replaced by the table byte at table + byte,
  fetched then stored before the next byte, so overlap follows the PoO. CC unchanged.
- TRT, TRTR: scan left to right (TRTR from the rightmost byte, right to left) until the
  table byte is nonzero. Found: GR2 bits 56-63 get it; GR1 gets the byte's address, bits
  33-63, with bit 32 zeroed (TRT) or kept (TRTR); CC 1, or 2 at the last byte scanned.
  None found: CC 0, GR1 and GR2 unchanged. Storage never written.
- TRE: R1 even, else S0C6. R1 address, R1+1 32-bit length, R2 256-byte table, test byte
  GR0 bits 56-63 (bits 0-55 ignored). Each byte equal to the test byte stops with CC 1,
  otherwise it is translated in place. Exhausted: CC 0. R1 advances and R1+1 counts down
  by the bytes processed.
- TROO, TROT, TRTO, TRTT: R1 even, else S0C6. R2 source, R1 destination, R1+1 source
  length; GR1 table address with bits 61-63 ignored (doubleword, ETF2). Argument width
  1/1/2/2, function width 1/2/1/2. TRTO and TRTT: odd length is S0C6. Test character
  GR0 bits 56-63 (one-byte functions) or 48-63; M3 bit 3 (C) on skips the test. A
  function equal to the test stops with CC 1; exhausted CC 0. R2 advances and R1+1
  counts down by the source bytes processed; R1 by the function bytes stored.
- TRTE, TRTRE: R1 even, else S0C6. M3 A (8) argument width 2, F (4) function width 2,
  L (2) with A: arguments over 255 select a zero function and read no table. A with an
  odd length is S0C6. GR1 table (bits 61-63 ignored). TRTRE's R1 is the rightmost
  argument. Found: R2 low word = function code, R1 = argument address, R1+1 = length
  less the bytes before it, CC 1. Exhausted: R2 low word 0, R1 moved by the length,
  R1+1 0, CC 0. R2 is written first, so R2 = R1 or R1+1 ends with the operand update.
- Updated R1 and R2 addresses lose bit 32 (the PoO lets it be zeroed or kept), as the
  long moves and compares do.

## Shared pieces

- `byte_loop.py`: `emit_scan_loop`, a counted loop whose body may branch out and whose
  values are returned; `emit_counted_loop` becomes a use of it.
- `unit_value.py`: `unit_value` converts a 1- or 2-byte image to an int; `unit_reader`
  composes it with the load.
- `long_registers.py`: `store_address`, which `advance_address` uses.
- `operands.py`: `optional_mask_operand` for the optional M3.
- `translation_table.py`: the GR1 table address and the argument scaled by function width.
- `translate_extended.py` (TRE), `translate_characters.py` (TROO family),
  `translate_and_test_extended.py` (TRTE, TRTRE), `opcodes/translate.py` (TR, TRT, TRTR,
  the unit table).

## Tests

- Unit `test_translate_lowering.py`: TR reads a byte and its table byte and writes one
  byte per iteration, no CC; the scans write no storage and compare no image; per-form
  unit widths read (TROT, TRTO, TRTT, TRTE M3=12); C=1 drops the test compare; odd R1
  abends S0C6 before any register is read; no SYMBOLIC.
- Integration `test_translate.py`, programs in `translate_programs.py`: every mnemonic.
  TR with overlap into the table; TRT/TRTR CC 0, 1, 2 with GR1 (bit 32) and GR2;
  TRE found, exhausted, length 0; TROO family found and exhausted, C=1, table bits 61-63
  ignored; TRTE/TRTRE with each A/F/L combination, found and exhausted. S0C6: TRTT odd
  length, TRTE A with odd length.
- z390 `test_translate_differential.py`: every case; differences pinned and noted on
  red-dragon-6uyp.74.

## Commits

1. This plan.
2. Shared pieces, lowering, tests, docs, bead snapshot.
