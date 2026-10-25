# COBOL Frontend

> `interpreter/cobol/cobol_frontend.py` · Extends `Frontend` directly

## Overview

The COBOL frontend lowers COBOL source code into RedDragon's flattened three-address-code IR. Unlike the 15 tree-sitter frontends that extend `BaseFrontend`, the COBOL frontend extends `Frontend` directly and uses the [ProLeap COBOL Parser](https://github.com/uwol/proleap-cobol-parser) via a subprocess bridge (JDK 17 required).

## Architecture

```
COBOL Source
  │
  ▼
ProLeap Bridge (Java subprocess)
  │  proleap-bridge/src/main/java/.../StatementSerializer.java
  │  Parses COBOL → ProLeap ASG → JSON serialization
  │
  ▼
Python ASG Layer
  │  cobol_asg/cobol_parser.py     — subprocess invocation
  │  cobol_asg/asg_types.py        — CobolASG, CobolSection, CobolParagraph
  │  cobol_asg/cobol_statements.py — typed statement hierarchy (frozen dataclasses)
  │
  ▼
CobolFrontend (this file)
  │  DATA DIVISION  → ALLOC_REGION + PIC-driven encoding
  │  PROCEDURE DIV  → statement-by-statement IR lowering
  │
  ▼
RedDragon IR (list[InstructionBase])
```

The pipeline has three layers, each independently testable:

1. **Java bridge** — `StatementSerializer.java` dispatches on ProLeap's `StatementTypeEnum` and serializes each statement type to JSON with extracted operands
2. **Python dispatch** — `cobol_statements.py` provides frozen dataclasses per statement type with `from_dict()`/`to_dict()` round-trip and a `parse_statement()` dispatch function
3. **Frontend lowering** — `statement_dispatch.py` routes each statement type to its lowering function (`dispatch_statement()`)

## Module Map

Files are under `interpreter/cobol/` unless prefixed with `cobol_asg/`.

| File | Purpose |
|------|---------|
| `cobol_frontend.py` | Main frontend: DATA DIVISION allocation, PROCEDURE DIVISION lowering |
| `cobol_asg/cobol_statements.py` | Typed statement hierarchy — frozen dataclasses + union type |
| `features.py` | `CobolFeature` enum — 150 semantic features; used with `@covers(CobolFeature.X)` test decorators |
| `io_provider.py` | `NullIOProvider` and `StubIOProvider` and their base `CobolIOProvider` (the record provider in `interpreter/record_io/io_provider.py` plus ACCEPT and the implementor switches and KEY OF REFERENCE) |
| `real_file_provider.py` | `RealFileIOProvider`, the disk provider: it finds each file's path by ASSIGN (a run override, then an environment variable named by a bare ASSIGN name, then the base directory, then `<file-name>.dat`) and adds SYSIN for ACCEPT and the switches and KEY OF REFERENCE to `RealFileProvider`'s record operations |
| `cobol_asg/cobol_expression.py` | `ExprNode` union type (`LiteralNode | FieldRefNode | RefModNode | BinOpNode`) + `expr_from_dict()` deserializer; legacy `parse_expression` tokenizer retained for standalone tests |
| `cobol_asg/cobol_parser.py` | Subprocess bridge to ProLeap JAR |
| `cobol_asg/asg_types.py` | `CobolASG`, `CobolSection`, `CobolParagraph`, `CobolField` |
| `cobol_asg/compilation_unit.py` | `CobolCompilationUnit` — a source file's top-level programs; `programs_in_preorder()` over the raw bridge JSON |
| `cobol_asg/cobol_types.py` | `CobolDataCategory` enum, `CobolTypeDescriptor` |
| `cobol_asg/pic_parser.py` | PIC clause parser (e.g., `9(5)V99` → type descriptor) |
| `data_layout.py` | `DataLayout`, `FieldLayout`, `build_data_layout()` |
| `global_names.py`, `enclosing_scope.py`, `use_selection.py` | GLOBAL names: which items and files of an enclosing program a contained program sees, their regions, and which USE declarative an I-O condition selects |
| `external_layout.py`, `external_area.py`, `lower_external.py` | EXTERNAL records and file record areas: their layout, the run unit's directories, and their allocation and binding |
| `file_definitions_data.py` | `FILE_DEFINITIONS`, `file_definitions_data()` — the program's SELECTs and FD formats as a `Data` directive |
| `layout_data.py` | `DATA_LAYOUT`, `layout_data()`, and the reader `field_positions()` → `FieldPosition` per WORKING-STORAGE field |
| `ir_encoders.py` | IR instruction builders for encode/decode (zoned, COMP-3, alphanumeric, string ops) |
| `byte_builtins.py` | 19 low-level builtins for byte/nibble/list/string manipulation |
| `interpreter/encoding/ebcdic_table.py` | EBCDIC (CP037) ↔ Latin-1 translation tables, built from Python's `cp037` codec: a bijection, so every byte survives a decode and re-encode |
| `data_filters.py` | `align_decimal()`, `left_adjust()` for PIC formatting |
| `zoned_decimal.py` | Zoned decimal encoding/decoding reference |
| `comp3.py` | COMP-3 (packed decimal) encoding/decoding reference |
| `alphanumeric.py` | Alphanumeric/EBCDIC encoding reference |

## Compilation Units

A source file is a compilation unit of one or more programs. Programs follow one another, each ended by END PROGRAM (batch compilation), or are contained in another program, ended by END PROGRAM before the containing program's own END PROGRAM header (nested programs; ANSI X3.23-1985 Inter-Program Communication module; IBM Enterprise COBOL LR, "Nested programs"). ProLeap's grammar nests them (`programUnit : ... programUnit* endProgramStatement?`); `CompilationUnit.getTopLevelProgramUnits()` and `ProgramUnit.getContainedProgramUnits()` read that tree from the parse tree.

The bridge emits the compilation unit as `{"programs": [...]}`: the top-level programs in source order. Each program object carries `program_id`, `attribute` (the PROGRAM-ID attribute — `COMMON`, `INITIAL`, ... — or `""`), its own divisions, and `programs`, the programs it directly contains, in source order. A program's divisions never include those of the programs it contains.

`ProLeapCobolParser.parse()` and `AstStore.get()` return a `CobolCompilationUnit` of top-level `CobolASG`s, each with its `attribute` (`ProgramAttribute`) and its contained `programs`; the preprocessor runs on each program object alone, in pre-order. A consumer that handles one program takes `first_program`, as `CobolFrontend.lower(source)` does.

`compile_cobol` and `lower_cobol_program` lower every program of a source, in pre-order (`programs_in_preorder`), each with a fresh frontend into a unit of its own, and link every unit. The run unit's main program is the first top-level program of the main source. A CALL to a sibling or contained program resolves through the run unit's program table like a CALL to a separately compiled one.

