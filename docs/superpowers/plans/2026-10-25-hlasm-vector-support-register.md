# HLASM vector support: register manipulation (red-dragon-6uyp.57.2)

Builds on the red-dragon-6uyp.90 foundation, unit .57.1 (`vector_memory.py`) and
`docs/superpowers/specs/2026-10-23-hlasm-vector-design.md`. The 23 base mnemonics lower in one
module, `interpreter/hlasm/opcodes/vector_register.py`. No builtin: a VR is a 128-bit integer,
and every family is shifts and masks on it, or on the 256-bit V2 || V3.

## Bridge

A dump of every base and extended mnemonic shows che4z exports each extended form as its base
with the implied masks: VZERO and VONE as VGBM 0 and X'FFFF'; VGMB..G, VLGVB..G, VLVGB..G,
VMRHB..G, VMRLB..G, VREPB..G, VREPIB..G, VUPHB..G, VUPLB/VUPLHW/VUPLF/VUPLG, VUPLHB..G and
VUPLLB..G with ES 0-3; VGEMB..Q and VBLENDB..Q 0-4; VSEGB/H/F 0-2; VPKH/F/G 1-3; VPKSH..G and
VPKLSH..G with M5 0, their S forms with M5 1. VLGV and VLVG take D2(B2) as a storage operand,
VLVGP two GPRs, VREPI a signed immediate. No fork change is needed.

## PoO facts (SA22-7832-14, chapter 21)

Every check below is a specification exception decided at lowering, before any access (R34).
Allowed sets are the full-facility ones (R37); "should be zero" bits are ignored. Where V1
names a source, the original source is used throughout.

| Mnemonic | Page | Fields | Result |
|---|---|---|---|
| VGBM | 21-6 | I2 | byte k of V1 all ones if bit k of I2 is one |
| VGM | 21-7 | M4 ES 0-3; I2, I3 mod element bits | ones from bit I2 to bit I3 in every element; I2 > I3 wraps past the last bit |
| VGEM | 21-7 | M3 ES 0-4 | element i all ones if bit i of V2 is one (bits 0 to count-1) |
| VLGV | 21-13 | M4 ES 0-3 | GR R1 = element (address low 12 bits) of V3, zero-extended; past the count unpredictable |
| VLVG | 21-16 | M4 ES 0-3 | element (address low 12 bits) of V1 = rightmost bits of GR R3; past the count unpredictable |
| VLVGP | 21-16 | - | V1 = GR R2 bits 0-63, GR R3 bits 64-127 |
| VMRH, VMRL | 21-17 | M4 ES 0-3 | left (VMRL: right) half elements of V2 to even, of V3 to odd elements |
| VPK | 21-18 | M4 ES 1-3 | each element of V2 || V3, rightmost half |
| VPKS | 21-18 | M4 ES 1-3, M5 bit 3 CS | as VPK, signed, saturating to the half-size range |
| VPKLS | 21-19 | M4 ES 1-3, M5 bit 3 CS | as VPK, unsigned, saturating to the half-size maximum |
| VPKS, VPKLS CC | 21-19 | CS on | 0 none saturated, 1 some but not all, 3 all; CS off: unchanged |
| VPERM | 21-20 | - | byte i of V1 = byte (V4 byte i & 31) of V2 \|\| V3 |
| VPDI | 21-20 | M4 bit 1, bit 3 | V1 doubleword 0 = V2 doubleword (bit 1), 1 = V3 doubleword (bit 3) |
| VREP | 21-21 | M4 ES 0-3; I2 index below the count | element I2 of V3 in every element |
| VREPI | 21-21 | M3 ES 0-3 | I2 sign-extended in every element; for bytes, I2 bits 8-15 |
| VSEL | 21-22 | - | bit of V2 where V4 is one, of V3 where zero |
| VSEG | 21-22 | M3 ES 0-2 | each doubleword = its rightmost element sign-extended |
| VBLEND | 21-5 | M5 ES 0-4 | element of V2 where bit 0 of V4's element is one, of V3 otherwise |
| VBPERM | 21-5 | - | bit i of V1 bits 48-63 = bit (V3 byte i) of V2 \|\| 128 zeros; rest of V1 zero |
| VUPH, VUPL | 21-27, 21-28 | M3 ES 0-3 | left (VUPL: right) half elements of V2 sign-extended to double size |
| VUPLH, VUPLL | 21-28, 21-29 | M3 ES 0-3 | as VUPH and VUPL, zero-extended |

The brief said VSEL and VBLEND work over the 256-bit concatenation; the PoO has them bitwise
and element-wise on V2, V3 and V4. VBPERM's second half is 128 zeros, not V3.

## Shape

- Byte moves (VMRH, VMRL, VPK, VPDI, VUPLH, VUPLL) gather bytes of V2 || V3 by a static map.
- VUPH, VUPL, VSEG and VBLEND widen a sign bit over its element with one shift and one
  multiply per register; VBLEND then selects as VSEL does.
- VGBM and VGM are constants. VREP and VREPI replicate an element by a multiply.
- VGEM, VPERM and VBPERM unroll one piece per element, byte or bit.
- VLGV and VLVG reuse the run-time element access (index = address mod the element count; the
  count divides 4096, so this equals the low 12 bits mod the count).
- VPKS and VPKLS are element functions (spec §2), one per signedness and element size, that
  return the result and the CC in the element return convention; the caller sets the CC
  only with CS.

## Order

One commit: every family, unit tests (IR per family, `S0C6` checks, no SYMBOLIC), VM tests per
behaviour family, the docs and the bead notes.
