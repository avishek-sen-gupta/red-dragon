# Ruby `case/in` Pattern Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Ruby 3.0+ `case/in` pattern matching via Pattern ADT + unified match framework.

**Architecture:** New `parse_ruby_pattern()` + `lower_case_match` using `lower_match_as_expr` from `common/match_expr.py`. Keep existing `case/when` unchanged.

**Tech Stack:** Python 3.13+, tree-sitter, pytest, Pattern ADT, unified match framework

**Spec:** `docs/superpowers/specs/2026-03-21-ruby-pattern-matching-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `interpreter/frontends/ruby/patterns.py` | Create | `parse_ruby_pattern()` |
| `interpreter/frontends/ruby/control_flow.py` | Modify | Add `lower_case_match` |
| `interpreter/frontends/ruby/frontend.py` | Modify | Add `CASE_MATCH` dispatch |
| `interpreter/frontends/ruby/node_types.py` | Modify | Add missing node type constants |
| `tests/unit/test_ruby_patterns.py` | Create | Unit tests |
| `tests/integration/test_ruby_pattern_matching.py` | Create | Integration tests |

---

### Task 1: `parse_ruby_pattern` — All in-scope pattern types

**Files:**
- Create: `tests/unit/test_ruby_patterns.py`
- Create: `interpreter/frontends/ruby/patterns.py`

- [ ] **Step 1: Write diagnostic test to inspect tree-sitter structure**

Before writing the parser, parse a Ruby `case/in` snippet and inspect the tree structure. Key things to verify:
- How does `case x; in 42 then 1; in _ then 0; end` parse?
- What node type is `_` (wildcard) in Ruby patterns?
- What does `in [a, b]` look like (array_pattern)?
- What does `in 1 | 2` look like (alternative_pattern)?
- How are `in_clause` children structured? (pattern position, body position)

Use tree-sitter Ruby parser: `tree_sitter_language_pack.get_parser("ruby")`.

- [ ] **Step 2: Write failing unit tests**

Test cases (verify node types during diagnostic):
- Integer `42` → `LiteralPattern(42)`
- String `"hello"` → `LiteralPattern("hello")`
- Symbol `:foo` → `LiteralPattern(":foo")` or similar
- Wildcard `_` → `WildcardPattern()`
- Identifier `x` → `CapturePattern("x")`
- Alternative `1 | 2 | 3` → `OrPattern(...)`
- Array `[a, b]` → `SequencePattern((CapturePattern("a"), CapturePattern("b")))`

- [ ] **Step 3: Implement `parse_ruby_pattern`**

Create `interpreter/frontends/ruby/patterns.py`. Follow Rust/Scala/Kotlin pattern. Key Ruby-specific details:
- Ruby uses `integer` (not `integer_literal`) — verify node type names
- Ruby symbols (`:foo`) may be a separate node type
- Array patterns use `array_pattern` node type
- Alternative patterns use `alternative_pattern`
- Check if node type constants exist in `node_types.py` — add any missing ones

- [ ] **Step 4: Run tests, format, commit**

```bash
git commit -m "feat(ruby): add parse_ruby_pattern for case/in patterns"
```

---

### Task 2: Add `lower_case_match` using unified framework

**Files:**
- Modify: `interpreter/frontends/ruby/control_flow.py`
- Modify: `interpreter/frontends/ruby/frontend.py`
- Modify: `interpreter/frontends/ruby/node_types.py` (if `CASE_MATCH` not present)
- Create: `tests/integration/test_ruby_pattern_matching.py`

- [ ] **Step 1: Write integration tests**

```python
"""Integration tests for Ruby case/in pattern matching."""

from __future__ import annotations
from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals

def _run_ruby(source: str, max_steps: int = 500):
    vm = run(source, language=Language.RUBY, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)
```

Test cases:
1. Literal match: `x = 2; r = case x; in 1 then 10; in 2 then 20; else 0; end`
2. Wildcard fallback: `x = 99; r = case x; in 1 then 10; else 0; end`
3. Alternative: `x = 3; r = case x; in 1 | 2 | 3 then 10; else 0; end`
4. Array destructuring: `arr = [1, 2]; r = case arr; in [a, b] then a + b; else 0; end` — xfail if arrays don't work

- [ ] **Step 2: Implement `lower_case_match` using framework**

Add to `control_flow.py`:

```python
from interpreter.frontends.common.match_expr import MatchArmSpec, lower_match_as_expr
from interpreter.frontends.ruby.patterns import parse_ruby_pattern

def lower_case_match(ctx, node) -> str:
    """Lower Ruby case/in using Pattern ADT + unified match framework."""
    # Subject is the first named child after 'case' keyword
    # in_clause children contain patterns + bodies
    # else clause is separate
    ...
    return lower_match_as_expr(ctx, subject_reg, node, _RUBY_CASE_MATCH_SPEC)
```

Key: Tree-sitter structure for `case_match` needs careful extraction:
- Subject: first named child (after `case` keyword)
- Arms: `in_clause` children
- Each `in_clause`: pattern is first named child, body is `then` clause or remaining children
- `else` clause: separate node, treated as wildcard arm

- [ ] **Step 3: Add dispatch entries**

In `frontend.py`, add `CASE_MATCH` to both expr and stmt dispatch tables. Add `CASE_MATCH` constant to `node_types.py` if not present.

- [ ] **Step 4: Run tests, verify existing case/when still works**

Run: `poetry run python -m pytest tests/integration/ -k "ruby" -v`
Run: `poetry run python -m pytest --tb=short -q`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(ruby): add case/in pattern matching via unified match framework"
```

---

### Task 3: Add Ruby to cross-language Rosetta test + ADR

**Files:**
- Modify: `tests/integration/test_rosetta_structural_pattern_matching.py`
- Modify: `docs/architectural-design-decisions.md`

- [ ] **Step 1: Add Ruby to Rosetta test**

Add `test_ruby` to `TestRosettaPatternMatchingClassifyNumber`:
```ruby
x = 2
result = case x
  in 1 then "one"
  in 2 then "small"
  in 3 then "small"
  else "other"
end
```
Assert result == "small". Ruby doesn't have or-patterns for `2 | 3` in the simple case — use separate arms.

- [ ] **Step 2: Add ADR-121**

- [ ] **Step 3: Close issues, run full suite, commit**

Run: `bd close red-dragon-6n0u`

```bash
git commit -m "docs: ADR-121 for Ruby case/in pattern matching + Rosetta test"
```