Not yet modelled: CALL visibility of contained programs and COMMON (red-dragon-ljku.2), INITIAL (ljku.5). EXTERNAL data and files are modelled; see [EXTERNAL data and files](#external-data-and-files). GLOBAL names are modelled; see [GLOBAL names](#global-names). Today every program in the run unit can CALL every other.

## COPY and REPLACE

ProLeap's preprocessor expands COPY and applies COPY REPLACING and REPLACE before the COBOL grammar runs (`proleap-cobol-parser`, `io/proleap/cobol/preprocessor`). Matching is by text-word (IBM Enterprise COBOL LR, COPY "Comparison and replacement rules"; ANSI X3.23-1985 Text Manipulation module): an operand matches only whole text-words, never part of a word or of a literal; a separator comma or semicolon counts as a space; comment and blank lines are ignored. The text is scanned once, left to right; at each text-word the operands are tried in the order written, and replacement text is not compared again. `(`, `)` and `:` are separators, so the IBM dummy operand `==:TAG:==` still replaces the tag inside `:TAG:-REC`. An identifier operand may continue its qualifiers or subscript on the next line (`TRUE-Q-04 OF TRUE-Q-03` / `IN TRUE-Q-02`). Not modelled: `LEADING`/`TRAILING` partial-word replacement.

`COPY text-name OF library-name` (or `IN`) copies the text-name of that library ("If text-name is not qualified, a library-name of SYSLIB is assumed", IBM Enterprise COBOL LR, COPY statement). A caller maps each library-name to a directory with `CopybookLibrary(name, directory)`, passed as `make_cobol_parser(copybook_libraries=...)` (a direct `ProLeapCobolParser` takes the directories, extensions and libraries together as one `CopybookSearch`); the bridge takes it as `-copybook-library <name> <dir>` and matches the name in upper case. An unqualified COPY, or one naming a library with no mapping, searches the copybook directories, and text copied from a library resolves its own unqualified COPYs the same way.

## Program Declarations

Right after its `entry` label, each program's IR declares two `Data` directives, which the VM steps over:

- `__cobol_file_definitions` — a record whose `files` list holds one record per SELECT, in FILE-CONTROL order: `program` (the declaring program's PROGRAM-ID, upper-cased), `file_name`, `assign_to`, `organization`, `access_mode`, `record_key`, `relative_key`, `file_status`, and `fd` — empty without an FD, else one record with `recording_mode`, `record_clause` (`kind` plus that clause's sizes and `depending_on`), `record_lengths` (one per 01 record) and `depending` (any 01 record contains OCCURS DEPENDING ON).
- `__cobol_data_layout` — a record whose `fields` list holds each WORKING-STORAGE entry's `name`, `offset`, `length`, `category`, `total_digits`, `decimal_digits` and `signed`. `field_positions(declarations)` reads it back as a name → `FieldPosition` mapping.

The linker namespaces labels only, so every linked module keeps both names. The loader copies the entered program's `Data` into `VMState.declarations` (`declarations_of(linked, program)` in `run.py` for a `ProgramEntry` run; the program at `entry_func_label` for an `EntryPoint` run) without looking inside.

## Data Division Lowering

The DATA DIVISION is lowered to byte-addressed memory regions:

1. `build_data_layout()` parses all WORKING-STORAGE fields, computing offsets and byte lengths from PIC clauses
2. `ALLOC_REGION` allocates a contiguous byte array sized to `layout.total_bytes`
3. Each field with a VALUE clause is encoded per its PIC type and written via `WRITE_REGION`; a group's VALUE is encoded as alphanumeric over the whole group, before its descendants'. A numeric-edited item stores a nonnumeric VALUE literal as its characters, unedited; a numeric literal (the bridge marks it `value_is_numeric`) and the figurative ZERO are edited as a MOVE would edit them (`PIC $.** VALUE ZERO` holds `*.**`). BLANK WHEN ZERO plays no part in a VALUE; it blanks an item, numeric-edited included, when a zero value is moved or stored into it

### EXTERNAL data and files

A WORKING-STORAGE 01 with the EXTERNAL clause, and the record area of an FD with it, is one area of the run unit, shared by every program that describes it (IBM Enterprise COBOL LR, EXTERNAL clause: "An external data item can be referenced by any program or method in the run unit that describes the data item"; for a file, "In a run unit, there is only one representative of an external file"). The bridge passes the clause through: `external: true` on the 01's data field, `external` on each `file_descriptions` entry. `CobolField.external`, `FileDescription.external` and `CobolASG.external_file_names()` carry it.

- **Layout.** `partition_external` (`external_layout.py`) takes each EXTERNAL record (with any 01 that REDEFINES it) and each EXTERNAL FD's records out of their section, lays them end to end in the program's EXTERNAL layout (`SectionedLayout.external`, `RegionId.EXTERNAL`), one `ExternalArea` (name, kind, start, length) per area, and lays out what is left of WORKING-STORAGE and the FILE SECTION again without them.
- **Run unit.** The start-up module declares two directories in the outermost frame, `__cobol_external_records` and `__cobol_external_files` (`external_area.py`): heap objects holding each area's region under its upper-cased name. Records and files are matched by name, each kind in its own directory.
- **Load.** Each program's load-time code probes the directory with `dict_contains_key` for each of its areas and, when the name is absent, allocates a zero-filled region of the area's length and stores it there (`lower_external.py`). The first program loaded that describes an area allocates it; an EXTERNAL file's connector state starts closed at the same point.
- **Entry.** The procedure loads each area's region from the directory (`bind_external`); a field in an area is addressed at its offset from the area's start.
- **Files.** An EXTERNAL file's state (open mode, position, refused verbs, last key, lock) is the run unit's `__cobol_external_file_<FILE>_*` variables, not the program's (`file_state_of`). The FILE STATUS item stays each program's own: a verb sets the one its program's SELECT names.
- **Not applied.** A VALUE clause in an EXTERNAL record is not applied, and lowering logs a warning: ANSI X3.23-1985 forbids VALUE there except on level 88. Programs whose descriptions of one area differ in size are not checked: IBM requires the same number of bytes, and each program addresses the area with its own description.

### GLOBAL names

A name declared GLOBAL is visible to the program that declares it and to every program it contains, at any depth (IBM Enterprise COBOL LR, GLOBAL clause). A reference is resolved in the program's own declarations first; "if no match is found, only global declarations are searched in successive outer containing programs", and "the search ends when the first matching name is found" (IBM LR, scope of names). A local declaration in an intervening program therefore masks nothing; a GLOBAL one does.

- **Reader.** The bridge writes `global` on a data field and on each `file_descriptions` entry (`CobolField.is_global`, `FileDescription.is_global`). `programs_in_preorder` gives each contained program its enclosing programs, nearest first, under `enclosing` (`CobolASG.enclosing`).
- **Layout.** `build_sectioned_layout` gives each enclosing program an `EnclosingLayout` (`enclosing_scope.py`): its WORKING-STORAGE and FILE SECTION, and the global part of each, the 01s with GLOBAL and every record of a GLOBAL FD (`global_names.global_records`).
- **Entry.** A contained program's procedure loads each enclosing program's WORKING-STORAGE from its program object and its FILE SECTION region from `__file_area_<PID>` (`InheritedScope`). `MaterialisedSectionedLayout.resolve_match` searches the program's own sections, then each enclosing program's global layouts, the nearest first; a global item is addressed at its offset in its own program's region.
- **GLOBAL files.** A file a program names but does not SELECT is the nearest enclosing program's GLOBAL file of that name (`global_names.file_owner`). Its connector state is that program's `__cobol_file_<OWNER>_<FILE>_*` variables, its SELECT is that program's (`visible_file_entries`), its records are reached as global data, and the I-O status goes to the FILE STATUS item that SELECT names, which is the owner's item whether or not it is global.
- **USE GLOBAL.** A USE GLOBAL declarative applies to its own program's I-O as a plain USE does. For an I-O condition the selection runs (`use_selection.use_procedures`): the program's own file-named USE, then its open-mode USEs, then each enclosing program's USE GLOBAL declaratives, the nearest first, a file-named one only when it names the same connector; the first that qualifies runs. An enclosing program's section runs in that program: the contained program stores the section's name in `__use_request_<PID>` and enters the program through `__entry_<PID>` with no arguments; that program's procedure, on entry, finds the request, clears it, performs the section and returns. The contained program then rebinds `__ws_region` to its own WORKING-STORAGE.
- **Condition-names.** The condition-names under an enclosing program's global items are in the contained program's condition index, below its own, the nearest program's winning, since "any item that is subordinate to a global item (including condition-names and indexes) is automatically global". Indexes of a global table are not yet reached from a contained program.
- **FILE SECTION.** Every program's FILE SECTION region is allocated once, at load, and kept in `__file_area_<PID>` (`lower_file_area`), as WORKING-STORAGE is kept: a record area keeps its contents from one CALL to the next, and the programs a program contains reach its GLOBAL files' records there.

### Data-name qualification

A reference `N OF Q1 OF Q2 ...` (or `IN`) is resolved by `DataLayout.qualified_matches`: every elementary or group item named N whose enclosing groups, read outward, contain Q1, Q2, ... in that order (intermediate levels may be skipped). One survivor is the item; more than one raises `CobolAmbiguousReferenceError`; none falls through to the next DATA DIVISION section, and a name no section declares is an `UndeclaredDataNameError` naming the item and the line of the statement that used it. A subscripted reference strides by, and is bounded by, the OCCURS tables enclosing that one match (`DataItemMatch.tables`), never another item of the same name.

`LENGTH OF X OF G` (in MOVE, arithmetic expressions and reference-modification bounds) measures the item its qualifiers select: the bridge's `length_of` node carries the qualifiers (`LengthOfNode`, `RefModLengthOf`, `RefModOperand.length_of`). LENGTH OF a table element is the length of one occurrence.

STRING and UNSTRING `WITH POINTER` items and the UNSTRING `TALLYING IN` item are qualified, subscriptable references (`RefModOperand`), resolved like any other operand.

A SEARCH table and its VARYING item are qualified references; the index layout records each INDEXED BY name's table by its full name path, so `SEARCH E OF T2` advances T2's own index.

READ `INTO` and `KEY IS`, WRITE and REWRITE `FROM`, and the SELECT entry's `RECORD KEY`, `RELATIVE KEY` and `FILE STATUS` items are qualified references (`RefModOperand`); `__cobol_file_definitions` still reports the three SELECT items by name.

A CALL USING argument (BY REFERENCE, CONTENT or VALUE, and ADDRESS OF) carries its qualifiers and subscripts (`CallUsingParam.qualifiers`, `.subscripts`), and CALL GIVING is a qualified reference.

A level-88 condition-name is indexed with its parent qualified by every enclosing group (`ConditionEntry.parent`), so `IF B OF D32` and `SET B OF D32 TO TRUE` select among same-named 88s the same way. A level-66 RENAMES item belongs to the 01 record it follows (`DataLayout.renames`): its FROM/THRU operands, elementary or group and qualified as written, resolve within that record, and the 66 item is itself qualified by the record name.

### Variable-length items (OCCURS DEPENDING ON)

Storage is allocated at the table's maximum. The bridge carries the DEPENDING ON object as a qualified reference (`CobolField.occurs_depending_on`, a `RefModOperand`), resolved by `qualified_matches` like any other operand. An unsubscripted reference to an item that ends in an OCCURS DEPENDING ON table (`DataLayout.odo_tail`) is as long as the object's current value says: the maximum less the inactive occurrences. Every read of it (MOVE and STRING senders, comparisons, INSPECT, UNSTRING, DISPLAY) takes that many characters. LENGTH OF it (in MOVE, arithmetic expressions and reference-modification bounds) and FUNCTION LENGTH of it are that length. As a receiver it is written over its current length and the bytes past it are kept, unless it contains its own ODO object, in which case it receives at its maximum length.

### PIC-Driven Encoding

| PIC Category | Encoding | Bytes | Example |
|---|---|---|---|
| `9(n)` (DISPLAY) | Zoned decimal — one byte per digit, sign in last byte zone; a SIGN clause moves it to the first byte or into a separate `+`/`-` byte. A signed item takes its own SIGN clause, else the nearest enclosing group's (resolved by the ASG reader, `CobolField.from_dict`; the bridge emits each entry's own clause) | n, +1 if SIGN SEPARATE | `PIC 9(5)` → 5 bytes |
| `S9(n) COMP-3` | Packed decimal — two digits per byte, sign nibble in last byte | ⌈(n+1)/2⌉ | `PIC S9(5) COMP-3` → 3 bytes |
| `X(n)` | Alphanumeric — one byte per character (ASCII or EBCDIC) | n | `PIC X(10)` → 10 bytes |
| `9(n) COMP` / `BINARY` | Big-endian two's-complement integer of the unscaled value (implied decimals and PIC P applied, truncated toward zero), cut to the PICTURE's digits as for any numeric receiver (IBM TRUNC(STD): 1023 into `PIC S999 COMP` stores 23); an unsigned item stores the magnitude, so a negative value is stored without its sign | 2 / 4 / 8 by n | `PIC 9(5) COMP` → 4 bytes |
| Numeric-edited | The edited characters, one byte per character position, built in IR from the PICTURE's plan (`cobol_asg.edit_picture.edit_plan`, `interpreter/cobol/numeric_edit_ir.py`). Trailing P divides the value before editing, and the item reads back as its characters, unscaled | one per character position | `PIC ZZZPP` holding 1200 → `" 12"` |

