# Unified Match Expression Lowering Framework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract duplicated match lowering from 4 languages into `common/match_expr.py`.

**Architecture:** `MatchArmSpec` dataclass with 4 callbacks + `lower_match_as_expr` entry point. Each language provides callbacks and a thin wrapper.

**Tech Stack:** Python 3.13+, existing Pattern ADT infrastructure

**Spec:** `docs/superpowers/specs/2026-03-21-match-expr-framework-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `interpreter/frontends/common/match_expr.py` | Create | `MatchArmSpec` + `lower_match_as_expr` + `_lower_arm` |
| `interpreter/frontends/rust/expressions.py` | Modify | Replace `_lower_match_arm` with callbacks + `lower_match_as_expr` |
| `interpreter/frontends/scala/expressions.py` | Modify | Replace `_lower_case_clause` with callbacks + `lower_match_as_expr` |
| `interpreter/frontends/kotlin/expressions.py` | Modify | Replace `_lower_when_entry` with callbacks + `lower_match_as_expr` |
| `interpreter/frontends/csharp/control_flow.py` | Modify | Replace inline switch_expr logic with callbacks + `lower_match_as_expr` |

---

### Task 1: Create `common/match_expr.py` with the framework

**Files:**
- Create: `interpreter/frontends/common/match_expr.py`

- [ ] **Step 1: Create the framework module**

This is a pure extraction — the arm-lowering logic comes directly from the existing Rust/Scala implementations (they're identical).

```python
"""Unified match expression lowering framework.

Provides lower_match_as_expr() which emits IR for expression-style match
statements that return a value. Language frontends provide callbacks via
MatchArmSpec to handle language-specific tree-sitter node extraction.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from interpreter.frontends.common.patterns import (
    CapturePattern,
    WildcardPattern,
    compile_pattern_bindings,
    compile_pattern_test,
    _needs_pre_guard_bindings,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.ir import Opcode


@dataclass(frozen=True)
class MatchArmSpec:
    """Language-specific callbacks for decomposing match/switch arms.

    extract_arms: (body_node) -> list of arm nodes
    pattern_of:   (ctx, arm) -> Pattern ADT
    guard_of:     (ctx, arm) -> guard expression node or None
    body_of:      (ctx, arm) -> result register (lowers body as expression)
    """
    extract_arms: Callable[[object], list[object]]
    pattern_of: Callable[[TreeSitterEmitContext, object], "Pattern"]
    guard_of: Callable[[TreeSitterEmitContext, object], object | None]
    body_of: Callable[[TreeSitterEmitContext, object], str]


def lower_match_as_expr(
    ctx: TreeSitterEmitContext,
    subject_reg: str,
    body_node: object,
    spec: MatchArmSpec,
) -> str:
    """Emit IR for expression-style match. Returns result register."""
    result_var = f"__match_result_{ctx.label_counter}"
    end_label = ctx.fresh_label("match_end")

    for arm in spec.extract_arms(body_node):
        _lower_arm(ctx, arm, subject_reg, result_var, end_label, spec)

    ctx.emit(Opcode.LABEL, label=end_label)
    reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=reg, operands=[result_var])
    return reg


def _lower_arm(
    ctx: TreeSitterEmitContext,
    arm: object,
    subject_reg: str,
    result_var: str,
    end_label: str,
    spec: MatchArmSpec,
) -> None:
    """Lower a single arm: test pattern, bind, evaluate body, store result."""
    pattern = spec.pattern_of(ctx, arm)
    guard_node = spec.guard_of(ctx, arm)

    is_irrefutable = (
        isinstance(pattern, (WildcardPattern, CapturePattern))
        and guard_node is None
    )

    if is_irrefutable:
        compile_pattern_bindings(ctx, subject_reg, pattern)
        body_reg = spec.body_of(ctx, arm)
        ctx.emit(Opcode.DECL_VAR, operands=[result_var, body_reg])
        ctx.emit(Opcode.BRANCH, label=end_label)
        return

    test_reg = compile_pattern_test(ctx, subject_reg, pattern)

    if guard_node:
        if _needs_pre_guard_bindings(pattern):
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

    if not (guard_node and _needs_pre_guard_bindings(pattern)):
        compile_pattern_bindings(ctx, subject_reg, pattern)

    body_reg = spec.body_of(ctx, arm)
    ctx.emit(Opcode.DECL_VAR, operands=[result_var, body_reg])
    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=next_label)
```

- [ ] **Step 2: Run full test suite to verify module imports correctly**

Run: `poetry run python -m pytest --tb=short -q`
Expected: No change (module not yet wired).

- [ ] **Step 3: Commit**

```bash
git add interpreter/frontends/common/match_expr.py
git commit -m "refactor: add unified match expression lowering framework (match_expr.py)"
```

---

### Task 2: Migrate Rust to use the framework

**Files:**
- Modify: `interpreter/frontends/rust/expressions.py`

- [ ] **Step 1: Replace `lower_match_expr` and `_lower_match_arm`**

Replace the current `lower_match_expr` (line 308-324) and `_lower_match_arm` (line 327-388) with:

```python
from interpreter.frontends.common.match_expr import MatchArmSpec, lower_match_as_expr


def _rust_pattern_of(ctx: TreeSitterEmitContext, arm) -> "Pattern":
    match_pattern_node = next(
        c for c in arm.children if c.type == RustNodeType.MATCH_PATTERN
    )
    named_children = [c for c in match_pattern_node.children if c.is_named]
    pattern_node = named_children[0] if named_children else match_pattern_node
    return parse_rust_pattern(ctx, pattern_node)


def _rust_guard_of(ctx: TreeSitterEmitContext, arm):
    match_pattern_node = next(
        c for c in arm.children if c.type == RustNodeType.MATCH_PATTERN
    )
    named_children = [c for c in match_pattern_node.children if c.is_named]
    return named_children[1] if len(named_children) > 1 else None


def _rust_body_of(ctx: TreeSitterEmitContext, arm) -> str:
    body_expr = _extract_arm_body(arm)
    return ctx.lower_expr(body_expr)


_RUST_MATCH_SPEC = MatchArmSpec(
    extract_arms=lambda body: [
        c for c in body.children if c.type == RustNodeType.MATCH_ARM
    ],
    pattern_of=_rust_pattern_of,
    guard_of=_rust_guard_of,
    body_of=_rust_body_of,
)


def lower_match_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower Rust match expression using unified framework."""
    value_node = node.child_by_field_name("value")
    body_node = node.child_by_field_name("body")
    subject_reg = ctx.lower_expr(value_node)
    return lower_match_as_expr(ctx, subject_reg, body_node, _RUST_MATCH_SPEC)
