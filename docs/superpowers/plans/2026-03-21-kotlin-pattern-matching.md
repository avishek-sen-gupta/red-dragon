# Kotlin `when` Pattern Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hook Kotlin `when` into the common Pattern ADT via `compile_pattern_test`/`compile_pattern_bindings`, replacing hand-rolled `==` comparisons.

**Architecture:** New `parse_kotlin_pattern()` maps when_condition inner nodes to the Pattern ADT. Refactored entry loop in `lower_when_expr` uses Pattern ADT test/bind per entry. Subject binding and block scope preserved unchanged.

**Tech Stack:** Python 3.13+, tree-sitter, pytest, existing Pattern ADT

**Spec:** `docs/superpowers/specs/2026-03-21-kotlin-pattern-matching-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `interpreter/frontends/kotlin/patterns.py` | Create | `parse_kotlin_pattern()` — when_condition content → Pattern ADT |
| `interpreter/frontends/kotlin/expressions.py` | Modify | Refactor entry loop in `lower_when_expr` (lines 358-416) |
| `tests/unit/test_kotlin_patterns.py` | Create | Unit tests for `parse_kotlin_pattern` |
| `tests/integration/test_kotlin_pattern_matching.py` | Create | Integration tests |

---

### Task 1: `parse_kotlin_pattern` — All pattern types

**Files:**
- Create: `tests/unit/test_kotlin_patterns.py`
- Create: `interpreter/frontends/kotlin/patterns.py`

Since Kotlin patterns are simpler than Rust/Scala (no case class destructuring, no tuples, no alternatives in scope), we can do all pattern types in one task.

- [ ] **Step 1: Write failing unit tests**

Test cases:
- Integer `42` → `LiteralPattern(42)`
- Real `3.14` → `LiteralPattern(3.14)`
- String `"hello"` → `LiteralPattern("hello")`
- Boolean `true` → `LiteralPattern(True)`
- Null `null` → `LiteralPattern(None)`
- Identifier `x` → `CapturePattern("x")`
- `is Int` (check_expression / type_test) → `ClassPattern("Int", positional=(), keyword=())` — write a diagnostic test first to verify tree-sitter structure for `is Type` in when conditions

To extract pattern nodes from Kotlin: parse a snippet with `when(x) { 42 -> 1; else -> 0 }`, find `when_entry` nodes, get `when_condition` child, then get the inner named child.

Reference `tests/unit/test_rust_patterns.py` and `tests/unit/test_scala_patterns.py` for the test helper setup pattern.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_kotlin_patterns.py -v`

- [ ] **Step 3: Implement `parse_kotlin_pattern`**

Create `interpreter/frontends/kotlin/patterns.py`:

```python
"""Parse tree-sitter Kotlin when-condition nodes into Pattern ADT."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    CapturePattern,
    ClassPattern,
    LiteralPattern,
    Pattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.kotlin.node_types import KotlinNodeType as KNT


def parse_kotlin_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
    """Map a tree-sitter Kotlin when-condition inner node to the Pattern ADT."""
    node_type = node.type
    text = ctx.node_text(node)

    if node_type in (KNT.INTEGER_LITERAL, KNT.LONG_LITERAL, KNT.HEX_LITERAL):
        return LiteralPattern(_parse_number(text))

    if node_type == KNT.REAL_LITERAL:
        return LiteralPattern(float(text.replace("_", "").rstrip("fFdD")))

    if node_type == KNT.STRING_LITERAL:
        content = text.strip('"')
        return LiteralPattern(content)

    if node_type == KNT.BOOLEAN_LITERAL:
        return LiteralPattern(text == "true")

    if node_type == KNT.NULL_LITERAL:
        return LiteralPattern(None)

    if node_type == KNT.SIMPLE_IDENTIFIER:
        return CapturePattern(text)

    # is Type check: check_expression or type_test
    if node_type in (KNT.CHECK_EXPRESSION, KNT.TYPE_TEST):
        return _parse_type_check(ctx, node)

    raise ValueError(f"Unsupported Kotlin pattern node type: {node_type!r} ({text!r})")


def _parse_type_check(ctx: TreeSitterEmitContext, node) -> ClassPattern:
    """Parse `is Type` as ClassPattern for isinstance check."""
    # Find the type node (user_type, type_identifier, or nullable_type)
    type_node = next(
        (c for c in node.children
         if c.type in (KNT.USER_TYPE, KNT.TYPE_IDENTIFIER, KNT.NULLABLE_TYPE)),
        None,
    )
    type_name = ctx.node_text(type_node) if type_node else ctx.node_text(node)
    return ClassPattern(type_name, positional=(), keyword=())


def _parse_number(text: str) -> int | float:
    """Parse numeric literal, stripping suffixes and _ separators."""
    cleaned = text.replace("_", "").rstrip("lLuU")
    if "." in cleaned:
        return float(cleaned)
    if cleaned.startswith("0x") or cleaned.startswith("0X"):
        return int(cleaned, 16)
    return int(cleaned, 0)
```

