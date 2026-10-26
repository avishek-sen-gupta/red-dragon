# z/OS divergences

Where a COBOL program run on RedDragon behaves differently from the same program compiled with IBM
Enterprise COBOL for z/OS. Each row is a case found by probing, not a guess. Add a row when you find
one. Delete a row when a fix lands.

## The z/OS rule usually depends on a compiler option

The Programming Guide (SC27-8714-03, "Checking for incompatible data") says the compiler does not
check data against its PICTURE and USAGE, and that a reference to an item holding incompatible data
is "undefined and your results are unpredictable". What actually happens is chosen by compiler
options:

| Option | Governs |
|---|---|
| `INVDATA(CLEANSIGN)` / `INVDATA(NOCLEANSIGN)` / `NOINVDATA` | an invalid sign nibble in DISPLAY or packed operands of compares and arithmetic. `CLEANSIGN` repairs the sign first; the others leave it for the hardware, which raises a data exception (S0C7) |
| `NUMPROC(NOPFD)` / `NUMPROC(PFD)` | which sign nibbles count as valid. Under `NOPFD` (the default) any of A–F is valid |
| `NUMCHECK(ZON,PAC,BIN,MSG\|ABD)` | run-time validation of numeric data before use, reporting or abending |
| `SSRANGE` / `NOSSRANGE` | subscript, reference-modification and ODO range checks. `NOSSRANGE` (the default) checks nothing |
| `TRUNC(STD)` / `TRUNC(BIN)` / `TRUNC(OPT)` | truncation of binary results |

So a row names the option setting that RedDragon matches, where it matches one. The z/Architecture
facts are fixed: decimal instructions take signs A, C, E and F as plus and B and D as minus, and
reject other signs and digits above 9 with a data exception.

Marks: **[C]** = certain (z/Architecture Principles of Operation, the IBM manuals, the COBOL
standard). **[R]** = recollection of Enterprise COBOL code generation, to confirm against the
manuals or a host.

## Divergences

| Case | z/OS | RedDragon | GnuCOBOL 3.2 default | Status |
|---|---|---|---|---|
| `DIVIDE` or `COMPUTE` by zero, no `ON SIZE ERROR` | abend: S0CB (packed) [C], S0C9 or S0CB (binary) [R] | prints a `SymbolicValue(...)` expression as the result | target unchanged | bug: a symbolic value leaks into output |
| `COMPUTE R = 0 ** -1` | size error by definition [C]; without `ON SIZE ERROR`, unpredictable [R] | `SymbolicValue(...)` | 0 | bug: same leak |
| `FUNCTION SQRT(-4)` | LE math condition, run ends [R] | `SymbolicValue(...)` | 0 | bug: same leak |
| packed sign X'B' (X'12345B') | -12345 [C]; `IF PK < 0` true [C]; NUMERIC true under `NUMPROC(NOPFD)` [C] | +12345; `PK < 0` false; NOT NUMERIC | +12345 | wrong value: only X'D' is read as negative (`interpreter/cobol/comp3.py`, `build_decode_comp3_ir`) |
| zoned sign zone X'B' (X'F1F2B3') | -123 [C] | +123 | (ASCII; not comparable) | wrong value, same cause |
| packed field after a group `MOVE SPACES` (X'404040'), then arithmetic | S0C7 under `NOINVDATA` or `NOCLEANSIGN`; +40404 under `INVDATA(CLEANSIGN)` (digits are valid, sign cleaned) [C] | +40404 | +20202 | matches `INVDATA(CLEANSIGN)` only |
| packed with a bad digit nibble (X'1A345C'), then arithmetic | S0C7, whatever INVDATA says [C] | nibble A taken as 10: 20345 | 20345 | lenient |
| signed zoned S9(4) holding spaces, `ADD 1` | S0C7 unless `INVDATA(CLEANSIGN)` [R] | 1 | 1 | matches `INVDATA(CLEANSIGN)` only [R] |
| ODO object above its maximum (5 > 3) | `NOSSRANGE`: the item is 5 long and the move overruns [R]; `SSRANGE`: abend [C] | caps at the maximum: 3 | crashes (macOS memset trap) | wrong length |
| ref-mod past the end, `S(3:4)` on X(4) | `NOSSRANGE`: 4 bytes, 2 from following storage [C]; `SSRANGE`: abend [C] | 2 bytes, clipped | 4 bytes | wrong length |
| subscript out of range, read or write `E(4)` of `OCCURS 3` | `NOSSRANGE`: no check [C]; 01 items are doubleword-aligned, so the overrun reaches slack bytes [R]; `SSRANGE`: abend [C] | reaches the next 01 item, which RedDragon packs with no slack | reaches slack bytes | different victim |
| dynamic `CALL` to a missing program, no `ON EXCEPTION` | abend S806 [C] | Python traceback (`UnresolvedProgramError`), exit 1 | `module not found`, exit 1 | ends the run, but not as a modelled abend |

## Cases that match

Probed and found to agree with z/OS:
- packed signs X'A', X'E' and X'F' read as plus;
- `'AB12'` in a PIC 9(4) computes as 1212 (PACK ignores zones);
- `'12 4'` moved to packed is 1204;
- unsigned zoned spaces plus 1 gives 1 (`NUMPROC(NOPFD)` [R]);
- high-order truncation on zoned, packed, and binary under `TRUNC(STD)`;
- divide by zero with `ON SIZE ERROR`;
- `STRING` overflow;
- `UNSTRING` with pointer 0;
- dynamic `CALL` with `ON EXCEPTION`.

## Not yet probed

Pointer and null-address checks, recursive `CALL`, `CANCEL` of an active program, floating-point
non-finite values, rounding truncation, `GO TO DEPENDING` on non-numeric data, and file I/O status
conditions.

## Method and sources

- Each case was a short program run on RedDragon and on GnuCOBOL 3.2, both with default options and
  with `-fec=EC-ALL`. GnuCOBOL's run-time checks are its `EC-*` exception conditions: see
  `libcob/exception.def`, emitted from `cobc/typeck.c` and evaluated in `libcob/common.c`. They mark
  where the language admits data can be invalid, and served as the checklist. GnuCOBOL's default
  matches RedDragon in most rows. The NIST COBOL-85 suite cannot catch any of this: it uses no
  packed-decimal items, and the standard leaves invalid data undefined.
- IBM Enterprise COBOL for z/OS 6.4: Language Reference (SC27-8713-03) and Programming Guide
  (SC27-8714-03), from IBM's documentation library. The INVDATA, NUMPROC and NUMCHECK option
  descriptions are in the Programming Guide's compiler-options chapter.
