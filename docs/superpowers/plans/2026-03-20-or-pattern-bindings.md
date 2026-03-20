# Or-Pattern Bindings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `case (1, x) | (2, x):` bind `x` from whichever alternative matched.

**Architecture:** Replace the `OrPattern` no-op in `compile_pattern_bindings` with a mini linear chain: re-test each alternative, bind from the first match, branch to done. Same approach as CPython.

**Tech Stack:** Python 3.13+, frozen dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-03-20-or-pattern-bindings-design.md`

---

## File Map

| File | Role | Action |
|---|---|---|
| `interpreter/frontends/common/patterns.py` | Replace `OrPattern` binding case | **Modify** (~15 lines) |
| `tests/unit/test_pattern_compiler.py` | Unit tests for or-pattern bindings | **Modify** |
| `tests/integration/test_python_pattern_matching.py` | Integration tests + remove xfail | **Modify** |

---

### Task 1: Or-pattern binding IR (TDD)

**Files:**
- Modify: `tests/unit/test_pattern_compiler.py`
- Modify: `interpreter/frontends/common/patterns.py`

- [ ] **Step 1: Write failing unit tests**

Add to `TestOrPattern` in `tests/unit/test_pattern_compiler.py`:

```python
    def test_or_pattern_binds_from_matched_alternative(self):
        """OrPattern with captures should emit STORE_VAR (not just pass)."""
        ctx = _make_ctx()
        pattern = OrPattern(alternatives=(
            SequencePattern(elements=(LiteralPattern(1), CapturePattern("x"))),
            SequencePattern(elements=(LiteralPattern(2), CapturePattern("x"))),
        ))
        compile_pattern_bindings(ctx, "%subj", pattern)
        instrs = ctx.instructions
        stores = [i for i in instrs if i.opcode == Opcode.STORE_VAR]
        store_names = [s.operands[0] for s in stores]
        assert "x" in store_names, f"expected STORE_VAR for 'x', got {store_names}"

    def test_or_pattern_bindings_use_branch_chain(self):
        """OrPattern bindings should emit BRANCH_IF per alternative."""
        ctx = _make_ctx()
        pattern = OrPattern(alternatives=(
            SequencePattern(elements=(LiteralPattern(1), CapturePattern("x"))),
            SequencePattern(elements=(LiteralPattern(2), CapturePattern("x"))),
        ))
        compile_pattern_bindings(ctx, "%subj", pattern)
        instrs = ctx.instructions
        branch_ifs = [i for i in instrs if i.opcode == Opcode.BRANCH_IF]
        assert len(branch_ifs) >= 2, f"expected >=2 BRANCH_IF (one per alt), got {len(branch_ifs)}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py::TestOrPattern::test_or_pattern_binds_from_matched_alternative tests/unit/test_pattern_compiler.py::TestOrPattern::test_or_pattern_bindings_use_branch_chain -v`
Expected: FAIL — current `OrPattern` binding is `pass`, no STORE_VAR or BRANCH_IF emitted

- [ ] **Step 3: Implement or-pattern binding chain**

In `interpreter/frontends/common/patterns.py`, replace the `OrPattern` case in `compile_pattern_bindings`:

```python
        case OrPattern(alternatives=alts):
            # Mini linear chain: re-test each alternative, bind from first match
            or_done = ctx.fresh_label("or_bind_done")
            for alt in alts:
                test_reg = compile_pattern_test(ctx, subject_reg, alt)
                bind_label = ctx.fresh_label("or_bind")
                next_label = ctx.fresh_label("or_next")
                ctx.emit(
                    Opcode.BRANCH_IF,
                    operands=[test_reg],
                    label=f"{bind_label},{next_label}",
                )
                ctx.emit(Opcode.LABEL, label=bind_label)
                compile_pattern_bindings(ctx, subject_reg, alt)
                ctx.emit(Opcode.BRANCH, label=or_done)
                ctx.emit(Opcode.LABEL, label=next_label)
            ctx.emit(Opcode.LABEL, label=or_done)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py -v`
Expected: All tests PASS (old + new)

- [ ] **Step 5: Commit**

```bash
poetry run python -m black .
git add interpreter/frontends/common/patterns.py tests/unit/test_pattern_compiler.py
git commit -m "feat: or-pattern bindings via mini linear chain (TDD)"
```

---

### Task 2: Integration tests + remove xfail

**Files:**
- Modify: `tests/integration/test_python_pattern_matching.py`

- [ ] **Step 1: Add integration tests**

Add a new class `TestOrPatternWithBindings`:

```python
class TestOrPatternWithBindings:
    def test_or_pattern_tuple_with_captures(self):
        """case (1, x) | (2, x): with (2, 99) — x bound to 99."""
        _, local_vars = _run_python(
            """\
data = (2, 99)
match data:
    case (1, x) | (2, x):
        result = x
""",
            max_steps=2000,
        )
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 99

    def test_or_pattern_first_alternative_binds(self):
        """case (1, x) | (2, x): with (1, 77) — first alt matches, x bound to 77."""
        _, local_vars = _run_python(
            """\
data = (1, 77)
match data:
    case (1, x) | (2, x):
        result = x
""",
            max_steps=2000,
        )
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 77

    def test_or_pattern_list_with_captures(self):
        """case [1, y] | [2, y]: with [2, 42] — y bound to 42."""
        _, local_vars = _run_python(
            """\
data = [2, 42]
match data:
    case [1, y] | [2, y]:
        result = y
""",
            max_steps=2000,
        )
        assert isinstance(local_vars["result"], int) and local_vars["result"] == 42

    def test_or_pattern_no_match_falls_through(self):
        """Neither alternative matches — falls to default."""
        _, local_vars = _run_python(
            """\
data = (3, 50)
result = "default"
match data:
    case (1, x) | (2, x):
        result = x
    case _:
        result = "default"
""",
            max_steps=2000,
        )
        assert isinstance(local_vars["result"], str) and local_vars["result"] == "default"
```

- [ ] **Step 2: Remove xfail from existing test**

Find `test_or_pattern_with_captures` in `TestOutOfScopePatterns` and remove its `@pytest.mark.xfail` decorator (or remove the test entirely if the new tests supersede it).

- [ ] **Step 3: Run tests**

Run: `poetry run python -m pytest tests/integration/test_python_pattern_matching.py -v`
Expected: All PASS (minus remaining xfails for other features)

- [ ] **Step 4: Commit**

```bash
poetry run python -m black .
git add tests/integration/test_python_pattern_matching.py
git commit -m "test: integration tests for or-patterns with capture bindings"
```

---

### Task 3: Full test suite + close issue + push

- [ ] **Step 1: Run Black**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --tb=short`
Expected: All tests pass, no regressions.

- [ ] **Step 3: Close beads issue**

```bash
bd update red-dragon-fv2p --status closed
```

- [ ] **Step 4: Push**

```bash
git push origin main
```