**Important:** Kotlin uses `simple_identifier` (not `identifier`) for variable names. Kotlin uses `real_literal` (not `float_literal`). Kotlin number literals may have suffixes (`L`, `u`, `f`, `d`) that need stripping.

**`is Type` handling:** Verify the exact tree-sitter structure by writing a diagnostic test first. The `is Int` pattern inside a `when_condition` may be a `check_expression` wrapping `is` keyword + `user_type`, or a `type_test` node. Extract the type name from whichever child represents the type.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_kotlin_patterns.py -v`

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/kotlin/patterns.py tests/unit/test_kotlin_patterns.py
git commit -m "feat(kotlin): add parse_kotlin_pattern for literals, captures, is-type checks"
```

---

### Task 2: Refactor `lower_when_expr` entry loop to use Pattern ADT

**Files:**
- Modify: `interpreter/frontends/kotlin/expressions.py` (lines 358-416)
- Create: `tests/integration/test_kotlin_pattern_matching.py`

- [ ] **Step 1: Write integration tests**

Create `tests/integration/test_kotlin_pattern_matching.py`:

```python
"""Integration tests for Kotlin when pattern matching — end-to-end execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_kotlin(source: str, max_steps: int = 500):
    """Run a Kotlin program and return frame.local_vars."""
    vm = run(source, language=Language.KOTLIN, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)
```

Test cases:
1. **Literal match:** `val x = 1; val r = when(x) { 1 -> 10; else -> 0 }` — assert r == 10
2. **Else fallthrough:** `val x = 5; val r = when(x) { 1 -> 10; else -> 0 }` — assert r == 0
3. **Capture binding:** `val x = 5; val r = when(x) { n -> n + 1 }` — assert r == 6 (xfail if captures in when conditions aren't standard Kotlin)
4. **`is Type` check:** `val x: Any = 5; val r = when(x) { is Int -> 1; else -> 0 }` — xfail with strict=False

Check existing Kotlin test patterns in `tests/integration/test_kotlin_p0_gaps_execution.py` for the correct program structure.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/integration/test_kotlin_pattern_matching.py -v`

- [ ] **Step 3: Refactor the entry loop in `lower_when_expr`**

Replace lines 358-416 in `expressions.py`. Add module-level imports:

```python
from interpreter.frontends.common.patterns import (
    CapturePattern,
    WildcardPattern,
    compile_pattern_bindings,
    compile_pattern_test,
)
from interpreter.frontends.kotlin.patterns import parse_kotlin_pattern
```

Replace the entry loop (lines 358-416) with:

```python
    entries = [c for c in node.children if c.type == KNT.WHEN_ENTRY]
    for entry in entries:
        _lower_when_entry(ctx, entry, val_reg, result_var, end_label)
```

New helper:

```python
def _lower_when_entry(
    ctx: TreeSitterEmitContext, entry, subject_reg: str, result_var: str, end_label: str
) -> None:
    """Lower a single when entry using Pattern ADT."""
    cond_node = next(
        (c for c in entry.children if c.type == KNT.WHEN_CONDITION), None
    )

    # Extract body
    body_node = next(
        (c for c in entry.children if c.type == KNT.CONTROL_STRUCTURE_BODY), None
    )
    body_children = [
        c for c in entry.children
        if c.type not in (KNT.WHEN_CONDITION, "->", ",")
        and c.is_named
        and c.type != KNT.CONTROL_STRUCTURE_BODY
    ]

    arm_label = ctx.fresh_label("when_arm")
    next_label = ctx.fresh_label("when_next")

    if cond_node:
        cond_inner = next((c for c in cond_node.children if c.is_named), None)
        pattern = parse_kotlin_pattern(ctx, cond_inner)

        is_irrefutable = isinstance(pattern, (WildcardPattern, CapturePattern))
        if is_irrefutable:
            compile_pattern_bindings(ctx, subject_reg, pattern)
            arm_result = _lower_when_body(ctx, body_node, body_children)
            ctx.emit(Opcode.DECL_VAR, operands=[result_var, arm_result])
            ctx.emit(Opcode.BRANCH, label=end_label)
            return

        test_reg = compile_pattern_test(ctx, subject_reg, pattern)
        ctx.emit(
            Opcode.BRANCH_IF,
            operands=[test_reg],
            label=f"{arm_label},{next_label}",
        )
        ctx.emit(Opcode.LABEL, label=arm_label)
        compile_pattern_bindings(ctx, subject_reg, pattern)
    else:
        # else branch — no condition, unconditional
        ctx.emit(Opcode.BRANCH, label=arm_label)
        ctx.emit(Opcode.LABEL, label=arm_label)

    arm_result = _lower_when_body(ctx, body_node, body_children)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, arm_result])
    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=next_label)


