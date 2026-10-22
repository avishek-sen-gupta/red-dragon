# HLASM Opcode Unit — Storage-to-Storage and Storage-Immediate Moves (red-dragon-6uyp.35)

**Goal:** lower MVC, MVCIN, MVCL, MVCLE, MVCLU, MVCRL, MVGHI, MVHHI, MVHI, MVI, MVIY, MVN,
MVO, MVST, MVZ.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14), MOVE through MOVE ZONES (pages 7-330 to 7-345).
None of them is lowered yet; the seed fixture's MVC is only parsed.

## Semantics

- MVI, MVIY store one immediate byte. MVHHI, MVHI, MVGHI sign-extend the 16-bit immediate
  into 2, 4 or 8 bytes. CC unchanged.
- MVC, MVN, MVZ: L bytes (written length, 0 means 1), left to right, as if one byte at a
  time, so MVC 1(255,R),0(R) propagates a byte. MVN moves the right nibbles, MVZ the left
  nibbles. MVCIN reverses: the second-operand address is its rightmost byte. CC unchanged.
- MVCRL: length GR0 bits 56-63 plus one, moved right to left. CC unchanged.
- MVO: right to left; the source shifted left one nibble, the destination's right nibble
  kept, the source zero-extended or truncated on the left. Each source byte is fetched once,
  after the bytes to its right are stored.
- MVCL: R1 and R2 even, else S0C6. 24-bit lengths in R1+1 and R2+1, pad in R2+1 bits 32-39.
  CC 0/1/2 compare the lengths. Destructive overlap (A2 < A1 < A2 + min(L1, L2)) moves
  nothing and sets CC 3. At completion R1 += L1, R1+1 length 0, R2 += moved, R2+1 length
  L2 - moved; bits 32-39 of the length registers and the high words are kept.
- MVCLE, MVCLU: R1 and R3 even, else S0C6. 32-bit lengths; pad from the D2(B2) address,
  one byte (MVCLE) or two (MVCLU, even byte first). MVCLU abends S0C6 on an odd length.
  Ruling: the whole operand moves in one execution, so CC 3 never occurs.
- MVST: GR0 bits 32-55 nonzero is S0C6; the terminator is GR0 bits 56-63. Copy through the
  terminator, R1 points at it in the destination, R2 unchanged, CC 1. Never CC 3.

## Shared pieces

- `byte_loop`: `emit_counted_loop(start, bound, step, body)`; `emit_byte_loop` becomes its
  compile-time case. Loop constants are hoisted out of the body.
- `HlasmEmitter`: `load_bytes`/`write_bytes` (raw byte images at a register offset) and
  `image` (an integer's unsigned byte image); `store_storage` and the WTO loop use them.
- `specification_check`: a runtime condition abends S0C6; `alignment_check` uses it.
- `even_odd`: the even-register test over a chosen set of register operands.
- `data_movement.to_storage_at(index, width)`.
- `long_move.py`: MVCL, MVCLE, MVCLU over one move-then-pad core.
- `opcodes/ss_move.py`: the unit table; MVC copies a block in one region read and write
  unless the destination starts inside the source, then a byte loop.

## Tests

- Unit `test_ss_move_lowering.py`: MVI/MVHI/MVGHI store widths and no CC; MVC has a block
  move and a one-byte loop; MVN reads two bytes per iteration; MVCL abends S0C6 for an
  odd register at lowering; no SYMBOLIC.
- Integration `test_ss_move.py`, programs in `ss_move_programs.py`: every mnemonic, storage
  read back into registers, CC; MVC propagation, MVCL CC 0/1/2/3 and pad, MVCLE and MVCLU
  pads, MVCLU odd-length and MVST GR0 S0C6, MVO truncation and zero extension.
- z390 `test_ss_move_differential.py`: every case against z390, bar MVCRL (z390 lacks it;
  Principles of Operation value in the VM test).

## Commits

1. This plan.
2. Shared pieces, lowering, tests, docs, bead snapshot.
