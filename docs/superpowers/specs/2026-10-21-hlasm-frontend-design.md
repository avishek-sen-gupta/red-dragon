# HLASM frontend — design

## Intent

Add IBM High Level Assembler (HLASM) as a deterministic RedDragon frontend: assembler
source is lowered to the existing IR and runs on the existing VM. The endgame is
mixed-language execution — a COBOL (or CICS) program `CALL`s an HLASM subroutine,
and HLASM calls back into COBOL — with both sides as IR in one linked image.

The first priority is complete coverage of the general, decimal and floating-point
instruction sets (wave 1). Running real programs follows: system services and COBOL
linkage (wave 3), then the macro language (wave 4). Vector (wave 2) comes after them,
since vector instructions appear mainly in compiler output; only its register layout
is fixed first (`2026-10-23-hlasm-vector-design.md`). The specialised facilities
come last (wave 5). The first runnable milestone is a
standalone HLASM program that starts, runs and stops; the register and storage model
must not rule out cross-language linkage.

An LLM-backed HLASM path already exists (`LLMFrontend(language="hlasm")`,
`scripts/demo_hlasm.py`). This frontend is the deterministic replacement and does
not touch it.

## Goals

- Every problem-state z/Architecture opcode in wave 1 (below) lowers to IR and
  matches z390 on the same program.
- HLASM compiles to on-disk unit files and links through the shared linker, exactly
  as COBOL does in `interpreter/project/cobol_compile.py`: parse →
  `<stem>-<digest>.ast.json`, lower → `<stem>[.<name>]-<digest>.unit.json`,
  link → `image-<digest>.linked.json`. The digest covers source bytes and lowering
  settings; an unchanged program is never re-lowered.
- HLASM and COBOL units link into one image and call each other.
- No new IR opcodes (see *IR policy*).

## Non-goals

- Privileged, semi-privileged, control and I/O instructions (`LPSW`, `SSK`, `LCTL`,
  `SSCH`, …). Application code cannot execute them.
- Self-modifying code. Instructions do not live in addressable memory, and nothing
  emits instruction encodings.
- Storage protection, real/absolute addressing, PSA and z/OS control-block
  emulation beyond what a supported system macro needs.
- Shipping or depending on IBM's `SYS1.MACLIB`.

## Anti-goals

- A second assembler in Python. Symbol values, lengths, attributes, location
  counters and `USING` resolution come from che4z and are trusted; disagreements
  are fixed in the fork, found by the z390 oracle.
- Changes to `hlasm_export` in the che4z fork. It stays as it is for its existing
  BMS consumers.
- Main going red. Every merge into `main` passes the full verification gate.

## Scope and waves

Source: binutils `opcodes/s390-opc.txt` (to z17/arch15) — 1,245 unique opcodes,
2,667 mnemonics including extended forms. Problem-state: ≈1,126 opcodes.
The authoritative references are z/Architecture Principles of Operation
SA22-7832-14, the Reference Summary SA22-7871-11, and HLASM V1R6 Language
Reference SC26-4940-09. Exact HLASM mnemonic spellings come from the Language
Reference and Reference Summary, not binutils (which has non-HLASM aliases).

**Wave 1**

| Group | Opcodes | Units |
|---|---|---|
| General (fixed-point, logical, branch, move, compare, shift, …) | 568 | ≈23 |
| Packed decimal | 23 | 4 |
| Floating point (BFP, HFP, DFP, FP support) — last in wave 1 | 307 | ≈7 |

**Wave 2 (after waves 3 and 4):** vector (169), vector-decimal (33). Data layout in
`2026-10-23-hlasm-vector-design.md`.

**Wave 3 — real programs run:** `SAVE`/`RETURN`, `STORAGE`/`GETMAIN`/`FREEMAIN`,
`CALL`/`LINK`/`LOAD`, `DCB`/`OPEN`/`GET`/`PUT`/`CLOSE`, and COBOL↔HLASM linkage (see
*System services* and *Cross-language linkage*).

**Wave 4 — the macro language:** conditional assembly, SET symbols, attributes,
system variable symbols, and the remaining DC types and type extensions.

**Wave 5 — specialised facilities:** NNPA (6), crypto (13, excluding the privileged
`PCKMO`), transactional execution (7), sort, compression and deflate.

### Opcode units

Opcodes are grouped into ≈35 units of 15–40 opcodes, one issue each — a family
sharing IR helpers and a test shape. Every problem-state opcode belongs to exactly
one unit; a coverage check over the opcode table proves it.

