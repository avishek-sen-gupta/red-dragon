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
| `features.py` | `CobolFeature` enum — 139 semantic features; used with `@covers(CobolFeature.X)` test decorators |
| `io_provider.py` | Injectable I/O provider: `CobolIOProvider` ABC, `NullIOProvider`, `StubIOProvider` |
| `cobol_asg/cobol_expression.py` | `ExprNode` union type (`LiteralNode | FieldRefNode | RefModNode | BinOpNode`) + `expr_from_dict()` deserializer; legacy `parse_expression` tokenizer retained for standalone tests |
| `cobol_asg/cobol_parser.py` | Subprocess bridge to ProLeap JAR |
| `cobol_asg/asg_types.py` | `CobolASG`, `CobolSection`, `CobolParagraph`, `CobolField` |
| `cobol_asg/cobol_types.py` | `CobolDataCategory` enum, `CobolTypeDescriptor` |
| `cobol_asg/pic_parser.py` | PIC clause parser (e.g., `9(5)V99` → type descriptor) |
| `data_layout.py` | `DataLayout`, `FieldLayout`, `build_data_layout()` |
| `file_definitions_data.py` | `FILE_DEFINITIONS`, `file_definitions_data()` — the program's SELECTs and FD formats as a `Data` directive |
| `layout_data.py` | `DATA_LAYOUT`, `layout_data()`, and the reader `field_positions()` → `FieldPosition` per WORKING-STORAGE field |
| `ir_encoders.py` | IR instruction builders for encode/decode (zoned, COMP-3, alphanumeric, string ops) |
| `byte_builtins.py` | 19 low-level builtins for byte/nibble/list/string manipulation |
| `ebcdic_table.py` | EBCDIC (CP037) ↔ Latin-1 translation tables, built from Python's `cp037` codec: a bijection, so every byte survives a decode and re-encode |
| `data_filters.py` | `align_decimal()`, `left_adjust()` for PIC formatting |
| `zoned_decimal.py` | Zoned decimal encoding/decoding reference |
| `comp3.py` | COMP-3 (packed decimal) encoding/decoding reference |
| `alphanumeric.py` | Alphanumeric/EBCDIC encoding reference |

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

### Data-name qualification

A reference `N OF Q1 OF Q2 ...` (or `IN`) is resolved by `DataLayout.qualified_matches`: every elementary or group item named N whose enclosing groups, read outward, contain Q1, Q2, ... in that order (intermediate levels may be skipped). One survivor is the item; more than one raises `CobolAmbiguousReferenceError`; none falls through to the next DATA DIVISION section. A subscripted reference strides by, and is bounded by, the OCCURS tables enclosing that one match (`DataItemMatch.tables`), never another item of the same name.

`LENGTH OF X OF G` (in MOVE, arithmetic expressions and reference-modification bounds) measures the item its qualifiers select: the bridge's `length_of` node carries the qualifiers (`LengthOfNode`, `RefModLengthOf`, `RefModOperand.length_of`).

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
| `9(n)` (DISPLAY) | Zoned decimal — one byte per digit, sign in last byte zone; a SIGN clause moves it to the first byte or into a separate `+`/`-` byte. A signed item takes its own SIGN clause, else the nearest enclosing group's (resolved by the bridge) | n, +1 if SIGN SEPARATE | `PIC 9(5)` → 5 bytes |
| `S9(n) COMP-3` | Packed decimal — two digits per byte, sign nibble in last byte | ⌈(n+1)/2⌉ | `PIC S9(5) COMP-3` → 3 bytes |
| `X(n)` | Alphanumeric — one byte per character (ASCII or EBCDIC) | n | `PIC X(10)` → 10 bytes |
| `9(n) COMP` / `BINARY` | Big-endian two's-complement integer of the unscaled value (implied decimals and PIC P applied, truncated toward zero), cut to the PICTURE's digits as for any numeric receiver (IBM TRUNC(STD): 1023 into `PIC S999 COMP` stores 23); an unsigned item stores the magnitude, so a negative value is stored without its sign | 2 / 4 / 8 by n | `PIC 9(5) COMP` → 4 bytes |
| Numeric-edited | The edited characters, one byte per character position (`__cobol_apply_edit_picture`). Trailing P divides the value before editing, and the item reads back as its characters, unscaled | one per character position | `PIC ZZZPP` holding 1200 → `" 12"` |

