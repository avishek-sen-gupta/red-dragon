# Or-Patterns with Bindings — Design Spec

**Date:** 2026-03-20
**Status:** Approved
**Scope:** `case (1, x) | (2, x):` — or-patterns where alternatives contain captures
**Issue:** red-dragon-fv2p

## Problem

`OrPattern` currently emits no bindings (`pass` in `compile_pattern_bindings`). When an or-pattern's alternatives contain captures (e.g., `case (1, x) | (2, x):`), the body references `x` but it's never bound.

Python requires all alternatives to bind the same set of names. This means we can emit bindings from whichever alternative matched.

## Approach

Replace the `OrPattern` case in `compile_pattern_bindings` with a mini linear chain: re-test each alternative, bind from the first one that matches, branch to done. This matches CPython's approach.

## Design

**Change in `compile_pattern_bindings`** — replace `case OrPattern(): pass` with:

```
for each alternative:
    test_reg = compile_pattern_test(ctx, subject_reg, alt)
    BRANCH_IF test_reg → bind_label, next_alt_label
    bind_label:
        compile_pattern_bindings(ctx, subject_reg, alt)
        BRANCH → or_done
    next_alt_label:
        (continue to next alt)
or_done:
```

This re-tests each alternative in the bind phase to find which one matched, then binds from that one. The re-test is cheap (BINOP comparisons) and only runs after the test phase already confirmed the OR passed.

**No changes to:** `OrPattern` ADT, `parse_pattern`, `compile_pattern_test` (test phase stays as-is with `_or_any`).

**Files modified:**
- `interpreter/frontends/common/patterns.py` — `compile_pattern_bindings` OrPattern case
- `tests/unit/test_pattern_compiler.py` — unit tests
- `tests/integration/test_python_pattern_matching.py` — integration tests + remove xfail

## Testing

**Unit tests:**
- `test_or_pattern_binds_from_matched_alternative` — OrPattern with captures emits STORE_VAR
- `test_or_pattern_bindings_use_branch_chain` — emits BRANCH_IF per alternative in binding phase

**Integration tests:**
- `test_or_pattern_tuple_with_captures` — `case (1, x) | (2, x):` with `(2, 99)` → `x == 99`
- `test_or_pattern_list_with_captures` — `case [1, y] | (2, y):` with `[2, 42]` → `y == 42`
- `test_or_pattern_first_alternative_binds` — `case (1, x) | (2, x):` with `(1, 77)` → `x == 77`
- Remove xfail from existing `test_or_pattern_with_captures`
