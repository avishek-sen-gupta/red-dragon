# COBOL Frontend

> `interpreter/cobol/cobol_frontend.py` · Extends `Frontend` directly · ~1590 lines

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
  │  interpreter/cobol/cobol_parser.py    — subprocess invocation
  │  interpreter/cobol/asg_types.py       — CobolASG, CobolSection, CobolParagraph
  │  interpreter/cobol/cobol_statements.py — typed statement hierarchy (frozen dataclasses)
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
3. **Frontend lowering** — `cobol_frontend.py` lowers each statement type to IR via `isinstance` dispatch in `_lower_statement()`

## Module Map

| File | Purpose |
|------|---------|
| `cobol_frontend.py` | Main frontend: DATA DIVISION allocation, PROCEDURE DIVISION lowering |
| `cobol_statements.py` | Typed statement hierarchy — 25 frozen dataclasses + union type |
| `features.py` | `CobolFeature` enum — 112 semantic features; used with `@covers(CobolFeature.X)` test decorators |
| `io_provider.py` | Injectable I/O provider: `CobolIOProvider` ABC, `NullIOProvider`, `StubIOProvider` |
| `cobol_expression.py` | `ExprNode` union type (`LiteralNode | FieldRefNode | RefModNode | BinOpNode`) + `expr_from_dict()` deserializer; legacy `parse_expression` tokenizer retained for standalone tests |
| `cobol_parser.py` | Subprocess bridge to ProLeap JAR |
| `asg_types.py` | `CobolASG`, `CobolSection`, `CobolParagraph`, `CobolField` |
| `cobol_types.py` | `CobolDataCategory` enum, `CobolTypeDescriptor` |
| `pic_parser.py` | PIC clause parser (e.g., `9(5)V99` → type descriptor) |
| `data_layout.py` | `DataLayout`, `FieldLayout`, `build_data_layout()` |
| `ir_encoders.py` | IR instruction builders for encode/decode (zoned, COMP-3, alphanumeric, string ops) |
| `byte_builtins.py` | 19 low-level builtins for byte/nibble/list/string manipulation |
| `ebcdic_table.py` | EBCDIC ↔ ASCII translation table |
| `data_filters.py` | `align_decimal()`, `left_adjust()` for PIC formatting |
| `zoned_decimal.py` | Zoned decimal encoding/decoding reference |
| `comp3.py` | COMP-3 (packed decimal) encoding/decoding reference |
| `alphanumeric.py` | Alphanumeric/EBCDIC encoding reference |

## Data Division Lowering

The DATA DIVISION is lowered to byte-addressed memory regions:

1. `build_data_layout()` parses all WORKING-STORAGE fields, computing offsets and byte lengths from PIC clauses
2. `ALLOC_REGION` allocates a contiguous byte array sized to `layout.total_bytes`
3. Each field with a VALUE clause is encoded per its PIC type and written via `WRITE_REGION`

### PIC-Driven Encoding

| PIC Category | Encoding | Bytes | Example |
|---|---|---|---|
| `9(n)` (DISPLAY) | Zoned decimal — one byte per digit, sign in last byte zone | n | `PIC 9(5)` → 5 bytes |
| `S9(n) COMP-3` | Packed decimal — two digits per byte, sign nibble in last byte | ⌈(n+1)/2⌉ | `PIC S9(5) COMP-3` → 3 bytes |
| `X(n)` | Alphanumeric — one byte per character (ASCII or EBCDIC) | n | `PIC X(10)` → 10 bytes |

Encoding/decoding is performed via composable IR instruction builders in `ir_encoders.py`. Each builder returns a `list[InstructionBase]` using parameter registers (`%p_data`, `%p_digits`, etc.) that are inlined at the lowering site via `_inline_ir()`.

## Statement Coverage

29 of 51 ProLeap statement types are handled (24 fully deterministic + 5 I/O stub via injectable provider):

### Arithmetic (6 types)

| Statement | IR Pattern |
|---|---|
| `MOVE X TO Y` | Decode X → encode as Y's type → `WRITE_REGION` |
| `ADD X TO Y` | Decode both → `BINOP +` → encode → write |
| `SUBTRACT X FROM Y` | Decode both → `BINOP -` → encode → write |
| `MULTIPLY X BY Y` | Decode both → `BINOP *` → encode → write |
| `DIVIDE X INTO Y` | Decode both → `BINOP /` → encode → write |
| `COMPUTE Y = expr` | Recursive expression lowering → encode → write |

### Control Flow (5 types)

| Statement | IR Pattern |
|---|---|
| `IF / ELSE` | `_lower_condition()` → `BRANCH_IF` → true/false blocks |
| `EVALUATE / WHEN` | Chain of `BRANCH_IF` per WHEN, `WHEN OTHER` as fallthrough |
| `PERFORM` | Simple: `SET_CONTINUATION` + `BRANCH` to paragraph. TIMES/UNTIL/VARYING: loop with counter/condition. THRU: range of paragraphs. Section-level: all paragraphs in section. |
| `GO TO` | `BRANCH` to paragraph label |
| `STOP RUN` | `RETURN` |

### No-ops (2 types)

| Statement | IR Pattern |
|---|---|
| `CONTINUE` | No IR emitted |
| `EXIT` | No IR emitted |

### Data Manipulation (2 types)

| Statement | IR Pattern |
|---|---|
| `INITIALIZE` | Reset fields to type-appropriate defaults (SPACES for alphanumeric, ZEROS for numeric) |
| `SET` | TO: encode value → write. UP/DOWN BY: decode → `BINOP +/-` → encode → write. |

