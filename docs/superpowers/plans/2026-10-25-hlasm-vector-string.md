# HLASM vector string (red-dragon-6uyp.57.6)

Six base mnemonics, PoO SA22-7832-14 chapter 23: VFAE, VFEE, VFENE, VISTR, VSTRC, VSTRS.
Every extended mnemonic arrives from the bridge as its base with the implied M fields
(dumped; no export is wrong).

## PoO facts

- All six: ES 0-2 (B, H, F); 3-15 is a specification exception. The index result is a
  byte index (element index × width) in byte 7 of V1, all other bytes zero; 16 when
  nothing is found. Elements compare as unsigned integers.
- Flag bits: IN 8, RT 4, ZS 2, CS 1. CS 0 leaves the CC unchanged.
- **VFAE** (23-2/3), M4 ES, M5 IN RT ZS CS, no reserved bits. IR1: V2 element equals any V3
  element, inverted by IN. IR2: V2 element is zero (ZS), else all false. RT 0: index of the
  lowest true in either. RT 1: elements of IR1 all ones, others zero; IR2 not shown. CC 0:
  ZS and no IR1 true below the first IR2 true; 1: IR1 some, IR2 none; 2: ZS and an IR1 true
  below the first IR2 true; 3: none in either.
- **VFEE** (23-3/4), M5 bits 0-1 reserved (S0C6). Index of the first V2 = V3 element, or of
  the first zero V2 element with ZS. CC as VFAE.
- **VFENE** (23-4/5), M5 bits 0-1 reserved. Index of the first V2 ≠ V3 element, or of a zero
  V2 element with a strictly lower index (ZS). CC 0: the zero came first; 1: mismatch, V2
  lower; 2: mismatch, V2 higher; 3: all equal and no zero.
- **VISTR** (23-5/6), M3 ES, M5 bits 0-2 reserved. Copies V2 up to the first zero element;
  that element and all to its right become zero. CC 0 zero found, 3 none.
- **VSTRC** (23-6/8), M5 ES, M6 IN RT ZS CS. Even-odd V3 pairs are range limits; each V4
  element's bits 0-2 are E (equal), L (low), H (high); other bits should be zero (ignored).
  A range is true when both comparisons are true. Result and CC as VFAE.
- **VSTRS** (23-8/11), vector-enhancements 2. M5 ES, M6 bits 0, 1, 3 reserved; the CC is
  always set. Substring length is V4 byte 7; with ZS, the lesser of it and the byte position
  of V3's first zero element. Figures 23-2 and 23-3: for k = 0, width, … the first k where
  V2[k:k+len) = V3[0:len) with k+len ≤ str_len (full, CC 2), or, with no zero in V2,
  k+len > 16 and V2[k:16) = V3[0:16−k) (partial, CC 3). Length 0 is a full match at 0.
  No match: CC 1 if ZS found a zero in V2, else CC 0. str_len is 16, or the byte position
  of V2's first zero element with ZS. Length > 16, or not a multiple of the width, is
  unpredictable.

## Approach

One module, `vector_string.py`. Spec §2: each instruction's body is an `IrFunction` per
element size and static flag combination (IN, RT, ZS), defined on first use; CS is applied
at the call. Lane arithmetic on the whole 128-bit value: per-element zero, equal and
unsigned-below flags as one bit per element, the leftmost true element by smearing right,
its index by counting the smeared elements. No builtin.

## Tests

Unit: IR shape per family, S0C6 on reserved ES and M bits, no SYMBOLIC. VM: one case per
behaviour family with expected images from an independent scratch model of the PoO text,
CC per outcome, V1 equal to a source, and S0C6 with storage unchanged.
