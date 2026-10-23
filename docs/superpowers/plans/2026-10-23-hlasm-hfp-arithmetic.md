# HLASM unit .53: HFP arithmetic

Bead red-dragon-6uyp.53. Rulings R31, R34, R39 (program mask), R40, R41, R43, R44, R46.
Eighty-one base mnemonics; no extended mnemonics. PoO SA22-7832-14 chapter 18.

## Mnemonic groups

| Group | Mnemonics | Path | CC |
|---|---|---|---|
| Add/subtract normalized | AE AER AD ADR AXR SE SER SD SDR SXR | builtin | from result |
| Add/subtract unnormalized | AU AUR AW AWR SU SUR SW SWR | builtin | from result |
| Compare | CE CER CD CDR CXR | builtin (guard-digit difference) | 0/1/2 |
| Multiply | MEE MEER MD MDR MXR, MDE MDER ME MER, MXD MXDR | builtin | unchanged |
| Divide | DE DER DD DDR DXR | builtin | unchanged |
| Halve, square root, FP integer | HER HDR, SQE SQER SQD SQDR SQXR, FIER FIDR FIXR | builtin | unchanged |
| Multiply and add/subtract | MAE MAER MAD MADR MSE MSER MSD MSDR | builtin | unchanged |
| Multiply unnormalized | MY MYR MYH MYHR MYL MYLR | builtin | unchanged |
| Multiply and add unnormalized | MAY MAYR MAYH MAYHR MAYL MAYLR | builtin | unchanged |
| Sign forms | LTER LTDR LTXR LCER LCDR LCXR LNER LNDR LNXR LPER LPDR LPXR | IR | from result |

## Why each path (R44, R46)

- **Builtins compute.** Alignment with one guard digit, normalization, exact products,
  quotients and roots, then truncation, are arithmetic on up to 28-digit fractions. IR
  would dwarf the program, so the "too cumbersome" clause applies. Compare is the same
  normalized subtraction (PoO "COMPARE"), so it shares the builtin path.
- **IR for the sign forms.** LT, LC, LN and LP change one bit and, for extended
  operands, rewrite the low-order sign and characteristic (PoO 18-14 to 18-16). No
  arithmetic.

## Design

- **Refactor first (no behaviour change).** FPR access by width (short high word, long,
  pair), `pick`, `list_item`, the operand sources `fpr` and `storage`, and the operand
  indexes move from `bfp_ir`/`bfp_forms` to a neutral `opcodes/fpr_images.py`. A
  protocol `FprLayout` (width) is inherited by `BfpLayout` and the new `HfpLayout`.
- **Leaf additions (own commit).** `zarch_float`: `hfp_load_fp_integer` (FIxR, truncate,
  normalize, positive true zero), `hfp_multiply_add`/`hfp_multiply_subtract` (op3 x op2
  +- op1 exact, one normalize and truncate; zero gives positive true zero; no
  significance), `hfp_multiply_unnormalized` and `hfp_multiply_add_unnormalized` (28-digit
  window of the exact product or sum, unbounded exponent, no conditions).
- **Adapter.** `hfp_builtins()`, one `__hlasm_hfp_<operation>_<format>` builtin per
  operation and source format; at most three operand lists. Operands arrive as
  `[sign, characteristic, fraction]`; results leave as `[sign, characteristic mod 128,
  fraction, conditions]`. Compare returns the CC.
- **Condition bits** line up with the program mask: significance 0b0001, underflow
  0b0010; overflow, divide and square root sit above the mask.
- **Program-mask ladder (R46)** in `hfp_ir.py`:
  1. HFP divide → `S0CF`, square root → `S0DD` (PIC 001D maps to S0Dx as 0013 gives
     S0D3); both suppressed, nothing stored (R34).
  2. Store: a true zero when underflow or significance is raised with its mask bit off,
     else the result with the wrapped characteristic (PoO 6-28, 6-29, 18-1).
  3. CC where the instruction sets it, from the stored image.
  4. Overflow → `S0CC`; underflow with PM 0b0010 → `S0CD`; significance with PM 0b0001
     → `S0CE`; each after the store (completion).
- **Encoding.** Short results replace bits 0-31 (ruling from .50). Extended results set
  the low-order sign to the high-order sign and the low characteristic to the high one
  minus 14 mod 128, or zero for a true zero (PoO 18-4); MY and MAY wrap regardless of a
  zero fraction (PoO 18-21, 18-22).
- **Registers.** Pairs (`pairs`) for AXR SXR CXR MXR DXR SQXR FIXR LTXR LCXR LNXR LPXR
  (both R), MXD MXDR MY MYR (R1). MAY and MAYR take any R1; the result goes to the pair
  holding it and the addend is R1 itself. MXD's multiplicand is R1's high-order part.
- **CC.** Add/subtract and the sign forms: 0 for a zero fraction, else 1 or 2 by sign.
  Compare: 0 when the guard-digit difference is zero.

## Tests

- `tests/unit/zarch_float/test_hfp.py`: one behaviour per new operation, PoO vectors.
- `tests/unit/hlasm/test_hfp_builtins.py`: fields to values and back; each builtin
  family's fields, wrapped characteristic and condition bits.
- `tests/unit/hlasm/test_hfp_arithmetic_lowering.py`: operands in argument order, one
  call, ladder order (suppress abends, store, CC, completion abends); sign forms with no
  call; pairs abend `S0C6` before any access; no SYMBOLIC in all 81.
- `tests/integration/hlasm/test_hfp_arithmetic.py`: every mnemonic on the VM with
  concrete images and CC; each exception with the PM on and off.
- `tests/z390/test_hfp_arithmetic_differential.py`: every case against z390;
  disagreements pinned and noted on red-dragon-6uyp.74.

## Commits

1. This plan.
2. Refactor: neutral FPR image module.
3. `zarch_float`: FIxR, multiply-add/subtract, the unnormalized multiplies.
4. HFP builtins, IR, arithmetic lowerings, tests, docs.
5. HFP sign forms, tests, docs; bead note and snapshot.
