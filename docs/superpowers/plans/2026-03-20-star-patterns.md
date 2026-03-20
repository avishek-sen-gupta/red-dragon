# Star Patterns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `*rest` star/splat patterns to sequence matching in Python list and tuple patterns.

**Architecture:** Add `StarPattern(name)` to the Pattern ADT. When a `SequencePattern` contains a `StarPattern`, the compiler switches from exact-length (`==`) to minimum-length (`>=`) matching. Fixed elements before/after the star use literal/computed indices. The star capture uses the existing `slice` builtin.

**Tech Stack:** Python 3.13+, tree-sitter, frozen dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-03-20-star-patterns-design.md`

---

## File Map

| File | Role | Action |
|---|---|---|
| `interpreter/frontends/common/patterns.py` | Add `StarPattern`, update `compile_pattern_test` and `compile_pattern_bindings` for star-in-sequence | **Modify** |
| `interpreter/frontends/python/patterns.py` | Handle `splat_pattern` in `parse_pattern` | **Modify** |
| `tests/unit/test_pattern_compiler.py` | Unit tests for star pattern IR emission | **Modify** |
| `tests/integration/test_python_pattern_matching.py` | Integration tests + remove existing xfail | **Modify** |

---

### Task 1: StarPattern ADT + standalone compile_pattern_test (TDD)

**Files:**
- Modify: `interpreter/frontends/common/patterns.py`
- Modify: `tests/unit/test_pattern_compiler.py`

- [ ] **Step 1: Write failing unit test**

Add to `tests/unit/test_pattern_compiler.py`:

```python
from interpreter.frontends.common.patterns import StarPattern


class TestStarPattern:
    def test_star_pattern_standalone_returns_true(self):
        """StarPattern by itself always matches (no test IR needed)."""
        ctx = _make_ctx()
        pattern = StarPattern(name="rest")
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        binops = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert len(binops) == 0, f"star should emit no BINOP, got {binops}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py::TestStarPattern::test_star_pattern_standalone_returns_true -v`
Expected: FAIL — `ImportError` or `NotImplementedError`

- [ ] **Step 3: Add StarPattern to ADT + handle in compile_pattern_test**

In `interpreter/frontends/common/patterns.py`, add after `AsPattern` (around line 75):

```python
@dataclass(frozen=True)
class StarPattern(Pattern):
    """Captures remaining elements in a sequence pattern. Python's ``*rest``."""
    name: str
```

In `compile_pattern_test`, add before the `case _:` fallthrough:

```python
case StarPattern():
    return _const_true(ctx)
```

In `compile_pattern_bindings`, add before the `case _:` fallthrough:

```python
case StarPattern(name=name):
    if name != "_":
        ctx.emit(Opcode.STORE_VAR, operands=[name, subject_reg])
```

