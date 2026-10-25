# HLASM vector integer: shifts and rotates (red-dragon-6uyp.57.5)

Builds on the red-dragon-6uyp.90 foundation, units .57.1-.57.4, and
`docs/superpowers/specs/2026-10-23-hlasm-vector-design.md`. The 18 base mnemonics lower in one
module, `interpreter/hlasm/opcodes/vector_integer_shift.py`. No builtin.

## Bridge

A dump of every base and extended mnemonic shows che4z exports each extended form as its base
with the implied ES: VERIMB..G, VERLLB..G, VERLLVB..G, VESLB..G, VESLVB..G, VESRAB..G,
VESRAVB..G, VESRLB..G, VESRLVB..G with ES 0-3. VSL, VSLB, VSRA, VSRAB, VSRL and VSRLB carry
three registers; VSLD, VSLDB and VSRD carry I4 as an immediate (a negative or past-255 value
arrives as written, so the lowering takes its 8-bit field image, R108). The VRS-a forms carry
D2(B2) as a storage operand. No bridge fix is needed.

## PoO facts (SA22-7832-14, chapter 22)

Allowed sets are the full-facility ones (R37): vector-enhancements 2 is installed. An invalid ES
or a set must-be-zero I4 bit abends S0C6 at lowering (R34). No instruction here changes the CC.

| Mnemonic | Page | Fields | Result |
|---|---|---|---|
| VERLLV | 22-27, 22-28 | M4 ES 0-3 | each V2 element rotated left by the matching V3 element, modulo the element's bits |
| VERLL | 22-28 | M4 ES 0-3 | each V3 element rotated left by the low bits of the D2(B2) address, modulo the element's bits; the address is not used for data |
| VERIM | 22-28, 22-29 | M5 ES 0-3, I4 count | each V2 element rotated left by I4 modulo the element's bits; where V3 has a one the rotated bit replaces V1's bit, elsewhere V1 is unchanged |
| VESLV, VESL | 22-29 | M4 ES 0-3 | shift left, zeros in; count from V3's element (VESLV) or the address (VESL), modulo the element's bits |
| VESRAV, VESRA | 22-30 | M4 ES 0-3 | shift right, vacated bits from the element's original sign bit |
| VESRLV, VESRL | 22-30 | M4 ES 0-3 | shift right, zeros in |
| VSL | 22-31 | none | each byte of V2 shifted left by bits 5-7 of the matching byte of V3; vacated bits from the byte to the right, zeros into the rightmost byte |
| VSLB | 22-31 | none | V2 shifted left by the byte count in bits 1-4 of byte 7 of V3, zeros in |
| VSLD | 22-31, 22-32 | I4 bits 5-7 count, bits 0-4 must be zero | the 128 bits of V2 ‖ V3 starting at bit I4 |
| VSLDB | 22-32 | I4 bits 4-7 index | the 16 bytes of V2 ‖ V3 starting at byte I4; bits 0-3 "should contain zeros; otherwise the results are unpredictable" |
| VSRA | 22-32 | none | each byte of V2 shifted right by bits 5-7 of the matching byte of V3; vacated bits from the byte to the left, bit 0 of V2 into the leftmost byte |
| VSRAB | 22-32 | none | V2 shifted right by the byte count in bits 1-4 of byte 7 of V3, bit 0 in |
| VSRD | 22-33 | I4 bits 5-7 count, bits 0-4 must be zero | the 128 bits of V2 ‖ V3 starting at bit 128 − I4 |
| VSRL | 22-33 | none | as VSRA with zeros into the leftmost byte |
| VSRLB | 22-33 | none | as VSRAB with zeros in |

**Per-byte counts.** VSL, VSRA and VSRL make the result unpredictable when the bytes of V3
differ only "if the vector-enhancements facility 2 is not installed". It is installed, so each
byte takes its own count and its vacated bits come from its neighbour.

**Programming notes.** VERLL and VERIM: a negative count rotates right (its field image, modulo
the element's bits). VSLD's example on 22-32 (V2 0123…3210, V3 F0E1…1E0A, I4 4) gives
1234…210F; the VM test uses it.

Unpredictable and not asserted: VSLDB with I4 bits 0-3 set (the lowering uses bits 4-7).

## Design

- One element operation per kind (left, right logical, right arithmetic, rotate) over an
  element value and a count already reduced modulo the element's bits. The VRS-a forms compute
  the count once from the address; the VRR-c forms take each element's count from V3; VERIM
  takes a constant.
- VSLB, VSRLB and VSRAB are the same operations on the whole 128-bit register, the count being
  bits 1-4 of byte 7 times 8.
- VSL, VSRL and VSRA unroll per byte over a 16-bit window of the 136-bit value V2 extended by a
  byte (zeros on the right for VSL, zeros or sign bits on the left for VSRL and VSRA).
- VSLD, VSRD and VSLDB shift the 256-bit V2 ‖ V3 right by a static amount and keep 128 bits.
- Every form reads its sources before writing V1, so V1 may name any source.

## Commits

1. `feat(hlasm): vector integer shifts and rotates` — module, registration, unit and VM tests,
   hlasm.md, bead note, `issues/issues.jsonl`.
