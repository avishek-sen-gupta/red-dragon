# HLASM wave 2: vector data layout

Extends `2026-10-21-hlasm-frontend-design.md` for wave 2 (vector, vector packed
decimal). It fixes the machine state and value shapes before any vector opcode is
lowered. PoO references are to SA22-7832-14.

## Scope

169 vector mnemonics (chapters 21-24; the earlier "170" was one too high) and 33
vector-packed-decimal mnemonics (chapter 25, plus VLRL, VLRLR, VSTRL, VSTRLR from
chapter 21). Chapter 26's NNP converts stay in wave 5.

## 1. Register file

- One region, `__hlasm_vrs`: 32 vector registers × 16 bytes, VR v at offset 16v,
  big-endian, initial zero. It replaces `__hlasm_fprs`. VLM/VSTM are one region
  copy of 16·n bytes.
- FPR f (0-15) is bytes 0-7 of VR f (PoO 2-6). The FPR accessors in `HlasmEmitter`
  keep their signatures; only the stride changes from 8 to 16. Short BFP in FPR
  bits 0-31 is vector short element 0.
- A scalar FP write, or a pair read, leaves bytes 8-15 unchanged. The PoO makes
  them unpredictable (2-6); unchanged is a permitted outcome.
- Extended scalar FP keeps the FPR pair (r, r+2): bytes 0-7 of VR r and VR r+2.
  Vector extended BFP (M4=4) uses all 16 bytes of one VR.

## 2. Values in IR

- A whole VR is one IR value: an unsigned 128-bit integer, read and written with the
  existing byte↔int path at width 16. No family needs an element list: permutes,
  element shifts, string ops and VPD are shifts and masks on this value, or on a
  256-bit concatenation of two.
- Element i of size s bytes (ES 0-4 → 1, 2, 4, 8, 16) occupies bytes
  [i·s, i·s+s) (PoO 21-2); as an integer `(v >> (128 − 8s(i+1))) & (2^(8s) − 1)`.
  Element counts are static, so element bodies unroll at lowering.
- Element access with a static index (VLEx, VSTEx, VREP, gather/scatter M3) reads or
  writes the region at 16v + i·s; an index at or above the element count is a
  specification exception at lowering.
- Element access with a runtime index (VLGV, VLVG: the low 12 bits of D2(B2)) uses
  index mod element count, so it never leaves the VR. The PoO leaves out-of-range
  results unpredictable (21-13, 21-16); mod is what z15 does.
- Element-wise operations are `IrFunction`s over whole-VR integers, defined once per
  program on first use. One function exists per operation, element size and
  combination of static M flags that change behaviour (S, XxC, rounding override, CS, IDC, ZS/IN/RT), so
  a single-element form never runs the other elements.
- **Return convention** (one for every element function): a single integer, the
  128-bit result in bits 0-127 and status above it — CC at bits 128-129, FPC flags
  at 136-143, VXC at 144-151 with bit 152 marking "trap". The caller splits it with
  shifts and masks; no builtin is involved.
- Element-wise BFP goes through the existing zarch_float builtins one element at a
  time inside such a function. No new arithmetic in zarch_float.

## 3. Operands

- che4z folds RXB into `VEC_REG`, so VR numbers arrive as 0-31. Extended mnemonics
  arrive as their base mnemonic plus the implied masks. An omitted trailing M operand
  is absent and defaults to 0.
- VRV operands `D2(V2,B2)` (VGEF, VGEG, VSCEF, VSCEG) arrive as a StorageOperand
  whose `index` is a VR number. The operand accessor returns its own typed value, so
  the GPR effective-address path cannot accept it. The V2 element is read before
  V1's element is written (V1 may equal V2).
- One helper reads an element size from an M field against the instruction's allowed
  set, and one checks must-be-zero M bits. Both raise S0C6 at lowering (R34). The
  allowed sets are the PoO's with every facility installed (fixed z17, R37).
  "Should be zero" bits and alignment hints are ignored.
- Runtime-length storage access (VLL, VSTL, VLRLR, VSTRLR, VLBB) touches only the
  bytes moved; length = min(GR, 15) + 1. VLBB zeroes bytes past the block boundary.
- `VZERO v` is exported by che4z as `VGBM 1,v` (wrong; `instruction_details.thh`
  transformation `{ { 1 } }` should be `{ { 1, 0 } }`). The foundation fixes it in
  the che4z fork with a test.

## 4. Control state and exceptions