General: load/store; load address and immediates; signed add/subtract; logical
add/subtract with carry/borrow; multiply/divide; compare (signed and logical);
compare-and-branch and compare-and-trap; boolean (`N/O/X`, `NC/OC/XC`, `NI/OI/XI`,
immediate forms); shifts and rotates incl. `RISBG` family; branch on condition and
extended mnemonics; branch-and-link/save (`BAL`, `BAS`, `BRAS`, `BASSM`, `BSM`);
loop branches (`BCT`, `BXH`, `BXLE`, relative forms); SS moves (`MVC`, `MVCL`,
`MVCLE`, `MVI`, `MVN`, `MVZ`, `MVO`, `MVCIN`, `MVST`); SS compares (`CLC`, `CLCL`,
`CLCLE`, `CLST`, `CUSE`); translate (`TR`, `TRT`, `TRTR`, `TRE`, `TRxx`); test under
mask (`TM`, `TMxx`); `EX`/`EXRL`; load-and-test/positive/negative/complement;
conditional load/store and select (`LOC`, `STOC`, `SELR`), `POPCNT`, `FLOGR`;
interlocked (`CS`, `CDS`, `CSG`, `LAA`, …; single-threaded, so trivially atomic);
Unicode conversion and string search (`CUxx`, `SRST`); high-word; miscellaneous
(`IPM`, `SPM`, `STCK`, `STCKF`, `EPSW`, `TRAP`, `CKSM`).

Decimal: packed arithmetic (`AP`, `SP`, `MP`, `DP`, `ZAP`, `SRP`); compare/test
(`CP`, `TP`); conversion (`PACK`, `UNPK`, `PKA`, `PKU`, `UNPKA`, `UNPKU`, `CVB*`,
`CVD*`); edit (`ED`, `EDMK`).

Floating point: FP registers, load/store and support; BFP arithmetic; BFP
conversions; HFP arithmetic; HFP conversions; DFP arithmetic; DFP conversions.

## Foundation units

These precede the opcode units.

1. **AST bridge.** A new C++ target in the che4z fork, separate from
   `hlasm_export`. It emits the macro-expanded statement stream as JSON: per
   statement, label, opcode, operand tree, source location and originating macro
   expansion; plus che4z's resolved symbol table (values, lengths, attributes,
   relocatability), section layout and `USING` state. Conditional assembly and
   macro expansion necessarily run inside it. Verify early what che4z does *not*
   compute — believed to be `DC` byte images and instruction encodings — and
   compute those in Python.
2. **Python model.** A new sibling root package (name to settle; `hlasm_asg` is the
   working name) parses the bridge JSON into Pydantic models on arrival. Like
   `cobol_asg` it is a leaf: an import-linter contract keeps it from importing
   `interpreter`. Lowering lives in `interpreter/hlasm/`.
3. **Machine model.** 16 GPRs as a byte region (so `STM`/`LM`/`STMG` address them
   directly), the condition code, the program mask and the addressing mode. Each
   CSECT's storage — instructions' operand data, `DC`/`DS` contents and literal
   pools — is a byte region in the VM's flat address space, so `LA R1,FIELD` yields
   a real address that COBOL can also dereference.
4. **Fixed-width arithmetic.** IR-built functions for 32/64-bit wraparound, carry,
   borrow, overflow and CC derivation, over the VM's unbounded ints. Implement the
   already-declared but unimplemented `>>>` `BinopKind` in the VM's BINOP table.
5. **Branch dispatch.** A label↔address table and an IR dispatch chain, so branches
   to computed addresses (`BR R14`, `BALR`, `B 0(R15)`, `A(label)`, `V(name)`)
   resolve. Follow the GO TO DEPENDING pattern (`interpreter/cobol/ordinal_dispatch_ir.py`).
6. **Compile and link.** The three on-disk stages above, unit files linked through
   `link_units`; a test proves a second compile of unchanged source reuses the unit
   file. `EXTRN`/`ENTRY`/`V(...)` map onto the existing export table.
7. **z390 harness.** Runs the same program in z390 and RedDragon and compares
   registers, storage and output. Tests carry a new `z390` pytest marker, excluded
   from the default run like `nist` (`addopts`), run with `-m z390`.
8. **Start and stop.** A standalone program entered at its entry point, returning
   via `BR R14` with R15 as the return code.

## IR policy

No new IR opcodes. Gaps are filled by IR-built functions from primitive builtins,
following `interpreter/cobol/ir_encoders.py`. Known gaps and their IR routes:

- Registers, CC → variables / region bytes.
- Width, carry, overflow → masking functions (foundation 4).
- Computed branches → dispatch chain (foundation 5).
- `EX`/`EXRL` → lower the target instruction with its length/register field taken
  from the runtime value.
- Runtime lengths (`MVC` under `EX`, `MVCL`, `CLCL`) and overlapping `MVC` → byte-at-
  a-time IR loops, since `LOAD_REGION`/`WRITE_REGION` lengths are compile-time
  constants. Byte-at-a-time also gives the architected overlap propagation.
- Floating-point arithmetic (BFP short/long/extended, HFP, DFP) → a new leaf
  Python package (name to settle), following ADR-148's `cobol_numeric` model: it
  owns the arithmetic, rounding modes and exception conditions, imports nothing
  from `interpreter`, and is exposed as builtins under the "too cumbersome" clause.
  The byte-level encode and decode (IEEE, HFP, DPD) stays in IR. DFP uses `Decimal`
  with explicit contexts at 7/16/34 digits. The package may later be rewritten in
  Rust or C for speed, which is a further reason to keep it a leaf.
