# HLASM wave 4: macro language and data constants

Extends `2026-10-21-hlasm-frontend-design.md` for wave 4, which now runs before
wave 3. Evidence: a survey that ran each feature through the che4z bridge, and a
review of this design against the code and IBM's manuals.

## Where things stand

che4z implements the whole macro language: expansion, AIF/AGO/ANOP/ACTR, SET
symbols, attributes, system variables, AREAD, AINSERT, COPY, OPSYN. The bridge
exports only the resulting ordinary statements, each with its open-code line, the
innermost macro name and the nesting depth. Every feature tried came out correct.
Wave 4 is therefore proof (tests) plus fixing what the bridge exports and what the
DC encoder gets wrong. No macro interpreter is written in Python.

## Decisions

- **The bridge exports assembly facts; Python encodes.** che4z owns the location
  counter, so the bridge exports each DC operand's offset and bit offset, the scale,
  exponent and bit-length modifiers (red-dragon-6uyp.66), `*` as the operand's own
  address (.65), S-constants as base and displacement resolved through USING (.67),
  CCW/CCW0/CCW1 as statements with their operands, AMODE/RMODE per section, and the
  macro call stack che4z already attaches to each diagnostic. Python's own DC
  alignment table is deleted: one location counter, che4z's.
- **Python encodes every DC type** from those fields: AD/FD/VD, CA/CE/CU, F/H with
  fractions, exponents and the U prefix, CCW images, and the floating-point types.
- **Floating-point DC images are built in Python at assembly time**, like the P and Z
  constants today: they are static bytes, not program behaviour, so the IR-first rule
  does not apply. The packers (BFP, HFP, DFP with DPD) go in `zarch_float` beside its
  rounding, with the DC encoder as their caller. The rounding suffix (R1-R8 and the
  per-type defaults), special values and a decimal constant's written exponent are
  taken from IBM's manual and checked against z390. This is its own bead (the one
  cited today, .21, is closed).
- **Assembly errors refuse.** Out-of-range F/H values are an error in HLASM
  (ASMA072E) and are refused with the statement's location, not wrapped. MNOTE and
  che4z warnings below error level go to the frontend's logger with their location,
  including the macro call stack. They are stored in the unit file, so a reused unit
  reports them again.
- **Assembly inputs are explicit, and nothing is defaulted.** `&SYSPARM`, the job,
  step and data-set names, and the assembly clock are inputs to `compile_hlasm`,
  passed to the bridge as che4z `asm_option`s. A program that reads a name it was not
  given is refused, as today. `&SYSSEQF` is computed by che4z from columns 73-80. The
  assembly clock follows COBOL's `CompileClock`: an input that the unit-file reuse check
  ignores, read once per assembly. `&SYSPARM` and the names are checked for reuse,
  with the SYSLIB member contents and the bridge version (.71; COBOL's reuse
  check has the same gap for copybooks). The bridge path no longer depends on the working
  directory (.72). No CLI flag is added in this wave.

## Not in this wave

- Q, J, CXD/DXD and the Python side of complex-relocatable A-constants (.68) need
  the linker work in .8; they move to a bead that depends on .8.
- CNOP padding stays with .64 (instructions have no bytes in storage).
- The outer macro chain on each statement, beyond diagnostics; SETAF/SETCF external
  functions; G (DBCS) and R/RD constants; COPY-member file names in source
  locations (the IR location has no file field).

## Units

1. Bridge export: the `DC 0F` crash, operand and bit offsets, modifiers, .65, .67,
   CCW statements, AMODE/RMODE, diagnostic call stacks.
2. Assembly inputs and reuse: `&SYSPARM`, names, `&SYSSEQF`, the assembly clock,
   .71, .72.
3. DC encoding, integer, character and address types, range refusal; the Python
   alignment table removed (.63).
4. Floating-point DC encoding (new bead).
5. Diagnostics to the logger, kept across unit reuse.
6. Macro-language conformance (.16): one program per feature — nested and inline
   macros, &SYSNDX, loops, GBL/LCL, SETC substrings, created SET symbols, &SYSLIST,
   opcode substitution, AREAD, AINSERT, COPY, OPSYN, each attribute, DSECTs, labeled
   and dependent USING — through the VM and against z390.

Wave 3 then writes its own SAVE, RETURN, STORAGE, GETMAIN/FREEMAIN, CALL, LINK, LOAD
and DCB macros for the maclib (the spec rules out copying IBM's).
