# HLASM unit red-dragon-6uyp.15: COBOL ↔ HLASM linkage and the mixed image

Spec: `docs/superpowers/specs/2026-10-24-hlasm-system-services-design.md` decisions 2–4;
rulings R66, R67, R69, R74, R80. Heavy: three commits, each green.

## Research (IBM)

| Question | IBM says | Source |
|---|---|---|
| BY VALUE in the list | Table 65: a copy of the identifier or literal goes directly in the parameter list | Enterprise COBOL V4.1 Programming Guide, Table 65 (methods for CALL data) |
| 4-byte BY VALUE | Figure 54: `CALL 'SUB1' USING BY VALUE X,Y,Z` (S9(9) BINARY, PIC X(4), POINTER) gives R1 → three fullwords holding 00007FFF, PRM2, 098FB0C4 | z/OS LE Writing ILC Applications, section on HLL and assembler arguments |
| VL bit | Note 3: COBOL turns on the high-order bit of the address of the last parameter when it goes by reference. Figure 54 shows no bit on a trailing BY VALUE word | ILC Applications, C/COBOL by-value table note 3; Figure 54 |
| OMITTED | "Testing for OMITTED arguments": the callee's ADDRESS OF is NULL. APAR PI44924: the compiler sets the high-order bit on a trailing OMITTED | Programming Guide; APAR PI44924 |
| 1-, 2-, 8-byte BY VALUE | Compatible with C char, short and double by value (direct) | ILC Applications, table of data types by value (direct) between C and COBOL |
| RETURN-CODE | "When control is returned to a COBOL program ... from a call, the contents of register 15 are stored into the RETURN-CODE special register"; a returning COBOL program stores RETURN-CODE into R15 | Programming Guide, "Understanding the RETURN-CODE special register" |

### Rulings where IBM is silent (listed as gaps in hlasm.md)

- **1- and 2-byte BY VALUE** take one fullword slot, right-aligned, high bytes zero, as
  non-XPLINK C widens char and short. **8-byte** values take two consecutive slots, big-endian.
  A BY VALUE length other than 1, 2, 4 or 8 (which IBM refuses) leaves a zero word.
- **VL bit** is set on the last word when the last argument is BY REFERENCE, BY CONTENT or
  OMITTED (X'80000000'); never after a trailing BY VALUE (Figure 54, note 3).
- **RETURN-CODE** is a halfword: COBOL → HLASM keeps R15's low halfword; HLASM → COBOL
  sign-extends RETURN-CODE into R15.

## Design

- `ArgumentMode` (REFERENCE, CONTENT, VALUE, OMITTED) and `UsingParameter(mode, length)` live in
  `interpreter/project`, beside the object-module records both languages already share.
- The argument element is `{mode, length, region, offset}`; `omitted` goes, the callee's
  binding tests `mode == OMITTED`. Sites: `lower_call._argument` and `call_arguments`.
- `ModuleUnit.using`: one `UsingParameter` per bound LINKAGE parameter, in order; mode VALUE
  where PROCEDURE DIVISION USING says BY VALUE. Unit and linked formats move to 8.
- **Mixed image.** `link_hlasm_units` links COBOL and HLASM unit files. Start-up order: COBOL
  run-unit allocation (only when a COBOL unit is present), the binder's start-up, the units
  in the order given, the job-step module. Image language HLASM.
- **Binder.** `Binder(modules, programs)` takes the COBOL programs as `CobolOwner(program,
  using, file)`. One duplicate check runs over SD, LD and PROGRAM-ID names, naming both units.
  COBOL programs take the first stubs; an EXTRN or V-con naming one binds to its stub, owner
  `CobolOwner`; only unresolved names warn.
- **COBOL → HLASM.** The job-step module defines `__hlasm_from_cobol(arguments, entry)`: an IR
  loop over the array that writes the list (8 bytes per argument allocated), sets VL, then
  R1, R13 (fresh 72 bytes), R14 (`0xFF0`), R15. Each SD/LD name gets
  `__hlasm_cobol_<NAME>(arguments)`, registered as `__entry_<NAME>`: it calls the conversion,
  calls `__hlasm_module_<module>(entry, 0)`, and returns R15's low halfword as RETURN-CODE's
  2 bytes.
- **HLASM → COBOL.** The far branch's `CobolOwner` case is unrolled per signature: slot
  offsets are static. Per position: REFERENCE reads a word, masks it, makes OMITTED for 0;
  the high bit ends the walk (count = position + 1). VALUE copies 1, 2, 4 or 8 bytes from the
  slot into a fresh region. Saves R14–R12 at 12(R13), `CallWithMemory __entry_<PROG>`,
  restores them, R15 = RETURN-CODE sign-extended, returns to R14.
- **CANCEL** of an HLASM name: the program directory does not hold it, so CANCEL skips
  it already; a test pins it.
- **Abend**: `emit_abend` halts the VM, so the run unit ends; a test pins it under COBOL.
- No new builtin: everything is IR over existing builtins.

## Tests

Unit (`tests/unit/hlasm/test_cobol_linkage.py`, `tests/unit/cobol/...`):
- USING signature on the unit: `USING A, BY VALUE N, H` → (REF 10), (VALUE 4), (VALUE 2).
- Argument element IR: StoreField of mode and length for each mode; no `omitted`.
- Conversion IR: `__hlasm_cobol_<NAME>` stored in `__entry_<NAME>`; far-branch CobolOwner case
  issues `CallWithMemory __entry_<PROG>`; no SYMBOLIC beyond parameters.
- Binder: duplicate PROGRAM-ID vs SD and vs LD refused naming both files.

Integration (`tests/integration/hlasm/test_cobol_linkage.py`, needs the ProLeap JAR):
- COBOL `CALL 'ASMSUB' USING BY REFERENCE A, BY CONTENT B, BY VALUE N` (N S9(9), H S9(4),
  C X, D COMP-2): HLASM copies slots into A, overwrites B's copy, sets R15=7 → A's bytes,
  B unchanged, RETURN-CODE 7.
- OMITTED in the middle and last: words 0 and X'80000000'.
- HLASM main → V-con + BALR with a VL list → COBOL sees the arguments and sets RETURN-CODE;
  R15 holds it; R2–R12 restored.
- Nested COBOL → HLASM → COBOL.
- HLASM ABEND under a COBOL caller: the COBOL statements after the CALL do not run.
- CANCEL of the HLASM name does nothing.
- z390 has no COBOL: no differential test.

## Commits

1. Argument mode and length, `ModuleUnit.using`, format 8 — no behaviour change.
2. Mixed image and the one duplicate check.
3. Both conversion directions, abend and CANCEL tests, docs.
