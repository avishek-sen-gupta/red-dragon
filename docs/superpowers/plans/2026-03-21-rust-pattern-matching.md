# Rust Structural Pattern Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hook Rust `match`, `if let`, and `while let` into the common Pattern ADT via `compile_pattern_test`/`compile_pattern_bindings`, replacing hand-rolled literal-only match lowering.

**Architecture:** New `parse_rust_pattern()` maps tree-sitter Rust pattern nodes to the Pattern ADT (LiteralPattern, WildcardPattern, CapturePattern, OrPattern, SequencePattern, ClassPattern, ValuePattern). Refactored `lower_match_expr` uses `compile_pattern_test`/`compile_pattern_bindings` per arm (C# switch expression pattern). `lower_let_condition` refactored to use pattern ADT for `if let`/`while let`.

**Tech Stack:** Python 3.13+, tree-sitter, pytest, existing Pattern ADT in `interpreter/frontends/common/patterns.py`

**Spec:** `docs/superpowers/specs/2026-03-21-rust-pattern-matching-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `interpreter/frontends/rust/patterns.py` | Create | `parse_rust_pattern()` — tree-sitter node → Pattern ADT |
| `interpreter/frontends/rust/expressions.py` | Modify | Refactor `lower_match_expr` to use pattern ADT; refactor `lower_let_condition` |
| `interpreter/frontends/rust/node_types.py` | Modify | Add any missing node type constants |
| `tests/unit/test_rust_patterns.py` | Create | Unit tests for `parse_rust_pattern` |
| `tests/integration/test_rust_pattern_matching.py` | Create | Integration tests for match/if-let/while-let |

---

### Task 1: `parse_rust_pattern` — Literals, Wildcards, Captures

**Files:**
- Create: `tests/unit/test_rust_patterns.py`
- Create: `interpreter/frontends/rust/patterns.py`

**Reference:**
- Python pattern parser: `interpreter/frontends/python/patterns.py:44-165`
- Pattern ADT types: `interpreter/frontends/common/patterns.py` (LiteralPattern, WildcardPattern, CapturePattern)
- Rust node types: `interpreter/frontends/rust/node_types.py`

- [ ] **Step 1: Write failing unit tests for literal, wildcard, capture patterns**

Test file: `tests/unit/test_rust_patterns.py`

Use tree-sitter to parse Rust snippets containing match expressions, extract the pattern nodes, and verify `parse_rust_pattern` returns the correct Pattern ADT type. Reference how `tests/unit/test_python_patterns.py` or similar tests work (if they exist), otherwise parse a full `match` expression and walk to the pattern node.

Test cases:
- Integer literal `42` → `LiteralPattern(42)`
- Float literal `3.14` → `LiteralPattern(3.14)`
- String literal `"hello"` → `LiteralPattern("hello")`
- Boolean `true` → `LiteralPattern(True)`, `false` → `LiteralPattern(False)`
- Negative literal `-1` → `LiteralPattern(-1)` (check if tree-sitter uses `negative_literal` or `unary_expression` in pattern position)
- Wildcard `_` → `WildcardPattern()` (note: anonymous node in tree-sitter, NOT an `identifier`)
- Capture `x` → `CapturePattern("x")`

```python
import pytest
from interpreter.frontends.rust.patterns import parse_rust_pattern
from interpreter.frontends.common.patterns import (
    LiteralPattern, WildcardPattern, CapturePattern,
)

# Use the Rust frontend's tree-sitter parser to parse snippets.
# Extract pattern nodes from match_arm > match_pattern children.
# See how the existing Rust unit tests in tests/unit/test_rust_frontend.py
# set up the TreeSitterEmitContext for parsing.
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_rust_patterns.py -v`
Expected: ImportError — `parse_rust_pattern` does not exist yet.

- [ ] **Step 3: Implement `parse_rust_pattern` for literals, wildcards, captures**

Create `interpreter/frontends/rust/patterns.py`:

```python
from interpreter.frontends.common.patterns import (
    CapturePattern, LiteralPattern, Pattern, WildcardPattern,
)
from interpreter.frontends.rust.node_types import RustNodeType


def parse_rust_pattern(ctx, node) -> Pattern:
    """Map a tree-sitter Rust pattern node to the Pattern ADT."""
    node_type = node.type
    text = ctx.node_text(node)

    # Wildcard: tree-sitter emits _ as anonymous node
    if text == "_":
        return WildcardPattern()

    # Literals
    if node_type in (
        RustNodeType.INTEGER_LITERAL,
        RustNodeType.FLOAT_LITERAL,
    ):
        return LiteralPattern(_parse_number(text))

    if node_type == RustNodeType.STRING_LITERAL:
        return LiteralPattern(text.strip('"'))

    if node_type == RustNodeType.BOOLEAN_LITERAL:
        return LiteralPattern(text == "true")

    # Negative literals (may be unary_expression with - operator)
    if node_type in (RustNodeType.NEGATIVE_LITERAL, RustNodeType.UNARY_EXPRESSION):
        child = node.children[-1]
        return LiteralPattern(-_parse_number(ctx.node_text(child)))

    # Capture: bare identifier
    if node_type == RustNodeType.IDENTIFIER:
        return CapturePattern(text)

    raise ValueError(f"Unsupported Rust pattern node type: {node_type} ({text})")


def _parse_number(text: str) -> int | float:
    """Parse numeric literal text to int or float."""
    cleaned = text.replace("_", "")
    if "." in cleaned:
        return float(cleaned)
    return int(cleaned, 0)
```

Important: Check `node_types.py` for exact constant names. The node type for boolean literals might need adding. Verify `_` handling against actual tree-sitter output — it may be the only named child of `match_pattern`, or it may be an anonymous child. Write a small diagnostic test first if unsure.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_rust_patterns.py -v`
Expected: All literal/wildcard/capture tests PASS.

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/rust/patterns.py tests/unit/test_rust_patterns.py
git commit -m "feat(rust): add parse_rust_pattern for literals, wildcards, captures"
```

---

### Task 2: `parse_rust_pattern` — Or-patterns, Tuple patterns, Scoped identifiers

**Files:**
- Modify: `interpreter/frontends/rust/patterns.py`
- Modify: `tests/unit/test_rust_patterns.py`

**Reference:**
- Pattern ADT: `OrPattern`, `SequencePattern`, `ValuePattern` in `interpreter/frontends/common/patterns.py`
- Existing or-pattern handling: `interpreter/frontends/rust/expressions.py:283-296` (for understanding what currently exists)

- [ ] **Step 1: Write failing unit tests**

Test cases:
- Or-pattern `1 | 2 | 3` → `OrPattern((LiteralPattern(1), LiteralPattern(2), LiteralPattern(3)))`
- Tuple pattern `(x, y)` → `SequencePattern((CapturePattern("x"), CapturePattern("y")))`
- Tuple with wildcard `(_, y)` → `SequencePattern((WildcardPattern(), CapturePattern("y")))`
- Tuple with literal `(0, y)` → `SequencePattern((LiteralPattern(0), CapturePattern("y")))`
- Scoped identifier `Color::Red` → `ValuePattern(("Color", "Red"))`

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_rust_patterns.py -v -k "or_pattern or tuple or scoped"`
Expected: FAIL — `parse_rust_pattern` raises ValueError for these node types.

- [ ] **Step 3: Add or-pattern, tuple, and scoped identifier handling**

Add to `parse_rust_pattern` in `interpreter/frontends/rust/patterns.py`:

```python
from interpreter.frontends.common.patterns import (
    OrPattern, SequencePattern, ValuePattern,
    # ... existing imports ...
)

# In parse_rust_pattern, add cases:

    # Or-pattern: 1 | 2 | 3
    if node_type == RustNodeType.OR_PATTERN:
        alternatives = tuple(
            parse_rust_pattern(ctx, c)
            for c in node.children
            if c.is_named
        )
        return OrPattern(alternatives)

    # Tuple pattern: (x, y, _)
    if node_type == RustNodeType.TUPLE_PATTERN:
        elements = tuple(
            parse_rust_pattern(ctx, c)
            for c in node.children
            if c.is_named
        )
        return SequencePattern(elements)

    # Scoped identifier: Color::Red
    if node_type == RustNodeType.SCOPED_IDENTIFIER:
        parts = tuple(text.split("::"))
        return ValuePattern(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_rust_patterns.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/rust/patterns.py tests/unit/test_rust_patterns.py
git commit -m "feat(rust): parse_rust_pattern for or-patterns, tuples, scoped identifiers"
```

---

### Task 3: `parse_rust_pattern` — Tuple-struct and Struct patterns (ClassPattern)

**Files:**
- Modify: `interpreter/frontends/rust/patterns.py`
- Modify: `tests/unit/test_rust_patterns.py`

**Reference:**
- `ClassPattern` in `interpreter/frontends/common/patterns.py`
- C# recursive_pattern handling: `interpreter/frontends/csharp/patterns.py`
- Prelude classes: `interpreter/frontends/rust/declarations.py:539-706` (Option, Box)

- [ ] **Step 1: Write failing unit tests**

Test cases:
- `Some(x)` → `ClassPattern("Option", positional=(CapturePattern("x"),), keyword=())`
- `Some(_)` → `ClassPattern("Option", positional=(WildcardPattern(),), keyword=())`
- `Some((a, b))` → `ClassPattern("Option", positional=(SequencePattern((CapturePattern("a"), CapturePattern("b"))),), keyword=())`
- `Point { x, y }` → `ClassPattern("Point", positional=(), keyword=(("x", CapturePattern("x")), ("y", CapturePattern("y"))))`
  - Note: shorthand struct fields use `shorthand_field_identifier` — the name IS the capture variable
- Nested: `Some(Some(x))` → recursive ClassPattern

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_rust_patterns.py -v -k "tuple_struct or struct_pattern or Some"`
Expected: FAIL.

- [ ] **Step 3: Implement tuple-struct and struct pattern parsing**

Add to `interpreter/frontends/rust/patterns.py`:

```python
from interpreter.frontends.common.patterns import ClassPattern

# Prelude variant → class resolution
VARIANT_TO_CLASS = {"Some": "Option", "Ok": "Result", "Err": "Result"}

# In parse_rust_pattern, add cases:

    # Tuple-struct pattern: Some(x), Message::Write(text)
    if node_type == RustNodeType.TUPLE_STRUCT_PATTERN:
        # Constructor name is the identifier child (NOT type_identifier)
        name_node = next(
            c for c in node.children
            if c.type in (RustNodeType.IDENTIFIER, RustNodeType.SCOPED_IDENTIFIER)
        )
        raw_name = ctx.node_text(name_node)
        class_name = VARIANT_TO_CLASS.get(raw_name, raw_name)
        positional = tuple(
            parse_rust_pattern(ctx, c)
            for c in node.children
            if c.is_named and c != name_node
        )
        return ClassPattern(class_name, positional=positional, keyword=())

    # Struct pattern: Point { x, y }
    if node_type == RustNodeType.STRUCT_PATTERN:
        type_node = next(
            c for c in node.children
            if c.type in (RustNodeType.TYPE_IDENTIFIER, RustNodeType.SCOPED_TYPE_IDENTIFIER)
        )
        class_name = ctx.node_text(type_node)
        field_patterns = [c for c in node.children if c.type == RustNodeType.FIELD_PATTERN]
        keyword = tuple(_parse_field_pattern(ctx, fp) for fp in field_patterns)
        return ClassPattern(class_name, positional=(), keyword=keyword)


def _parse_field_pattern(ctx, fp) -> tuple[str, Pattern]:
    """Parse a single field_pattern into (name, Pattern) pair."""
    # Shorthand: Point { x } — shorthand_field_identifier is both name and capture
    shorthand = next(
        (c for c in fp.children if c.type == RustNodeType.SHORTHAND_FIELD_IDENTIFIER),
        None,
    )
    if shorthand:
        name = ctx.node_text(shorthand)
        return (name, CapturePattern(name))
    # Explicit: Point { x: val }
    field_name_node = next(
        c for c in fp.children if c.type == RustNodeType.FIELD_IDENTIFIER
    )
    pattern_child = next(
        c for c in fp.children if c.is_named and c != field_name_node
    )
    return (ctx.node_text(field_name_node), parse_rust_pattern(ctx, pattern_child))
```

Verify tree-sitter node type names by adding a diagnostic test that prints the tree structure of `match x { Some(v) => v }` and `match p { Point { x, y } => x }`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_rust_patterns.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/rust/patterns.py tests/unit/test_rust_patterns.py
git commit -m "feat(rust): parse_rust_pattern for tuple-struct and struct patterns (ClassPattern)"
```

---

### Task 4: Refactor `lower_match_expr` to use Pattern ADT

**Files:**
- Modify: `interpreter/frontends/rust/expressions.py` (lines 283-407)
- Create: `tests/integration/test_rust_pattern_matching.py`

**Reference:**
- C# switch expression lowering: `interpreter/frontends/csharp/control_flow.py:266-319`
- `compile_pattern_test` / `compile_pattern_bindings`: `interpreter/frontends/common/patterns.py:173, 319`
- Existing match tests: `tests/integration/test_rust_or_pattern_execution.py`
- Test helper: `_run_rust()` at line 14 of that file

- [ ] **Step 1: Write failing integration tests for new pattern types**

Create `tests/integration/test_rust_pattern_matching.py`. Use the same `_run_rust()` helper pattern from `test_rust_or_pattern_execution.py`:

```python
from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_rust(source: str, max_steps: int = 300):
    """Run a Rust program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.RUST, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)
```

Test cases (each a separate test method in a `TestRustPatternMatching` class):

1. **Capture binding:** `match x { n => n + 1 }` — verify `n` is bound
2. **Or-pattern (regression in new file):** `match x { 1 | 2 => 10, _ => 0 }` — verify or-pattern still works through Pattern ADT path
3. **Tuple destructuring:** `match pair { (a, b) => a + b }` — verify tuple elements extracted. Need to construct a tuple first: `let pair = (3, 4);`
4. **Some(x) destructuring:** `let opt = Some(5); match opt { Some(v) => v, _ => 0 }` — verify `v` bound to 5
5. **Struct destructuring:** Define a struct with fields, create instance, match on fields
6. **Guard clause:** `match x { n if n > 0 => 1, _ => -1 }` — verify guard filters
7. **Nested pattern:** `match opt { Some((a, b)) => a + b, _ => 0 }`
8. **Scoped identifier:** `match c { Color::Red => 1, _ => 0 }` — verify ValuePattern lookup (requires enum with Color defined)

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/integration/test_rust_pattern_matching.py -v`
Expected: FAIL — current `lower_match_expr` doesn't support destructuring/guards.

- [ ] **Step 3: Also run existing or-pattern tests to establish baseline**

Run: `poetry run python -m pytest tests/integration/test_rust_or_pattern_execution.py -v`
Expected: PASS (6 tests). This is our regression baseline.

- [ ] **Step 4: Refactor `lower_match_expr` in `expressions.py`**

Replace lines ~283-407 (the `_lower_or_pattern_condition`, `_lower_single_comparison`, `_lower_arm_condition`, and `lower_match_expr` functions). Keep helper functions that are still used elsewhere (check with grep first).

New `lower_match_expr` structure (following C# `lower_switch_expr` pattern):

```python
from interpreter.frontends.rust.patterns import parse_rust_pattern
from interpreter.frontends.common.patterns import (
    compile_pattern_test, compile_pattern_bindings,
    WildcardPattern, CapturePattern,
)

def lower_match_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Rust match expression using Pattern ADT."""
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")
    subject_reg = ctx.lower_expr(value_node)

    result_var = f"__match_result_{ctx.label_counter}"
    end_label = ctx.fresh_label("match_end")
    arms = [c for c in body_node.children if c.type == RustNodeType.MATCH_ARM]

    for arm in arms:
        _lower_match_arm(ctx, arm, subject_reg, result_var, end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def _lower_match_arm(ctx, arm, subject_reg, result_var, end_label):
    """Lower a single match arm: test pattern, bind, evaluate body, store result."""
    match_pattern_node = next(
        c for c in arm.children if c.type == RustNodeType.MATCH_PATTERN
    )

    # Guard is inside match_pattern (after anonymous 'if' token), NOT a sibling
    named_children = [c for c in match_pattern_node.children if c.is_named]
    pattern_node = named_children[0]
    guard_node = named_children[1] if len(named_children) > 1 else None

    pattern = parse_rust_pattern(ctx, pattern_node)

    # Body: named children of match_arm excluding match_pattern and punctuation
    body_expr = _extract_arm_body(arm)

    is_irrefutable = (
        isinstance(pattern, (WildcardPattern, CapturePattern))
        and guard_node is None
    )

    if is_irrefutable:
        compile_pattern_bindings(ctx, subject_reg, pattern)
        body_reg = ctx.lower_expr(body_expr)
        ctx.emit(Opcode.DECL_VAR, operands=[result_var, body_reg])
        ctx.emit(Opcode.BRANCH, label=end_label)
        return

    test_reg = compile_pattern_test(ctx, subject_reg, pattern)
    if guard_node:
        # Pre-bind for guard evaluation, then AND with test
        compile_pattern_bindings(ctx, subject_reg, pattern)
        guard_reg = ctx.lower_expr(guard_node)
        final_test = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=final_test,
            operands=["&&", test_reg, guard_reg],
        )
        test_reg = final_test

    arm_label = ctx.fresh_label("match_arm")
    next_label = ctx.fresh_label("match_next")
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[test_reg],
        label=f"{arm_label},{next_label}",
    )
    ctx.emit(Opcode.LABEL, label=arm_label)

    if not guard_node:
        compile_pattern_bindings(ctx, subject_reg, pattern)

    body_reg = ctx.lower_expr(body_expr)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, body_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=next_label)


def _extract_arm_body(arm):
    """Extract the body expression node from a match_arm."""
    return [
        c
        for c in arm.children
        if c.type
        not in (
            RustNodeType.MATCH_PATTERN,
            RustNodeType.FAT_ARROW,
            RustNodeType.COMMA,
            RustNodeType.FAT_ARROW_ALIAS,
        )
        and c.is_named
    ][0]
```

**API patterns (verified against existing code):**
- Labels: `ctx.emit(Opcode.LABEL, label=arm_label)` — NOT `ctx.emit_label()`
- Branches: `ctx.emit(Opcode.BRANCH, label=end_label)` — labels go in `label` kwarg, NOT `operands`
- Branch-if: `ctx.emit(Opcode.BRANCH_IF, operands=[cond_reg], label=f"{true},{false}")` — condition in operands, targets in label
- Result var: `f"__match_result_{ctx.label_counter}"` — NOT `ctx.fresh_id()` (doesn't exist)
- Result storage: `DECL_VAR` per arm (matches existing pattern at line 400 of expressions.py)

**Guard handling note:** When a guard is present, bindings must be emitted BEFORE the guard is evaluated (so guard can reference pattern variables like `n if n > 0`). But bindings should only be emitted once, not duplicated. The code above handles this by binding before the guard check in the guarded case.

- [ ] **Step 5: Run ALL tests**

Run: `poetry run python -m pytest tests/integration/test_rust_or_pattern_execution.py tests/integration/test_rust_pattern_matching.py -v`
Expected: ALL PASS (existing or-pattern tests + new pattern matching tests).

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `poetry run python -m pytest --tb=short -q`
Expected: No regressions. Test count should not decrease.

- [ ] **Step 7: Commit**

```bash
git add interpreter/frontends/rust/expressions.py tests/integration/test_rust_pattern_matching.py
git commit -m "feat(rust): refactor lower_match_expr to use Pattern ADT with compile_pattern_test"
```

---

### Task 5: Refactor `lower_let_condition` for `if let` / `while let`

**Files:**
- Modify: `interpreter/frontends/rust/expressions.py` (line 860-876, `lower_let_condition`)
- Modify: `tests/integration/test_rust_pattern_matching.py`

**Reference:**
- Current `lower_let_condition`: `interpreter/frontends/rust/expressions.py:860-876`
- Current dispatch: `interpreter/frontends/rust/frontend.py:116` (LET_CONDITION → lower_let_condition)
- Spec if-let/while-let section

- [ ] **Step 1: Write failing integration tests for if let and while let**

Add to `tests/integration/test_rust_pattern_matching.py`:

```python
class TestRustIfLet:
    def test_if_let_some_match(self):
        """if let Some(v) = Some(5) should bind v to 5."""
        _, local_vars = _run_rust("""\
let opt = Some(5);
let result = if let Some(v) = opt { v } else { 0 };
""")
        assert local_vars["result"] == 5

    def test_if_let_no_match(self):
        """if let Some(v) = expr where expr is not Some should take else branch."""
        _, local_vars = _run_rust("""\
let x = 42;
let result = if let Some(v) = x { v } else { -1 };
""")
        assert local_vars["result"] == -1
```

Note: `while let` tests are deferred — they depend on having a mutable data source that returns `Some` then stops. This likely requires array/iterator support or manual mutation patterns that may not be available yet. File a follow-up issue if needed.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/integration/test_rust_pattern_matching.py -v -k "if_let"`
Expected: FAIL — current `lower_let_condition` doesn't destructure.

- [ ] **Step 3: Refactor `lower_if_expr` to detect and handle `if let` inline**

The challenge: `lower_let_condition` returns a condition register, but bindings must happen AFTER the branch to the true block. Instead of adding pending state to `ctx`, detect `let_condition` in `lower_if_expr` and handle the full flow inline.

In `lower_if_expr` (line ~161 of `expressions.py`), add early detection before the existing logic:

```python
def lower_if_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Rust if expression (value-producing)."""
    cond_node = node.child_by_field_name(ctx.constants.if_condition_field)

    # if let: detect let_condition and handle inline
    if cond_node and cond_node.type == RustNodeType.LET_CONDITION:
        return _lower_if_let_expr(ctx, node, cond_node)

    # ... existing if-expr logic unchanged from here ...


def _lower_if_let_expr(ctx: TreeSitterEmitContext, node, let_cond_node) -> str:
    """Lower `if let Pattern = expr { body } else { alt }` as expression."""
    pattern_node = let_cond_node.child_by_field_name("pattern")
    value_node = let_cond_node.child_by_field_name("value")
    body_node = node.child_by_field_name(ctx.constants.if_consequence_field)
    alt_node = node.child_by_field_name(ctx.constants.if_alternative_field)

    subject_reg = ctx.lower_expr(value_node)
    pattern = parse_rust_pattern(ctx, pattern_node)
    test_reg = compile_pattern_test(ctx, subject_reg, pattern)

    true_label = ctx.fresh_label("if_let_true")
    false_label = ctx.fresh_label("if_let_false")
    end_label = ctx.fresh_label("if_let_end")
    result_var = f"__if_let_result_{ctx.label_counter}"

    target_label = false_label if alt_node else end_label
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[test_reg],
        label=f"{true_label},{target_label}",
        node=node,
    )

    # True branch: bind pattern variables, evaluate body
    ctx.emit(Opcode.LABEL, label=true_label)
    compile_pattern_bindings(ctx, subject_reg, pattern)
    true_reg = lower_block_expr(ctx, body_node)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, true_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)

    # Else branch (if present)
    if alt_node:
        ctx.emit(Opcode.LABEL, label=false_label)
        false_reg = ctx.lower_expr(alt_node)
        ctx.emit(Opcode.DECL_VAR, operands=[result_var, false_reg])
        ctx.emit(Opcode.BRANCH, label=end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg
```

**Verify:** `child_by_field_name("pattern")` and `child_by_field_name("value")` work on `let_condition` nodes. The existing `lower_let_condition` at line 862-863 already uses these field names successfully.

Also update `lower_let_condition` (line 860) to use `parse_rust_pattern` + `compile_pattern_test` so it returns a proper boolean test register (for any remaining callers):

```python
def lower_let_condition(ctx: TreeSitterEmitContext, node) -> str:
    """Lower `let Pattern = expr` — returns boolean test register."""
    pattern_node = node.child_by_field_name("pattern")
    value_node = node.child_by_field_name("value")
    subject_reg = ctx.lower_expr(value_node)
    pattern = parse_rust_pattern(ctx, pattern_node)
    return compile_pattern_test(ctx, subject_reg, pattern)
```

- [ ] **Step 4: Run tests**

Run: `poetry run python -m pytest tests/integration/test_rust_pattern_matching.py -v`
Expected: All if-let and while-let tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: No regressions.

- [ ] **Step 6: Commit**

```bash
git add interpreter/frontends/rust/expressions.py tests/integration/test_rust_pattern_matching.py
git commit -m "feat(rust): refactor lower_let_condition for if-let/while-let with Pattern ADT"
```

---

### Task 6: Clean up deleted code and update node_types

**Files:**
- Modify: `interpreter/frontends/rust/expressions.py`
- Modify: `interpreter/frontends/rust/node_types.py`

- [ ] **Step 1: Remove dead code**

After Tasks 4-5, check if these functions are still referenced anywhere:
- `_lower_arm_condition` (line ~330)
- `_lower_or_pattern_condition` (line ~283)
- `_lower_single_comparison` (line ~298)
- `_flatten_or_alternatives`
- `_fold_or`
- `_is_or_pattern`
- `lower_struct_pattern_expr` (line ~879) — may still be needed for non-match struct pattern contexts

Use grep to verify. Delete any that are unused.

- [ ] **Step 2: Add missing node type constants**

Check `interpreter/frontends/rust/node_types.py` for any missing constants used in the new code. Already present: `BOOLEAN_LITERAL` (line 21), `SHORTHAND_FIELD_IDENTIFIER` (line 14), `FIELD_IDENTIFIER` (line 13), `NEGATIVE_LITERAL` (line 23). May need to add: `MATCH_BLOCK = "match_block"` if used, and `GUARD = "match_arm_guard"` or similar if tree-sitter uses a named node for guards. Only add what's actually used.

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: No regressions.

- [ ] **Step 4: Run black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/rust/expressions.py interpreter/frontends/rust/node_types.py
git commit -m "refactor(rust): clean up dead match lowering code, add missing node types"
```

---

### Task 7: ADR and final verification

**Files:**
- Modify: `docs/architectural-design-decisions.md`
- Modify: `README.md`

- [ ] **Step 1: Add ADR entry**

Add to `docs/architectural-design-decisions.md`:

```markdown
## ADR-NNN: Rust Structural Pattern Matching (2026-03-21)

**Status:** Accepted
**Issue:** red-dragon-r06p

Rust `match`, `if let`, and `while let` now use the common Pattern ADT
(`interpreter/frontends/common/patterns.py`) via `compile_pattern_test`
and `compile_pattern_bindings`. This replaces the hand-rolled literal-only
match lowering.

Supported patterns: literals, wildcards, captures, or-patterns, tuples,
tuple-struct (`Some(x)` via `ClassPattern`), struct (`Point { x, y }`),
scoped identifiers (`Color::Red` via `ValuePattern`), and guards.

Custom enum variant destructuring (e.g., `Shape::Circle(r)`) requires
variant class infrastructure (red-dragon-vwqd) and is out of scope.

**Decision:** Use `compile_pattern_test`/`compile_pattern_bindings` directly
(not `compile_match`) because Rust `match` is expression-style (returns a value),
following the C# `lower_switch_expr` pattern.
```

- [ ] **Step 2: Update README**

Update relevant sections of `README.md` to reflect Rust pattern matching support.

- [ ] **Step 3: Run full test suite one final time**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass. Note test count for verification.

- [ ] **Step 4: Close beads issue**

Run: `bd close red-dragon-r06p`

- [ ] **Step 5: Commit**

```bash
git add docs/architectural-design-decisions.md README.md
git commit -m "docs: ADR for Rust structural pattern matching (red-dragon-r06p)"
```
