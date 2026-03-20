# Pattern Matching Infrastructure — Design Spec

**Date:** 2026-03-20
**Status:** Approved
**Scope:** Structural pattern matching + guards, Python as first consumer, common infrastructure for all languages

## Problem

The current `lower_match` in `interpreter/frontends/python/control_flow.py` handles every case by lowering the pattern as an expression and comparing with `BINOP ==`. This works for literals but fails for structural patterns (tuple, list, dict, class, union, as) which cannot be meaningfully lowered as expressions.

6 Python pattern types are missing: `tuple_pattern`, `class_pattern`, `union_pattern`, `as_pattern`, `complex_pattern`, `keyword_pattern`. 28 total pattern matching P1s exist across 7 languages.

## Approach

**Pattern ADT + single compiler.** Language frontends parse their tree-sitter AST into a shared Pattern algebraic data type. A single `compile_match` function emits test+destructure IR using existing opcodes (no new opcodes, no VM changes). Follows the CPython linear chain model: sequential test-and-branch per case.

This mirrors the SpreadArguments precedent: frontend decides (parses pattern), IR carries the decision (Pattern ADT), shared layer acts on it (emits IR).

## Design

### 1. Pattern ADT (`interpreter/frontends/common/patterns.py`)

Frozen dataclass hierarchy:

