# Follow-up Issues: Reference Modification Support

**Epic**: red-dragon-4q25.29 — Reference Modification  
**Status**: Main issue (MOVE) complete, filed 2026-04-20

This document describes follow-on issues for reference modification support in statements beyond MOVE.

---

## Issue 1: COMPUTE Reference Modification

**Scope**: Add reference modification support to COMPUTE statement operands  
**Subtasks**:
- Update `ComputeStatement` in `/interpreter/cobol/cobol_statements.py` to support operand reference modification
- Extend `lower_compute` in `/interpreter/cobol/lower_arithmetic.py` to handle ref mod via SLICE/SPLICE
- Add unit tests in `tests/unit/test_compute_lowering.py`
- Add integration tests in `tests/integration/test_cobol_programs.py::TestComputeReferenceModification`

**Details**:
COMPUTE arithmetic statements can reference-modify their operands:
```cobol
COMPUTE WS-RESULT(2:5) = WS-A(1:3) + WS-B.
```

Implementation mirrors MOVE lowering: parse arithmetic expressions, emit SLICE/SPLICE for ref-modified operands, adjust 1-indexed COBOL positions to 0-indexed Python indices.

---

## Issue 2: STRING Reference Modification

**Scope**: Add reference modification support to STRING statement operands  
**Subtasks**:
- Update `StringStatement` in `/interpreter/cobol/cobol_statements.py` to support operand reference modification
- Extend `lower_string` in `/interpreter/cobol/lower_statement.py` to handle ref mod via SLICE/SPLICE
- Add unit tests in `tests/unit/test_string_lowering.py`
- Add integration tests in `tests/integration/test_cobol_programs.py::TestStringReferenceModification`

**Details**:
STRING concatenates field substrings:
```cobol
STRING WS-A(1:2) DELIMITED BY SIZE
       WS-B(2:3) DELIMITED BY SIZE
       INTO WS-OUT(1:5).
```

Each source operand may have reference modification. The INTO target may also have ref mod to specify the substring to write to.

---

## Issue 3: UNSTRING Reference Modification

**Scope**: Add reference modification support to UNSTRING statement operands  
**Subtasks**:
- Update `UnstringStatement` in `/interpreter/cobol/cobol_statements.py` to support operand reference modification
- Extend `lower_unstring` in `/interpreter/cobol/lower_statement.py` to handle ref mod via SLICE/SPLICE
- Add unit tests in `tests/unit/test_unstring_lowering.py`
- Add integration tests in `tests/integration/test_cobol_programs.py::TestUnstringReferenceModification`

**Details**:
UNSTRING parses a field into delimited portions and stores each into target fields:
```cobol
UNSTRING WS-INPUT(2:20) DELIMITED BY ','
         INTO WS-OUT1(1:5) WS-OUT2(1:5).
```

The source may have ref mod to specify which substring to parse. Each target may have ref mod to specify where to write the parsed value.

---

## Issue 4: IF Condition Reference Modification

**Scope**: Add reference modification support to IF condition operands  
**Subtasks**:
- Update condition lowering in `/interpreter/cobol/condition_lowering.py` to handle ref mod
- Extend `_lower_condition_binop` and related functions to emit SLICE/SPLICE for ref-modified operands
- Add unit tests in `tests/unit/test_condition_lowering.py`
- Add integration tests in `tests/integration/test_cobol_programs.py::TestIfReferenceModification`

**Details**:
IF conditions can reference-modify their operands:
```cobol
IF WS-FIELD(2:3) = WS-VALUE(1:2)
    PERFORM DO-SOMETHING
END-IF.
```

Both source and target of the comparison may have reference modification. Implementation reuses SLICE instruction to extract substrings for comparison.

---

## Implementation Notes

### Reusable Patterns

All four issues reuse the same core patterns established in MOVE lowering:

1. **eval_ref_mod_expr** (already exists in `lower_arithmetic.py`): Evaluates a reference modification expression to an IR register
2. **SLICE/SPLICE instructions** (already implemented): Substring extraction and replacement
3. **1-to-0 index conversion**: COBOL uses 1-indexed positions; convert via `(position - 1)` before SLICE
4. **Test utilities** (existing): `_run_cobol()`, `_first_region()`, `_decode_alpha()` already support all statement types

### File Structure

- **Grammar/AST updates**: Language-specific (`cobol_statements.py`, `cobol_expression.py`)
- **Lowering updates**: `lower_arithmetic.py`, `lower_statement.py`, `condition_lowering.py`
- **Test files**: Parallel test structure for unit and integration tests per issue

### Estimated Effort

- Issue 1 (COMPUTE): 2–3 hours (single operator, reuses arithmetic lowering)
- Issue 2 (STRING): 3–4 hours (multiple operands, concatenation logic)
- Issue 3 (UNSTRING): 3–4 hours (multiple targets, parsing logic)
- Issue 4 (IF): 2–3 hours (condition comparison, reuses existing condition lowering)

Total: ~10–14 hours of implementation + testing

---

## Closure Criteria

Each follow-on issue is closed when:
- Grammar/statement structures support reference modification
- Lowering code emits correct IR with SLICE/SPLICE
- Unit tests cover all expression forms (literal, reference, binop, nested)
- Integration tests verify end-to-end execution
- Full test suite passes (13,661+ tests)
