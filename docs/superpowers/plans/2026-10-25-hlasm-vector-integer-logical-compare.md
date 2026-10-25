# HLASM vector integer: logical, compare, min/max, counts (red-dragon-6uyp.57.3)

Builds on the red-dragon-6uyp.90 foundation, units .57.1 and .57.2, and
`docs/superpowers/specs/2026-10-23-hlasm-vector-design.md`. The 24 base mnemonics lower in one
module, `interpreter/hlasm/opcodes/vector_logical_compare.py`. No builtin.

## Bridge

A dump of every base and extended mnemonic shows che4z exports each extended form as its base
with the implied masks: VNOT as VNO V1,V2,V2; VCEQB..Q, VCHB..Q and VCHLB..Q with ES 0-4 and
M5 0, their S forms with M5 1; VECB..Q, VECLB..Q, VMNB..Q, VMNLB..Q, VMXB..Q, VMXLB..Q, VLCB..Q,
VLPB..Q, VCLZB..Q and VCTZB..Q with ES 0-4; VPOPCTB..G with ES 0-3. VEVAL's I5 arrives as an
immediate. che4z requires all five operands of VCH. No fork change is needed.

## PoO facts (SA22-7832-14, chapter 22)

Allowed sets are the full-facility ones (R37): ES 4 is reserved only without the
vector-enhancements facility 3. An invalid ES abends S0C6 at lowering (R34). M5 bits 0-2 of the
compares are reserved "should contain zeros" and are ignored.

| Mnemonic | Page | Fields | Result |
|---|---|---|---|
| VN | 22-6 | - | V2 AND V3 |
| VNC | 22-6 | - | V2 AND NOT V3 |
| VEC, VECL | 22-8 | M3 ES 0-4 | CC from one element of V1 and V2, signed (VEC) or unsigned: 0 equal, 1 V1 low, 2 V1 high. The element is byte 7, halfword 3, word 1, doubleword 0 or quadword 0 (Figure 22-2) |
| VCEQ | 22-9 | M4 ES 0-4, M5 bit 3 CS | element all ones where V2 = V3, else zeros. CS: CC 0 all equal, 1 some, 3 none |
| VCH | 22-9 | M4 ES 0-4, M5 bit 3 CS | all ones where V2 > V3, signed. CS: CC 0 all high, 1 some, 3 none |
| VCHL | 22-10 | M4 ES 0-4, M5 bit 3 CS | as VCH, unsigned |
| VCLZ | 22-11 | M3 ES 0-4 | per element, the number of leftmost zeros; the element's bits if zero |
| VCTZ | 22-12 | M3 ES 0-4 | per element, the number of rightmost zeros; the element's bits if zero |
| VEVAL | 22-13 | I5 | each bit: I5 bit (A B C), A from V2, B from V3, C from V4, I5 bit 0 leftmost |
| VX | 22-15 | - | V2 XOR V3 |
| VLC | 22-17 | M3 ES 0-4 | per element, two's complement; overflow wraps, no exception |
| VLP | 22-17 | M3 ES 0-4 | per element, absolute value; overflow wraps, no exception |
| VMX, VMXL, VMN, VMNL | 22-18 | M4 ES 0-4 | per element, the greater (VMX) or smaller (VMN), signed, or unsigned for the L forms |
| VNN | 22-25 | - | NOT (V2 AND V3) |
| VNO | 22-25 | - | NOT (V2 OR V3); VNOT is VNO V1,V2,V2 |
| VNX | 22-25 | - | NOT (V2 XOR V3) |
| VO | 22-26 | - | V2 OR V3 |
| VOC | 22-26 | - | V2 OR NOT V3 |
| VPOPCT | 22-26 | M3 ES 0-3 | per element, the number of one bits |
| VTM | 22-37 | - | bits of V1 under the V2 mask: CC 0 all zero or mask zero, 1 mixed, 3 all one |

Where the brief differs: VEC and VECL compare byte 7, halfword 3, word 1, doubleword 0 or
quadword 0, the rightmost element of the left doubleword, not element 0. VPOPCT has no
quadword form.

## Shape

- The bitwise forms and VEVAL work on whole registers. VEVAL ORs one minterm per I5 bit that
  is one.
- VMN, VMNL, VMX, VMXL, VLC and VLP unroll one piece per element. Signed order is unsigned order
  after flipping each sign bit. A compare is the borrow of a subtraction.
- VCEQ, VCH and VCHL are element functions (spec §2), one per operation and element size,
  because the CC depends on every element. Each returns the element masks and the CC; the
  caller sets the CC only with CS, as VPKS does.
- VEC, VECL and VTM set the CC inline from one element or one AND.
- VPOPCT counts bits with the usual pair, nibble and byte sums over the whole register, then
  folds the byte counts into each element. VCLZ and VCTZ smear the leading (trailing) one
  across the rest of its element and subtract the population count from the element's bits.
- The borrow compare, the count-to-CC rule and the status-function call move from
  `vector_register.py` to `vector_fields.py` for both units to share.

## Tests

- Unit: per family IR structure (sources read whole, V1 written whole, CC writes), one function
  per compare and size with the CC only for CS, S0C6 for every invalid ES, no SYMBOLIC.
- VM: one case per family, read back with VST/VSTM and IPM; each S compare's CC 0, 1 and 3,
  VTM's three CCs, VEC/VECL's three CCs, signed against logical order with high-bit elements,
  ES 4 forms, V1 equal to a source for every three-operand family, the S0C6 refusals with
  storage unchanged. Expected values computed from the PoO, page cited per case.
