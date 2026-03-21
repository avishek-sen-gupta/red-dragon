# Scala Structural Pattern Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hook Scala `match` into the common Pattern ADT via `compile_pattern_test`/`compile_pattern_bindings`, replacing hand-rolled expression-based match lowering.

**Architecture:** New `parse_scala_pattern()` maps tree-sitter Scala pattern nodes to the Pattern ADT. Refactored `lower_match_expr` uses `compile_pattern_test`/`compile_pattern_bindings` per case clause (same expression-style pattern as Rust ADR-117 and C# switch expressions). Guard extracted by iterating `case_clause` children for `NT.GUARD` type.

**Tech Stack:** Python 3.13+, tree-sitter, pytest, existing Pattern ADT in `interpreter/frontends/common/patterns.py`

**Spec:** `docs/superpowers/specs/2026-03-21-scala-pattern-matching-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `interpreter/frontends/scala/patterns.py` | Create | `parse_scala_pattern()` — tree-sitter node → Pattern ADT |
| `interpreter/frontends/scala/expressions.py` | Modify | Refactor `lower_match_expr` to use pattern ADT; delete old pattern lowerers |
| `interpreter/frontends/scala/frontend.py` | Modify | Remove pattern expr_dispatch entries that are no longer needed |
| `tests/unit/test_scala_patterns.py` | Create | Unit tests for `parse_scala_pattern` |
| `tests/integration/test_scala_pattern_matching.py` | Create | Integration tests for match with Pattern ADT |

---

### Task 1: `parse_scala_pattern` — Literals, Wildcards, Captures

**Files:**
- Create: `tests/unit/test_scala_patterns.py`
- Create: `interpreter/frontends/scala/patterns.py`

**Reference:**
- Rust pattern parser: `interpreter/frontends/rust/patterns.py` (template)
- Scala node types: `interpreter/frontends/scala/node_types.py`
- Scala frontend setup: `tests/unit/test_scala_frontend.py` (for TreeSitterEmitContext setup pattern)

- [ ] **Step 1: Write failing unit tests for literal, wildcard, capture patterns**

Create `tests/unit/test_scala_patterns.py`. Use tree-sitter to parse Scala snippets containing match expressions, extract pattern nodes from `case_clause`, and verify `parse_scala_pattern` returns correct Pattern ADT types.

To extract pattern nodes from Scala: parse `object Main { def main(): Unit = { x match { case 42 => 1 } } }`, walk tree to find `case_clause`, then use `clause.child_by_field_name("pattern")` to get the pattern node.

Test cases:
- Integer literal `42` → `LiteralPattern(42)`
- Float literal `3.14` → `LiteralPattern(3.14)` (node type: `floating_point_literal`)
- String `"hello"` → `LiteralPattern("hello")` (node type: `string`)
- Boolean `true` → `LiteralPattern(True)`
- Wildcard `_` → `WildcardPattern()` (node type: `wildcard` — a NAMED node, unlike Rust)
- Capture `x` → `CapturePattern("x")` (node type: `identifier`)

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_scala_patterns.py -v`
Expected: ImportError — `parse_scala_pattern` does not exist yet.

- [ ] **Step 3: Implement `parse_scala_pattern` for basics**

Create `interpreter/frontends/scala/patterns.py`:

```python
"""Parse tree-sitter Scala pattern AST nodes into Pattern ADT."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    CapturePattern,
    LiteralPattern,
    Pattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.scala.node_types import ScalaNodeType as NT


def parse_scala_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
    """Map a tree-sitter Scala pattern node to the Pattern ADT."""
    node_type = node.type
    text = ctx.node_text(node)

    if node_type == NT.WILDCARD:
        return WildcardPattern()

    if node_type == NT.INTEGER_LITERAL:
        return LiteralPattern(_parse_number(text))

    if node_type == NT.FLOATING_POINT_LITERAL:
        return LiteralPattern(float(text.replace("_", "")))

    if node_type in (NT.STRING, NT.STRING_LITERAL):
        # Strip surrounding quotes
        content = text.strip('"')
        return LiteralPattern(content)

    if node_type == NT.BOOLEAN_LITERAL:
        return LiteralPattern(text == "true")

    if node_type == NT.IDENTIFIER:
        return CapturePattern(text)

    raise ValueError(f"Unsupported Scala pattern node type: {node_type!r} ({text!r})")


def _parse_number(text: str) -> int | float:
    """Parse numeric literal text to int or float, stripping _ separators."""
    cleaned = text.replace("_", "")
    if "." in cleaned:
        return float(cleaned)
    return int(cleaned, 0)
```

**Important:** Scala `wildcard` is a NAMED node type (`ScalaNodeType.WILDCARD = "wildcard"`), unlike Rust where `_` is anonymous. This simplifies detection — just check `node.type == NT.WILDCARD`.

Verify string handling: tree-sitter Scala may emit `string` or `string_literal` — check which appears in practice. The node may include quotes in its text or have a `string_content` child. Write a diagnostic test to verify.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_scala_patterns.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/scala/patterns.py tests/unit/test_scala_patterns.py
git commit -m "feat(scala): add parse_scala_pattern for literals, wildcards, captures"
```

---

### Task 2: `parse_scala_pattern` — Alternatives, Tuples, Case class, Typed patterns

**Files:**
- Modify: `interpreter/frontends/scala/patterns.py`
- Modify: `tests/unit/test_scala_patterns.py`

**Reference:**
- Pattern ADT: `OrPattern`, `SequencePattern`, `ClassPattern`, `AsPattern` in `interpreter/frontends/common/patterns.py`
- Rust ClassPattern handling: `interpreter/frontends/rust/patterns.py` (`_parse_tuple_struct_pattern`)

- [ ] **Step 1: Write failing unit tests**

Test cases:
- Alternative `1 | 2 | 3` → `OrPattern((LiteralPattern(1), LiteralPattern(2), LiteralPattern(3)))`
- Tuple `(x, y)` → `SequencePattern((CapturePattern("x"), CapturePattern("y")))`
- Case class `Circle(r)` → `ClassPattern("Circle", positional=(CapturePattern("r"),), keyword=())`
- Case class `Point(x, y)` → `ClassPattern("Point", positional=(CapturePattern("x"), CapturePattern("y")), keyword=())`
- Typed `i: Int` → `AsPattern(ClassPattern("Int", positional=(), keyword=()), "i")`
- Stable identifier `Color.Red` → `ValuePattern(("Color", "Red"))` — split on `.`
- Nested `Some(Circle(r))` → `ClassPattern("Some", positional=(ClassPattern("Circle", positional=(CapturePattern("r"),), keyword=()),), keyword=())`

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_scala_patterns.py -v -k "alternative or tuple or case_class or typed"`
Expected: FAIL — `parse_scala_pattern` raises ValueError.

- [ ] **Step 3: Implement remaining pattern types**

Add to `interpreter/frontends/scala/patterns.py`:

```python
from interpreter.frontends.common.patterns import (
    AsPattern,
    ClassPattern,
    OrPattern,
    SequencePattern,
    ValuePattern,
    # ... plus existing imports
)

# In parse_scala_pattern, add cases:

    # Alternative pattern: 1 | 2 | 3
    if node_type == NT.ALTERNATIVE_PATTERN:
        alternatives = tuple(
            parse_scala_pattern(ctx, c)
            for c in node.children
            if c.is_named
        )
        return OrPattern(alternatives)

    # Tuple pattern: (a, b)
    if node_type == NT.TUPLE_PATTERN:
        elements = tuple(
            parse_scala_pattern(ctx, c)
            for c in node.children
            if c.is_named
        )
        return SequencePattern(elements)

    # Case class pattern: Circle(r), Point(x, y)
    if node_type == NT.CASE_CLASS_PATTERN:
        return _parse_case_class_pattern(ctx, node)

    # Typed pattern: i: Int
    if node_type == NT.TYPED_PATTERN:
        return _parse_typed_pattern(ctx, node)

    # Stable type identifier in pattern position: Color.Red
    if node_type == NT.STABLE_TYPE_IDENTIFIER:
        parts = tuple(text.split("."))
        return ValuePattern(parts)
```

Helper functions:

```python
def _parse_case_class_pattern(ctx: TreeSitterEmitContext, node) -> ClassPattern:
    """Parse case_class_pattern: Circle(r), Point(x, y)."""
    type_node = next(
        c for c in node.children
        if c.type in (NT.TYPE_IDENTIFIER, NT.IDENTIFIER, NT.STABLE_TYPE_IDENTIFIER)
    )
    class_name = ctx.node_text(type_node)
    positional = tuple(
        parse_scala_pattern(ctx, c)
        for c in node.children
        if c.is_named and c != type_node
    )
    return ClassPattern(class_name, positional=positional, keyword=())


def _parse_typed_pattern(ctx: TreeSitterEmitContext, node) -> AsPattern:
    """Parse typed_pattern: i: Int → AsPattern(ClassPattern('Int', (), ()), 'i').

    First named child is the variable identifier, type child provides the class name.
    """
    named = [c for c in node.children if c.is_named]
    # named[0] is the variable (identifier or wildcard)
    # named[1] is the type (type_identifier or generic_type)
    var_name = ctx.node_text(named[0])
    type_name = ctx.node_text(named[1])
    return AsPattern(
        ClassPattern(type_name, positional=(), keyword=()),
        var_name,
    )
```

**Typed pattern note:** `_: Int` (wildcard with type) should return just `ClassPattern("Int", (), ())` without the AsPattern wrapper since there's no variable to bind. Check if first named child is `wildcard` and handle accordingly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_scala_patterns.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/scala/patterns.py tests/unit/test_scala_patterns.py
git commit -m "feat(scala): parse_scala_pattern for alternatives, tuples, case class, typed patterns"
```

---

### Task 3: Refactor `lower_match_expr` to use Pattern ADT

**Files:**
- Modify: `interpreter/frontends/scala/expressions.py` (lines 191-246)
- Create: `tests/integration/test_scala_pattern_matching.py`

**Reference:**
- Rust `lower_match_expr`: `interpreter/frontends/rust/expressions.py:253-355` (exact template)
- Existing Scala match tests: `tests/integration/test_scala_frontend_execution.py` and `tests/integration/test_scala_p0_gaps_execution.py`

- [ ] **Step 1: Write integration tests**

Create `tests/integration/test_scala_pattern_matching.py`:

```python
"""Integration tests for Scala structural pattern matching — end-to-end execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_scala(source: str, max_steps: int = 500):
    """Run a Scala program and return (vm, frame.local_vars)."""
    vm = run(source, language=Language.SCALA, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)
```

Test cases (each a separate test method):

1. **Capture binding:** `val r = x match { case n => n + 1 }` — assert r == 6
2. **Alternative (regression):** `val r = x match { case 1 | 2 => 10; case _ => 0 }` — assert r == 10
3. **Guard clause:** `val r = x match { case n if n > 0 => 1; case _ => -1 }` — assert r == 1
4. **Guard no-match:** `val r = x match { case n if n > 0 => 1; case _ => -1 }` with x = -3 — assert r == -1
5. **Case class destructuring:** Define case class, match on it — may need xfail if case class isinstance not wired
6. **Typed pattern:** `val r = x match { case i: Int => i + 1; case _ => 0 }` — may need xfail if isinstance for primitives doesn't work
7. **Tuple destructuring:** `val r = pair match { case (a, b) => a + b }` — verify tuple elements extracted

Wrap programs in `object Main { ... }` or bare val definitions depending on what the Scala frontend expects. Check existing test patterns in `test_scala_frontend_execution.py` for the correct wrapper.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/integration/test_scala_pattern_matching.py -v`
Expected: FAIL for destructuring/guard tests.

- [ ] **Step 3: Run existing Scala match tests as baseline**

Run: `poetry run python -m pytest tests/integration/test_scala_frontend_execution.py tests/integration/test_scala_p0_gaps_execution.py -v -k "match or pattern"`
Expected: PASS. This is the regression baseline.

- [ ] **Step 4: Refactor `lower_match_expr`**

Replace lines 191-246 in `interpreter/frontends/scala/expressions.py`. Add imports at module level:

```python
from interpreter.frontends.common.patterns import (
    CapturePattern,
    WildcardPattern,
    compile_pattern_bindings,
    compile_pattern_test,
    _needs_pre_guard_bindings,
)
from interpreter.frontends.scala.patterns import parse_scala_pattern
```

New implementation (follows Rust pattern exactly):

```python
def lower_match_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Scala match expression using Pattern ADT."""
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")
    subject_reg = ctx.lower_expr(value_node)

    result_var = f"__match_result_{ctx.label_counter}"
    end_label = ctx.fresh_label("match_end")
    clauses = [c for c in body_node.children if c.type == NT.CASE_CLAUSE]

    for clause in clauses:
        _lower_case_clause(ctx, clause, subject_reg, result_var, end_label)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def _lower_case_clause(
    ctx: TreeSitterEmitContext, clause, subject_reg: str, result_var: str, end_label: str
) -> None:
    """Lower a single case clause: test pattern, bind, evaluate body, store result."""
    pattern_node = clause.child_by_field_name("pattern")
    body_node = clause.child_by_field_name("body")

    # Guard is a direct child of case_clause, NOT a field — iterate by type
    guard_node = next(
        (c for c in clause.children if c.type == NT.GUARD), None
    )

    pattern = parse_scala_pattern(ctx, pattern_node)

    is_irrefutable = (
        isinstance(pattern, (WildcardPattern, CapturePattern))
        and guard_node is None
    )

    if is_irrefutable:
        compile_pattern_bindings(ctx, subject_reg, pattern)
        body_reg = _lower_body_as_expr(ctx, body_node)
        ctx.emit(Opcode.DECL_VAR, operands=[result_var, body_reg])
        ctx.emit(Opcode.BRANCH, label=end_label)
        return

    test_reg = compile_pattern_test(ctx, subject_reg, pattern)

    if guard_node:
        if _needs_pre_guard_bindings(pattern):
            compile_pattern_bindings(ctx, subject_reg, pattern)
        # Guard node wraps the condition — extract the named child
        guard_condition = next(c for c in guard_node.children if c.is_named)
        guard_reg = ctx.lower_expr(guard_condition)
        final_test = ctx.fresh_reg()
        ctx.emit(
            Opcode.BINOP,
            result_reg=final_test,
            operands=["&&", test_reg, guard_reg],
        )
        test_reg = final_test

    arm_label = ctx.fresh_label("case_arm")
    next_label = ctx.fresh_label("case_next")
    ctx.emit(
        Opcode.BRANCH_IF,
        operands=[test_reg],
        label=f"{arm_label},{next_label}",
    )
    ctx.emit(Opcode.LABEL, label=arm_label)

    if not (guard_node and _needs_pre_guard_bindings(pattern)):
        compile_pattern_bindings(ctx, subject_reg, pattern)

    body_reg = _lower_body_as_expr(ctx, body_node)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, body_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=next_label)
