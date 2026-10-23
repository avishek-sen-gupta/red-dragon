# HLASM unit .55: DFP arithmetic

Bead red-dragon-6uyp.55. Rulings R34, R40, R41, R43, R44, R48, R49. Forty-six base mnemonics,
no extended mnemonics. PoO SA22-7832-14: chapter 20 (20-1 to 20-60), chapter 9 (FPC, DXC).

## Mnemonic groups

| Group | Mnemonics | Path | CC |
|---|---|---|---|
| Arithmetic | ADTR(A) AXTR(A) SDTR(A) SXTR(A) MDTR(A) MXTR(A) DDTR(A) DXTR(A) | builtin | add, subtract: by result; others unchanged |
| Compare | CDTR CXTR KDTR KXTR | builtin | 0/1/2, 3 unordered |
| Load and test | LTDTR LTXTR | IR | by result |
| Biased exponent | CEDTR CEXTR EEDTR EEXTR IEDTR IEXTR | IR | CEDTR/CEXTR only |
| Significance | ESDTR ESXTR | IR | unchanged |
| Rounding | FIDTR FIXTR QADTR QAXTR RRDTR RRXTR | builtin | unchanged |
| Shift | SLDT SLXT SRDT SRXT | IR | unchanged |
| Class, group | TDCET TDCDT TDCXT TDGET TDGDT TDGXT | IR | 0/1 |

## Why each path (R44, R49)

- **Builtins round or align.** Add, subtract, multiply, divide, quantize, reround and load FP
  integer round once by a method to a preferred quantum (figures 20-4, 20-5, 20-6). Compare
  aligns coefficients across exponents up to 12287 apart. `zarch_float` already does all of
  it. "Too cumbersome" clause.
- **IR for the rest.** Load and test, the biased-exponent forms, significance, shifts and the
  class and group tests are field and digit logic on decoded operands.
- **DPD codec is IR (R49).** One IR function per format, defined once per program that uses DFP
  and called by name: decode (short, long, extended) and encode (long, extended). Each works
  on all the format's declets at once, ten bits per lane.

## Decoded fields

An operand crosses as `[negative, e, significand]`. `e` is the biased exponent of a finite
number, or -1 infinity, -2 QNaN, -3 SNaN (EXTRACT BIASED EXPONENT's values, figure 20-21).
A finite significand includes the LMD; a special's is its trailing significand (20-5). The
builtins return the BFP result-list layout, so the slots and the trap ladder are shared.

## Rules pinned from the PoO

- Format (20-3 to 20-6, figure 20-1): combination bits 1-5 give the top two exponent bits and
  the LMD; 11110 infinity, 11111 NaN with bit 6 the SNaN bit. Reserved fields and
  noncanonical declets are accepted on input and never produced (20-6, 20-7).
- DPD (20-58 to 20-60, figures 20-32, 20-33): the 24 noncanonical declets decode as figure
  20-33 marks them.
- Rounding (20-19, 20-20): M 0 or 2 → the FPC DFP mode (bits 25-27); 1, 3-15 → the modifier.
  M 0 or 8-15 → XqC 1, quantum suppressed; 1-7 → XqC 0. The non-A forms are M 0.
- FIxTR (20-42, 20-43): M3 rounds and sets XqC; M4 bit 1 (X'4') is XxC.
- Quantum exception (figures 20-6, 20-8, 9-21): DXC 04, mask and flag bit X'04'. Not
  recognized when the inexact trap is taken; then neither SFq nor PIDq. XqC 1 → no flag.
- Trap ladder (R43): invalid and divide by zero suppress; overflow and underflow deliver the
  scaled result then abend (DXC 20/28/2C, 10/18/1C); inexact or quantum abend after the store.
- CC: ADD/SUBTRACT figure 20-10, 3 for a NaN. COMPARE figures 20-12, 20-14: CxTR invalid
  only on SNaN, KxTR on any NaN.
- CEDTR/CEXTR (figure 20-15): finite compares e; infinities equal; NaNs equal each other;
  other mixes CC 3. No IEEE exception.
- EExTR (figure 20-21): e, or -1/-2/-3. ESxTR (figure 20-22): significant digits, 0 for zero.
- IExTR (20-40, figure 20-23): GR R2 signed. 0..MBE finite; -1 infinity with the trailing
  digits; -3 SNaN; -2, < -3 or > MBE QNaN. The sign is the third operand's.
- LTxTR (20-41, figure 20-24): canonicalized; SNaN → invalid, QNaN result. An infinity loses
  its trailing digits.
- QAxTR (20-49 to 20-51): R2 gives the quantum, R3 the value. RRxTR (20-52, 20-53): GR R2 bits
  58-63. QUANTUM is judged against the third operand's quantum.
- SLxT/SRxT (20-54, 20-55): EA bits 58-63. Finite: all p digits shift, e kept. Special: the
  trailing digits shift, the kind kept.
- TDCxT (figure 20-30), TDGxT (figure 20-31): EA bits 52-63; selector class×2 + sign.
  Subnormal: nonzero, value below Nmin. Extreme: e is 0 or MBE. A subnormal with a
  nonextreme exponent falls in safe nonzero (allowed by 20-57).
- Pairs (R41): every extended FPR operand is checked before any access → `S0C6`.

## Shared pieces

- `ieee_words.py`: the condition→FPC-bit maps and the trap, flag and DXC words, moved out of
  `bfp_builtins.py` (refactor commit, no behaviour change). Adds QUANTUM, which BFP never
  raises.
- `ir_function.py`, `program_functions.py`: an IR function defined once per program, and the
  set a program's statements need. The frontend defines them after its entry function.
- Reused: `bfp_ir` (outcome slots, `without`, the ladder), `bfp_forms.inexact_control`,
  `fpr_images`, `floating_point_support.pairs`.

## Tests

- Unit: `test_dpd_codec.py` (all 1000 declets round-trip, figure 20-32 and 20-33 entries,
  the 24 noncanonical declets, each format's combination cases and specials);
  `test_dfp_builtins.py` (field mapping, quantum/flag words); `test_dfp_arithmetic_lowering.py`
  (IR traces: decode calls, builtin, ladder, encode, store; pair checks; no SYMBOLIC).
- Integration: `dfp_arithmetic_programs.py` + `test_dfp_arithmetic.py`: every mnemonic's images,
  CC and FPC; traps (invalid, divide by zero, overflow and underflow scaled, inexact, quantum
  on an A form, quantum not taken under an inexact trap); the divide tininess edge (9.99…E-384
  rounding to Nmin: underflow, inexact).
- z390: `test_dfp_arithmetic_differential.py`, one case per mnemonic; disagreements pinned and
  noted on red-dragon-6uyp.74.

## Commits

1. This plan.
2. Refactor: IEEE words shared by BFP and DFP builtins.
3. IR functions and the DPD codec, with the frontend defining them.
4. DFP builtins adapter.
5. Arithmetic (16) with the quantum ladder; hlasm.md.
6. Compare, load and test, biased exponent, significance (12); hlasm.md.
7. Rounding (6); hlasm.md.
8. Shifts, class and group tests (10); hlasm.md.
9. z390 differential tests; .74 notes; issues snapshot.
