# HLASM Opcode Unit — Interlocked Update (red-dragon-6uyp.42)

**Goal:** lower CS, CSY, CSG, CDS, CDSY, CDSG; CAL, CALGF, CALG; CSST; LAA, LAAG, LAAL, LAALG,
LAN, LANG, LAO, LAOG, LAX, LAXG; LPD, LPDG; LPQ, STPQ; TS; PLO with every function code.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14): COMPARE AND LOAD, COMPARE (DOUBLE) AND SWAP, COMPARE AND
SWAP AND STORE, LOAD AND ADD (LOGICAL), LOAD AND AND / OR / EXCLUSIVE OR, LOAD PAIR DISJOINT,
LOAD PAIR FROM QUADWORD, STORE PAIR TO QUADWORD, TEST AND SET, PERFORM LOCKED OPERATION
(Figure 7-380 is the function-code table).

**Ruling R33:** the VM runs one CPU. Interlocks, serialization and what other CPUs observe hold
trivially; no lock is modelled. Everything one CPU sees is: results, CC, registers, `S0C8`
where the PoO allows it, and the `S0C6` alignment and register checks.

## Semantics

- CS, CSY (low words, word), CSG (64, doubleword); CDS, CDSY (low words of the R1 and R3 pairs
  as one 64-bit value, doubleword), CDSG (both pairs 128 bits, quadword). Equal: storage ← R3,
  CC 0. Unequal: R1 ← storage, CC 1. The boundary is checked before anything; che4z refuses an
  odd R1 or R3 for CDS*, so only the unit test reaches that `S0C6`.
- CAL R3,D1,D2: op1 at D1 compared with R3. Equal: R3 ← op2, CC 0. Unequal: R3 ← op1, CC 1.
  CAL words (low word of R3 kept high); CALGF compares a word, loads R3 whole (op2 doubleword,
  or op1 zero-extended); CALG doublewords. D1 aligned always; D2 only when it is accessed
  (equal), since the PoO leaves the unequal case model dependent.
- CSST D1,D2,R3: GR0 bits 56-63 FC (0 word, 1 doubleword, 2 quadword with R3 even), bits 48-55
  SC (store 2^SC bytes, 0-4); GR1 bits 33-59 the quadword parameter list (replacement at 0,
  store value at 16). Unassigned FC or SC, op1 off its boundary, op2 off 2^SC, odd R3 with FC 2
  abend `S0C6` first. Equal: op1 ← replacement, then op2 ← store value, CC 0. Unequal: R3 ← op1,
  CC 1. All fetches before stores.
- LAA* family: temp ← op2; op2 ← temp OP R3; R1 ← temp. CC as AR (with `S0C8` under the mask
  bit, after both stores), ALR, NR, OR, XR. Word or doubleword boundary.
- LPD, LPDG: R3 even; R3 ← op1, R3+1 ← op2 (low words or whole), CC 0 (one CPU: always
  interlocked). LPQ, STPQ: quadword ↔ R1:R1+1, CC unchanged.
- TS: CC = bit 0 of the byte, then the byte ← X'FF'.
- PLO: GR0 bits 32-54 nonzero `S0C6`. Test bit (55): CC 0 for FC 0-61, else 3; nothing else.
  Otherwise FC > 61 `S0C6`; the PLO-extension facility (z17) makes 0-61 valid, so GR1 is
  unused. Per FC: odd R1 (FC 4-22 even, register forms) or odd R3 (FC 8, 10) `S0C6`; D2 on its
  boundary (FC 0-29); the parameter list (D4) on a doubleword; D4 as an operand on its boundary;
  addresses in the list (bits 33-63) on theirs, checked only when the operand is accessed.
  Compares are unsigned and in order; an unequal one replaces its comparison value with the
  operand and sets CC 1 (CC 2 for DCS's second; CC 2 and UR byte 48 = k for FC 30-37). All
  equal: the stores in the PoO order, CC 0. Loads and stores (38-61) leave the CC.

## Shared pieces

- `place.py` (`Place`: read and write callables), `places.py` (register low word, whole
  register, joined pair, storage at an address, storage at an address held in a doubleword).
- `comparison.py` + `compare_chain.py`: compare places in order, refresh and branch out on the
  first unequal one, run the equal path. CS*, CDS*, CAL*, CSST and PLO share it.
- `value_tree.py`: the `<` tree over runtime values, moved out of `execute.py`; PLO's function
  codes and CSST's FC and SC use it.
- PLO: `locked_operation.py` (row: width, compares, unequal CC, UR marking, stores, even
  registers), `plo_frame.py`, `locked_operations.py` (the table, one row per FC built from
  Figure 7-380 offsets), `perform_locked_operation.py` (GR0 checks, tree, rows).
- Reused: ADD_32/64 (signed and logical), `build_boolean_cc_ir`, `apply_result_and_cc`,
  `emit_fixed_point_overflow_check`, `emit_alignment_check`, `even_odd_pairs`, `move`.
- New `opcodes/interlocked.py`, registered in `opcodes/__init__.py`.

## Tests

- Unit `test_interlocked_lowering.py`: CS reads storage once and branches on one compare; CDS
  odd R1/R3 and LPQ/STPQ/LPD odd R abend `S0C6`; LAA stores op2 before R1 and checks overflow;
  TS writes X'FF'; CAL's D2 check sits on the equal path; PLO table rows: every FC 0-61 present,
  widths and boundaries per Figure 7-380; no SYMBOLIC.
- Integration `test_interlocked.py`, programs in `interlocked_programs.py`: every mnemonic;
  equal and unequal for each compare form, R1 = base, CDS pairs, CALGF zero extension, CSST
  every FC and SC and each `S0C6`, LAA overflow CC 3 and the max-negative, LAAL carry, the
  boolean CCs, misaligned operands `S0C6`, TS on X'00' and X'80'.
- Integration `test_perform_locked_operation.py`, programs in
  `perform_locked_operation_programs.py`: every FC equal and (where it compares) unequal at
  each compare position, the UR byte, the test bit for FC 0, 61, 62, GR0 bits 32-54, FC 62,
  odd R1 and R3, a misaligned D2, D4 and pointed operand.
- z390 `test_interlocked_differential.py`, `test_perform_locked_operation_differential.py`:
  every case; z390 lacks CAL* (and, from its source, executes neither CSST nor PLO): PoO-derived
  expectations, stated; disagreements pinned and noted on red-dragon-6uyp.74.

## Commits

1. This plan.
2. CS, CDS, CAL, CSST, LAA family, LPD, LPQ, STPQ, TS: lowering, shared pieces, tests, docs.
3. PLO: table, lowering, tests, docs.
4. Bead note and snapshot.