Encoding/decoding is performed via composable IR instruction builders in `ir_encoders.py`. Each builder returns a `list[InstructionBase]` using parameter registers (`%p_data`, `%p_digits`, etc.) that are inlined at the lowering site via `_inline_ir()`.

## Statement Coverage

29 of 51 ProLeap statement types are handled (24 fully deterministic + 5 I/O stub via injectable provider):

### Arithmetic (6 types)

| Statement | IR Pattern |
|---|---|
| `MOVE X TO Y` | Decode X → encode as Y's type → `WRITE_REGION`. A group sender is an alphanumeric move with no conversion: its characters fill a numeric or edited receiver as one alphanumeric item, left to right, space-padded or truncated, with no editing (`MOVE` of a group holding `123ABC` to `PIC 99` stores `12`). HIGH-VALUE and LOW-VALUE fill any receiver with their raw byte, except an alphanumeric-edited one, which takes them as a literal of its size, edited in (`PIC XX0XX` gets `FF FF F0 FF FF`). |
| `ADD X W TO Y Z` | Sum the sending operands once (X + W), then for each receiver in turn: decode it → add the sum → encode → write. The bridge emits the sending operands as `operands` and the receivers, each with its own `rounded`, as `targets`. |
| `SUBTRACT X W FROM Y Z` | As ADD: each receiver loses the sum X + W. |
| `MULTIPLY X BY Y Z` | Each receiver in turn becomes receiver × X. |
| `DIVIDE X INTO Y Z` | Each receiver in turn becomes receiver ÷ X. |
| `... GIVING G H` | The result is computed once as `operands[0] <op> (sum of the remaining operands)` — ADD sums every operand, `SUBTRACT X W FROM Y GIVING G` is Y − (X + W) — and written to every GIVING receiver, each with its own ROUNDED. |
| Size error condition | A result is a size error when it reaches 10^(the receiver's integer digit positions) — e.g. 100 for `PIC 99V9`, 1 for `PIC V999`, 10000 for `PIC $9999.00` (a numeric-edited receiver counts 9, Z, * and floating symbols but the first, never insertion characters). Digits past the receiver's decimal places are truncated and never cause one: 99.95 into `PIC 99V9` stores 99.9. The magnitude decides, not the sign (emitted as IR: result ≥ capacity or result ≤ −capacity): −4.57 into an unsigned `PIC V999` is a size error, while −3 into an unsigned `PIC 9` stores 3. A ROUNDED receiver is rounded first and the rounded value is tested and stored: −99.4 ROUNDED into `PIC S99` stores −99, −99.5 ROUNDED is a size error. PIC P scaling moves both positions: `PIC S99P` holds up to ±990 and ROUNDED rounds it to tens (0 − 99 ROUNDED stores −100); `PIC PP9` holds up to .009. |
| `ON SIZE ERROR` with several receivers | Per receiver: one whose result does not fit is left unchanged while the others are written; ON SIZE ERROR runs once afterwards if any receiver failed, NOT ON SIZE ERROR otherwise. DIVIDE by zero is a size error for every receiver. |
| `DIVIDE ... GIVING ... REMAINDER r` | `remainder = dividend - quotient * divisor`, where `quotient` is the GIVING quotient truncated to that receiver's decimal places (before any ROUNDED), computed exactly from the same operands; it is written back alongside the quotient, so not when the quotient has a size error. `DIVIDE X INTO Y GIVING Z` computes `Z = Y / X` (dividend/divisor); `DIVIDE X BY Y GIVING Z` computes `Z = X / Y` — the bridge normalizes both forms to a `[dividend, divisor]` operand order before lowering. |
| `MOVE CORRESPONDING A TO B ...` | Each corresponding pair is a separate MOVE of A's item to B's. Items correspond when their names and every qualifier below A and B agree, at any depth, and at least one of the two is elementary (an elementary item paired with a group is an alphanumeric group move). A subordinate item with OCCURS or REDEFINES, everything under it, FILLER and RENAMES items never pair. Subscripts on A and B select the occurrence each pair is read from and written to. Each group is found in whichever section declares it (WORKING-STORAGE, LOCAL-STORAGE, LINKAGE, FILE); a LINKAGE group reads and writes its caller's argument. |
| `ADD/SUBTRACT CORRESPONDING A TO/FROM B [ROUNDED] [[NOT] ON SIZE ERROR]` | Each pair of corresponding items that are both elementary numeric (same pairing rules as MOVE CORRESPONDING) is a separate ADD/SUBTRACT of A's item to/from B's, with the statement's ROUNDED and the same exact arithmetic and per-receiver size error test as the other arithmetic verbs: a pair whose result does not fit leaves its B.field unchanged, the others are written, and ON SIZE ERROR (or NOT ON SIZE ERROR) runs once after every pair. Non-matching fields untouched. |
| `COMPUTE Y Z = expr` | Recursive expression lowering, then stored in every receiver as for GIVING: each with its own ROUNDED and its own size error test. |

### Control Flow (7 types)

| Statement | IR Pattern |
|---|---|
| `IF / ELSE` | `_lower_condition()` → `BRANCH_IF` → true/false blocks |
| `EVALUATE / WHEN` | Chain of `BRANCH_IF` per WHEN, `WHEN OTHER` as fallthrough. The bridge sends typed selection subjects (an expression, a condition, or `TRUE`/`FALSE`) and, per WHEN, one selection object per subject (`ANY`, `TRUE`/`FALSE`, a condition, `[NOT] value`, `[NOT] low THRU high`), every operand a structured expression. An expression subject is compared with a value or range through the relation-condition lowering, the `NOT` negating it; under a condition or truth-value subject the WHEN is selected when both have the same truth value, an identifier object there being a condition-name. The pairs are ANDed via `BINOP &&`; `ANY` skips its position. Stacked WHENs (`WHEN c1 WHEN c2 <body>`) are one `WhenStatement` with one body: the first WHEN's objects on the WHEN itself, the rest in `alternatives`, ORed via `BINOP or`. |
| `PERFORM` | Simple: `SET_CONTINUATION` + `BRANCH` to paragraph. TIMES/UNTIL/VARYING: loop with counter/condition. The TIMES count and each VARYING/AFTER identifier, FROM and BY operand is a structured expression node, so an identifier contributes its value and a subscripted one addresses its occurrence. VARYING/AFTER sets every identifier to its FROM value, outermost first; stepping a level resets every level inside it to FROM; TEST BEFORE tests the UNTILs outermost first before the body, TEST AFTER tests them innermost first after the body and before any step. THRU: range of procedures; control returns at the end of the THRU procedure, which for a section is the end of its last paragraph. Section-level: all paragraphs in section. |
| `GO TO` | `BRANCH` to paragraph label |
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
| `SET mnemonic TO ON\|OFF` | An implementor switch's mnemonic-name: `CALL_FUNCTION __cobol_set_switch(environment-name, status)`. A switch-status condition-name (`ON STATUS IS c`) lowers to `__cobol_switch_status(environment-name)` compared with its status. The switch settings are a run input held by the I/O provider (`RealFileIOProvider(switches=...)`); a switch not supplied is OFF. |
| `SET p TO ADDRESS OF x \| NULL \| q` | A POINTER target: the address — x's region register `BINOP +` its offset, 0 for NULL, or q's contents — written as the addressing mode's binary (`INT_TO_BINARY_BYTES`, signed, 4 bytes under LP(32), 8 under LP(64)). |
| `SET ADDRESS OF lk TO …` | A LINKAGE 01 or 77 item only: its region register becomes the address and its shift moves its static start there (`STORE_VAR` into its binding variables, then `LOAD_VAR` into its binding registers, so every later access follows). A subordinate item is rejected at lowering. |
| `SET p UP/DOWN BY n` | A POINTER target: decode → `BINOP +/-` n bytes → write the address back. |
| `ADDRESS OF x` in a condition | x's region register `BINOP +` its offset; NULL is 0, so `ADDRESS OF lk = NULL` tests for an OMITTED or unsupplied parameter. |
| `USAGE POINTER` | A signed binary of the addressing mode's width; the `LP` option given to `compile_cobol` sets it, and reaches the bridge's offsets as `-pointer-size`. |
| `USAGE INDEX` | An unsigned fullword binary holding an occurrence number, like an `INDEXED BY` index; `SET` moves one into and out of it. A USAGE written on a group applies to every elementary item in it (the bridge resolves the nearest enclosing USAGE). |

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
| `CALL 'prog' USING params` | One address per argument, by position. The caller builds an argument array (`NEW_ARRAY`, a `count` field, one `NEW_OBJECT` per argument holding `region`, `offset` and `omitted`) and dispatches via `CALL_WITH_MEMORY __entry_<NAME>`, binding the array to the callee entry function's `__call_arguments` parameter. BY REFERENCE passes the argument's own region and offset, so the callee's writes land in the caller as they happen and nothing is copied back — which is also why they survive a callee's STOP RUN. BY CONTENT, BY VALUE and a literal pass a fresh `RegionId.CALL_ARGUMENT` copy. A literal is copied in the representation IBM defines: under BY VALUE a fixed-point numeric literal or ZERO as a fullword binary and a floating-point literal as COMP-2; a figurative constant as one byte of its character (HIGH-VALUE and LOW-VALUE raw); anything else as its characters. OMITTED passes a marker. The callee binds each LINKAGE 01 to the argument at its PROCEDURE DIVISION USING position (`CobolASG.procedure_using`; declaration order when there is no USING) in plain IR: a region register and a shift, which every LINKAGE field access adds to its static offset. LINKAGE keeps its static end-to-end layout for strides and analysis extents. An absent or OMITTED parameter binds NULL — `ADDRESS OF` it is NULL, and touching it goes to the VM's null-access strategy (warn and read zeroes by default, or halt); a LINKAGE 01 USING does not name binds zero-filled storage of its own. `USING BY VALUE|CONTENT|REFERENCE ADDRESS OF x` hands over a fresh copy of x's address. A parameter declared wider than its argument reads on into the caller's following bytes. GIVING writes the result back. With ON EXCEPTION (or ON OVERFLOW), `__cobol_program_present` first tests whether the entry variable is bound to a function: if not, the ON EXCEPTION statements run and the CALL is not made; if so, the program is called and NOT ON EXCEPTION follows. Without ON EXCEPTION the call is made, and a program not in the run unit goes to the run's unresolved-call strategy (`permit_unresolved_call_targets`). |
| `ALTER para-1 TO PROCEED TO para-2` | `STORE_VAR __alter_source = target_label` (captures data flow of dynamic retargeting) |
| `ENTRY 'name'` | `LABEL entry_name` (alternate subprogram entry point) |
| `CANCEL prog` | No-op for static analysis (program state invalidation has no data-flow effect) |

### I/O (8 types — HANDLED_STUB)

| Statement | IR Pattern |
|---|---|
| `ACCEPT var` | `CALL_FUNCTION __cobol_accept(device, receiver byte length)` → store the characters unedited (`as_characters`) → `WRITE_REGION` to target field. `RealFileIOProvider(system_input=...)` fills the area from successive fixed-length system input records, truncating the last |
| `OPEN mode file` | `CALL_FUNCTION __cobol_open_file(filename, mode, program)` per file. The program's start-up code (module scope, once per run unit, before any OPEN) declares each SELECT to the provider with `__cobol_declare_file(frame, program)`: `frame` is a Const holding the `DataRecord` of a `FileFrame` (`file_frame.py`), which the provider reads back with `frame_of`. It carries what the driver frames records by: the file name, organization, the RECORD KEY's offset and length within the file's own record area (not within the FILE region), `variable` (true when the FD's records vary in length: RECORDING MODE V or S; else RECORD IS VARYING, RECORD CONTAINS m TO n with m ≠ n, or 01s of different lengths or with OCCURS DEPENDING ON), and `record_length`, the FD's largest record, the length of its record area |
| `CLOSE file [WITH LOCK]` | `CALL_FUNCTION __cobol_close_file(filename, program)` per file; WITH LOCK is IR state (the file's `locked` variable), not a separate call |
| `READ file [NEXT] INTO var` | `CALL_FUNCTION __cobol_read_record(filename, key, program)` → `__cobol_io_data(result, program)` → the record into the FD's record area and, when the READ succeeds, into the INTO item space-filled or truncated to its length (an alphanumeric move). `key` is, for a random READ (RANDOM access, or DYNAMIC without NEXT), an indexed file's key of reference as bytes (the KEY phrase's item, else the RECORD KEY) or a relative file's KEY phrase or RELATIVE KEY value, else `""` |
| `WRITE rec FROM var` | Decode FROM field → `CALL_FUNCTION __cobol_write_record(filename, data, key, program)`; `key` is a relative file's RELATIVE KEY under RANDOM or DYNAMIC access, else `""` |
| `REWRITE rec FROM var` | Decode FROM field → `CALL_FUNCTION __cobol_rewrite_record(filename, data, key, program)`, `key` as for WRITE |
| `START file KEY key` | `CALL_FUNCTION __cobol_start_file(filename, key, relop, program)` — `key` is the KEY item's bytes (indexed) or value (relative); without KEY, the RECORD KEY or RELATIVE KEY's, with `=`. An indexed KEY item shorter than the RECORD KEY is compared with the record key's leading bytes. The file is positioned at the first record satisfying the relation; when none does, the status is 23 |
| `DELETE file` | `CALL_FUNCTION __cobol_delete_record(filename, key, program)` — `key` is the RECORD KEY's bytes or the RELATIVE KEY's value in random or dynamic access, empty in sequential access |
| `SORT sd ON ASCENDING/DESCENDING KEY k ... USING f ... GIVING g ...` | `OPEN OUTPUT sd`; per USING file `OPEN INPUT f`, `__cobol_sort_using(sd, f, program)`, `CLOSE f`; then `__cobol_sort_file(sd, record_length, weights, offset, length, encoding, direction, ..., program)`; per GIVING file `OPEN INPUT sd`, `OPEN OUTPUT g`, `__cobol_sort_giving(sd, g, program)`, `CLOSE g`, `CLOSE sd` |
| `SORT ... INPUT PROCEDURE p [THRU p2] ... OUTPUT PROCEDURE q [THRU q2]` | As above, with a procedure PERFORM of `p` in place of the USING copies (after `OPEN OUTPUT sd`) and of `q` in place of the GIVING copies (between `OPEN INPUT sd` and `CLOSE sd`) |
| `MERGE sd ON ASCENDING/DESCENDING KEY k ... USING f1 f2 ... GIVING g ... \| OUTPUT PROCEDURE q` | Lowered as the SORT with those USING files: the stable sort of the files' records, read in USING order, is their merge, equal keys coming out in USING-file order |
| `RELEASE rec [FROM x]` | Lowered as `WRITE rec [FROM x]` on the sort file |
| `RETURN sd [INTO x] AT END ... NOT AT END ...` | Lowered as `READ sd [INTO x] AT END ... NOT AT END ...` on the sort file |

The sort file (SD) is a sequential work file at its ASSIGN path, opened and closed by the same lowering as any file. `__cobol_sort_file` puts its records in key order: keys major to minor as written, each by its own direction, numeric keys (zoned with any SIGN clause, packed, binary, COMP-1/COMP-2) by algebraic value, alphanumeric and edited keys byte by byte through `weights` (a 256-character string, character b the weight of native byte b) of the alphabet the COLLATING SEQUENCE phrase names, which the bridge writes into the statement as `collating_sequence`, else of the program collating sequence, with a stable sort so records with equal keys keep the order they were released in. Each key's offset is relative to the sort record.

Each file verb's status is `__cobol_io_status(result, program)`. A sequential READ or WRITE of a relative file MOVEs `__cobol_io_record_number(result, program)` to its RELATIVE KEY when the status is successful. Each verb's I-O status rules are IR around its primitive (`file_verb_ir.py`): the checks run in order, the first that holds sets the status and the primitive is not called. Per program and file, module-scope variables `__cobol_file_<PROGRAM>_<FILE>_mode`, `_locked`, `_position`, `_absent` and `_last_key` hold the open mode, whether it was closed WITH LOCK, the position indicator (no current record, current record, at end), whether it is an OPTIONAL file opened INPUT while absent, and the prime key of its last record read or written. The IR reports 41 OPEN of an open file, 42 CLOSE of a closed one, 43 REWRITE/DELETE in sequential access without a preceding successful READ (any statement in between, even a failed one, clears the current record), 46 a sequential READ after at end, 47/48/49 a verb the open mode does not permit, and 38 OPEN after CLOSE WITH LOCK. It also reports 14 for a READ of a relative file whose record number has more digits than the RELATIVE KEY (no record and no number; the RELATIVE KEY's digit count is a lowering-time constant), 44 for a WRITE or REWRITE of a variable-length record outside the FD's smallest and largest sizes (constants too), and 24 for a WRITE of a relative file at a record number below 1 (READ, REWRITE, DELETE and START at 0 find no record, 23, from the driver). The open primitive answers 35 for any OPEN other than OUTPUT of a file that does not exist. For an OPTIONAL file the IR turns that into 05: for INPUT the file's `_absent` variable is set, it is not created, and READ gives 10 (a keyed READ or START 23) and CLOSE 00 without calling the provider; for I-O and EXTEND the IR creates it by an OUTPUT open and a close, then opens it again. In sequential access to an indexed file the IR keeps the prime key of the last record read or written in the file's `_last_key` variable and reports 21 for a WRITE whose prime key is below it or a REWRITE whose prime key differs from it. The provider's primitives do I/O only and return the driver's outcome. AT END runs for any class 1 status (10 or 14). A USE declarative fires for any unsuccessful status the statement's own AT END (class 1) or INVALID KEY (class 2) phrase does not handle; one scoped by open mode is chosen by the mode an OPEN attempts, and for other verbs by the file's `mode` variable. `program` is the calling program's PROGRAM-ID, upper-cased, a constant the lowering emits as the last argument of every file call, and each `CobolIOProvider` method takes it as its last parameter; red-dragon's providers accept and ignore it (ADR-185).

I/O statements dispatch to an injectable `CobolIOProvider` (ABC in `io_provider.py`). `NullIOProvider` returns `UNCOMPUTABLE` (symbolic fallthrough). `StubIOProvider` returns queued test data for concrete execution without real files or console. Provider is injected via `VMConfig(io_provider=stub)`.

Every 01 under one FD starts at that FD's record area (an implicit redefinition), so a MOVE to one record is what a WRITE of another record of the same file sends. Each FD has its own area, as long as its largest record; the bridge places the areas one after another in the FILE region (red-dragon-sl30.31).

Each FD's `RECORDING MODE` and `RECORD` clause (`CONTAINS n`, `CONTAINS m TO n`, `IS VARYING [FROM m] [TO n] [DEPENDING ON x]`) reach `CobolASG.file_descriptions` as `FileDescription` values, for an I/O provider to derive the file's record format from. A `WRITE` or `REWRITE` hands the provider the record at its own length: the RECORD VARYING DEPENDING ON item's value in bytes of the record area, else the named record's length; after a successful `READ` the DEPENDING ON item is set to the length of the record read. `RealFileIOProvider` stores a variable sequential file as records behind 4-byte record descriptor words and a variable relative file as slots of 4 + maximum bytes led by one; a sequential `REWRITE` of another length, and a `WRITE` or `REWRITE` of a variable record shorter than the smallest or longer than the largest, give 44 (ADR-187). A DEPENDING ON value past the record area releases one byte more than the area, so the provider sees the record is too long.

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
- A bare identifier after a relation parses as a condition name; it carries the implied subject and operator under `"abbreviation"`, and lowering compares with it when the name is a data item rather than a level-88 (`{"not": bool, "condition_name": ...}`, names indexed over WORKING-STORAGE, LOCAL-STORAGE, LINKAGE and the FILE SECTION).
- A combined relation expands into one relation per operand under `"condition"`; a parenthesised condition is resolved the same way.

`_lower_condition()` deserializes this tree and recursively emits IR: leaf relation nodes produce a `BINOP` comparison; compound nodes chain via `BRANCH_IF` with short-circuit blocks.

A relation with a nonnumeric operand (a nonnumeric literal or figurative, a reference-modified slice, or an alphanumeric, edited or group item) compares characters. A numeric operand there becomes its digit characters without the sign: an integer literal as written, an unsigned zoned item its own bytes, any other numeric item the digits of its value (in IR: the value's digits encoded as unsigned zoned decimal and read back as characters, each P position a trailing zero). The shorter operand is then extended on the right with spaces (in IR at run time, from a list of space bytes as long as the shortfall, so variable-length reference modification pads too). Two numeric operands compare by value.

A class condition `IS NUMERIC` reads characters for a nonnumeric operand (every character 0-9). For a zoned or packed decimal item it reads the stored bytes: every digit a digit, and the sign position a C, D or F sign (or a separate `+`/`-`) when the picture is signed, an F when it is not; so `12AB` in a `PIC 9(4)` and a C sign in an unsigned packed item are not numeric. Binary and floating items are always numeric. The tests are IR: a byte and nibble comparison per stored byte, unrolled from the item's length, and a character scan for character data.

A SPECIAL-NAMES `CLASS name IS literal [THRU literal] ...` clause names a set of native (EBCDIC) characters: a nonnumeric literal's characters, a numeric literal's ordinal position (194 is `A`), and for THRU every native character between the two, written in either order. The bridge emits the clauses as `special_names.classes` and the condition `item IS [NOT] name` as `{"class_name": ..., "operand": ...}`; it lowers to an IR scan of the value, true when every character of the value is in the set (`__string_find` of each character in the set's characters, stopping at the first that is not).

A doubled delimiter inside a nonnumeric literal stands for one delimiter character (`"A""B"` is `A"B`), in a VALUE and in the procedure division. Under SPECIAL-NAMES DECIMAL-POINT IS COMMA the bridge emits `"decimal_point_is_comma": true` and every literal as written. The ASG reader (`cobol_asg/decimal_point.py`) gives each numeric literal a period for its point (`1234,56` becomes `1234.56`): a VALUE the bridge marks `value_is_numeric`, a level-88 value it marks `numeric`, and each procedure-division operand that is a comma-point numeric literal; the pictures are parsed with the period and comma exchanged, and an edited image swaps them back (`PIC 9.999.999,99` holding 1234567.89 is `1.234.567,89`).

An ALL literal (`ALL "AB"`) is its literal repeated to the size of the associated item and truncated on the right: the receiver of a MOVE, the item a VALUE initialises, the parent of a level-88 VALUE, and the other operand of a relation (once, when that operand has no size of its own). The bridge carries the ALL as data (`"all"` on a MOVE source and a level-88 value, `value_is_all` on an item, `{"kind":"figurative","value":"ALL","literal":...}` in a relation); ALL with a figurative constant is that figurative constant.

## Known Gaps

- **Exponentiation (`**`) is not parsed or lowered** (red-dragon-wxur). Fixed-point arithmetic itself is exact: values, IBM `ARITH(COMPAT)` intermediate scales and every conversion live behind the `cobol_numeric` boundary (ADR-148, ADR-149), and only COMP-1/COMP-2 fields and floating intrinsics use IEEE floats.
- **CANCEL is a no-op** — doesn't reset the cancelled subprogram's WORKING-STORAGE on next CALL (red-dragon-8dpn).
- **SEARCH ALL is lowered as a whole-table linear scan**, not a binary search (red-dragon-c32s); for a correctly ordered table the result is the same.
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
| ALTER | Modifies GO TO targets dynamically — **testable**, not yet written |
| ENTRY | Alternate entry point — requires multi-program CALL support |
| CANCEL | Cancels called subprogram — requires multi-program CALL support |
| ACCEPT | Reads from stdin/system — requires I/O provider injection into `run()` |
| OPEN, CLOSE, READ, WRITE, REWRITE, START, DELETE | File I/O — requires I/O provider injection into `run()` |