- The vector enablement control (CR0 bit 46) is fixed on, like AFP (R37, R41). The
  DXC FE "vector disabled" exception is unreachable and not lowered.
- STFLE: floating-point and vector facilities count, as R37 says ("consistent with
  the facilities lowered"). The FP bits turn on now, in their own commit. The vector
  bits turn on together at the end of wave 2 (129, 135, 148, 198; 134, 152, 192,
  199), since the PoO makes them imply each other and a facility covers M-field
  values as well as mnemonics.
- Vector-processing exception, PIC 001B: VXC = source element index (bits 0-3) and
  code (bits 4-7: 1 invalid, 2 divide by zero, 3 overflow, 4 underflow, 5 inexact,
  8 integer divide) is stored in FPC byte 2 via `store_dxc`; the program abends
  S0DB, following `hlasm_constants` (S0D3 for PIC 13, S0DD for 1D).
- **Vector BFP has its own ending.** The scalar ladder stores before the flags and
  traps; vector is all-or-nothing (PoO 24-1). Every element is computed first. If
  any element has an enabled trap, nothing is stored, no flags are set and the VXC
  holds the lowest source index; overflow or underflow beat inexact on one element.
  Otherwise the result is stored and the element flags are ORed into the FPC. The
  ending reuses the scalar pieces that decode an outcome (`outcome_of`,
  `enabled_traps`, the FPC constants), not the ladder.
- Single-element mode (S): only element 0 is computed and only its bytes are written.
  Extended (M4=4) is element 0 = the whole VR.
- Integer divide (VD, VDL, VR, VRL; ES F, G, Q): divide by zero, and for VD also
  −max ÷ −1, trap with VIC 8 unless M5 IDC masks it (element result 0). A trap
  suppresses the whole instruction. Quotients truncate toward zero.
- Vector packed decimal: the VR is one 16-byte packed field, 31 digits and a sign in
  bits 124-127, reusing `packed_decimal`/`decimal_lanes` over the 128-bit value.
  - Invalid digit or sign → data exception, DXC 00 via `store_dxc`.
  - VDP, VRP, VSDP divide by zero → decimal divide, S0CB, suppressed.
  - Decimal overflow completes: truncated result stored, CC 3 if CS, then S0CA if
    the PSW decimal-overflow mask is on and IOM = 0. VCVB/VCVBG do the same with the
    fixed-point-overflow mask and S0C8; with M4 ORC set, overflow stores zeros.
  - VSCHP, VSCSHP, VCSPH produce or consume HFP and reuse the wave-1 HFP IR.
- EX of a vector instruction keeps today's S0C1 when R1 is nonzero (EX would change
  V1 and V2's low bits). Documented limit, tracked on red-dragon-6uyp.78.
- Unpredictable results (bits 64-127 after scalar FP, out-of-range VLGV/VLVG, S-mode
  elements 1-n, bytes past VLBB's boundary, VSCHP scale ≥ 8): the observed hardware
  behaviour where known, otherwise unchanged. Tests never assert them.

## 5. Tests

- Unit tests assert IR structure as in wave 1. `fp_trace.py` trace strings, the
  `test_machine.py` region read and `hlasm_helpers._fpr` move to a named VR stride
  of 16 in the foundation; no expected FP value changes.
- Integration tests run through the VM and read VRs back by storing them (VST,
  VSTEG) or moving them to GPRs (VLGV).
- There is no z390 differential for vectors: z390 executes no E6/E7 instruction.
  Expected values come from the PoO, cited in each test.

## 6. Order of work

1. Foundation, no behaviour change for existing instructions: `__hlasm_vrs`; FPR
   accessors at stride 16; VR and element access (static and runtime index); the
   return convention; the M-field helpers; the VRV operand; the VXC delivery helper;
   the VZERO bridge fix. All wave-1 z390 suites stay green.
2. STFLE FP bits (own commit).
3. Vector support instructions (chapter 21).
4. Vector integer (chapter 22), in units of 20-40 mnemonics.
5. Vector string (chapter 23).
6. Vector BFP (chapter 24), with its ending.
7. Vector packed decimal (chapter 25 and the four VD-facility loads/stores).
8. STFLE vector bits.

Steps 1 and 2 run now, so the register layout is fixed before more code depends on
it. Steps 3-8 wait until waves 3 and 4 are done: vector instructions appear mainly
in compiler output, while nearly every hand-written program needs system services
and macros first. Exact mnemonic lists per unit come from
`hlasm_asg/opcode_units.json` when the units are filed.