Note: The standalone `compile_pattern_bindings` for `StarPattern` just does a simple `STORE_VAR` of the subject. The actual slice logic lives in the `SequencePattern` handler (Task 2), which calls `compile_pattern_bindings` with the sliced sub-array as the subject.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/common/patterns.py tests/unit/test_pattern_compiler.py
git commit -m "feat: add StarPattern to Pattern ADT (TDD)"
```

---

### Task 2: SequencePattern with star — test IR (TDD)

**Files:**
- Modify: `interpreter/frontends/common/patterns.py`
- Modify: `tests/unit/test_pattern_compiler.py`

- [ ] **Step 1: Write failing unit tests**

Add to `TestStarPattern` in `tests/unit/test_pattern_compiler.py`:

```python
    def test_star_pattern_emits_gte_length_check(self):
        """SequencePattern with star uses >= instead of == for length."""
        ctx = _make_ctx()
        pattern = SequencePattern(elements=(LiteralPattern(1), StarPattern("rest")))
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        # Should have BINOP >= (not ==) for length check
        binops = [i for i in instrs if i.opcode == Opcode.BINOP]
        gte_ops = [b for b in binops if b.operands[0] == ">="]
        assert len(gte_ops) >= 1, f"expected >= length check, got {[b.operands[0] for b in binops]}"

    def test_star_pattern_no_test_for_star_element(self):
        """The star element itself should not produce any equality test."""
        ctx = _make_ctx()
        pattern = SequencePattern(elements=(LiteralPattern(1), StarPattern("rest")))
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        eq_binops = [i for i in instrs if i.opcode == Opcode.BINOP and i.operands[0] == "=="]
        # Only 1 equality check: for LiteralPattern(1). Star should produce none.
        assert len(eq_binops) == 1, f"expected 1 equality check (literal only), got {len(eq_binops)}"

    def test_star_at_beginning_computes_tail_indices(self):
        """[*head, last] — last element uses computed index from length."""
        ctx = _make_ctx()
        pattern = SequencePattern(elements=(StarPattern("head"), LiteralPattern(99)))
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        # Should compute index for 'last' via BINOP - (len, 1)
        sub_binops = [i for i in instrs if i.opcode == Opcode.BINOP and i.operands[0] == "-"]
        assert len(sub_binops) >= 1, f"expected BINOP - for tail index, got {[b.operands for b in instrs if b.opcode == Opcode.BINOP]}"

    def test_star_in_middle(self):
        """[a, *mid, z] — elements before and after star, with star in between."""
        ctx = _make_ctx()
        pattern = SequencePattern(elements=(
            CapturePattern("a"), StarPattern("mid"), CapturePattern("z")
        ))
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        gte_ops = [b for b in instrs if b.opcode == Opcode.BINOP and b.operands[0] == ">="]
        assert len(gte_ops) >= 1, "expected >= length check for star-in-middle"
        # Fixed count is 2 (a and z), so >= 2
        const_2 = [c for c in instrs if c.opcode == Opcode.CONST and c.operands == ["2"]]
        assert len(const_2) >= 1, "expected CONST 2 for fixed element count"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py::TestStarPattern -v`
Expected: FAIL — existing SequencePattern handler uses `==` not `>=`

- [ ] **Step 3: Implement star-aware SequencePattern in compile_pattern_test**

In `interpreter/frontends/common/patterns.py`, add two helpers to detect and find the star:

```python
def _has_star(elems: tuple[Pattern, ...]) -> bool:
    """Return True if elements contain a StarPattern."""
    return any(isinstance(e, StarPattern) for e in elems)


def _star_index(elems: tuple[Pattern, ...]) -> int:
    """Return index of StarPattern in elements. Only call when _has_star is True."""
    return next(i for i, e in enumerate(elems) if isinstance(e, StarPattern))
```

Add a helper for computing after-star indices:

```python
def _compile_after_star_element_test(
    ctx: TreeSitterEmitContext,
    subject_reg: str,
    len_reg: str,
    after_count: int,
    after_offset: int,
    elem_pat: Pattern,
) -> str:
    """Load an after-star element by computing index = len - (after_count - after_offset)."""
    offset_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=offset_reg, operands=[str(after_count - after_offset)])
    idx_reg = _emit_binop(ctx, "-", len_reg, offset_reg)
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[subject_reg, idx_reg])
    return compile_pattern_test(ctx, elem_reg, elem_pat)
```

Replace the `SequencePattern` case in `compile_pattern_test` with:

```python
case SequencePattern(elements=elems):
    has_star = _has_star(elems)
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", subject_reg])

    if not has_star:
        # No star — exact length match (existing logic)
        expected_len_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=expected_len_reg, operands=[str(len(elems))])
        len_ok_reg = _emit_binop(ctx, "==", len_reg, expected_len_reg)
        sub_results = [len_ok_reg] + [
            _compile_indexed_element(ctx, subject_reg, i, elem_pat)
            for i, elem_pat in enumerate(elems)
        ]
    else:
        # Star present — minimum length match
        star_idx = _star_index(elems)
        fixed_count = len(elems) - 1
        min_len_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CONST, result_reg=min_len_reg, operands=[str(fixed_count)])
        len_ok_reg = _emit_binop(ctx, ">=", len_reg, min_len_reg)
        sub_results = [len_ok_reg]
        # Before star: literal indices
        sub_results.extend(
            _compile_indexed_element(ctx, subject_reg, i, elem_pat)
            for i, elem_pat in enumerate(elems[:star_idx])
        )
        # After star: computed indices
        after_count = len(elems) - star_idx - 1
        sub_results.extend(
            _compile_after_star_element_test(
                ctx, subject_reg, len_reg, after_count, k, elem_pat
            )
            for k, elem_pat in enumerate(elems[star_idx + 1:])
        )
        # StarPattern itself: no test (skipped)
    return _and_all(ctx, sub_results)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/common/patterns.py tests/unit/test_pattern_compiler.py
