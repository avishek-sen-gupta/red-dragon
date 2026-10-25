# HLASM vector support: loads and stores (red-dragon-6uyp.57.1)

Builds on the red-dragon-6uyp.90 foundation and
`docs/superpowers/specs/2026-10-23-hlasm-vector-design.md`. All 38 base mnemonics lower in
one module, `interpreter/hlasm/opcodes/vector_memory.py`. No builtin: a VR is a 128-bit
integer, and every family is loads, stores, shifts and masks.

## Bridge

A dump of every base and extended mnemonic shows che4z exports each extended form as its
base with the implied M3 (VLREPB..G 0-3, VLLEZB..G 0-3 and VLLEZLF 6, VLBRH..Q 1-4,
VLBRREPH..G 1-3, LDRV 3, LERV and VLLEBRZE 6, VLLEBRZH..G 1-3, VLERH..G and VSTERH..G 1-3,
VSTBRH..Q 1-4, STERV and STDRV 0). VRV operands arrive with the VR number as the storage
operand's index. No fork change is needed.

## PoO facts (SA22-7832-14, chapter 21)

Alignment hints (M3 of VL, VST, VLM's and VSTM's M4) are ignored. Every check below is a
specification exception, decided at lowering, before any access (R34). Allowed M values are
the full-facility sets (R37).

| Mnemonic | Format | M field | Bytes touched |
|---|---|---|---|
| VL, VST | VRX | M3 hint | 16 |
| VLR | VRR-a | - | none |
| VLM, VSTM | VRS-a | M4 hint; more than 16 registers is a specification exception; V1 to V3 wraps 31 to 0 | 16 per register |
| VLL, VSTL | VRS-b | - | min(R3 bits 32-63, 15) + 1, from byte 0; VLL zeroes the rest of V1 |
| VLBB | VRX | M3 0-6, block 64 << M3 | up to the block boundary, at most 16; spec: the rest of V1 zero |
| VLREP | VRX | M3 ES 0-3 | one element, replicated |
| VLEB/H/F/G, VSTEB/H/F/G | VRX | M3 index < 16/8/4/2 | one element |
| VLEIB/H/F/G | VRI-a | M3 index; I2 sign-extended to the element | none |
| VLLEZ | VRX | M3 ES 0-3 (rightmost element of the left doubleword), 6 (left-aligned word) | one element; rest of V1 zero |
| VGEF, VGEG, VSCEF, VSCEG | VRV | M3 index < 4/2 | one element at D2 + B2 + element M3 of V2 |
| VLBR, VSTBR | VRX | M3 ES 1-4 | 16, each element's bytes reversed |
| VLBRREP | VRX | M3 ES 1-3 | one element, reversed, replicated |
| VLEBRH/F/G, VSTEBRH/F/G | VRX | M3 index < 8/4/2 | one element, reversed |
| VLLEBRZ | VRX | M3 ES 1-3, 6 | one element, reversed, placed as VLLEZ |
| VLER, VSTER | VRX | M3 ES 1-3 | 16, element order reversed |

## Order

1. Carry the .90 lows (trace label `vr`, VRV test V1 as VEC_REG).
2. Every family in one commit, with unit tests (IR per family, no SYMBOLIC), VM tests per
   behaviour, the docs and the bead notes.
