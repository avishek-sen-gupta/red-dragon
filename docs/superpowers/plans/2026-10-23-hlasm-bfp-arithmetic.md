# HLASM unit .51: BFP arithmetic

Bead red-dragon-6uyp.51. Rulings R31, R34, R36, R37, R40, R41 (amended: invalid FPC values
give S0C6), R42, R43. Seventy base mnemonics; no extended mnemonics.

## Mnemonic groups

| Group | Mnemonics | Builtin | CC |
|---|---|---|---|
| Add, subtract | AEBR AEB ADBR ADB AXBR SEBR SEB SDBR SDB SXBR | add, subtract | by result |
| Multiply | MEEBR MEEB MDBR MDB MXBR | multiply | unchanged |
| Lengthening multiply | MDEBR MDEB MXDBR MXDB | multiply_lengthened (source format) | unchanged |
| Divide | DEBR DEB DDBR DDB DXBR | divide | unchanged |
| Square root | SQEBR SQEB SQDBR SQDB SQXBR | square_root | unchanged |
| Fused | MAEBR MAEB MADBR MADB MSEBR MSEB MSDBR MSDB | multiply_add, multiply_subtract (op3, op2, op1) | unchanged |
| Compare | CEBR CEB CDBR CDB CXBR, KEBR KEB KDBR KDB KXBR | compare, compare_signaling | comparison |
| Load FP integer | FIEBR FIEBRA FIDBR FIDBRA FIXBR FIXBRA | round_to_integral | unchanged |
| Divide to integer | DIEBR DIDBR | divide_to_integer | Figure 19-22 |
| Test data class | TCEB TCDB TCXB | test_data_class | 0 or 1 |
| Sign forms | LTEBR LTDBR LTXBR, LCEBR LCDBR LCXBR, LNEBR LNDBR LNXBR, LPEBR LPDBR LPXBR | none (IR) | by result |

## Design (R43)

- **Layouts.** `BfpLayout` groups the static facts of one format: the `zarch_float` format,
  the image width and the builtin-name suffix. SHORT lives in FPR bits 0-31, LONG in the
  whole FPR, EXTENDED in a register pair (R41 pairs; an invalid pair abends S0C6 at
  compile time through the .50 pair check).
- **IR decodes and encodes.** IR splits an image into sign, biased exponent and fraction and
  hands them over as a three-element list per operand. The builtin
  returns fields; IR shifts them back into an image and stores it.
- **Builtins.** `bfp_builtins()` in `interpreter/hlasm/bfp_builtins.py`, one builtin per
  (operation, format), named `__hlasm_bfp_<operation>_<format>`. At most four parameters:
  a rounding code, then the operand lists. The rounding code is the M-field code; IR maps the
  FPC BFP mode to it with `(mode + 4) & 7`. Composed by the CLI and the test helpers, as the
  clock builtins are; `run.py` stays free of `interpreter.hlasm`.
- **Result list.** `[value fields (3), scaled fields (3), trap, flags, scaled DXC, inexact DXC,
  CC]`, and for divide to integer the quotient fields after it. `trap` uses the FPC mask
  layout (invalid, division by zero, overflow, tininess, inexact); `flags` the flag layout
  (underflow only when tiny and inexact).
- **Traps in IR.** `enabled = trap & mask`. Invalid or division by zero enabled: DXC, S0C7,
  nothing stored (R34). Overflow or underflow enabled: store the scaled value, DXC from its
  exactness, S0C7. Otherwise store the value, OR the unenabled flags into FPC byte 1, and
  if inexact is enabled set DXC 08/0C and abend.
- **Result shape.** `BfpResult` keeps `scaled`/`scaled_conditions`: the IR reads the scaled
  fields only when overflow or tininess is enabled. No `zarch_float` change for it.
- **Sign forms and LOAD AND TEST** are IR on the image: CC from the magnitude against the
  infinity image; LT quiets an SNaN and raises invalid through the same trap IR.
- **Static checks.** FI M3 and DI M4 values 2 and 8-15, and DI registers not distinct, abend
  S0C6 at compile time. FI M4 bit 1 (XxC) clears inexact from trap and flags in IR.

## zarch_float additions (own commit)

- `bfp_divide_to_integer(a, b, quotient_mode, remainder_mode)` returning
  `BfpDivideToIntegerResult(remainder, quotient, partial, quotient_overflow)`: final when
  |q| < 2^P or q is an integer, else partial (quotient toward zero to P bits, exact
  remainder, no underflow); quotient overflow scales the quotient by 2^-192/-1536.
- `bfp_test_data_class(a, mask)`: Figure 19-26 bit selection.
- `bfp_widened(a, target)`: exact retag into a wider format, keeping SNaNs signaling, for the
  lengthening multiplies.

## Tests

- `tests/unit/zarch_float/test_bfp_divide_to_integer.py`: final with each rounding, partial,
  quotient overflow, specials table, inexact and tiny remainders. `test_bfp.py` gains data
  class and widening behaviours.
- `tests/unit/hlasm/test_bfp_builtins.py`: fields round trip and the result list for add,
  overflow, compare, divide to integer and test data class.
- `tests/unit/hlasm/test_bfp_arithmetic_lowering.py`: builtin name and argument lists, no
  SYMBOLIC, pair checks before any access, compare stores no FPR, sign forms call nothing.
- `tests/integration/hlasm/bfp_arithmetic_programs.py` + `test_bfp_arithmetic.py`: every
  mnemonic with concrete FPR images, CC, FPC and abend; traps (DXC 80, 40, 2x, 1x, 08/0C);
  FMA NaN order and 0 x inf with an SNaN addend (.21 notes).
- `tests/z390/test_bfp_arithmetic_differential.py`: the same cases against z390, FPC set
  first (z390 starts it at X'70000000'). Disagreements pinned and noted on .74.

## Commits

1. Plan.
2. `zarch_float`: divide to integer, data class, widening; zarch-float.md.
3. Builtin adapter + composition (CLI, test helpers); "too cumbersome" clause in the message.
4. Arithmetic: add, subtract, multiply, lengthening multiply, divide, square root, fused.
5. Compare, load FP integer, divide to integer, test data class.
6. Sign forms and LOAD AND TEST. hlasm.md updated in 4-6; bead notes and snapshot last.