```

Keep `_extract_arm_body` unchanged — it's used by `_rust_body_of`.

Delete `_lower_match_arm` entirely. Remove imports that were only used by `_lower_match_arm` (compile_pattern_test, compile_pattern_bindings, _needs_pre_guard_bindings, WildcardPattern, CapturePattern) — they're now in `match_expr.py`.

- [ ] **Step 2: Run Rust tests**

Run: `poetry run python -m pytest tests/integration/test_rust_or_pattern_execution.py tests/integration/test_rust_pattern_matching.py tests/unit/test_rust_frontend.py -v`
Expected: All pass.

- [ ] **Step 3: Run full suite**

Run: `poetry run python -m pytest --tb=short -q`

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(rust): migrate lower_match_expr to unified match framework"
```

---

### Task 3: Migrate Scala to use the framework

**Files:**
- Modify: `interpreter/frontends/scala/expressions.py`

- [ ] **Step 1: Replace `lower_match_expr` and `_lower_case_clause`**

Same pattern as Rust. Key Scala differences:
- Pattern via `clause.child_by_field_name("pattern")`
- Guard is child of type `NT.GUARD`, then unwrap inner named child
- Body via `_lower_body_as_expr(ctx, clause.child_by_field_name("body"))`

- [ ] **Step 2: Run Scala tests, then full suite**
- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(scala): migrate lower_match_expr to unified match framework"
```

---

### Task 4: Migrate Kotlin to use the framework

**Files:**
- Modify: `interpreter/frontends/kotlin/expressions.py`

- [ ] **Step 1: Replace the subject-based entry loop with framework call**

The subjectless `when` path stays unchanged. Only the `has_subject=True` path uses the framework. Replace `_lower_when_entry` with callbacks.

Key: `guard_of` always returns `None` for Kotlin. `body_of` calls `_lower_when_body`. Else entries (no `when_condition`) should return `WildcardPattern()` from `pattern_of`.

- [ ] **Step 2: Run Kotlin tests, then full suite**
- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(kotlin): migrate lower_when_expr to unified match framework"
```

---

### Task 5: Migrate C# switch expression to use the framework

**Files:**
- Modify: `interpreter/frontends/csharp/control_flow.py`

- [ ] **Step 1: Replace `lower_switch_expr` inline logic with framework call**

C# is the simplest: no guards, pattern is first named child, body is last named child.

**Important:** Only migrate `lower_switch_expr` (expression form). Leave `lower_switch` (statement form with `break_target_stack`) unchanged.

- [ ] **Step 2: Run C# tests, then full suite**
- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(csharp): migrate lower_switch_expr to unified match framework"
```

---

### Task 6: Final cleanup and ADR

**Files:**
- Modify: `docs/architectural-design-decisions.md`

- [ ] **Step 1: Add ADR-120**
- [ ] **Step 2: Run full suite, format, close issue**

Run: `bd close red-dragon-lgsk`

```bash
git commit -m "docs: ADR-120 for unified match expression lowering framework"
```