```

**Critical API patterns (verified against existing Scala code):**
- Labels: `ctx.emit(Opcode.LABEL, label=...)` — same as current code at line 229/241/243
- Branches: `ctx.emit(Opcode.BRANCH, label=...)` — same as line 211/240
- Branch-if: `ctx.emit(Opcode.BRANCH_IF, operands=[cond_reg], label=f"{true},{false}")` — same as line 221-225
- Result var: `f"__match_result_{ctx.label_counter}"` — same as line 196
- Body: `_lower_body_as_expr(ctx, body_node)` — existing function at line 176

**Guard note:** The `guard` node type wraps the condition expression (it includes the `if` keyword). Extract the actual condition by getting the first named child of the guard node.

- [ ] **Step 5: Run ALL tests**

Run: `poetry run python -m pytest tests/integration/test_scala_frontend_execution.py tests/integration/test_scala_p0_gaps_execution.py tests/integration/test_scala_pattern_matching.py -v`
Expected: All existing + new tests PASS (some new tests may be xfailed).

- [ ] **Step 6: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: No regressions.

- [ ] **Step 7: Commit**

```bash
git add interpreter/frontends/scala/expressions.py tests/integration/test_scala_pattern_matching.py
git commit -m "feat(scala): refactor lower_match_expr to use Pattern ADT"
```

---

### Task 4: Clean up dead pattern lowering code and dispatch table

**Files:**
- Modify: `interpreter/frontends/scala/expressions.py`
- Modify: `interpreter/frontends/scala/frontend.py`

- [ ] **Step 1: Identify dead code**

Grep for references to each of these functions from ANY file other than their definitions:
- `lower_wildcard` (line 331)
- `lower_case_class_pattern` (line 549)
- `lower_typed_pattern` (line 583)
- `lower_guard` (line 591)
- `lower_tuple_pattern_expr` (line 599)
- `lower_infix_pattern` (line 623) — **keep if `ctx.lower_expr` may be called on infix_pattern nodes outside match context**
- `lower_case_clause_expr` (line 700)
- `lower_alternative_pattern` (line 708)

If any are only referenced from `frontend.py` dispatch table entries AND the match lowerer no longer calls `ctx.lower_expr` on pattern nodes, they are dead.

- [ ] **Step 2: Remove dead functions and dispatch entries**

Delete the dead functions from `expressions.py`. Remove corresponding entries from `_build_expr_dispatch()` in `frontend.py` (lines 94-104).

**Be careful:** If `lower_match_expr` still calls `ctx.lower_expr(body_node)` via `_lower_body_as_expr`, and body nodes could contain pattern-like node types, those dispatch entries may still be needed. Check whether `lower_infix_pattern`, `lower_case_clause_expr`, `lower_case_block` are reachable from body lowering.

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: No regressions.

- [ ] **Step 4: Format and commit**

Run: `poetry run python -m black interpreter/frontends/scala/expressions.py interpreter/frontends/scala/frontend.py`

```bash
git add interpreter/frontends/scala/expressions.py interpreter/frontends/scala/frontend.py
git commit -m "refactor(scala): remove dead pattern lowering code and dispatch entries"
```

---

### Task 5: ADR and final verification

**Files:**
- Modify: `docs/architectural-design-decisions.md`
- Modify: `README.md`

- [ ] **Step 1: Add ADR entry**

Read `docs/architectural-design-decisions.md`, find the latest ADR number (should be 117 from Rust), add ADR-118:

```markdown
## ADR-118: Scala Structural Pattern Matching (2026-03-21)

**Status:** Accepted
**Issue:** red-dragon-hgfq

Scala `match` now uses the common Pattern ADT via `compile_pattern_test`
and `compile_pattern_bindings`, replacing the hand-rolled expression-based
match lowering. Same architecture as Rust (ADR-117).

Supported patterns: literals, wildcards, captures, alternatives (or),
tuples, case class destructuring (`Circle(r)` via `ClassPattern`),
typed patterns (`i: Int` via `AsPattern(ClassPattern, name)`), and guards.

Infix patterns (`head :: tail`), as-patterns (`x @ pat`), and extractor
patterns are out of scope (red-dragon-hham, red-dragon-4s1a, red-dragon-loht).
```

- [ ] **Step 2: Update README**

Update Scala entry in README to mention pattern matching support.

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Note test count.

- [ ] **Step 4: Close beads issue**

Run: `bd close red-dragon-hgfq`

- [ ] **Step 5: Commit**

```bash
git add docs/architectural-design-decisions.md README.md
git commit -m "docs: ADR-118 for Scala structural pattern matching (red-dragon-hgfq)"
```