git commit -m "feat: star-aware SequencePattern test IR with >= length check (TDD)"
```

---

### Task 3: SequencePattern with star — bind IR (TDD)

**Files:**
- Modify: `interpreter/frontends/common/patterns.py`
- Modify: `tests/unit/test_pattern_compiler.py`

- [ ] **Step 1: Write failing unit tests**

Add to `TestStarPattern`:

```python
    def test_star_pattern_binds_via_slice(self):
        """Star binding emits CALL_FUNCTION slice + STORE_VAR."""
        ctx = _make_ctx()
        pattern = SequencePattern(elements=(CapturePattern("a"), StarPattern("rest")))
        compile_pattern_bindings(ctx, "%subj", pattern)
        instrs = ctx.instructions
        calls = [i for i in instrs if i.opcode == Opcode.CALL_FUNCTION]
        slice_calls = [c for c in calls if "slice" in str(c.operands)]
        assert len(slice_calls) >= 1, f"expected slice call, got {calls}"
        stores = [i for i in instrs if i.opcode == Opcode.STORE_VAR]
        store_names = [s.operands[0] for s in stores]
        assert "a" in store_names, "expected binding for 'a'"
        assert "rest" in store_names, "expected binding for 'rest'"

    def test_wildcard_star_skips_slice(self):
        """StarPattern(name='_') should emit no slice or STORE_VAR."""
        ctx = _make_ctx()
        pattern = SequencePattern(elements=(CapturePattern("a"), StarPattern("_")))
        compile_pattern_bindings(ctx, "%subj", pattern)
        instrs = ctx.instructions
        calls = [i for i in instrs if i.opcode == Opcode.CALL_FUNCTION]
        slice_calls = [c for c in calls if "slice" in str(c.operands)]
        assert len(slice_calls) == 0, f"wildcard star should skip slice, got {slice_calls}"
        stores = [i for i in instrs if i.opcode == Opcode.STORE_VAR]
        store_names = [s.operands[0] for s in stores]
        assert "_" not in store_names, "wildcard star should not emit STORE_VAR _"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py::TestStarPattern::test_star_pattern_binds_via_slice tests/unit/test_pattern_compiler.py::TestStarPattern::test_wildcard_star_skips_slice -v`
Expected: FAIL

- [ ] **Step 3: Implement star-aware SequencePattern bindings**

Add a helper:

```python
def _compile_after_star_element_binding(
    ctx: TreeSitterEmitContext,
    subject_reg: str,
    len_reg: str,
    after_count: int,
    after_offset: int,
    elem_pat: Pattern,
) -> None:
    """Bind an after-star element by computing index = len - (after_count - after_offset)."""
    offset_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=offset_reg, operands=[str(after_count - after_offset)])
    idx_reg = _emit_binop(ctx, "-", len_reg, offset_reg)
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[subject_reg, idx_reg])
    compile_pattern_bindings(ctx, elem_reg, elem_pat)