- **`LiteralPattern(value: int | float | str | bool | None)`** — match against a literal value
- **`WildcardPattern()`** — matches anything, binds nothing (Python's `_`)
- **`CapturePattern(name: str)`** — matches anything, binds subject to variable name
- **`SequencePattern(elements: tuple[Pattern, ...])`** — matches tuple/list by length + element-wise recursion
- **`MappingPattern(entries: tuple[tuple[int | float | str | bool | None, Pattern], ...])`** — matches dict by key existence + value pattern recursion
- **`ClassPattern(class_name: str, positional: tuple[Pattern, ...], keyword: tuple[tuple[str, Pattern], ...])`** — matches by isinstance, then positional (by index) and keyword (by field name) sub-patterns
- **`OrPattern(alternatives: tuple[Pattern, ...])`** — matches if any alternative matches. Simple or-patterns (literals only) work. Or-patterns with capture bindings (e.g., `case (1, x) | (2, x):`) are out of scope — filed as issue, tested with xfail.
- **`AsPattern(pattern: Pattern, name: str)`** — matches inner pattern, then binds subject to name

### 2. Pattern Compiler (`compile_match` in same file)

```python
@dataclass(frozen=True)
class MatchCase:
    """A single case in a match statement."""
    pattern: Pattern
    guard_node: object  # tree-sitter node or _NO_GUARD sentinel
    body_node: object   # tree-sitter node or _NO_BODY sentinel

_NO_GUARD = object()
_NO_BODY = object()
```

```
compile_match(ctx: TreeSitterEmitContext, subject_reg: str, cases: list[MatchCase]) -> None
```

**Compilation model per case:**
1. `compile_pattern_test(ctx, subject_reg, pattern)` → boolean register
2. If guard exists: `ctx.lower_expr(guard_node)` → AND with test result
3. `BRANCH_IF → case_body_label, next_case_label`
4. At `case_body_label`: `compile_pattern_bindings(ctx, subject_reg, pattern)` → emit `STORE_VAR` for captures, then lower body, then `BRANCH → match_end`
5. At `next_case_label`: continue to next case

**Two-pass design:** Tests and bindings are separate passes over the pattern tree. All tests must pass before any bindings are emitted. This prevents partial binding when a pattern fails midway through a compound test.

**Per-pattern IR emission:**

| Pattern | Test IR | Bind IR |
|---|---|---|
| `LiteralPattern(v)` | `CONST v` → `BINOP == subject, v_reg` | — |
| `WildcardPattern` | no test (always true) | — |
| `CapturePattern(name)` | no test (always true) | `STORE_VAR name, subject` |
| `SequencePattern(elems)` | `CALL_FUNCTION len(subject)` → `BINOP == len_reg, N` → for each `elems[i]`: `LOAD_INDEX subject, i` → recurse. Note: if `len()` returns symbolic for a non-sequence subject, the `BINOP ==` will produce symbolic/false, causing fall-through to the next case. | recursive from elements |
| `MappingPattern(entries)` | for each `(key, pat)`: `LOAD_FIELD subject, str(key)` → recurse on value pattern. Non-string keys (int, float, bool, None) are stringified at IR emission time since heap fields are string-keyed dicts. | recursive from value patterns |
| `ClassPattern(cls, pos, kw)` | `CALL_FUNCTION isinstance(subject, cls)` → positional: `LOAD_INDEX subject, i` → recurse; keyword: `LOAD_FIELD subject, name` → recurse | recursive |
| `OrPattern(alts)` | try alt[0], if success → done; else try alt[1] → ...; short-circuit on first match | — |
| `AsPattern(inner, name)` | compile inner test | inner bindings + `STORE_VAR name, subject` |

### 3. Python Frontend Parser (`interpreter/frontends/python/patterns.py`)

```
parse_pattern(ctx, node) -> Pattern
```

Maps tree-sitter node types to Pattern ADT:

| tree-sitter node | Pattern |
|---|---|
| `integer`, `string`, `true`, `false`, `none` | `LiteralPattern(value)` |
| `_` | `WildcardPattern()` |
| `dotted_name` / `identifier` (not `_`) | `CapturePattern(name)` |
| `tuple_pattern` | `SequencePattern(elements)` |
| `list_pattern` | `SequencePattern(elements)` |
| `dict_pattern` | `MappingPattern(entries)` |
| `class_pattern` | `ClassPattern(class_name, positional, keyword)` |
| `union_pattern` | `OrPattern(alternatives)` |
| `as_pattern` | `AsPattern(inner, name)` |
| `complex_pattern` | **Out of scope** — xfail test + issue reference |

### 4. `lower_match` Refactoring

The existing `lower_match` (control_flow.py:415-482) changes to:
1. Lower subject expression → `subject_reg`
2. For each case clause: `parse_pattern(ctx, inner_pattern_node)` → Pattern ADT
3. Extract guard node if present
4. Build `MatchCase(pattern, guard_node, body_node)` and pass list to `compile_match`

The existing `lower_case_pattern` in expressions.py is removed. The `CASE_PATTERN` mapping in frontend.py is removed.

### 5. File Layout

**New files:**
- `interpreter/frontends/common/patterns.py` — Pattern ADT + `compile_match`
- `interpreter/frontends/python/patterns.py` — `parse_pattern`
- `tests/unit/test_pattern_compiler.py` — unit tests for IR emission
- `tests/integration/test_python_pattern_matching.py` — integration tests

**Modified files:**
- `interpreter/frontends/python/control_flow.py` — `lower_match` refactored
- `interpreter/frontends/python/node_types.py` — add missing constants
- `interpreter/frontends/python/frontend.py` — remove `CASE_PATTERN` mapping
- `interpreter/frontends/python/expressions.py` — remove `lower_case_pattern`

**Also modified:**
- `interpreter/builtins.py` — add `isinstance` builtin (takes `(subject, class_name)` args, uses `vm.heap[pointer].type_hint` to compare against class name; follows existing `(args, vm)` signature pattern like `_builtin_clone`)

**No changes to:** `ir.py`, `executor.py`, `vm.py`

## Testing Strategy

**Exhaustive TDD** — all tests written before implementation.

### Unit Tests (`tests/unit/test_pattern_compiler.py`)

Each pattern type's test IR and bind IR verified in isolation:

- `test_literal_pattern_emits_const_and_binop_eq`
- `test_wildcard_pattern_emits_no_test`
- `test_capture_pattern_emits_store_var`
- `test_sequence_pattern_emits_len_check_and_load_index`
- `test_sequence_pattern_nested_literals`
- `test_mapping_pattern_emits_load_field_per_key`
- `test_class_pattern_emits_isinstance_and_field_access`
- `test_or_pattern_short_circuits`
- `test_as_pattern_binds_after_inner_test`
- `test_guarded_case_emits_guard_after_pattern_test`
- `test_two_pass_no_partial_binding`
- `test_multiple_cases_linear_chain`

### Integration Tests (`tests/integration/test_python_pattern_matching.py`)

Real Python programs through `run()`:

- `test_literal_int_match`
- `test_literal_str_match`
- `test_wildcard_default`
- `test_capture_binds_value`
- `test_tuple_destructure`
- `test_list_destructure`
- `test_nested_sequence`
- `test_dict_pattern`
- `test_class_positional`
- `test_class_keyword`
- `test_or_pattern`
- `test_as_pattern`
- `test_guard_filters`
- `test_fall_through_to_default`
- `test_no_match_no_crash`
- `test_nested_class_in_sequence`
- `test_nested_mapping_in_class`

Out-of-scope features get integration tests with correct assertions marked `xfail` + issue references.

## Out of Scope (filed as issues)

1. **Exhaustiveness checking** — type system integration for Rust/Scala/Kotlin
2. **Custom extractors** — Scala `unapply`/`unapplySeq`, Kotlin `componentN`
3. **Nested or-patterns with bindings** — `case (1, x) | (2, x):` binding consistency
4. **Star patterns in sequences** — `case [first, *rest]:` with rest capture
5. **Complex literal patterns** — `case 1+2j:`
6. **Value patterns (dotted names as constants)** — `case Color.RED:` constant lookup vs. capture

## Future Language Hookup

Each language adds its own `parse_pattern` function mapping tree-sitter AST → Pattern ADT, then calls the same `compile_match`. The common layer is language-agnostic. No changes needed to the compiler or ADT when adding new languages (unless they introduce genuinely new pattern semantics).
