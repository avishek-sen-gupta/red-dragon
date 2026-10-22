# HLASM Opcode Unit — Unicode conversion and string search (red-dragon-6uyp.43)

**Goal:** lower CU12, CU14, CU21, CU24, CU41, CU42, CUTFU, CUUTF, SRST, SRSTU.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14), pages 7-268 to 7-288 and 7-432 to 7-434. Rulings:
R28 (one execution, never CC 3 for partial completion), R29 (compares on ints), R31 (EX
data fields; none here — byte 1 of every form is opcode), R33 (S0C6 before any store).

## Semantics

- The bridge presents CUTFU and CUUTF as their own base mnemonics with the optional M3;
  they lower exactly as CU12 and CU21.
- Conversions: R1 and R2 even, else S0C6 at assembly. R1/R2 address (31-bit), R1+1/R2+1
  32-bit unsigned lengths. Characters convert left to right until: second operand
  exhausted (CC 0), an invalid character (CC 2, R2 at it), or the first operand too short
  for the next result (CC 1). CC 0 beats CC 1; CC 2 beats CC 1; exhaustion is judged from
  the lead unit before continuation units are validated. Odd lengths are not exceptions.
  At the end R2 and R1 advance, R2+1 and R1+1 count down, by bytes consumed and stored;
  updated addresses lose bit 32.
- Model choices (the PoO leaves them to the model; this machine claims z17 with the
  ETF3-enhancement facility): an isolated low surrogate with W=1 is CC 2 (CU21, CU24);
  UTF-32 DC00-DFFF is invalid (CU41, CU42) like D800-DBFF and anything over 10FFFF.
- UTF-8 source, W=0: leads 00-7F one byte, C0-DF two, E0-EF three, F0-F7 four; 80-BF and
  F8-FF invalid; continuation bits 0-1 ignored. W=1: C0-C1 and F5-F7 invalid leads too,
  continuations must be 80-BF, and the PoO's per-lead second-byte ranges reduce to the
  value checks: three-byte at least 800 and not D800-DFFF, four-byte 10000 to 10FFFF.
- UTF-16 source: D800-DBFF is a high surrogate needing 4 bytes; with W=1 the next unit
  must be DC00-DFFF. A four-byte UTF-8 or a surrogate pair is "supplementary": UTF-16
  output is a pair (zabcd = uvwxy - 1, z dropped), UTF-8 output four bytes.
- SRST/SRSTU: GR0 bits 32-55 (SRST) or 32-47 (SRSTU) nonzero is S0C6. Search R2 up to the
  end at R1 (SRSTU: R1 + 1 when R1 and R2 differ in bit 63). Found: R1 = its address,
  CC 1. Not found: CC 2, registers unchanged. R1 = R2 is CC 2 at once. No CC 3.

## Shared pieces

- `ending_character.py`: `ending_unit(width)` generalises the GR0 check to SRSTU's 16-bit
  character; `ending_character` becomes its one-byte use.
- `range_dispatch.py`: branch an int to the first of ascending bounds it is below.
- `conversion_cursor.py`, `conversion_labels.py`: the loop's offsets and its exits.
- `unicode_decoders.py` (UTF-8, UTF-16, UTF-32 readers storing the code point and the
  next source offset), `unicode_encoders.py` (UTF-8, UTF-16, UTF-32 writers with the
  space check), `unicode_conversion.py` (loop, CC, register updates), `search_string.py`.
- `opcodes/unicode_string_search.py`: the unit table.

## Tests

- Unit `test_unicode_string_search_lowering.py`: per form the storage widths read and
  written; no comparison on a byte image; W=1 adds compares; odd R1 or R2 abends before
  any register is read; SRST/SRSTU read GR0 first; no SYMBOLIC.
- Integration `test_unicode_string_search.py`, programs in
  `unicode_string_search_programs.py`: every mnemonic. Each conversion of "A é € 😀"
  exhausted (CC 0, output in registers 6-7, lengths left), first operand full (CC 1),
  invalid (CC 2, R2 at it), truncated lead (CC 0, unconsumed), W=0 vs W=1 on overlong,
  surrogate, bad continuation and isolated low surrogate; the address offsets in
  separate "registers" cases. SRST/SRSTU found, not found, R1 = R2, end excluded,
  SRSTU's odd end, bit 32. S0C6: odd pairs and GR0 reserved bits, storage unchanged.
- z390 `test_unicode_string_search_differential.py`: SRST matches. z390 abends S0C1 on
  every CU form and on SRSTU; those cases pin z390's S0C1 and check the PoO value.

## Commits

1. This plan.
2. Lowering, tests, `docs/frontend-design/hlasm.md`, issue snapshot.
