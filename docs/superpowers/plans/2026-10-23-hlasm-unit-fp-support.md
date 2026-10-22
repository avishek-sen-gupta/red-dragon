# HLASM Opcode Unit — Floating-point registers, load/store and support (red-dragon-6uyp.50)

**Goal:** lower CPSDR EFPC LCDFR LD LDGR LDR LDY LE LER LEY LFAS LFPC LGDR LNDFR LPDFR LXR
LZDR LZER LZXR SFASR SFPC SRNM SRNMB SRNMT STD STDY STE STEY STFPC. PFPO moved to .56 (R42).

**Contract:** `.superpowers/sdd/hlasm-wave1/unit-contract.md`. Semantics: z/Architecture
Principles of Operation (SA22-7832-14), pages 9-9 to 9-11 and 9-30 to 9-49. Rulings: R34
(checks before the first store), R35/R41 (FPR region, FPC word), R37 (fixed z17), R42.

## Semantics

- Machine state: `__hlasm_fprs`, a 16 x 8-byte region (initial 0), and `__hlasm_fpc`, an
  int (initial 0). AFP control is on; every FPR is usable; no AFP data exception.
- Short (E) operands are bits 0-31 of an FPR; a short result leaves bits 32-63 unchanged
  (PoO 9-9). LER, LE, LEY, LZER write the high word; STE, STEY store it.
- Long moves: LDR, LD, LDY, STD, STDY, LZDR, LDGR (GR to FPR), LGDR (FPR to GR).
- Extended: LXR, LZXR on pairs (r, r+2); r with bit 2 set (2,3,6,7,...) abends S0C6.
- Sign: LCDFR flips, LNDFR sets, LPDFR clears bit 0; CPSDR R1,R3,R2 takes R2 with R3's
  sign. No CC, no NaN handling.
- FPC: EFPC to GR bits 32-63; STFPC stores the word. LFPC (storage) and SFPC (GR bits
  32-63) load it after the PoO checks: bits 6-7, 14-15, 24, 28 must be zero and the BFP
  rounding mode (bits 29-31) must not be 4-6; otherwise a specification exception, S0C6,
  FPC unchanged. R41 names S0C7 for invalid FPC values; the PoO says specification, so
  S0C6.
- SRNM: bits 30-31 from the address, bit 29 zero. SRNMB: address bits 56-60 nonzero or
  mode 4-6 is S0C6; bits 29-31 from the address. SRNMT: bits 25-27 from the address.
- LFAS/SFASR: signaling flags are the old FPC byte 1 bits 0-5 (Figure 9-21 includes the
  quantum flag); load the source after the same checks; flags = source flags OR
  signaling. If signaling AND source masks is nonzero, the DXC from Figure 9-21 (by the
  leftmost enabled bit; o and u take w = signaling inexact) replaces FPC byte 2 and the
  run abends S0C7 after the store (completion).

## Shared pieces

- `hlasm_constants.py`: FPR region and FPC names and sizes. `machine.py`: their start-up
  allocation. `hlasm_emitter.py`: `load_fpr`/`store_fpr` and the high-word pair.
- `opcodes/floating_point_support.py`: the unit table, FPC checks and the signal step.

## Tests

- Unit `test_floating_point_support_lowering.py`: FPR region offsets and widths per form
  (short touches 4 bytes at 8r, long 8); invalid pairs abend with no access; LFPC/SFPC
  and SRNMB check before the FPC store; LFAS/SFASR store then trap; no SYMBOLIC.
- Integration `test_floating_point_support.py`, programs in
  `floating_point_support_programs.py`: every mnemonic through GPRs (LGDR, EFPC, LG of
  stored data). S0C6 cases leave FPC unchanged; the LFAS/SFASR trap reads the DXC.
- z390 `test_floating_point_support_differential.py`: agreed cases match; z390's initial
  FPC (70000000), short loads clearing bits 32-63, lossy sign copies of unnormalised
  values, missing FPC checks and missing LFAS/SFASR traps are pinned and noted on .74.

## Commits

1. This plan.
2. FPR/FPC state, the unit, tests, `docs/frontend-design/hlasm.md`.
