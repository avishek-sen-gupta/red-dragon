# HLASM unit .96: Q, J, CXD/DXD and complex-relocatable A-constants

Bead red-dragon-6uyp.96 (and the bridge side, red-dragon-6uyp.68). Builds on .8: `ObjectModule`,
`RelocationKind` (ADDRESS applied; PR_OFFSET, CLASS_LENGTH, PR_TOTAL refused), the binder and
`bound_start_up`. Spec: 2026-10-24-hlasm-system-services-design.md decisions 1-2.

## IBM facts checked

HLASM Language Reference (SC26-4940), z/OS 2.1 topics:

- **DXD.** Defines an external dummy section. The assembler computes its length and alignment from
  the operands, written as for DS. HLASM assigns the most restrictive alignment of the operands
  (General Information: earlier assemblers used the first operand's).
- **DSECT as XD.** A DSECT is also an external dummy section, but only when its name appears in a
  Q-type constant of the same module.
- **Q-type.** Names a DXD, DSECT or (GOFF) part. The binder enters the section's offset in the
  external dummy area. Lengths 1-4 (Q), 1-8 (QD), 3 only (QY, 20-bit long-displacement format).
  Fullword alignment for Q.
- **J-type.** Length of a DXD, class or DSECT, entered by the binder. "Only available if the GOFF
  option is specified." Lengths 2-4 (J), 2-4 or 8 (JD).
- **CXD.** A fullword-aligned fullword. The binder enters the total length of all external dummy
  sections of the image. Without a control section it starts private code.
- **Merging.** Same-named external dummy sections from different modules: most restrictive
  alignment, largest length. The binder may order them any way; the program must not assume an order.
- **Use.** The program allocates CXD bytes itself, adds a Q value to the area's address, and
  addresses the section from there. The sections produce no object code.
- **A and Y constants** may be absolute, relocatable or complex relocatable. Relocatable lengths:
  A 2-4, Y 2 only, AD 2-8.
- **RLD record** (Programmer's Guide, object deck): flag bits 2-3 give the type (0 A, 1 V, 2 Q,
  3 CXD), bits 4-5 the length less one, bit 6 the direction (0 +, 1 -), bit 7 "same P-ID and R-ID
  for the next item". A complex-relocatable constant is several items at one address, each signed.
  OBJ has no J type: J is a GOFF facility.

z390 (az390): DXD and CXD are no-ops. It does write signed RLD items for complex-relocatable A
constants. So the z390 differential covers A(X-Y) and A(E1-E2) only; DXD, Q, J and CXD rest on IBM.

## Rulings

- R-1. The binder does not allocate the external dummy area. The program GETMAINs CXD bytes, as
  IBM's steps say. Nothing reaches the area except through the program's own pointer.
- R-2. Layout: merged XDs in first appearance (module order, then ESD order), each at the next
  offset aligned to its merged alignment, from 0. CXD is the end of the last one.
- R-3. A DSECT named in a Q-constant is an XD of its assembled length, doubleword aligned (a
  section's origin is doubleword aligned; the OBJ ESD alignment field tops out at doubleword).
- R-4. J naming a DXD or a Q-named DSECT binds to that XD's merged length, as GOFF would. che4z
  accepts J without GOFF; so do we. J naming anything else (a class, a control section, a DSECT
  no Q-constant names) is refused at bind with `UnsupportedBinding`, listed as a gap.
- R-5. QY (20-bit long-displacement image) is refused as an unsupported data type, with a new bead.
- R-6. A complex-relocatable value becomes one RLD item per relocatable term occurrence
  (cardinality n gives n items), each with its sign; the first carries the absolute part as its
  addend, the rest 0. The binder sums the items at one address and stores once. A term in a DSECT
  contributes no item: its offset is already in the absolute part (R75).
- R-7. An external symbol the bridge has no line for (e.g. one EXTRN PART names) gets line 0.

## Shapes

- Bridge (program format 3): `external_dummies: [{name, length, alignment}]` for every DXD and
  every Q-named DSECT; a `CXD` statement `{section, offset, label, origin}`; Q and J values stay
  `RELOC` naming the XD; a complex value is `{"kind": "COMPLEX", "terms": [{kind SECTION|EXTERNAL,
  name, sign PLUS|MINUS}], "offset": absolute part}`; external terms join `externals`.
- `RelocationRecord.target: RelocationTarget = RelocationName | NoRelocationTarget` (PR_TOTAL).
  Unit and linked file formats move to 9.
- `object_module` emits `ExternalDummySection` per XD, PR_OFFSET per Q, CLASS_LENGTH per J,
  PR_TOTAL per CXD, and signed ADDRESS items per complex constant.
- `Binder.pseudo_registers` (name to offset and merged length) and `Binder.pseudo_register_total`;
  `bound_start_up` applies the three kinds and groups ADDRESS items by address.

## Tests

- Unit: `test_object_module` gains a fixture-driven test for XD, Q, J, CXD and complex records;
  `test_binder` gains XD merge and PR layout, and the J refusal replaces the old refusals;
  `test_unit_files` round-trips the new target shapes.
- Integration (`tests/integration/hlasm/test_binder.py`): two modules with DXD + Q + CXD, one
  GETMAINs CXD bytes and both store and read through Q offsets (R15 and the stored bytes); a J
  constant's value; A(X-Y) across two sections, A(E1-E2) across modules, Y(X-Y).
- C++ (`program_export_test.cpp`): external dummies, CXD statement, complex value, line-0 external.
- z390 (`tests/z390/test_binder_differential.py`): A(X-Y) across sections and modules.

## Commits

1. This plan.
2. RelocationRecord target union; unit and linked formats 9. No behaviour change.
3. Bridge: XDs, CXD, Q/J names, line-0 externals (fork commit, submodule bump); Python models,
   object module records, binder XD merge, PR layout and the three kinds; docs.
4. Bridge: complex values (fork commit, bump); Python model, signed multi-item RLDs, binder
   summing; z390 differential; docs. g++-14 container build before this commit.