### String Operations (3 types)

| Statement | IR Pattern |
|---|---|
| `STRING ... INTO` | Decode sources → concatenate (with optional delimiter truncation) → encode → write to target |
| `UNSTRING ... INTO` | Decode source → `__string_split` → extract parts → encode → write to targets |
| `INSPECT` | TALLYING: `__string_count` → write count. REPLACING: `__string_replace` → write back. |

### Table Operations (1 type)

| Statement | IR Pattern |
|---|---|
| `SEARCH` | Loop with bound check, WHEN condition chain (`BRANCH_IF` per clause), VARYING index increment, AT END fallthrough |

### Inter-program (4 types)

| Statement | IR Pattern |
|---|---|
| `CALL 'prog' USING params` | Decode USING params → `CALL_FUNCTION` with program name (symbolic, unresolved). GIVING writes result back. |
| `ALTER para-1 TO PROCEED TO para-2` | `STORE_VAR __alter_source = target_label` (captures data flow of dynamic retargeting) |
| `ENTRY 'name'` | `LABEL entry_name` (alternate subprogram entry point) |
| `CANCEL prog` | No-op for static analysis (program state invalidation has no data-flow effect) |

### I/O (8 types — HANDLED_STUB)

| Statement | IR Pattern |
|---|---|
| `ACCEPT var` | `CALL_FUNCTION __cobol_accept(device)` → encode result → `WRITE_REGION` to target field |
| `OPEN mode file` | `CALL_FUNCTION __cobol_open_file(filename, mode)` per file |
| `CLOSE file` | `CALL_FUNCTION __cobol_close_file(filename)` per file |
| `READ file INTO var` | `CALL_FUNCTION __cobol_read_record(filename)` → encode → `WRITE_REGION` to INTO target |
| `WRITE rec FROM var` | Decode FROM field → `CALL_FUNCTION __cobol_write_record(filename, data)` |
| `REWRITE rec FROM var` | Decode FROM field → `CALL_FUNCTION __cobol_rewrite_record(filename, data)` |
| `START file KEY key` | `CALL_FUNCTION __cobol_start_file(filename, key)` |
| `DELETE file` | `CALL_FUNCTION __cobol_delete_record(filename)` |

I/O statements dispatch to an injectable `CobolIOProvider` (ABC in `io_provider.py`). `NullIOProvider` returns `UNCOMPUTABLE` (symbolic fallthrough). `StubIOProvider` returns queued test data for concrete execution without real files or console. Provider is injected via `VMConfig(io_provider=stub)`.

### Remaining 19 types

Not yet implemented in the bridge. Includes communication (SEND, RECEIVE), embedded SQL (EXEC SQL), and less common statements (GENERATE, SORT, etc.).

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

## String Operation Builtins

String operations use 7 low-level builtins registered in `byte_builtins.py`:

| Builtin | Signature | Purpose |
|---|---|---|
| `__string_find` | `(source, needle) → int` | Find first occurrence (-1 if not found) |
| `__string_split` | `(source, delimiter) → list[str]` | Split by delimiter |
| `__string_count` | `(source, pattern, mode) → int` | Count occurrences (mode: all/leading/characters) |
| `__string_replace` | `(source, from, to, mode) → str` | Replace occurrences (mode: all/leading/first) |
| `__string_concat` | `(parts) → str` | Concatenate list of strings |
| `__string_slice__` | `(source, start, length) → str` | Extract substring (0-based start, exclusive end); used for reference modification reads |
| `__string_splice__` | `(source, start, length, replacement) → str` | Replace substring (0-based start); used for reference modification writes |

These are composed into IR instruction sequences via builders in `ir_encoders.py` (`build_string_split_ir`, `build_inspect_tally_ir`, `build_inspect_replace_ir`). The composed IR is inlined at each lowering site, keeping all operations visible to data-flow analysis.

## SEARCH Lowering

SEARCH implements a linear table search with the following IR structure:

```
STORE_VAR counter = 0
LABEL search_loop:
  LOAD_VAR counter
  BINOP >= counter, 256        (safety bound)
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
  ; No match — increment varying index + counter, loop
  BRANCH → search_incr
LABEL search_incr:
  decode varying → BINOP + 1 → encode → write
  counter += 1
  BRANCH → search_loop
LABEL at_end:
  lower_statement(at_end children)
LABEL search_end:
```

## Condition Lowering

Conditions are serialized by the Java bridge as recursive JSON trees (not raw source text). Each node carries a `"kind"` discriminant:

- `{"kind": "relation", "left": ..., "right": ..., "op": "EQ"|"GT"|"LT"|...}` — relational comparison
- `{"kind": "and"|"or", "left": ..., "right": ...}` — compound condition
- `{"kind": "not", "expr": ...}` — negation
- `{"kind": "condition_name", "name": "COND-88-NAME"}` — 88-level condition name test

`_lower_condition()` deserializes this tree and recursively emits IR: leaf relation nodes produce a `BINOP` comparison; compound nodes chain via `BRANCH_IF` with short-circuit blocks.

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

Tests are in `tests/unit/test_cobol_*.py`:

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
| EXIT | No-op — trivial, no observable effect |
| ALTER | Modifies GO TO targets dynamically — **testable**, not yet written |
| ENTRY | Alternate entry point — requires multi-program CALL support |
| CANCEL | Cancels called subprogram — requires multi-program CALL support |
| ACCEPT | Reads from stdin/system — requires I/O provider injection into `run()` |
| OPEN, CLOSE, READ, WRITE, REWRITE, START, DELETE | File I/O — requires I/O provider injection into `run()` |
