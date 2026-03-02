# COBOL Frontend

> `interpreter/cobol/cobol_frontend.py` · Extends `Frontend` directly · ~1470 lines

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
RedDragon IR (list[IRInstruction])
```

The pipeline has three layers, each independently testable:

1. **Java bridge** — `StatementSerializer.java` dispatches on ProLeap's `StatementTypeEnum` and serializes each statement type to JSON with extracted operands
2. **Python dispatch** — `cobol_statements.py` provides frozen dataclasses per statement type with `from_dict()`/`to_dict()` round-trip and a `parse_statement()` dispatch function
3. **Frontend lowering** — `cobol_frontend.py` lowers each statement type to IR via `isinstance` dispatch in `_lower_statement()`

## Module Map

| File | Purpose |
|------|---------|
| `cobol_frontend.py` | Main frontend: DATA DIVISION allocation, PROCEDURE DIVISION lowering |
| `cobol_statements.py` | Typed statement hierarchy — 20 frozen dataclasses + union type |
| `cobol_expression.py` | Recursive-descent expression parser for COMPUTE |
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

Encoding/decoding is performed via composable IR instruction builders in `ir_encoders.py`. Each builder returns a `list[IRInstruction]` using parameter registers (`%p_data`, `%p_digits`, etc.) that are inlined at the lowering site via `_inline_ir()`.

## Statement Coverage

24 of 51 ProLeap statement types are fully handled (bridge → dispatch → lowering):

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

### Remaining 27 types

Not yet implemented in the bridge. Includes I/O (READ, WRITE, OPEN, CLOSE), communication (SEND, RECEIVE), embedded SQL (EXEC SQL), and less common statements (GENERATE, etc.).

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

String operations use 5 low-level builtins registered in `byte_builtins.py`:

| Builtin | Signature | Purpose |
|---|---|---|
| `__string_find` | `(source, needle) → int` | Find first occurrence (-1 if not found) |
| `__string_split` | `(source, delimiter) → list[str]` | Split by delimiter |
| `__string_count` | `(source, pattern, mode) → int` | Count occurrences (mode: all/leading/characters) |
| `__string_replace` | `(source, from, to, mode) → str` | Replace occurrences (mode: all/leading/first) |
| `__string_concat` | `(parts) → str` | Concatenate list of strings |

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

`_lower_condition()` parses simple condition strings of the form `"field OP value"` where OP is `>`, `<`, `>=`, `<=`, `=`, or `NOT =`. Each side is resolved as either a field decode or a literal constant, producing a `BINOP` comparison.

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

Tests are in `tests/unit/test_cobol_*.py`:

- **Statement hierarchy**: dispatch + round-trip for all 24 handled types
- **Frontend lowering**: per-statement IR verification (opcode presence, WRITE_REGION counts, loop structure)
- **PIC parsing**: `pic_parser.py` coverage
- **Data layout**: offset/length computation
- **Expression parser**: COMPUTE expression trees
- **PERFORM variants**: TIMES, UNTIL (TEST BEFORE/AFTER), VARYING
- **End-to-end fixtures**: Full COBOL programs through the pipeline