def _lower_when_body(ctx, body_node, body_children):
    """Lower a when entry body, returning the result register."""
    if body_node:
        return _lower_control_body(ctx, body_node)
    if body_children:
        return ctx.lower_expr(body_children[0])
    arm_result = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=arm_result, operands=[ctx.constants.none_literal])
    return arm_result
```

**API patterns (verified against existing code lines 376-416):**
- Labels: `ctx.emit(Opcode.LABEL, label=...)` — line 402
- Branches: `ctx.emit(Opcode.BRANCH, label=...)` — lines 397/415
- Branch-if: `ctx.emit(Opcode.BRANCH_IF, operands=[eq_reg], label=f"{arm_label},{next_label}")` — lines 390-394
- Result: `ctx.emit(Opcode.DECL_VAR, operands=[result_var, arm_result])` — line 414
- Body: `_lower_control_body(ctx, body_node)` — line 404

**Preserve unchanged:** Lines 308-357 (subject binding, block scope, subject extraction).

- [ ] **Step 4: Run ALL tests**

Run: `poetry run python -m pytest tests/integration/test_kotlin_p0_gaps_execution.py tests/integration/test_kotlin_pattern_matching.py -v`

- [ ] **Step 5: Run full suite**

Run: `poetry run python -m pytest --tb=short -q`

- [ ] **Step 6: Commit**

```bash
git add interpreter/frontends/kotlin/expressions.py tests/integration/test_kotlin_pattern_matching.py
git commit -m "feat(kotlin): refactor lower_when_expr to use Pattern ADT"
```

---

### Task 3: ADR and final verification

**Files:**
- Modify: `docs/architectural-design-decisions.md`
- Modify: `README.md`

- [ ] **Step 1: Add ADR-119**

```markdown
## ADR-119: Kotlin `when` Pattern Matching (2026-03-21)

**Status:** Accepted
**Issue:** red-dragon-y0df

Kotlin `when` expression now uses the common Pattern ADT via
`compile_pattern_test` and `compile_pattern_bindings`, replacing
hand-rolled `==` comparisons. Same architecture as Rust (ADR-117)
and Scala (ADR-118).

Supported: literals, `else` (wildcard), `is Type` (ClassPattern
isinstance), captures. Subject binding (`when(val x = expr)`) preserved.

Range patterns (`in 1..10`), destructuring, and smart casts are out
of scope (red-dragon-1qcf, red-dragon-bijo, red-dragon-tq0m).
```

- [ ] **Step 2: Update README, close issue, run tests, commit**

Run: `bd close red-dragon-y0df`

```bash
git commit -m "docs: ADR-119 for Kotlin when pattern matching (red-dragon-y0df)"
```