```

Replace the `SequencePattern` case in `compile_pattern_bindings` with:

```python
case SequencePattern(elements=elems):
    if not _has_star(elems):
        # No star — bind each element by literal index
        for i, elem_pat in enumerate(elems):
            elem_reg = ctx.fresh_reg()
            ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[subject_reg, str(i)])
            compile_pattern_bindings(ctx, elem_reg, elem_pat)
    else:
        # Star present — need length for after-star index computation
        star_idx = _star_index(elems)
        len_reg = ctx.fresh_reg()
        ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", subject_reg])
        after_count = len(elems) - star_idx - 1
        # Before star: literal indices
        for i, elem_pat in enumerate(elems[:star_idx]):
            elem_reg = ctx.fresh_reg()
            ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[subject_reg, str(i)])
            compile_pattern_bindings(ctx, elem_reg, elem_pat)
        # Star element: slice(subject, star_idx, len - after_count)
        star_pat = elems[star_idx]
        if isinstance(star_pat, StarPattern) and star_pat.name != "_":
            start_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=start_reg, operands=[str(star_idx)])
            after_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=after_reg, operands=[str(after_count)])
            stop_reg = _emit_binop(ctx, "-", len_reg, after_reg)
            slice_reg = ctx.fresh_reg()
            ctx.emit(
                Opcode.CALL_FUNCTION,
                result_reg=slice_reg,
                operands=["slice", subject_reg, start_reg, stop_reg],
            )
            ctx.emit(Opcode.STORE_VAR, operands=[star_pat.name, slice_reg])
        # After star: computed indices
        for k, elem_pat in enumerate(elems[star_idx + 1:]):
            _compile_after_star_element_binding(
                ctx, subject_reg, len_reg, after_count, k, elem_pat
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/common/patterns.py tests/unit/test_pattern_compiler.py
git commit -m "feat: star-aware SequencePattern bind IR with slice (TDD)"
```

---

### Task 4: Python parse_pattern — handle splat_pattern

**Files:**
- Modify: `interpreter/frontends/python/patterns.py`

- [ ] **Step 1: Add StarPattern import and splat_pattern handling**

In `interpreter/frontends/python/patterns.py`, add `StarPattern` to the import:

```python
from interpreter.frontends.common.patterns import (
    ...
    StarPattern,
)
```

Add before the tuple pattern block (around line 75), since `splat_pattern` nodes appear as children of `case_pattern` within list/tuple patterns:

```python
    # Splat/star pattern
    if node_type == PythonNodeType.SPLAT_PATTERN:
        named = [c for c in node.children if c.is_named]
        name = ctx.node_text(named[0]) if named else "_"
        return StarPattern(name=name)
```

- [ ] **Step 2: Write unit test for parse_pattern with splat_pattern**

Create a quick verification script at `/tmp/test_parse_star.py`:

```python
"""Verify parse_pattern handles splat_pattern → StarPattern."""
from interpreter.parser import TreeSitterParserFactory
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.frontends.common.patterns import StarPattern, SequencePattern

frontend = get_frontend(Language.PYTHON)
# Parse a program with a star pattern to get the tree-sitter AST
factory = TreeSitterParserFactory()
parser = factory.get_parser(Language.PYTHON)
tree = parser.parse(b"match x:\n    case [a, *rest]:\n        pass\n")

# Find the splat_pattern node
def find_node(node, type_name):
    if node.type == type_name:
        return node
    for child in node.children:
        result = find_node(child, type_name)
        if result:
            return result
    return None

list_pattern = find_node(tree.root_node, "list_pattern")
assert list_pattern is not None, "Expected list_pattern in AST"

# Use parse_pattern on the list_pattern's parent case_pattern
case_pattern = find_node(tree.root_node, "case_pattern")
from interpreter.frontends.python.patterns import parse_pattern
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontend_observer import NullFrontendObserver

ctx = TreeSitterEmitContext(
    source=b"match x:\n    case [a, *rest]:\n        pass\n",
    language=Language.PYTHON,
    observer=NullFrontendObserver(),
    constants=frontend._build_constants(),
    type_map=frontend._build_type_map(),
    stmt_dispatch=frontend._build_stmt_dispatch(),
    expr_dispatch=frontend._build_expr_dispatch(),
)

result = parse_pattern(ctx, case_pattern)
assert isinstance(result, SequencePattern), f"Expected SequencePattern, got {type(result)}"
assert len(result.elements) == 2, f"Expected 2 elements, got {len(result.elements)}"
assert isinstance(result.elements[1], StarPattern), f"Expected StarPattern, got {type(result.elements[1])}"
assert result.elements[1].name == "rest", f"Expected name='rest', got {result.elements[1].name}"
print("All parse_pattern star tests passed!")
```

Run: `poetry run python /tmp/test_parse_star.py`
Expected: `All parse_pattern star tests passed!`

- [ ] **Step 3: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/python/patterns.py
git commit -m "feat: parse_pattern handles splat_pattern → StarPattern"
```

---

### Task 5: Integration tests — all star pattern variants

**Files:**
- Modify: `tests/integration/test_python_pattern_matching.py`

- [ ] **Step 1: Write integration tests**

Add to `tests/integration/test_python_pattern_matching.py`:

```python
class TestStarPatterns:
    def test_star_at_end(self):
        vm, local_vars = _run_python("""\
items = [1, 2, 3, 4]
match items:
    case [first, *rest]:
        result_first = first
        rest_len = len(rest)
""", max_steps=1000)
        assert local_vars["result_first"] == 1
        assert local_vars["rest_len"] == 3

    def test_star_at_beginning(self):
        _, local_vars = _run_python("""\
items = [1, 2, 3]
match items:
    case [*head, last]:
        result_last = last
        head_len = len(head)
""", max_steps=1000)
        assert local_vars["result_last"] == 3
        assert local_vars["head_len"] == 2

    def test_star_in_middle(self):
        _, local_vars = _run_python("""\
items = [1, 2, 3, 4, 5]
match items:
    case [a, *mid, z]:
        result_a = a
        result_z = z
        mid_len = len(mid)
""", max_steps=1000)
        assert local_vars["result_a"] == 1
        assert local_vars["result_z"] == 5
        assert local_vars["mid_len"] == 3

    def test_star_empty_rest(self):
        _, local_vars = _run_python("""\
items = [1, 2]
match items:
    case [a, b, *rest]:
        result_a = a
        result_b = b
        rest_len = len(rest)
""", max_steps=1000)
        assert local_vars["result_a"] == 1
        assert local_vars["result_b"] == 2
        assert local_vars["rest_len"] == 0

    def test_star_in_tuple(self):
        _, local_vars = _run_python("""\
data = (10, 20, 30)
match data:
    case (first, *rest):
        result = first
""", max_steps=1000)
        assert local_vars["result"] == 10

    def test_star_minimum_length_rejects(self):
        _, local_vars = _run_python("""\
items = [1]
result = "default"
match items:
    case [a, b, *rest]:
        result = "matched"
    case _:
        result = "default"
""", max_steps=1000)
        assert local_vars["result"] == "default"

    def test_wildcard_star_no_binding(self):
        _, local_vars = _run_python("""\
items = [1, 2, 3]
match items:
    case [first, *_]:
        result = first
""", max_steps=1000)
        assert local_vars["result"] == 1

    def test_nested_star_pattern(self):
        _, local_vars = _run_python("""\
data = [1, [2, 3, 4], 5]
match data:
    case [a, [b, *inner], c]:
        result_a = a
        result_b = b
        result_c = c
""", max_steps=2000)
        assert local_vars["result_a"] == 1
        assert local_vars["result_b"] == 2
        assert local_vars["result_c"] == 5
```

- [ ] **Step 2: Run tests**

Run: `poetry run python -m pytest tests/integration/test_python_pattern_matching.py::TestStarPatterns -v`
Expected: All PASS. If any fail, debug the issue (likely in the compiler or parse_pattern).

- [ ] **Step 3: Remove xfail from existing test**

Find `test_star_pattern_in_list` in the `TestOutOfScopePatterns` class and remove the `@pytest.mark.xfail` decorator (or remove the test entirely if the new `TestStarPatterns` covers it).

- [ ] **Step 4: Run full integration test file**

Run: `poetry run python -m pytest tests/integration/test_python_pattern_matching.py -v`
Expected: All PASS (minus remaining xfails for other out-of-scope features)

- [ ] **Step 5: Commit**

```bash
poetry run python -m black .
git add tests/integration/test_python_pattern_matching.py
git commit -m "test: integration tests for star patterns in Python match/case"
```

---

### Task 6: Full test suite + formatting + push

**Files:**
- No new files

- [ ] **Step 1: Run Black**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --tb=short`
Expected: All tests pass, no regressions.

- [ ] **Step 3: Update docs**

Add to `docs/architectural-design-decisions.md` after ADR-111:

```markdown
### ADR-112: Star Patterns in Sequence Matching (2026-03-20)

**Context:** Python's `case [first, *rest]:` star patterns were unsupported — `SequencePattern` only did exact-length matching.

**Decision:** Add `StarPattern(name)` to the Pattern ADT. When present in a `SequencePattern`, the compiler switches from exact-length (`==`) to minimum-length (`>=`) matching. Fixed elements before/after the star use literal/computed indices. The star capture uses the existing `slice` builtin. Wildcard star (`*_`) skips the slice entirely.

**Consequences:** Star patterns work in both list and tuple patterns. No new opcodes or VM changes. The `_has_star`/`_star_index` helpers and `_compile_after_star_element_test`/`_binding` functions are reusable when other languages add star/rest patterns.
```

- [ ] **Step 4: Close beads issue**

```bash
bd update red-dragon-2uke --status closed
```

- [ ] **Step 5: Push**

```bash
git push origin main
```