- Packed decimal → the COMP-3 encode/decode in `ir_encoders.py` for the bytes;
  arithmetic on the VM's exact integers.

Builtins are allowed only under the project rule (irreducible, or IR too cumbersome),
and each new builtin's commit states which applies. If a gap ever seems to need a
new IR opcode, it gets its own issue with the case argued, and the user decides.

## Machine semantics (builder's defaults, set in review)

- **Architecture level.** The machine claims z17 (arch15) with every wave-1 facility
  installed. `STFLE` reports that set. `STCK`/`STCKF` read an injected clock.
- **Program interruptions.** Fixed-point and decimal overflow respect the program
  mask. An unmasked interruption (data exception, divide, specification, addressing,
  operation, `TRAP`) ends the run unit as an abend `S0Cx` with the architected
  interruption code. The abend is visible to a COBOL caller the way a COBOL abend
  is. Recovery (`ESTAE`, `SPIE`) is out of scope until it gets its own issue.
- **Addressing modes.** Programs run AMODE 31 or 64. Instructions that mask
  addresses to the mode (`LA`, `BSM`, `BASSM`, …) implement the masking. The VM's
  allocator is not constrained below 16MB, so AMODE 24 is not supported.
- **Problem-state classification.** The builder derives it from Principles of
  Operation (each instruction's privileged-operation exception) and produces the
  table of opcode → unit. The user approves that table before any opcode issue is
  filed. The coverage check runs against it.

## Oracle

z390 is the oracle where it implements the instruction. Where it doesn't (likely
some z14–z17 instructions), expected values are derived from Principles of
Operation by hand, and the test says so. Programs that use system macros are
compared on observable output, registers and storage that our macros and z390's
both define; save-area chaining and `WTO` formatting are not compared.

## System services

System macros are our own definitions, not IBM's or z390's — as Forge did for BMS.
They are HLASM macro source in a maclib in this repo, expanded by che4z like any
other macro. Each expands to `SVC n` using the z/OS SVC number where one exists
(`WTO` → 35, `ABEND` → 13, `GETMAIN` → 10, …), and the lowering maps each SVC number
to a builtin. The bridge therefore never passes a macro call through unexpanded.
The later macro-language phase is coverage, not machinery: tests that conditional
assembly, SET symbols, attributes and system variable symbols come out of che4z
correctly, with fork fixes where they don't. The builtins reuse existing
infrastructure (`CobolIOProvider` for file I/O, `print`/`println` for console,
CALL_WITH_MEMORY and the program directory for `LINK`/`CALL`, `HALT` for
termination, ALLOC_REGION for storage). The first set, enough for the start/stop
milestone and the COBOL call: `SAVE`, `RETURN`, `WTO`, `ABEND`, `STORAGE`/`GETMAIN`/
`FREEMAIN`, `CALL`. File I/O (`DCB`, `OPEN`, `GET`, `PUT`, `CLOSE`) and `LINK`/`LOAD`
follow.

## Cross-language linkage

Standard z/OS linkage: R1 → parameter list of addresses with the high bit set on the
last, R13 → caller's 72-byte save area, R14 → return address, R15 → entry point on
call and return code on return. COBOL currently passes a NEW_ARRAY of `{region,
offset}` (`interpreter/cobol/lower_call.py`). A linkage unit bridges the two shapes
in both directions; the bridge belongs to the call boundary, not to either frontend.

## Branching and merging

Work lands on `main` directly, one reviewed unit at a time; the `hlasm` branch was
merged and retired. Every commit passes the full gate. Unfinished work is either not
yet wired in or carries `xfail` tests citing the bead id.

## Issue tracking

One epic in this repo's beads, cross-referencing Forge's `red-dragon-forge-6r0s`
(which weighs the same option). Children: the foundation units, one issue per opcode
unit with its exact mnemonic list derived from the opcode table, the system-services
units, the linkage unit, and the wave 2, 4 and 5 issues at coarser grain until they
start. Each issue carries a `wave-N` label. IR gaps found during the work get their
own issues. One further issue, outside the epic: check whether IBM Enterprise COBOL
stores COMP-1/COMP-2 as hexadecimal floating point; RedDragon packs them as IEEE
today (`byte_builtins.py`), and the HFP work here would close that gap if so.

## Left to the builder

- Package and module names, the bridge target's name and the JSON schema.
- How the fork is brought in (submodule plus a `make` target that `make test`
  depends on, as `make jar` does for ProLeap, is the expected shape) and how CI
  gets a C++ toolchain.
- Unit boundary for a unit file: per entry point or per CSECT.
- Order of the general-instruction units after load/store, branch and arithmetic.
- Merge cadence beyond "at milestones".
- Exact system-macro operand coverage.
