# IR Lowering Gaps

Tracking document for tree-sitter frontend IR lowering gaps, discovered via cross-language type inference integration tests (ADR-079).

---

## All gaps resolved (2026-03-06)

All three gaps identified during the initial cross-language type inference work have been fixed:

- **GAP-001** (Scala `this.field` in expression-bodied getters): Fixed by detecting bare expression bodies in `lower_function_def` and using `lower_expr` + RETURN instead of `lower_block`.
- **GAP-002** (Ruby implicit return): Fixed by extracting `_lower_body_with_implicit_return` helper that detects when the last child of a method body is an expression and wires its register to RETURN.
- **GAP-003** (Kotlin/Scala expression-bodied functions): Fixed by returning expression registers from body lowering and wiring them to RETURN instead of default nil.

All `xfail` markers removed from `tests/integration/test_type_inference.py`. Scala added to `TestReturnBackfillAllLanguages`.
