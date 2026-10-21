# HLASM Opcode Unit — Boolean AND, OR and Exclusive OR (red-dragon-6uyp.30)

**Goal:** lower the 54 base mnemonics of red-dragon-6uyp.30.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14) pages AND, AND IMMEDIATE, AND WITH COMPLEMENT,
EXCLUSIVE OR, EXCLUSIVE OR IMMEDIATE, NAND, NOR, NOT EXCLUSIVE OR, OR, OR IMMEDIATE,
OR WITH COMPLEMENT.

## Semantics (from the PoO pages)

- Every form: CC 0 result zero, 1 result nonzero. No interruption beyond access.
- Register and storage: N, NY, NR, NRK (32); NG, NGR, NGRK (64); likewise O and X forms.
  RK forms combine R2 and R3 into R1. 32-bit forms write only the low word.
- Distinct-operand connectives (32 and 64): NCRK/NCGRK R2 AND ¬R3; OCRK/OCGRK R2 OR ¬R3;
  NNRK/NNGRK ¬(R2 AND R3); NORK/NOGRK ¬(R2 OR R3) (NOTR/NOTGR arrive as NORK R1,R2,R2);
  NXRK/NXGRK ¬(R2 XOR R3).
- Storage immediate: NI, NIY, OI, OIY, XI, XIY combine one storage byte with I2.
- Register immediate: the instruction combines I2 with a field of R1 and replaces only that
  field; the CC reflects only that field. NIHF/OIHF/XIHF bits 0-31, NIHH/OIHH 0-15,
  NIHL/OIHL 16-31, NILF/OILF/XILF 32-63, NILH/OILH 32-47, NILL/OILL 48-63.
- Storage to storage: NC, OC, XC D1(L,B1),D2(B2), L bytes (as written, 1-256), left to
  right, each result byte stored before the next is fetched, so overlap is honoured
  (XC A,A clears; OC A+1(n),A propagates). CC from the whole result.

## Shared pieces

- Refactor first: `logical_add_subtract.py`'s register/storage result-and-CC lowering and
  its storage-immediate form move to `opcodes/result_and_cc.py`; the bit-field mask and a
  field source/sink (`field_of`, `into_field`) go to `data_movement.py`, and
  `load_address_immediate.py` uses `into_field`.
- New `interpreter/hlasm/boolean_connective.py`: a frozen value naming the binop and
  whether the right operand and the result are complemented; the eight connectives.
- New in `fixed_width_ir`: `build_boolean_cc_ir(func_name, bits, connective)` returning
  (result, nonzero CC), operands wrapped to the width first.
- New `interpreter/hlasm/opcodes/boolean.py`: table rows per mnemonic; the SS forms as one
  IR loop over the bytes (counter and CC accumulator in variables), not unrolled.
- `effective_address.based_address` for a D(L,B) operand.

## Tests

- Unit `test_fixed_width_ir.py`: the builder on vectors per connective and width.
- Unit `test_boolean_lowering.py`: NRK, NG, NI, NIHH, NILF, NNGRK read/write their
  widths and set the CC; NC is one loop (one back branch) whose IR size does not grow
  with L; no SYMBOLIC.
- Integration `test_boolean.py`, programs in `boolean_programs.py`: one case per mnemonic
  (result registers, CC), both CCs across the unit; NIHH CC 0 with the rest of R1 nonzero;
  XC A,A clears; OC overlap propagates a byte; NC of 16 bytes.
- z390 `test_boolean_differential.py`: every case against z390; differences pinned, or
  PoO-derived values where z390 lacks the instruction.

## Commits

1. Plan.
2. Refactor: shared result-and-CC lowering and field source/sink.
3. Builder, connectives, lowering, tests, `docs/frontend-design/hlasm.md`; bead note;
   issues snapshot.
