# COBOL compilation units with several programs — design

Date: 2026-10-18. Issue: red-dragon-ljku (epic red-dragon-8auq). Status: approved for
autonomous execution under the user's standing rules: IR only, no new builtins, and fixes
start as far left as possible (parser, then bridge, then lowering, then runtime).

## The idea

A COBOL source file is a compilation unit holding one or more programs. Programs follow
one another (batch compilation) or are contained in one another (nested programs). Every
program reaches the ASG with its place in that tree, is lowered as a program of its own,
and is linked into the run unit beside separately compiled programs.

## What the NIST IC programs need

Program-unit structure of the 12 failing programs, from their sources:

| Shape | Programs | Also needs |
|---|---|---|
| batch: `A` then `A-1` | IC222A IC223A IC224A IC225A IC237A | nothing more |
| batch | IC226A IC227A | EXTERNAL data and files |
| nested: `A` contains `A-1` | IC228A IC233A | GLOBAL data |
| nested three deep | IC234A | GLOBAL file, GLOBAL data, USE GLOBAL |
| nested: `A` contains `A-1` and `A-2` | IC235A | nothing more |
| nested, COMMON / INITIAL | IC401M | none: it is a FIPS flagger program (11 flags) |

## Where each piece lives

**Parser (ProLeap).** The grammar already nests programs:
`programUnit : identificationDivision ... programUnit* endProgramStatement?`. The ASG
loses the tree: `CompilationUnitImpl.addProgramUnit` puts every unit, nested or not, in
one flat list. `ProgramUnit` gains its contained units, in source order, and
`CompilationUnit` gains its top-level units. Containment is read from the parse tree
there, once. `ProgramIdParagraph.getAttribute()` already carries COMMON and INITIAL.

**Bridge.** A passthrough of that tree. The output becomes the compilation unit:

```json
{"programs": [
  {"program_id": "IC235A", "attribute": "", "data_fields": ..., "statements": ...,
   "programs": [
     {"program_id": "IC235A-1", "attribute": "", ..., "programs": []},
     {"program_id": "IC235A-2", "attribute": "", ..., "programs": []}]},
  ...]}
```

Each program object is what the bridge emits today for its one program, plus `attribute`
and `programs`. No COBOL rule is computed in the bridge.

**cobol_asg.** The reader returns a compilation unit: its top-level programs, each a
`CobolASG` carrying its contained programs and its PROGRAM-ID attribute. Consumers that
handle one program take the first top-level program and say so by name.

**Compile and link.** The parse stage still writes one AST file per source file. The
lower stage lowers every program in it, top-level and contained, in pre-order, each to its
own unit file named after its program. Link takes every unit. The run unit's main program
is the first top-level program of the main source. A CALL to a contained program
resolves through the run unit's program table like any other.

## Later beads (not in the first unit)

- **Call visibility (ANSI X3.23-1985, Inter-Program Communication module).** A contained program can be called only
  by the program that directly contains it, or, when it is COMMON, also by the other
  programs that program contains. A CALL that names a contained program from anywhere else
  resolves as if the contained program did not exist. Today's flat table accepts calls the
  standard rejects, but no valid NIST program depends on the difference.
- **EXTERNAL data and files.** An EXTERNAL record or file is one storage area shared by
  every program in the run unit that declares it (IC226A, IC227A).
- **GLOBAL names.** A GLOBAL data item, file or USE GLOBAL declarative of a containing
  program is visible to the programs it contains (IC228A, IC233A, IC234A).
- **INITIAL.** An INITIAL program is in its initial state on every CALL.

## Testing

- **Parser:** a test over a source holding a batch pair and a two-level nest, asserting
  the tree and the attributes.
- **Bridge:** a test asserting the `programs` tree.
- **cobol_asg:** a reader test.
- **Integration:**
  - a batch source whose main program CALLs its sibling;
  - a nested source whose main program CALLs both contained programs, asserting the values
    passed back.
- **NIST:** IC222A, IC223A, IC224A, IC225A, IC237A and IC235A pass. IC401M is classified
  as a flagger. No program goes from pass to fail.