Encoding/decoding is performed via composable IR instruction builders in `ir_encoders.py`. Each builder returns a `list[InstructionBase]` using parameter registers (`%p_data`, `%p_digits`, etc.) that are inlined at the lowering site via `_inline_ir()`.

## Statement Coverage

Every statement operand states its kind. The bridge writes a data reference as `{"kind": "ref", "name", ...}` and a literal as `{"kind": "lit" | "figurative", "name": <text as written>, "numeric"?: true}`, read from the parse tree's alternative. The ASG reader keeps it on the operand (`RefModOperand.kind`, `CallUsingParam.kind` and `numeric`), and MOVE, DISPLAY, the arithmetic verbs, STRING, INSPECT, INITIALIZE REPLACING and CALL USING take a data item only where the bridge wrote a reference. A data name the program does not declare is an error, not literal text.

29 of 51 ProLeap statement types are handled (24 fully deterministic + 5 I/O stub via injectable provider):

### Arithmetic (6 types)

| Statement | IR Pattern |
|---|---|
| `MOVE X TO Y` | Decode X → encode as Y's type → `WRITE_REGION`. A group sender is an alphanumeric move with no conversion: its characters fill a numeric or edited receiver as one alphanumeric item, left to right, space-padded or truncated, with no editing (`MOVE` of a group holding `123ABC` to `PIC 99` stores `12`). An elementary sender moved to a group receiver is the same move the other way: the group takes the sender's stored bytes, so a separate or overpunched sign and COMP-3 or COMP bytes arrive unconverted (`PIC S9(5) SIGN LEADING SEPARATE` holding 7 fills `PIC X(7)`'s group with `+00007 `), while an elementary alphanumeric receiver still takes the digit image (`00007 `). A literal sender fills a group with its characters as written. HIGH-VALUE and LOW-VALUE fill any receiver with their raw byte, except an alphanumeric-edited one, which takes them as a literal of its size, edited in (`PIC XX0XX` gets `FF FF F0 FF FF`). |
| `ADD X W TO Y Z` | Sum the sending operands once (X + W), then for each receiver in turn: decode it → add the sum → encode → write. The bridge emits the sending operands as `operands` and the receivers, each with its own `rounded`, as `targets`. |
| `SUBTRACT X W FROM Y Z` | As ADD: each receiver loses the sum X + W. |
| `MULTIPLY X BY Y Z` | Each receiver in turn becomes receiver × X. |
| `DIVIDE X INTO Y Z` | Each receiver in turn becomes receiver ÷ X. |
| `... GIVING G H` | The result is computed once as `operands[0] <op> (sum of the remaining operands)` — ADD sums every operand, `SUBTRACT X W FROM Y GIVING G` is Y − (X + W) — and written to every GIVING receiver, each with its own ROUNDED. |
| Size error condition | A result is a size error when it reaches 10^(the receiver's integer digit positions) — e.g. 100 for `PIC 99V9`, 1 for `PIC V999`, 10000 for `PIC $9999.00` (a numeric-edited receiver counts 9, Z, * and floating symbols but the first, never insertion characters). Digits past the receiver's decimal places are truncated and never cause one: 99.95 into `PIC 99V9` stores 99.9. The magnitude decides, not the sign (emitted as IR: result ≥ capacity or result ≤ −capacity): −4.57 into an unsigned `PIC V999` is a size error, while −3 into an unsigned `PIC 9` stores 3. A ROUNDED receiver is rounded first and the rounded value is tested and stored: −99.4 ROUNDED into `PIC S99` stores −99, −99.5 ROUNDED is a size error. PIC P scaling moves both positions: `PIC S99P` holds up to ±990 and ROUNDED rounds it to tens (0 − 99 ROUNDED stores −100); `PIC PP9` holds up to .009. |
| `ON SIZE ERROR` with several receivers | Per receiver: one whose result does not fit is left unchanged while the others are written; ON SIZE ERROR runs once afterwards if any receiver failed, NOT ON SIZE ERROR otherwise. DIVIDE by zero is a size error for every receiver. |
| `DIVIDE ... GIVING ... REMAINDER r` | `remainder = dividend - quotient * divisor`, where `quotient` is the GIVING quotient truncated to that receiver's decimal places (before any ROUNDED), computed exactly from the same operands; it is written back alongside the quotient, so not when the quotient has a size error. `DIVIDE X INTO Y GIVING Z` computes `Z = Y / X` (dividend/divisor); `DIVIDE X BY Y GIVING Z` computes `Z = X / Y`. The bridge names each operand by its role as written (DIVIDE `dividend` and `divisor`; SUBTRACT `subtrahends` and, with GIVING, `minuend`), and the typed ASG reads them by name. |
| `MOVE CORRESPONDING A TO B ...` | Each corresponding pair is a separate MOVE of A's item to B's. Items correspond when their names and every qualifier below A and B agree, at any depth, and at least one of the two is elementary (an elementary item paired with a group is an alphanumeric group move). A subordinate item with OCCURS or REDEFINES, everything under it, FILLER and RENAMES items never pair. Subscripts on A and B select the occurrence each pair is read from and written to. Each group is found in whichever section declares it (WORKING-STORAGE, LOCAL-STORAGE, LINKAGE, FILE); a LINKAGE group reads and writes its caller's argument. |
| `ADD/SUBTRACT CORRESPONDING A TO/FROM B [ROUNDED] [[NOT] ON SIZE ERROR]` | Each pair of corresponding items that are both elementary numeric (same pairing rules as MOVE CORRESPONDING) is a separate ADD/SUBTRACT of A's item to/from B's, with the statement's ROUNDED and the same exact arithmetic and per-receiver size error test as the other arithmetic verbs: a pair whose result does not fit leaves its B.field unchanged, the others are written, and ON SIZE ERROR (or NOT ON SIZE ERROR) runs once after every pair. Non-matching fields untouched. |
| `COMPUTE Y Z = expr` | Recursive expression lowering, then stored in every receiver as for GIVING: each with its own ROUNDED and its own size error test. |

### Control Flow (7 types)

| Statement | IR Pattern |
|---|---|
| `IF / ELSE` | `_lower_condition()` → `BRANCH_IF` → true/false blocks |
| `EVALUATE / WHEN` | Chain of `BRANCH_IF` per WHEN, `WHEN OTHER` as fallthrough. The bridge sends typed selection subjects (an expression, a condition, or `TRUE`/`FALSE`) and, per WHEN, one selection object per subject (`ANY`, `TRUE`/`FALSE`, a condition, `[NOT] value`, `[NOT] low THRU high`), every operand a structured expression. An expression subject is compared with a value or range through the relation-condition lowering, the `NOT` negating it; under a condition or truth-value subject the WHEN is selected when both have the same truth value, an identifier object there being a condition-name. The pairs are ANDed via `BINOP &&`; `ANY` skips its position. Stacked WHENs (`WHEN c1 WHEN c2 <body>`) are one `WhenStatement` with one body: the first WHEN's objects on the WHEN itself, the rest in `alternatives`, ORed via `BINOP or`. |
| `PERFORM` | Simple: `SET_CONTINUATION` + `BRANCH` to paragraph. TIMES/UNTIL/VARYING: loop with counter/condition. The TIMES count and each VARYING/AFTER identifier, FROM and BY operand is a structured expression node, so an identifier contributes its value and a subscripted one addresses its occurrence. VARYING/AFTER sets every identifier to its FROM value, outermost first; stepping a level resets every level inside it to FROM; TEST BEFORE tests the UNTILs outermost first before the body, TEST AFTER tests them innermost first after the body and before any step. THRU: range of procedures; control returns at the end of the THRU procedure, which for a section is the end of its last paragraph. Section-level: all paragraphs in section. |
| `GO TO` | `BRANCH` to paragraph label. The GO TO of a paragraph that holds nothing else (`P. GO TO Q.` or `P. GO TO.`) is alterable: it branches to a dispatch, emitted after the procedure, that compares the variable `__alter_<PROGRAM>_<label>` with the ordinal of each ALTER target named for P anywhere in the program (1, 2, ... in the order the ALTERs are lowered) and branches to the match, or to the written target (after the GO TO for `GO TO.`) on 0. |
| `STOP RUN` | `HALT` — unconditionally terminates the entire run unit. Emitted by `lower_stop_run` as a dedicated `Halt_` IR instruction (`interpreter/instructions.py`), distinct from `RETURN`/`Return_`. Previously (fixed red-dragon-mjin) STOP RUN lowered to the same `Return_` as GOBACK/EXIT PROGRAM, so a callee's STOP RUN incorrectly returned control to the caller instead of halting the whole program. |
| `GOBACK` | `RETURN` — returns control to the caller (subprogram) or terminates (main program). No longer the same IR as STOP RUN (see above). |
| `EXIT PROGRAM` | `RETURN` — returns control to the caller. Distinguished from plain `EXIT` (no-op) by the bridge via `ExitStatementContext.PROGRAM()`. |

### No-ops (2 types)

| Statement | IR Pattern |
|---|---|
| `CONTINUE` | No IR emitted |
| `EXIT` | No IR emitted |
| `EXIT PERFORM` / `EXIT PERFORM CYCLE` | `BRANCH` to `perform_leave_<n>` after the innermost inline PERFORM, or to `perform_cycle_<n>` after one iteration of its body — before the loop's own step (TIMES count, VARYING increment, UNTIL test), which still runs. Numbered from their own counter, so no other label is renumbered, and emitted only when an EXIT asked for them. Outside an inline PERFORM it is not lowered and raises |
| `NEXT SENTENCE` | `BRANCH` past the period that ends its sentence: the bridge records each paragraph's `sentence_ends` (positions of each sentence's last statement), and the lowering places `para_<name>_sentence_<n>_exit` after that statement, only when a NEXT SENTENCE asked for it. Unlike CONTINUE it skips anything after an `END-IF` or `END-SEARCH` in the same sentence. Outside a paragraph (section- or division-level statements) it is not lowered and raises |
| `EXIT PARAGRAPH` / `EXIT SECTION` | `BRANCH` to `para_<name>_exit` / `section_<name>_exit`, a label emitted just before the construct's `ResumeContinuation` — and only when some EXIT asked for it, so programs without these statements lower unchanged |

### Data Manipulation (2 types)

| Statement | IR Pattern |
|---|---|
| `INITIALIZE` | A MOVE into every occurrence of each elementary item, FILLER and REDEFINES items skipped: SPACES to character items and ZERO to numeric ones, so an edited item is edited; with REPLACING, only the named categories, each from its own literal or identifier |
| `SET` | TO: encode value → write. UP/DOWN BY: decode → `BINOP +/-` → encode → write. A subscripted or qualified target or value resolves to the occurrence it names. Each target takes the value of its own TO phrase (`SET A TO 1 B TO 2`). |
| `SET mnemonic TO ON\|OFF` | An implementor switch's mnemonic-name: `CALL_FUNCTION __cobol_set_switch(environment-name, status)`. A switch-status condition-name (`ON STATUS IS c`) lowers to `__cobol_switch_status(environment-name)` compared with its status. The switch settings are a run input held by the I/O provider (`RealFileIOProvider(base_dir, RunInputs(switches=...))`); a switch not supplied is OFF. |
| `SET p TO ADDRESS OF x \| NULL \| q` | A POINTER target: the address — x's region register `BINOP +` its offset, 0 for NULL, or q's contents — written as the addressing mode's binary (`INT_TO_BINARY_BYTES`, signed, 4 bytes under LP(32), 8 under LP(64)). |
| `SET ADDRESS OF lk TO …` | A LINKAGE 01 or 77 item only: its region register becomes the address and its shift moves its static start there (`STORE_VAR` into its binding variables, then `LOAD_VAR` into its binding registers, so every later access follows). A subordinate item is rejected at lowering. |
| `SET p UP/DOWN BY n` | A POINTER target: decode → `BINOP +/-` n bytes → write the address back. |
| `ADDRESS OF x` in a condition | x's region register `BINOP +` its offset; NULL is 0, so `ADDRESS OF lk = NULL` tests for an OMITTED or unsupplied parameter. |
| `USAGE POINTER` | A signed binary of the addressing mode's width; the `LP` option given to `compile_cobol` sets it, and the ASG reader lays the item out with that width. |
| `USAGE INDEX` | An unsigned fullword binary holding an occurrence number, like an `INDEXED BY` index; `SET` moves one into and out of it. A USAGE written on a group applies to every elementary item in it (the ASG reader, `CobolField.from_dict`, takes the nearest enclosing USAGE; the bridge emits each entry's own clause). |

### String Operations (3 types)

| Statement | IR Pattern |
|---|---|
| `STRING ... INTO` | Each sending is evaluated once: a data item's stored characters, a figurative constant's single character, or a literal's text, cut at the first occurrence of its DELIMITED BY operand (a literal, figurative constant or data item; SIZE keeps it whole) → IR (`interpreter/cobol/string_ir.py`) moves the parts, one after another, into the receiver's current characters from the pointer (1 without WITH POINTER) until the receiver is full → write the receiver and the pointer back → branch to ON / NOT ON OVERFLOW. The pointer advances by the characters moved; overflow is a pointer below 1 or past the receiver, or characters left over. Characters STRING does not transfer keep their value. |
| `UNSTRING ... INTO` | The source (with its qualifiers, subscripts and reference modification), the pointer (1 without WITH POINTER) and every delimiter (a literal, figurative constant or data item, with its ALL flag) are evaluated once → IR (`interpreter/cobol/unstring_ir.py`, one block per receiver) examines the source from the pointer: each receiver takes the characters before the nearest delimiter (the first written wins a tie; ALL takes a run of contiguous occurrences), or its own size without DELIMITED BY → each receiver reached is written, with its DELIMITER IN (spaces at the end of the source) and COUNT IN; receivers not reached are untouched → the pointer is written back and TALLYING IN gains the receivers acted on → branch to ON / NOT ON OVERFLOW. Overflow is a pointer below 1 or past the source, or characters left unexamined after the last receiver. |
| `INSPECT` | An IR loop over the inspected characters (no builtin of its own). TALLYING → add each identifier's count. REPLACING → write back. TALLYING ... REPLACING: both, tallying first. CONVERTING → write back. See INSPECT Lowering |

### Table Operations (1 type)

| Statement | IR Pattern |
|---|---|
| `SEARCH` | Loop with bound check against the current occurrence count (OCCURS DEPENDING ON honoured), WHEN condition chain (`BRANCH_IF` per clause), the table's index advanced with any VARYING operand in step, AT END fallthrough; `SEARCH ALL` starts from occurrence 1 |

### Inter-program (4 types)

| Statement | IR Pattern |
|---|---|
| `CALL 'prog' USING params` | One address per argument, by position. The caller builds an argument array (`NEW_ARRAY`, a `count` field, one `NEW_OBJECT` per argument holding `mode` — `ArgumentMode` REFERENCE, CONTENT, VALUE or OMITTED — its byte `length`, and, unless OMITTED, `signed` (a signed numeric item), `region` and `offset`) and dispatches via `CALL_WITH_MEMORY __entry_<NAME>`, binding the array to the callee entry function's `__call_arguments` parameter. BY REFERENCE hands over the argument's own region and offset, so the callee's writes land in the caller as they happen and nothing is copied back — which is also why they survive a callee's STOP RUN. BY CONTENT, BY VALUE and a literal hand over a fresh `RegionId.CALL_ARGUMENT` copy. A literal is copied in the representation IBM defines: under BY VALUE a fixed-point numeric literal or ZERO as a fullword binary and a floating-point literal as COMP-2; a figurative constant as one byte of its character (HIGH-VALUE and LOW-VALUE raw); anything else as its characters. `LENGTH OF x` (`OperandKind.LENGTH_OF`) hands over a fresh copy of x's length as PIC 9(9) BINARY, BY CONTENT or BY VALUE; BY REFERENCE raises `LengthOfByReferenceError`, since IBM allows the special register only by content or value. OMITTED has length 0 and no address. A reference-modified operand (`CallUsingParam.ref_mod`, static or data-name bounds) hands over its substring: BY REFERENCE the substring's own bytes, so the callee's writes land at that offset in the caller's item; BY CONTENT and BY VALUE a fresh copy of the whole item, at the substring's offset. A BY VALUE data item must be elementary binary, COMP-1, COMP-2 or a pointer, one alphanumeric character, or a DISPLAY item reference-modified to a literal length of 1, as IBM's CALL statement requires; any other raises `ByValueOperandError` at lowering, naming it and its line. A PROCEDURE DIVISION USING BY VALUE parameter is held to the same rule (`allowed_by_value`), the error giving the line the LINKAGE item is declared on. The callee binds each LINKAGE 01 to the argument at its PROCEDURE DIVISION USING position (`CobolASG.procedure_using`; declaration order when there is no USING) in plain IR: a region register and a shift, which every LINKAGE field access adds to its static offset. LINKAGE keeps its static end-to-end layout for strides and analysis extents. An absent or OMITTED parameter binds NULL — `ADDRESS OF` it is NULL, and touching it goes to the VM's null-access strategy (warn and read zeroes by default, or halt); a LINKAGE 01 USING does not name binds zero-filled storage of its own. `USING BY VALUE|CONTENT|REFERENCE ADDRESS OF x` hands over a fresh copy of x's address. A parameter declared wider than its argument reads on into the caller's following bytes. GIVING writes the result back. With ON EXCEPTION (or ON OVERFLOW), `__cobol_program_present` first tests whether the entry variable is bound to a function: if not, the ON EXCEPTION statements run and the CALL is not made; if so, the program is called and NOT ON EXCEPTION follows. Without ON EXCEPTION the call is made, and a program not in the run unit goes to the run's unresolved-call strategy (`permit_unresolved_call_targets`). |
| `ALTER para-1 TO PROCEED TO para-2` | `STORE_VAR __alter_<PROGRAM>_<para-1 label>` = para-2's ordinal among para-1's ALTER targets. The program's initial state (at load, and on the first entry after a CANCEL) sets every alterable GO TO's variable back to 0. |
| `ENTRY 'name'` | `LABEL entry_name` (alternate subprogram entry point) |
| `CANCEL prog` | Puts each named program back in its initial state. A program's WORKING-STORAGE is laid down by one block in its init block (`__ws_initial_<pid>_0`: `ALLOC_REGION`, the VALUE encodings, `STORE_FIELD ws_handle`, `STORE_FIELD initial_state False`, `RESUME_CONTINUATION`), which the init block runs through once at load with no continuation set. Each operand is a literal or an identifier, serialised as CALL's callee is (`program` or `program_ref`); an identifier's contents are read at run time, trimmed and upper-cased as for CALL identifier. The start-up module declares a program directory, `__cobol_programs`, and each program's init block lists its program object there under its name. CANCEL looks the name up with `dict_contains_key` and, when it is there, loads the object with `LOAD_FIELD_INDIRECT` and sets its `initial_state`; a name not in the run unit is passed over. The procedure's entry tests `initial_state` and, when set, performs the block (`SET_CONTINUATION` + `BRANCH`, the PERFORM pattern) before binding `__ws_region`, so the next CALL sees the VALUE clauses again. CANCEL of a program never called, or already cancelled, changes nothing. Each program also emits a cancel routine, `func_cancel_<pid>_0`, after its procedure behind a branch, registered as `__cancel_<PID>`: for each of its files with an internal connector that is open, it runs the CLOSE statement's own close (no FILE STATUS update, no USE procedure); EXTERNAL files are left alone. CANCEL calls it with `CALL_WITH_MEMORY` on `'__cancel_' + name`, after setting `initial_state`. |

### I/O (8 types — HANDLED_STUB)

| Statement | IR Pattern |
|---|---|
| `ACCEPT var` | A loop of `CALL_FUNCTION __cobol_accept(device)`, one record (`IOResult`) per call, concatenated with `__string_concat_pair` until `__length` reaches the receiver's byte length or the outcome is not OK (input ended) → `__string_slice` to that length → store the characters unedited (`as_characters`) → `WRITE_REGION` to target field. No record received leaves the field unchanged. `RealFileIOProvider(base_dir, RunInputs(system_input=...))` returns successive system input records, then END_OF_FILE |
| `OPEN mode file` | `CALL_FUNCTION __cobol_open_file(filename, mode, program)` per file. The program's start-up code (module scope, once per run unit, before any OPEN) declares each SELECT to the provider with `__cobol_declare_file(frame, program)`: `frame` is a Const holding the `DataRecord` of a `FileFrame` (`file_frame.py`), which the provider reads back with `frame_of`. It carries what the driver frames records by: the file name, organization, the RECORD KEY's offset and length within the file's own record area (not within the FILE region), `variable` (true when the FD's records vary in length: RECORDING MODE V or S; else RECORD IS VARYING, RECORD CONTAINS m TO n with m ≠ n, or 01s of different lengths or with OCCURS DEPENDING ON), `record_length`, the FD's largest record, the length of its record area, and `alternate_keys`, each ALTERNATE RECORD KEY's offset, length and uniqueness (unique unless WITH DUPLICATES), in declaration order. The indexed driver keeps one index per alternate key, built when the file opens. Duplicates of an alternate key are kept in the order they were stored; after a CLOSE and OPEN that order is prime-key order. The driver refuses a WRITE or REWRITE that would duplicate a unique alternate key (22), and reports one that duplicates an alternate key WITH DUPLICATES (02) |
| `CLOSE file [REEL\|UNIT [FOR REMOVAL]] [WITH NO REWIND\|LOCK]` | `CALL_FUNCTION __cobol_close_file(filename, program)` per file; WITH LOCK is IR state (the file's `locked` variable), not a separate call. The bridge lists the files each phrase was written on (`reel_unit`, `for_removal`, `no_rewind`, `with_lock`). Every file is on a non-reel/unit medium, so REEL or UNIT (with or without FOR REMOVAL or NO REWIND) leaves the file open and sets status 07 without calling the primitive (IBM's code F); WITH NO REWIND alone closes the file and turns its 00 into 07. A file that is not open is refused with 42 either way |
| `READ file [NEXT] INTO var` | `CALL_FUNCTION __cobol_read_record(filename, key, program)` → `__cobol_io_data(result, program)` → the record into the FD's record area and, when the READ succeeds, into the INTO item space-filled or truncated to its length (an alphanumeric move). `key` is, for a random READ (RANDOM access, or DYNAMIC without NEXT), an indexed file's key of reference as bytes (the KEY phrase's item, else the RECORD KEY) or a relative file's KEY phrase or RELATIVE KEY value, else `""`. For a random READ of a file that has alternate keys, `CALL_FUNCTION __cobol_key_of_reference(filename, n, program)` comes first: `n` is 0 for the RECORD KEY, else the ALTERNATE RECORD KEY whose leftmost character position the KEY phrase's item shares. Sequential READs follow the key of reference. A READ by a key with duplicates gives 02 when the next record in that key has the same value. After a random READ, READ NEXT returns the record following the one read |
| `WRITE rec FROM var` | Decode FROM field → `CALL_FUNCTION __cobol_write_record(filename, data, key, program)`; `key` is a relative file's RELATIVE KEY under RANDOM or DYNAMIC access, else `""` |
| `REWRITE rec FROM var` | Decode FROM field → `CALL_FUNCTION __cobol_rewrite_record(filename, data, key, program)`, `key` as for WRITE |
| `START file KEY key` | `CALL_FUNCTION __cobol_start_file(filename, key, relop, program)` — `key` is the KEY item's bytes (indexed) or value (relative); without KEY, the RECORD KEY or RELATIVE KEY's, with `=`. An indexed KEY item shorter than the RECORD KEY is compared with the record key's leading bytes. The file is positioned at the first record satisfying the relation; when none does, the status is 23. For a file with alternate keys, `__cobol_key_of_reference(filename, n, program)` precedes the START. `n` is the key the KEY item names, by its leftmost character position (a REDEFINES or a leading part of an alternate key names that key), or 0 without KEY. That key becomes the key of reference for the READ NEXTs that follow |
| `DELETE file` | `CALL_FUNCTION __cobol_delete_record(filename, key, program)` — `key` is the RECORD KEY's bytes or the RELATIVE KEY's value in random or dynamic access, empty in sequential access |
| `SORT sd ON ASCENDING/DESCENDING KEY k ... USING f ... GIVING g ...` | `OPEN OUTPUT sd`; per USING file `OPEN INPUT f`, an IR loop of `__cobol_read_record(f)` → `__cobol_write_record(sd)` until the read is not successful, `CLOSE f`; then the ordering pass (below); per GIVING file `OPEN INPUT sd`, `OPEN OUTPUT g`, the same loop from `sd` to `g`, `CLOSE g`, `CLOSE sd` |
| `SORT ... INPUT PROCEDURE p [THRU p2] ... OUTPUT PROCEDURE q [THRU q2]` | As above, with a procedure PERFORM of `p` in place of the USING copies (after `OPEN OUTPUT sd`) and of `q` in place of the GIVING copies (between `OPEN INPUT sd` and `CLOSE sd`) |
| `MERGE sd ON ASCENDING/DESCENDING KEY k ... USING f1 f2 ... GIVING g ... \| OUTPUT PROCEDURE q` | Lowered as the SORT with those USING files: the stable sort of the files' records, read in USING order, is their merge, equal keys coming out in USING-file order |
| `RELEASE rec [FROM x]` | Lowered as `WRITE rec [FROM x]` on the sort file |
| `RETURN sd [INTO x] AT END ... NOT AT END ...` | Lowered as `READ sd [INTO x] AT END ... NOT AT END ...` on the sort file |

The sort file (SD) is a sequential work file at its ASSIGN path, opened and closed by the same lowering as any file. The ordering pass is IR on the file primitives: it closes the SD, reopens it INPUT under the frame the program declared for it at start-up (so a varying SD keeps each record its own size) and collects its records into a list, reopens it OUTPUT, and writes back the records `__cobol_sort_records(records, ordering)` returns. That builtin, the only SORT builtin, puts the records in key order. `ordering` is one `SortOrdering` record: the keys, major to minor as written, each with its offset relative to the sort record, length, encoding and direction, and `weights`, the 256 collating weights (entry b the weight of native byte b) of the alphabet the COLLATING SEQUENCE phrase names, else of the program collating sequence. The bridge writes each COLLATING SEQUENCE phrase as written (`{"alphabet_names", "alphanumeric"?, "national"?}`, on the statement and as `special_names.program_collating_sequence`) and every ALPHABET clause once (`special_names.alphabets`); the ASG reader (`CollatingSequencePhrase`) takes the FOR ALPHANUMERIC name, else the first, and refuses a name no ALPHABET clause declares. Numeric keys (zoned with any SIGN clause, packed, binary, COMP-1/COMP-2) compare by algebraic value, alphanumeric and edited keys byte by byte through the weights, with a stable sort so records with equal keys keep the order they were released in.

Each file primitive returns an `IOResult` holding the driver's outcome, an `AccessCondition` (OK, duplicates follow, end of file, not found, duplicate key, file not found, attribute conflict, open mode not supported, boundary violation, not open, write not permitted), never a FILE STATUS. `__cobol_io_outcome(result, program)` gives the condition's name, and the IR maps it to the status it reports (`outcome_status.py`): 00, 02, 10, 23, 22, 35, 39, 37, 44, 47 and 48. A sequential READ or WRITE of a relative file MOVEs `__cobol_io_record_number(result, program)` to its RELATIVE KEY when the status is successful. Each verb's I-O status rules are IR around its primitive (`file_verb_ir.py`): the checks run in order, the first that holds sets the status and the primitive is not called. Per program and file (the program whose SELECT declares it), module-scope variables `__cobol_file_<PROGRAM>_<FILE>_mode`, `_locked`, `_position`, `_absent` and `_last_key` hold the open mode, whether it was closed WITH LOCK, the position indicator (no current record, current record, at end), whether it is an OPTIONAL file opened INPUT while absent, and the prime key of its last record read or written. The IR reports 41 OPEN of an open file, 42 CLOSE of a closed one, 43 REWRITE/DELETE in sequential access without a preceding successful READ (any statement in between, even a failed one, clears the current record), 46 a sequential READ after at end, 47/48/49 a verb the open mode does not permit, and 38 OPEN after CLOSE WITH LOCK. It also reports 14 for a READ of a relative file whose record number has more digits than the RELATIVE KEY (no record and no number; the RELATIVE KEY's digit count is a lowering-time constant), 44 for a WRITE or REWRITE of a variable-length record outside the FD's smallest and largest sizes (constants too), and 24 for a WRITE of a relative file at a record number below 1 (READ, REWRITE, DELETE and START at 0 find no record, 23, from the driver). The open primitive answers 35 for any OPEN other than OUTPUT of a file that does not exist. For an OPTIONAL file the IR turns that into 05: for INPUT the file's `_absent` variable is set, it is not created, and READ gives 10 (a keyed READ or START 23) and CLOSE 00 without calling the provider; for I-O and EXTEND the IR creates it by an OUTPUT open and a close, then opens it again. In sequential access to an indexed file the IR keeps the prime key of the last record read or written in the file's `_last_key` variable and reports 21 for a WRITE whose prime key is below it or a REWRITE whose prime key differs from it. The provider's primitives do I/O only and return the driver's outcome. AT END runs for any class 1 status (10 or 14). A USE declarative fires for any unsuccessful status the statement's own AT END (class 1) or INVALID KEY (class 2) phrase does not handle; one scoped by open mode is chosen by the mode an OPEN attempts, and for other verbs by the file's `mode` variable; which one runs follows the precedence in [GLOBAL names](#global-names). `program` is the calling program's PROGRAM-ID, upper-cased, a constant the lowering emits as the last argument of every file call, and each `CobolIOProvider` method takes it as its last parameter; red-dragon's providers accept and ignore it (ADR-185).

The drivers, `AccessCondition`, `FileFrame`, `RunInputs`, the record-operation interface `RecordIOProvider` and the disk provider `RealFileProvider` are record I/O shared with HLASM, in `interpreter/record_io/`. I/O statements dispatch to an injectable `CobolIOProvider` (in `io_provider.py`). `NullIOProvider` returns `UNCOMPUTABLE` (symbolic fallthrough). `StubIOProvider` returns queued test data for concrete execution without real files or console. Provider is injected via `run(..., io_provider=stub)` or `initial_vm_state(io_provider=stub)`. A `CobolIOProvider` is a `RecordIOProvider` that also serves ACCEPT and the switches and KEY OF REFERENCE.

Every 01 under one FD starts at that FD's record area (an implicit redefinition), so a MOVE to one record is what a WRITE of another record of the same file sends. Each FD has its own area, as long as its largest record; the ASG reader places the areas one after another in the FILE region (red-dragon-sl30.31). The files an I-O-CONTROL `SAME RECORD AREA` clause names share one area, as long as the largest of their records. The bridge passes each clause's file names as `same_record_areas`, and `CobolASG.record_area` names the area a record lies in (red-dragon-sl30.97). `SAME AREA` and `SAME SORT AREA` leave each file its own record area. The bridge emits no offsets: `cobol_asg/storage_layout.py` computes every item's offset and OCCURS element size from its picture and usage (ADR-188).

Each FD's `RECORDING MODE` and `RECORD` clause (`CONTAINS n`, `CONTAINS m TO n`, `IS VARYING [FROM m] [TO n] [DEPENDING ON x]`) reach `CobolASG.file_descriptions` as `FileDescription` values, for an I/O provider to derive the file's record format from. A `WRITE` or `REWRITE` hands the provider the record at its own length: the RECORD VARYING DEPENDING ON item's value in bytes of the record area, else the named record's length; after a successful `READ` the DEPENDING ON item is set to the length of the record read. `RealFileIOProvider` stores a variable sequential file as records behind 4-byte record descriptor words and a variable relative file as slots of 4 + maximum bytes led by one; a sequential `REWRITE` of another length, and a `WRITE` or `REWRITE` of a variable record shorter than the smallest or longer than the largest, give 44 (ADR-187). A DEPENDING ON value past the record area releases one byte more than the area, so the provider sees the record is too long.

An FD's `LINAGE` clause reaches `FileDescription.linage` as a `LinageClause`: the page body's lines, the first footing line (`NoFooting` when WITH FOOTING is not written) and the top and bottom margins, each an integer or a data-name expression; the bridge passes the clause as written (`linage: {lines, footing?, top?, bottom?}`). Each such file gets a `LINAGE-COUNTER` in the program's special-register region, after RETURN-CODE, declared under a group named after the file so that `LINAGE-COUNTER OF file` resolves it (the bridge passes the file name as the qualifier of `LINAGE-COUNTER IN/OF file` only); an unqualified reference with two LINAGE files is ambiguous. For an integer the counter is binary with that integer's digits, for a data-name it has the data-name's PICTURE and USAGE (IBM Enterprise COBOL LR, LINAGE-COUNTER). The bridge passes a WRITE's `advancing` (`{position: BEFORE|AFTER, kind: LINES|PAGE|MNEMONIC, lines?, mnemonic?}`; the ASG reader takes no phrase as AFTER ADVANCING 1 LINE) and its `at_end_of_page` and `not_at_end_of_page` statements. For a LINAGE file the counter, page and end-of-page logic is IR around the unchanged file primitives (`linage_page.py`, `linage_write.py`): a successful OPEN begins the first logical page, storing the page body and footing in the file's `_page_body` and `_page_footing` variables and setting the counter to 1; a successful WRITE ADVANCING n (or without ADVANCING, 1) adds n, unless that would pass the page body, when it begins the next page with the clause's values taken again (so a data-name's new value applies from the next page) and resets the counter to 1; ADVANCING PAGE begins the next page. The end-of-page condition holds on a page overflow, or when the counter reaches the footing line (never without WITH FOOTING); AT END-OF-PAGE then runs after the WRITE, NOT AT END-OF-PAGE after any other successful WRITE. Advancing writes no records of its own: a file holds one record per WRITE, BEFORE and AFTER alike, and the margins have no effect on what is written; a WRITE on a file without LINAGE ignores its ADVANCING phrase.

### Remaining 19 types

Not yet implemented in the bridge. Includes communication (SEND, RECEIVE), embedded SQL (EXEC SQL), and less common statements (GENERATE, MERGE, etc.).

## PERFORM Semantics

PERFORM uses named continuations (`SET_CONTINUATION`/`RESUME_CONTINUATION`) to implement paragraph-level call-and-return:

```
SET_CONTINUATION "para_WORK_end" → "return_point_N"
BRANCH → "para_WORK"
LABEL "return_point_N"
```

At the end of each paragraph, `RESUME_CONTINUATION "para_WORK_end"` returns to the saved label. This supports:

- Simple PERFORM (call one paragraph)
- PERFORM THRU (call a range of paragraphs)
- Section-level PERFORM (call all paragraphs in a section)
- PERFORM TIMES/UNTIL/VARYING (loops wrapping the continuation-based call)

Every section and paragraph label, its `_end` continuation and its `_exit` landing is built by `ProcedureLabels` (`interpreter/cobol/procedure_labels.py`) from the upper-cased procedure-name. Procedure-names are COBOL words and case-insensitive, so `perform pass` reaches a paragraph declared `PASS.`

A paragraph-name need be unique only within its section. A name declared once keeps the label `para_<NAME>`; a name declared in two sections is labelled `para_<SECTION>_<NAME>` in each. `PERFORM`/`GO TO P OF S` (or `IN S`) reaches S's P; an unqualified P means the P in the referencing section, else the section that declares it. The bridge carries the qualifier as `ProcedureRef.section` (GO TO) and `PerformStatement.target_section`/`thru_section`.

## String Operation Builtins

String operations use these low-level builtins registered in `byte_builtins.py`:

| Builtin | Signature | Purpose |
|---|---|---|
| `__string_find` | `(source, needle) → int` | Find first occurrence (-1 if not found) |
| `__string_split` | `(source, delimiter) → list[str]` | Split by delimiter |
| `__string_concat` | `(parts) → str` | Concatenate list of strings |
| `__string_slice__` | `(source, start, length) → str` | Extract substring (0-based start, exclusive end); used for reference modification reads |
| `__string_splice__` | `(source, start, length, replacement) → str` | Replace substring (0-based start); used for reference modification writes |

These are composed into IR instruction sequences via builders in `ir_encoders.py` (`build_string_split_ir`); INSPECT uses its own builtins (see INSPECT Lowering). The composed IR is inlined at each lowering site, keeping all operations visible to data-flow analysis.

## INSPECT Lowering

The inspected item (with its qualifiers, subscripts and reference modification) and every operand are evaluated once, then the scan runs as IR emitted per statement by `interpreter/cobol/inspect_ir.py` from the string primitives (`__string_find`, `__string_slice`, `__string_splice`) and a loop: each round finds every phrase's nearest match at or after the cursor and applies the nearest, so positions where nothing matches cost nothing, and a symbolic operand flows through the primitives instead of making the whole result opaque. Each phrase (CHARACTERS, ALL, LEADING, FIRST) has a region: it starts after the first occurrence of its AFTER operand (an AFTER operand that does not occur leaves the region empty) and ends before the first occurrence of its BEFORE operand at or after that start (one that does not occur leaves the region running to the end). The item is scanned left to right once; at each position the phrases are tried in the order written, and the first that matches inside its region is applied and consumes the matched characters. LEADING matches only contiguously from its region's start, FIRST at most once. TALLYING adds each identifier's matches to its value; REPLACING rewrites the matched characters (a one-character BY fills them all); TALLYING ... REPLACING tallies and then replaces; CONVERTING translates the characters inside its region. A reference-modified item is rewritten in place. The bridge serialises operands as data references, keeps phrases in written order, and starts a new ALL phrase where the grammar has read `ALL literal` as a figurative operand of the previous phrase.

## SEARCH Lowering

SEARCH implements a linear table search. The search index is the VARYING
operand when it is one of the table's own `INDEXED BY` names, otherwise the
table's first `INDEXED BY` name; a VARYING operand that is another table's index
or a data item is incremented in step with it. The loop ends once the search
index exceeds the table's current occurrence count, which is the value of the
OCCURS DEPENDING ON object for a variable table and the OCCURS count otherwise. `SEARCH ALL`
sets the search index to 1 first and scans the whole table, which finds the same
entry a binary search would in a correctly ordered table.

```
  [SEARCH ALL: search index = 1]
  bound = ODO object value | OCCURS count
LABEL search_loop:
  BINOP > search index, bound
  BRANCH_IF → at_end, body
LABEL body:
  ; For each WHEN clause:
  lower_condition(when.condition)
  BRANCH_IF → when_true, when_next
  LABEL when_true:
    lower_statement(when.children)
    BRANCH → search_end
  LABEL when_next:
  ; ... next WHEN ...
  BRANCH → search_incr
LABEL search_incr:
  search index += 1; VARYING companion += 1
  BRANCH → search_loop
LABEL at_end:
  lower_statement(at_end children)
LABEL search_end:
```

A table whose occurrence count is unknown falls back to an iteration counter
bounded by a runaway guard.

## Condition Lowering

The Java bridge writes a condition as the parse tree has it: `{"first": <atom>, "rest": [...]}`, each link an AND or OR with either one atom or a list of abbreviations (`{"not", "op"?, "right"}`), and a combined relation `A = (X OR Y)` as `{"combined": {"left", "op", "bool", "operands"}}`. The ASG reader (`cobol_asg/abbreviated_condition.py`) resolves it into the tree lowering walks (ANSI X3.23-1985 VI-6.15):

- AND binds tighter than OR: `{"op": "AND"|"OR", "left": ..., "right": ...}`.
- An abbreviated operand takes the last stated subject and relational operator; a NOT immediately before an operator is part of it, and a NOT before a bare operand negates that relation: `{"not": bool, "relation": {"left", "op", "right"}}`.
- A bare identifier after a relation parses as a condition name. The bridge passes ProLeap's name resolution through, as it does for EVALUATE: a name that resolves to a data item arrives as `{"not": bool, "data_operand": <ref>}`, and the ASG reader expands it with the last stated subject and operator (with no stated subject it stays as text). Anything else, a level-88 or a switch condition, arrives as `{"not": bool, "condition_name": ...}` (names indexed over WORKING-STORAGE, LOCAL-STORAGE, LINKAGE and the FILE SECTION; switch condition-names from SPECIAL-NAMES).
- A combined relation expands into one relation per operand under `"condition"`; a parenthesised condition is resolved the same way.

`_lower_condition()` deserializes this tree and recursively emits IR: leaf relation nodes produce a `BINOP` comparison; compound nodes chain via `BRANCH_IF` with short-circuit blocks.

A relation with a nonnumeric operand (a nonnumeric literal or figurative, a reference-modified slice, or an alphanumeric, edited or group item) compares characters. A numeric operand there becomes its digit characters without the sign: an integer literal as written, an unsigned zoned item its own bytes, any other numeric item the digits of its value (in IR: the value's digits encoded as unsigned zoned decimal and read back as characters, each P position a trailing zero). The shorter operand is then extended on the right with spaces (in IR at run time, from a list of space bytes as long as the shortfall, so variable-length reference modification pads too). Two numeric operands compare by value.

A class condition `IS NUMERIC` reads characters for a nonnumeric operand (every character 0-9). For a zoned or packed decimal item it reads the stored bytes: every digit a digit, and the sign position a C, D or F sign (or a separate `+`/`-`) when the picture is signed, an F when it is not; so `12AB` in a `PIC 9(4)` and a C sign in an unsigned packed item are not numeric. Binary and floating items are always numeric. The tests are IR: a byte and nibble comparison per stored byte, unrolled from the item's length, and a character scan for character data.

A SPECIAL-NAMES `CLASS name IS literal [THRU literal] ...` clause names a set of native (EBCDIC) characters: a nonnumeric literal's characters, a numeric literal's ordinal position (194 is `A`), and for THRU every native character between the two, written in either order. The bridge emits the clauses as `special_names.classes` and the condition `item IS [NOT] name` as `{"class_name": ..., "operand": ...}`; it lowers to an IR scan of the value, true when every character of the value is in the set (`__string_find` of each character in the set's characters, stopping at the first that is not).

A doubled delimiter inside a nonnumeric literal stands for one delimiter character (`"A""B"` is `A"B`), in a VALUE and in the procedure division. The bridge writes every literal as written, delimiters included (VALUE, level-88 values with `numeric` or `figurative` beside them, ALPHABET and CLASS literals, CURRENCY SIGN), and one decoder (`cobol_asg/nonnumeric_literal.py`) turns a nonnumeric literal into its characters: the ASG reader calls it once per VALUE, level-88 value, ALPHABET literal and currency sign, and `to_dict` writes the literal back delimited, so a cached ASG reads back to the same characters. Under SPECIAL-NAMES DECIMAL-POINT IS COMMA the bridge emits `"decimal_point_is_comma": true` and every literal as written. The ASG reader (`cobol_asg/decimal_point.py`) gives each numeric literal a period for its point (`1234,56` becomes `1234.56`): a VALUE the bridge marks `value_is_numeric`, a level-88 value it marks `numeric`, and each procedure-division operand or literal node the bridge marks `numeric` (the grammar's numericLiteral, which the lexer takes as one NUMERICLITERAL token); the pictures are parsed with the period and comma exchanged, and an edited image swaps them back (`PIC 9.999.999,99` holding 1234567.89 is `1.234.567,89`).

An ALL literal (`ALL "AB"`) is its literal repeated to the size of the associated item and truncated on the right: the receiver of a MOVE, the item a VALUE initialises, the parent of a level-88 VALUE, and the other operand of a relation (once, when that operand has no size of its own). The bridge carries the ALL as data (`"all"` on a MOVE source and a level-88 value, `value_is_all` on an item, `{"kind":"figurative","value":"ALL","literal":...}` in a relation); ALL with a figurative constant is that figurative constant.

## Known Gaps

- **Exponentiation (`**`) is not parsed or lowered** (red-dragon-wxur). Fixed-point arithmetic itself is exact: values, IBM `ARITH(COMPAT)` intermediate scales and every conversion live behind the `cobol_numeric` boundary (ADR-148, ADR-149), and only COMP-1/COMP-2 fields and floating intrinsics use IEEE floats.
- **LINAGE is lowered only for a program's own, non-EXTERNAL files**: a contained program writing a GLOBAL LINAGE file, or an EXTERNAL LINAGE file shared across programs, does not reach the owner's LINAGE-COUNTER; WRITE ADVANCING mnemonic-name on a LINAGE file is refused at lowering; a statement that modifies LINAGE-COUNTER is not diagnosed (red-dragon-sl30.102).
- **SEARCH ALL is lowered as a whole-table linear scan**, not a binary search (red-dragon-c32s); for a correctly ordered table the result is the same.
- **An independent segment is not reset on entry**: section priority numbers are not serialized, so an ALTERed GO TO in a segment of priority 50-99 keeps its altered target when control re-enters the segment from another one (red-dragon-sl30.74).
- **Index items hold occurrence numbers, not byte displacements**, for `INDEXED BY` names and USAGE INDEX items alike (red-dragon-zm9w); no conforming program can observe the difference.
- **Most intrinsic `FUNCTION`s fall back to their first argument** instead of being implemented (red-dragon-clpn, deprioritized — `MOD` and `DATE-OF-INTEGER` are implemented, the only ones observed in real corpora so far).

## Differences from Tree-Sitter Frontends

| Aspect | Tree-sitter frontends | COBOL frontend |
|---|---|---|
| Parser | tree-sitter (in-process) | ProLeap (Java subprocess) |
| Base class | `BaseFrontend` | `Frontend` (direct) |
| AST format | tree-sitter Node | JSON (CobolASG dataclasses) |
| Memory model | Variables (`STORE_VAR`/`LOAD_VAR`) | Byte-addressed regions (`ALLOC_REGION`/`WRITE_REGION`/`LOAD_REGION`) |
| Encoding | None (values stored directly) | PIC-driven (zoned decimal, COMP-3, alphanumeric) |
| Call semantics | `CALL_FUNCTION`/`RETURN` | `SET_CONTINUATION`/`RESUME_CONTINUATION` |

## Audit

The COBOL-specific audit script (`scripts/audit_cobol_frontend.py`) checks all three pipeline layers:

1. **Pass 1 — Bridge**: Which of ProLeap's 51 statement types does the Java bridge serialize?
2. **Pass 2 — Dispatch**: Which bridge types have Python dataclass dispatch entries?
3. **Pass 3 — Runtime**: Does the frontend lower without unhandled statement warnings?

Output is a per-type coverage matrix showing HANDLED / DISPATCH_MISSING / NOT_LOWERED / BRIDGE_UNKNOWN for each of the 51 types.

## Test Coverage

### Unit tests

Tests are in `tests/unit/test_cobol_*.py` and `tests/unit/cobol/`:

- **Statement hierarchy**: dispatch + round-trip for all 29 handled types
- **Frontend lowering**: per-statement IR verification (opcode presence, WRITE_REGION counts, loop structure)
- **I/O provider**: NullIOProvider/StubIOProvider unit tests, executor integration tests (concrete/symbolic dispatch)
- **PIC parsing**: `pic_parser.py` coverage
- **Data layout**: offset/length computation
- **Expression parser**: COMPUTE expression trees
- **PERFORM variants**: TIMES, UNTIL (TEST BEFORE/AFTER), VARYING
- **End-to-end fixtures**: Full COBOL programs through the pipeline

### Integration tests

Full-pipeline tests in `tests/integration/test_cobol_programs.py` exercise real `.cbl` source → ProLeap bridge → ASG → IR → CFG → VM, verifying decoded memory values. Tests skip when the bridge JAR is absent.

#### Coverage matrix

| Statement type | Integration test | Verified behaviour |
|---|---|---|
| VALUE clauses (PIC 9) | `TestInitialValues` | Zoned decimal initial values decoded correctly |
| ADD, SUBTRACT | `TestAddSubtract` | Multi-operand arithmetic |
| MULTIPLY, DIVIDE | `TestMultiplyDivide` | GIVING clause writes result to third field |
| COMPUTE | `TestComputeExpression` | Infix expression with operator precedence |
| MOVE (numeric) | `TestMoveLiteral` | Literal → numeric field |
| MOVE (alphanumeric) | `TestStringMove` | EBCDIC character encoding of PIC X fields |
| IF / ELSE | `TestIfElseBranch` | Conditional branching with comparison |
| EVALUATE / WHEN | `TestEvaluateWhen` | Multi-branch switch on subject value |
| PERFORM TIMES | `TestPerformTimes` | Counted loop with paragraph call |
| PERFORM UNTIL | `TestPerformUntil` | Condition-tested loop |
| PERFORM VARYING | `TestPerformVarying` | FROM/BY/UNTIL loop accumulating a sum |
| Nested PERFORM | `TestNestedPerform` | Paragraph calling another paragraph |
| GO TO | `TestGotoSkipsParagraph`, `TestGotoExitsPerform` | Jump-over and escape-from-PERFORM semantics |
| ALTER | `test_cobol_alter.py` | ALTER redirects a lone GO TO (with or without an operand), is re-altered, and is reset by CANCEL |
| INITIALIZE | `TestInitialize` (3 tests) | Numeric → zero, alphanumeric → spaces, multi-field |
| SET | `TestSetStatement` (4 tests) | SET TO, SET UP BY, SET DOWN BY, combined |
| SEARCH / WHEN | `TestSearchStatement` (2 tests) | WHEN match found, AT END when no match |
| INSPECT TALLYING | `TestInspectTallying` | FOR ALL character count |
| INSPECT REPLACING | `TestInspectReplacing` | ALL character substitution |
| CALL | `TestCallStatement` | Symbolic call doesn't crash surrounding code |
| STRING | `TestStringStatement` | DELIMITED BY SIZE concatenation into PIC X target |
| UNSTRING | `TestUnstringStatement` | DELIMITED BY SPACES splitting into multiple targets |
| Combined program | `TestCombinedProgram` | Arithmetic + IF + PERFORM TIMES + GO TO |
| MOVE CORRESPONDING | `TestMoveCorresponding` | Group-to-group field matching by name |
| ADD/SUBTRACT CORRESPONDING | `TestAddCorresponding` (2 tests, `test_cobol_e2e_features.py`) | Group arithmetic on matching leaf names; non-matching fields untouched |
| EVALUATE ALSO | `TestEvaluateAlso` (4 tests, `test_cobol_e2e_features.py`) | Multi-subject `ALSO` switch ANDs each subject=condition pair; `ANY` skips a dimension |
| Multi-dimensional subscripts | `TestTwoDimensionalSubscript` (3 tests, `test_cobol_subscript_occurrence.py`) | `TABLE(i, j)` offset = base + Σ (idxₖ-1)·strideₖ across nested OCCURS |
| Figurative constants | `TestFigurativeConstants` | SPACES, ZEROS, HIGH-VALUES, LOW-VALUES, QUOTES |
| Reference modification (MOVE) | `TestMoveRefMod` | Source and target `WS-FIELD(start:length)` slice semantics |
| Reference modification (DISPLAY) | `TestDisplayRefMod` | `DISPLAY WS-FIELD(start:length)` operand slicing |
| Reference modification (STRING/UNSTRING) | `TestStringRefMod`, `TestUnstringRefMod` | Sending-item and source slicing |
| Reference modification (INSPECT) | `TestInspectRefMod` | Subject slicing on TALLYING and REPLACING |
| Reference modification (arithmetic) | `TestArithmeticRefMod` | Source ref_mod in ADD, SUBTRACT, MULTIPLY, DIVIDE |
| Reference modification (COMPUTE) | `TestComputeRefMod` | `WS-FIELD(start:length)` in arithmetic expressions |
| ON SIZE ERROR | `TestOnSizeError` | Overflow detection in ADD/SUBTRACT/MULTIPLY/DIVIDE + div-by-zero |
| COMPUTE ON SIZE ERROR | `TestComputeOnSizeError` | Overflow detection in COMPUTE expressions |
| 88-level conditions | `TestLevel88Condition` | Condition name resolution via BRANCH_IF |
| REDEFINES | `TestRedefines` | Field overlay and type reuse |

#### Not covered (with rationale)

| Statement type | Reason not integration-tested |
|---|---|
| DISPLAY | Console output only — no memory side-effect to verify |
| STOP RUN | Implicitly exercised by every test (terminates execution) |
| CONTINUE | No-op — trivial, no observable effect |
| EXIT | Plain EXIT is a no-op; EXIT PARAGRAPH / EXIT SECTION are covered by `TestExitParagraphAndSection` |
| ENTRY | Alternate entry point — requires multi-program CALL support |
| ACCEPT | Reads from stdin/system — requires I/O provider injection into `run()` |
| OPEN, CLOSE, READ, WRITE, REWRITE, START, DELETE | File I/O — requires I/O provider injection into `run()` |
