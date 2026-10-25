# HLASM vector integer: add, subtract, multiply, divide, sums (red-dragon-6uyp.57.4)

Builds on the red-dragon-6uyp.90 foundation, units .57.1-.57.3, and
`docs/superpowers/specs/2026-10-23-hlasm-vector-design.md`. The 35 base mnemonics lower in one
module, `interpreter/hlasm/opcodes/vector_integer_arithmetic.py`. No builtin.

## Bridge

A dump of every base and extended mnemonic shows che4z exports each extended form as its base
with the implied masks: VAB..VAQ, VACCB..Q, VAVGB..Q, VAVGLB..Q, VSB..Q, VSCBIB..Q, VMHB..Q,
VMLHB..Q, VMLB/VMLHW/VMLF/VMLG/VMLQ, VMAHB..Q, VMALHB..Q, VMALB/VMALHW/VMALF/VMALG/VMALQ with
ES 0-4; VMEB..G, VMLEB..G, VMOB..G, VMLOB..G, VMAEB..G, VMALEB..G, VMAOB..G, VMALOB..G, VGFMB..G
and VGFMAB..G with ES 0-3; VACQ, VACCCQ, VSBIQ, VSBCBIQ with M5 4; VDF..VRLQ with ES 2-4 and
their M5 operand; VMSLG with ES 3 and its M6 operand; VSUMB/H, VSUMGH/F, VSUMQF/G. che4z
requires M5 on the divide forms and M6 on VMSL. The fork exported VACQ and VACCCQ with register 4
in place of V4 and V4 as M5; it now appends M5 4 after V4 (fixed in the fork, with a test).

## PoO facts (SA22-7832-14, chapter 22)

Allowed sets are the full-facility ones (R37). An invalid ES abends S0C6 at lowering (R34).
Reserved "should contain zeros" bits (VD/VR M5 bits 1-3, VMSL M6 bits 2-3) are ignored. No
instruction here changes the CC.

| Mnemonic | Page | Fields | Result |
|---|---|---|---|
| VA | 22-4 | M4 ES 0-4 | per element V2 + V3, carry out ignored |
| VACC | 22-5 | M4 ES 0-4 | per element the carry out of V2 + V3 (1 or 0) |
| VAC | 22-5 | M5 must be 4 | V2 + V3 + bit 127 of V4, 128-bit, carry out ignored |
| VACCC | 22-6 | M5 must be 4 | the carry out of V2 + V3 + bit 127 of V4 |
| VAVG, VAVGL | 22-7 | M4 ES 0-4 | per element (V2 + V3 + 1) >> 1 over one extra bit, signed or unsigned |
| VCKSM | 22-7, 22-8 | - | the four words of V2 and word 1 of V3 summed with the carry out of bit 0 added back into bit 31 after each addition; the sum goes to word 1, zeros elsewhere |
| VD, VDL | 22-12, 22-13 | M4 ES 2-4, M5 bit 0 IDC | per element quotient, signed or unsigned, truncated toward zero (algebraic sign, zero positive) |
| VGFM | 22-16 | M4 ES 0-3 | per double-wide element, the carry-less products of the even and odd pair XORed |
| VGFMA | 22-16 | M5 ES 0-3 | VGFM XORed with the double-wide element of V4 |
| VMAL | 22-19 | M5 ES 0-4 | per element low half of V2 x V3 + V4 |
| VMAH, VMALH | 22-19, 22-20 | M5 ES 0-4 | per element high half of V2 x V3 + V4, signed or unsigned |
| VMAE, VMALE | 22-20 | M5 ES 0-3 | double-wide: even elements' product + the double-wide V4 element, carry ignored |
| VMAO, VMALO | 22-21 | M5 ES 0-3 | as VMAE with the odd elements |
| VMH, VMLH | 22-21, 22-22 | M4 ES 0-4 | per element high half of V2 x V3, signed or unsigned |
| VML | 22-22 | M4 ES 0-4 | per element low half of V2 x V3 |
| VME, VMLE, VMO, VMLO | 22-23, 22-24 | M4 ES 0-3 | double-wide product of the even (odd) elements, signed or unsigned |
| VMSL | 22-24 | M5 ES 3 only, M6 bit 0 even shift, bit 1 odd shift | even product (shifted left 1 if bit 0) + odd product (shifted if bit 1) + V4, 128-bit, unsigned, carries ignored |
| VR, VRL | 22-27 | M4 ES 2-4, M5 bit 0 IDC | per element remainder, the dividend's sign (zero positive) |
| VS | 22-33, 22-34 | M4 ES 0-4 | per element V2 - V3, wraps |
| VSCBI | 22-34 | M4 ES 0-4 | per element the carry out of V2 + NOT V3 + 1: 1 when V2 >= V3 unsigned |
| VSBI | 22-35 | M5 must be 4 | V2 + NOT V3 + bit 127 of V4, 128-bit |
| VSBCBI | 22-35 | M5 must be 4 | the carry out of V2 + NOT V3 + bit 127 of V4 |
| VSUMG | 22-36 | M4 ES 1-2 | per doubleword, its halfwords (words) of V2 + the rightmost one of V3's doubleword |
| VSUMQ | 22-36 | M4 ES 2-3 | the words (doublewords) of V2 + the rightmost one of V3, in the quadword |
| VSUM | 22-36, 22-37 | M4 ES 0-1 | per word, its bytes (halfwords) of V2 + the rightmost one of V3's word |

**Integer divide (22-2, 22-12, 22-13, 22-27; 6-20).** A zero divisor, and for VD only the
negative maximum divided by -1, is an integer-divide condition. With IDC zero it is a
vector-processing exception: the instruction is suppressed for all elements, the FPC gets the
VXC (index of the lowest faulting source element in bits 0-3, VIC 8 in bits 4-7), and the
program abends S0DB. With IDC one the exception is not recognized and that element's result is
zero. VR has no overflow condition.

Where the brief differs: VD/VR forms exist only at ES 2-4 (no byte or halfword). The
negative-maximum-by-minus-one condition belongs to VD alone.

## Shape

- Element-wise forms reuse `element_wise` (moved with `element_of` and `assembled` from
  `vector_logical_compare.py` to `vector_fields.py`): one piece per element, masked to the
  element when assembled, so wraparound needs no extra code.
- Signed values are the unsigned element minus 2^bits when the sign bit is on. The signed
  average flips each sign bit, takes the unsigned average and flips back.
- The double-wide forms (VME..VMALO, VGFM, VGFMA, VMSL) read the even and odd elements of V2 and
  V3 and the double-wide element of V4 and assemble at the double size.
- Carry-less multiply XORs the multiplicand shifted by each one bit of the multiplier.
- VCKSM folds the carry back after each of the five additions.
- VD, VDL, VR, VRL call one element function per operation, size and IDC. It returns the
  result, the VXC and the trap bit in the element return convention; the caller abends S0DB
  through the .90 VXC helper before V1 is written when the trap bit is on.

## Tests

- Unit: IR structure per family (sources read whole, V1 written whole), one divide function per
  operation, size and IDC with the S0DB path only without IDC, S0C6 for every invalid ES, no
  SYMBOLIC in any of the 35.
- VM: one case per family with V1 equal to a source; wraparound and carry out at every ES;
  signed against logical high multiply on negative elements; multiply-and-add overflow; VMSL
  with each shift flag; VGFM with a nonzero XOR fold; VCKSM with an end-around carry; divide by
  zero trapping (S0DB, FPC byte 2, V1 unchanged) and masked by IDC; VD of the negative maximum
  by -1; S0C6 refusals with storage unchanged. Expected values from the PoO, page cited.
