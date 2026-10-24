# HLASM unit .8: the object module and the binder

Bead red-dragon-6uyp.8. Design: `docs/superpowers/specs/2026-10-24-hlasm-system-services-design.md`,
decisions 1 and 2, and the linking-branch shape of decision 3. Rulings R66-R69.

## Part A: the object module (no behaviour change)

### Bridge (che4z fork, program format 2)

- `entries`: the ENTRY operands, in order. A non-symbol operand refuses the assembly.
- `externals`: `{name, kind}` with kind `EXTRN` or `WXTRN`; a V-constant name not declared
  is `EXTRN`.
- An `EXTERNAL` address carries its `offset` (`A(EXT+4)`).

### Types (interpreter/project, one class per file)

- ESD: `ControlSection(name, length)` (SD, private code named ""), `CommonSection(name,
  length)` (CM), `EntryLabel(name, section, offset)` (LD), `ExternalReference(name)` (ER),
  `WeakReference(name)` (WX), `ExternalDummySection(name, length, alignment)` (PR/XD; the
  bridge does not export DXD yet, .96).
- `TextRecord(section, offset, image: bytes)`.
- `RelocationKind`: ADDRESS, PR_OFFSET, CLASS_LENGTH, PR_TOTAL. `RelocationSign`: PLUS,
  MINUS. `RelocationRecord(section, offset, length, kind, target, sign, addend)`.
- END: `NamedEnd(name, section, offset)` or `DefaultEnd(section)`.
- `ObjectModule(esd, text, relocations, end)`; `NO_OBJECT_MODULE` for other languages.
- `ModuleUnit.object_module`; unit and linked formats 6 → 7.

### Construction (interpreter/hlasm/object_module.py)

From the AST: ESD in section order, then LD, ER, WX; TXT from today's placed pieces;
an `AddressSlot` is an ADDRESS RLD on its section, an external address (a new
`ExternalSlot` piece) an ADDRESS RLD on the external name. `HlasmFrontend.object_module`.

### Module paths and qualified names

- `lower_hlasm_program(program: SourceFile, ...)`: the unit takes the caller's path.
  `compile_hlasm` keeps `__main__.asm` for its main source.
- `HlasmFrontend(program, module)`; section variables become `__hlasm_sect_<module>.<section>`
  through `HlasmEmitter.section_base`. The module is the unit path's stem.

## Part B: the binder (interpreter/hlasm/binder.py, reached through hlasm_frontend)

- Layout: one region per module, ALLOC_REGION of the module length + 7, base rounded up
  to a doubleword (as storage_services.py does); each SD at its doubleword-aligned
  offset in ESD order. CM: one region per name at the largest length, shared by every
  module naming it.
- Names: `BoundName` = section placement (module, section, offset) | stub (index) |
  weak zero. Local SD/CM first, then image-wide SD and LD. Unresolved WX → 0; unresolved
  ER → a stub in one link-allocated region, 8 bytes apart, logged as a warning
  (`CodedDiagnostic` kind via the unit-diagnostic path).
- Far-branch table: `FarBranchEntry(low, high, owner)`, owner `ModuleOwner(module)`,
  `CobolOwner(program)` (none built until .15), `UnresolvedOwner(name)`.
- Start-up IR, once: machine state, ABEND variable, layout, TXT, every RLD after all
  layout. RLD kinds other than ADDRESS, and XD records, raise `UnsupportedRelocation`.
- Job step: per SD, LD and END name a function `func___hlasm_job_<name>_0` in a job-step
  module, registered in `programs`: R1 → one-entry VL list → halfword length + text
  (PARM from the `__hlasm_job_parm` builtin, 100-byte area, IBM's PARM limit; irreducible:
  a run input); R13 a fresh 72-byte save area; R14 = 0xFF0; R15 = entry address; then
  calls the module function, which now starts by dispatching on R15.
- Linking branches (BAL, BALR, BAS, BASR, BRAS, BRASL, BASSM) branch to
  `hl_link_dispatch`: a target in the stub range calls `__hlasm_stub_call`, which issues
  `CallWithMemory` on `__entry_<NAME>`; the result goes to R15 and control to R14.
  Otherwise the plain dispatch.
- Duplicate SD or LD names across units: `DuplicateProgramInImage` before link.
- API: `compile_hlasm(..., programs=())` and `link_hlasm_units(units, work_dir)`.

## Tests

- Unit `tests/unit/hlasm/test_object_module.py`: ESD/TXT/RLD/END of a program with two
  CSECTs, a COM, ENTRY, EXTRN, WXTRN, A and V constants.
- Unit `tests/unit/hlasm/test_binder.py`: layout offsets and alignment, CM merge at the
  largest length, RLD across modules (later module), stub allocation and warning, weak 0,
  non-ADDRESS refusal, duplicate refusal.
- Integration `tests/integration/hlasm/test_binder.py`: two modules, A's V-constant to
  B's ENTRY, A reads B's data; PARM supplied and empty; BALR to an unresolved EXTRN with
  unresolved calls permitted (R15 from the strategy) and refused
  (`UnresolvedProgramError`); duplicate CSECT across two units refused; reuse of the unit
  file on a second compile.
- z390: single-module parity (z390's linker needs separate object decks; say why).

## Commits

1. This plan.
2. Part A: bridge (fork commit, push, submodule bump), types, construction, paths,
   qualified names, docs. Full suite and z390 suite green.
3. Part B: binder, job step, stubs, link dispatch, duplicates, API, tests, docs, ADR.
