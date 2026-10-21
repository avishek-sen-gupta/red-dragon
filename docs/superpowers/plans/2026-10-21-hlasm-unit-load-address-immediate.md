# HLASM Opcode Unit — Load Address and Immediates (red-dragon-6uyp.24)

**Goal:** lower the 30 base mnemonics of red-dragon-6uyp.24 (extended LFI → IILF, LLGFI → LLILF,
LLGHI → LLILL arrive resolved). LA moves here from `opcodes/seed.py`, behaviour unchanged.

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14), AMODE 31. No instruction here changes the CC.

## Semantics (from the PoO pages)

- LA, LAY, LAE, LAEY: EA into bits 33-63, bit 32 zero, bits 0-31 unchanged. LAE/LAEY also
  load access register R1; access registers are not modelled (Known Gap), the GR result is LA's.
- LARL: section base + offset into bits 33-63, same rule.
- LXAB/H/F/G/Q, LLXAB/H/F/G/Q: ((low word of X2 + DX2) mod 2^32, extended to 64 bits) shifted
  left 0-4, plus GR B2 (64-bit); bits 33-63 of that into R1. In AMODE 31 only bits 33-63 survive,
  and they depend only on the low 31 bits of each term, so the sign (LXA) and zero (LLXA)
  extensions give the same result. X2 or B2 = 0 means absent. che4z types R1 as a 4-bit mask.
- LHI: 16-bit immediate sign extended to 32, low word. LGHI: to 64. LGFI: 32 → 64.
- LLIHF 0-31, LLIHH 0-15, LLIHL 16-31, LLILF 32-63, LLILH 32-47, LLILL 48-63; rest zero.
- IIHF, IIHH, IIHL, IILF, IILH, IILL: same positions; rest unchanged.
- The bridge hands immediates signed or unsigned (`LLILF X'FFFFFFFF'` → -1, `LHI X'FFFF'` →
  65535), so each lowering takes the immediate's bit image of its field width first.

## Shared pieces

- `effective_address.indexed_address(operand, shift)`: (D + X) << shift + B, masked to 31 bits;
  `effective_address` is the shift-0 case (same IR as today).
- `data_movement`: sources `storage_address`, `relative_target`, `immediate(bits)`; transform
  `shifted(bits)`; sink `into_bits(field_mask)` merging into the 64-bit register.
- Module `interpreter/hlasm/opcodes/load_address_immediate.py`, rows of `move(...)`.

## Tests

- Unit `tests/unit/hlasm/test_load_address_immediate_lowering.py`: LA reads base and index low
  words and writes only the low word; LXAG has an LSHIFT by 3 between index and base;
  IIHL reads and writes the full GPR; LLIHF writes the full GPR without reading it; no SYMBOLIC,
  no CC store.
- Integration `tests/integration/hlasm/test_load_address_immediate.py`, programs in
  `load_address_immediate_programs.py`, registers preloaded with `X'A5…'` by LMG:
  addresses (LA/LAY/LAE/LAEY with index+base, high bit dropped, high word kept; LARL then L
  through the address); indexed addresses (all ten, negative DX2 and a 32-bit wrap);
  immediates (sign-extending, logical, inserting — every mnemonic and extended mnemonic);
  CC unchanged across all of them.
- z390 `tests/z390/test_load_address_immediate_differential.py`: address, immediates and
  inserts families against z390 registers and CC. z390 assembles but does not execute
  LXA*/LLXA*: their expected values are PoO-derived in the VM test, stated there.

## Commits

1. Plan.
2. Lowering, tests, `docs/frontend-design/hlasm.md`; bead note.
3. `fix(hlasm): load/store review leftovers` — halfword relative operands skip the alignment
   check; hlasm.md Known Gaps (LM/STM/LMD no 2 GiB wrap; ICM mask 0 no access exception) and
   the storage_layout entry (doubleword-aligned section bases from address 4096); snapshot.
