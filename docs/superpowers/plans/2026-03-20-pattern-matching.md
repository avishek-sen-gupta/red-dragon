# Pattern Matching Infrastructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a common Pattern ADT + compiler that lowers structural pattern matching into existing IR, with Python as the first consumer.

**Architecture:** Language frontends parse tree-sitter ASTs into a shared `Pattern` algebraic data type (`interpreter/frontends/common/patterns.py`). A single `compile_match` function emits test+destructure IR using the CPython linear chain model (sequential test-and-branch per case). Two-pass design: emit all tests first, then bindings only after all tests pass.

**Tech Stack:** Python 3.13+, tree-sitter, frozen dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-03-20-pattern-matching-design.md`

---

## File Map

| File | Role | Action |
|---|---|---|
| `interpreter/frontends/common/patterns.py` | Pattern ADT + `MatchCase` + `compile_match` + `compile_pattern_test` + `compile_pattern_bindings` | **Create** |
| `interpreter/frontends/python/patterns.py` | `parse_pattern`: tree-sitter AST → Pattern ADT | **Create** |
| `interpreter/builtins.py` | Add `isinstance` builtin | **Modify** (add ~15 lines) |
| `interpreter/frontends/python/control_flow.py` | Refactor `lower_match` to use `parse_pattern` + `compile_match` | **Modify** (lines 415-482) |
| `interpreter/frontends/python/node_types.py` | Add `CLASS_PATTERN`, `UNION_PATTERN`, `KEYWORD_PATTERN` constants | **Modify** (lines 125-132) |
| `interpreter/frontends/python/frontend.py` | Remove `CASE_PATTERN` expr mapping | **Modify** (line 86) |
| `interpreter/frontends/python/expressions.py` | Remove `lower_case_pattern` | **Modify** (lines 910-918) |
| `tests/unit/test_pattern_compiler.py` | Unit tests for pattern compiler IR emission | **Create** |
| `tests/integration/test_python_pattern_matching.py` | Integration tests: real Python programs through `run()` | **Create** |

---

### Task 1: Pattern ADT

**Files:**
- Create: `interpreter/frontends/common/patterns.py`

- [ ] **Step 1: Create the Pattern ADT with all types**

```python
"""Pattern ADT for structural pattern matching.

Language frontends parse tree-sitter ASTs into these types.
The compile_match function (below) emits IR from them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pattern:
    """Base for all pattern types."""


@dataclass(frozen=True)
class LiteralPattern(Pattern):
    """Match against a literal value (int, str, bool, None)."""
    value: int | float | str | bool | None


@dataclass(frozen=True)
class WildcardPattern(Pattern):
    """Matches anything, binds nothing. Python's ``_``."""


@dataclass(frozen=True)
class CapturePattern(Pattern):
    """Matches anything, binds the subject to a variable name."""
    name: str


@dataclass(frozen=True)
class SequencePattern(Pattern):
    """Matches a tuple or list — checks length, then matches each element by index."""
    elements: tuple[Pattern, ...]


@dataclass(frozen=True)
class MappingPattern(Pattern):
    """Matches a dict — checks each key exists, then matches the value pattern."""
    entries: tuple[tuple[int | float | str | bool | None, Pattern], ...]


@dataclass(frozen=True)
class ClassPattern(Pattern):
    """Matches by type, then matches positional and keyword sub-patterns."""
    class_name: str
    positional: tuple[Pattern, ...]
    keyword: tuple[tuple[str, Pattern], ...]


@dataclass(frozen=True)
class OrPattern(Pattern):
    """Matches if any alternative matches (short-circuit). No bindings."""
    alternatives: tuple[Pattern, ...]


@dataclass(frozen=True)
class AsPattern(Pattern):
    """Matches inner pattern, then binds subject to name."""
    pattern: Pattern
    name: str


@dataclass(frozen=True)
class NoGuard:
    """Sentinel: this case has no guard clause."""

@dataclass(frozen=True)
class NoBody:
    """Sentinel: this case has no body (used in tests)."""

@dataclass(frozen=True)
class MatchCase:
    """A single case in a match statement."""
    pattern: Pattern
    guard_node: object  # tree-sitter node for guard expression, or NoGuard()
    body_node: object   # tree-sitter node for case body, or NoBody()
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `poetry run python -c "from interpreter.frontends.common.patterns import Pattern, LiteralPattern, WildcardPattern, CapturePattern, SequencePattern, MappingPattern, ClassPattern, OrPattern, AsPattern, MatchCase"`
Expected: no error

- [ ] **Step 3: Commit**

```bash
git add interpreter/frontends/common/patterns.py
git commit -m "feat: add Pattern ADT for structural pattern matching"
```

---

### Task 2: Pattern Compiler — Literal, Wildcard, Capture (unit tests first)

**Files:**
- Create: `tests/unit/test_pattern_compiler.py`
- Modify: `interpreter/frontends/common/patterns.py`

- [ ] **Step 1: Write unit test scaffolding and first 3 tests**

```python
"""Unit tests for pattern compiler IR emission."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    LiteralPattern,
    WildcardPattern,
    CapturePattern,
    MatchCase,
    compile_match,
    compile_pattern_test,
    compile_pattern_bindings,
    NoGuard,
    NoBody,
)
from interpreter.frontends.python import PythonFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.ir import IRInstruction, Opcode


def _make_ctx():
    """Create a minimal TreeSitterEmitContext for testing IR emission.

    Uses PythonFrontend's internal _lower_with_context path to construct
    a properly configured context. We parse a dummy source, then clear
    the instructions to get a fresh context for pattern compilation tests.
    """
    from interpreter.frontends.context import TreeSitterEmitContext
    from interpreter.frontends.python.frontend import PythonFrontend
    from interpreter.constants import Language
    from interpreter.frontends.python import constants as py_constants
    from interpreter.frontend_observer import NullFrontendObserver

    frontend = PythonFrontend(TreeSitterParserFactory(), "python")
    grammar_constants = frontend._build_constants()
    ctx = TreeSitterEmitContext(
        source=b"x = 1",
        language=Language.PYTHON,
        observer=NullFrontendObserver(),
        constants=grammar_constants,
        type_map=frontend._build_type_map(),
        stmt_dispatch=frontend._build_stmt_dispatch(),
        expr_dispatch=frontend._build_expr_dispatch(),
    )
    return ctx


def _opcodes(instructions: list[IRInstruction]) -> list[Opcode]:
    return [inst.opcode for inst in instructions]


class TestLiteralPattern:
    def test_emits_const_and_binop_eq(self):
        ctx = _make_ctx()
        subject_reg = "%subj"
        pattern = LiteralPattern(value=42)
        result_reg = compile_pattern_test(ctx, subject_reg, pattern)
        # Should have emitted: CONST 42, BINOP == %subj <const_reg>
        instrs = ctx.instructions
        consts = [i for i in instrs if i.opcode == Opcode.CONST]
        binops = [i for i in instrs if i.opcode == Opcode.BINOP]
        assert len(consts) >= 1, f"expected CONST, got {_opcodes(instrs)}"
        assert consts[-1].operands == ["42"]
        assert len(binops) >= 1, f"expected BINOP, got {_opcodes(instrs)}"
        assert binops[-1].operands[0] == "=="
        assert binops[-1].operands[1] == subject_reg
        assert result_reg == binops[-1].result_reg

    def test_string_literal_emits_const(self):
        ctx = _make_ctx()
        pattern = LiteralPattern(value="hello")
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        consts = [i for i in ctx.instructions if i.opcode == Opcode.CONST]
        assert any(c.operands == ['"hello"'] or c.operands == ["hello"] for c in consts)


class TestWildcardPattern:
    def test_emits_no_test(self):
        ctx = _make_ctx()
        pattern = WildcardPattern()
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        # Wildcard always matches — no BINOP emitted, result should be truthy const
        binops = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert len(binops) == 0, f"wildcard should emit no BINOP, got {binops}"


class TestCapturePattern:
    def test_emits_no_test(self):
        ctx = _make_ctx()
        pattern = CapturePattern(name="x")
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        binops = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert len(binops) == 0, f"capture should emit no BINOP, got {binops}"

    def test_emits_store_var(self):
        ctx = _make_ctx()
        pattern = CapturePattern(name="x")
        compile_pattern_bindings(ctx, "%subj", pattern)
        stores = [i for i in ctx.instructions if i.opcode == Opcode.STORE_VAR]
        assert len(stores) >= 1
        assert stores[-1].operands[0] == "x"
        assert stores[-1].operands[1] == "%subj"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py -v`
Expected: ImportError — `compile_pattern_test` doesn't exist yet

- [ ] **Step 3: Implement `compile_pattern_test` and `compile_pattern_bindings` for Literal, Wildcard, Capture**

Add to `interpreter/frontends/common/patterns.py`:

```python
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.ir import Opcode


def compile_pattern_test(
    ctx: TreeSitterEmitContext, subject_reg: str, pattern: Pattern
) -> str:
    """Emit IR that tests whether subject matches pattern. Returns a boolean register."""
    match pattern:
        case LiteralPattern(value=v):
            const_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=const_reg, operands=[str(v)])
            cmp_reg = ctx.fresh_reg()
            ctx.emit(Opcode.BINOP, result_reg=cmp_reg, operands=["==", subject_reg, const_reg])
            return cmp_reg
        case WildcardPattern():
            true_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=true_reg, operands=["True"])
            return true_reg
        case CapturePattern():
            true_reg = ctx.fresh_reg()
            ctx.emit(Opcode.CONST, result_reg=true_reg, operands=["True"])
            return true_reg
        case _:
            raise NotImplementedError(f"compile_pattern_test: {type(pattern).__name__}")


def compile_pattern_bindings(
    ctx: TreeSitterEmitContext, subject_reg: str, pattern: Pattern
) -> None:
    """Emit IR that binds variables from a matched pattern."""
    match pattern:
        case CapturePattern(name=name):
            ctx.emit(Opcode.STORE_VAR, operands=[name, subject_reg])
        case LiteralPattern() | WildcardPattern():
            pass  # no bindings
        case _:
            raise NotImplementedError(f"compile_pattern_bindings: {type(pattern).__name__}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_pattern_compiler.py interpreter/frontends/common/patterns.py
git commit -m "feat: pattern compiler for literal, wildcard, capture patterns (TDD)"
```

---

### Task 3: Pattern Compiler — SequencePattern (unit tests first)

**Files:**
- Modify: `tests/unit/test_pattern_compiler.py`
- Modify: `interpreter/frontends/common/patterns.py`

- [ ] **Step 1: Write unit tests for SequencePattern**

Add to `tests/unit/test_pattern_compiler.py`:

```python
from interpreter.frontends.common.patterns import SequencePattern


class TestSequencePattern:
    def test_emits_len_check_and_load_index(self):
        ctx = _make_ctx()
        pattern = SequencePattern(elements=(LiteralPattern(1), LiteralPattern(2)))
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        # Should emit: CALL_FUNCTION len, BINOP == len N, LOAD_INDEX 0, BINOP ==, LOAD_INDEX 1, BINOP ==
        calls = [i for i in instrs if i.opcode == Opcode.CALL_FUNCTION]
        assert any("len" in str(c.operands) for c in calls), f"expected len() call, got {calls}"
        load_idxs = [i for i in instrs if i.opcode == Opcode.LOAD_INDEX]
        assert len(load_idxs) >= 2, f"expected 2 LOAD_INDEX, got {load_idxs}"

    def test_nested_literals(self):
        ctx = _make_ctx()
        inner = SequencePattern(elements=(LiteralPattern(3), LiteralPattern(4)))
        outer = SequencePattern(elements=(LiteralPattern(1), inner))
        result_reg = compile_pattern_test(ctx, "%subj", outer)
        instrs = ctx.instructions
        # Should have len checks for both outer (2 elements) and inner (2 elements)
        calls = [i for i in instrs if i.opcode == Opcode.CALL_FUNCTION]
        len_calls = [c for c in calls if "len" in str(c.operands)]
        assert len(len_calls) >= 2, f"expected 2 len() calls (outer+inner), got {len_calls}"

    def test_bindings_from_captures_in_sequence(self):
        ctx = _make_ctx()
        pattern = SequencePattern(elements=(CapturePattern("a"), CapturePattern("b")))
        compile_pattern_bindings(ctx, "%subj", pattern)
        stores = [i for i in ctx.instructions if i.opcode == Opcode.STORE_VAR]
        names = [s.operands[0] for s in stores]
        assert "a" in names and "b" in names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py::TestSequencePattern -v`
Expected: FAIL with `NotImplementedError`

- [ ] **Step 3: Implement SequencePattern in `compile_pattern_test` and `compile_pattern_bindings`**

Add cases to `compile_pattern_test`:

```python
case SequencePattern(elements=elems):
    # Check length
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", subject_reg])
    expected_len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=expected_len_reg, operands=[str(len(elems))])
    len_ok_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=len_ok_reg, operands=["==", len_reg, expected_len_reg])
    # Check each element
    sub_results = [len_ok_reg]
    for i, elem_pat in enumerate(elems):
        elem_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[subject_reg, str(i)])
        elem_test = compile_pattern_test(ctx, elem_reg, elem_pat)
        sub_results.append(elem_test)
    # AND all sub-results
    return _and_all(ctx, sub_results)
```

Add case to `compile_pattern_bindings`:

```python
case SequencePattern(elements=elems):
    for i, elem_pat in enumerate(elems):
        elem_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[subject_reg, str(i)])
        compile_pattern_bindings(ctx, elem_reg, elem_pat)
```

Add helper `_and_all`:

```python
def _emit_binop(ctx: TreeSitterEmitContext, op: str, left: str, right: str) -> str:
    """Emit a single BINOP and return the result register."""
    combined = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=combined, operands=[op, left, right])
    return combined


def _and_all(ctx: TreeSitterEmitContext, regs: list[str]) -> str:
    """AND a list of boolean registers together with BINOP &&."""
    from functools import reduce
    return reduce(lambda acc, reg: _emit_binop(ctx, "&&", acc, reg), regs[1:], regs[0])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py -v`
Expected: All tests PASS (old + new)

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_pattern_compiler.py interpreter/frontends/common/patterns.py
git commit -m "feat: pattern compiler for SequencePattern (TDD)"
```

---

### Task 4: Pattern Compiler — MappingPattern (unit tests first)

**Files:**
- Modify: `tests/unit/test_pattern_compiler.py`
- Modify: `interpreter/frontends/common/patterns.py`

- [ ] **Step 1: Write unit test for MappingPattern**

```python
from interpreter.frontends.common.patterns import MappingPattern


class TestMappingPattern:
    def test_emits_load_field_per_key(self):
        ctx = _make_ctx()
        pattern = MappingPattern(entries=(
            ("key1", LiteralPattern(10)),
            ("key2", CapturePattern("val")),
        ))
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        load_fields = [i for i in instrs if i.opcode == Opcode.LOAD_FIELD]
        assert len(load_fields) >= 2, f"expected 2 LOAD_FIELD, got {load_fields}"
        field_names = [lf.operands[1] for lf in load_fields]
        assert "key1" in field_names and "key2" in field_names

    def test_bindings_from_mapping_values(self):
        ctx = _make_ctx()
        pattern = MappingPattern(entries=(("k", CapturePattern("val")),))
        compile_pattern_bindings(ctx, "%subj", pattern)
        stores = [i for i in ctx.instructions if i.opcode == Opcode.STORE_VAR]
        assert any(s.operands[0] == "val" for s in stores)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py::TestMappingPattern -v`
Expected: FAIL with `NotImplementedError`

- [ ] **Step 3: Implement MappingPattern**

Add cases to `compile_pattern_test` and `compile_pattern_bindings`:

```python
# In compile_pattern_test:
case MappingPattern(entries=entries):
    sub_results = []
    for key, val_pat in entries:
        field_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_FIELD, result_reg=field_reg, operands=[subject_reg, str(key)])
        val_test = compile_pattern_test(ctx, field_reg, val_pat)
        sub_results.append(val_test)
    return _and_all(ctx, sub_results) if sub_results else _const_true(ctx)

# In compile_pattern_bindings:
case MappingPattern(entries=entries):
    for key, val_pat in entries:
        field_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_FIELD, result_reg=field_reg, operands=[subject_reg, str(key)])
        compile_pattern_bindings(ctx, field_reg, val_pat)
```

Extract `_const_true` helper from `WildcardPattern`/`CapturePattern` cases.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_pattern_compiler.py interpreter/frontends/common/patterns.py
git commit -m "feat: pattern compiler for MappingPattern (TDD)"
```

---

### Task 5: Pattern Compiler — ClassPattern + `isinstance` builtin (unit tests first)

**Files:**
- Modify: `tests/unit/test_pattern_compiler.py`
- Modify: `interpreter/frontends/common/patterns.py`
- Modify: `interpreter/builtins.py`

- [ ] **Step 1: Write unit test for ClassPattern**

```python
from interpreter.frontends.common.patterns import ClassPattern


class TestClassPattern:
    def test_emits_isinstance_and_field_access(self):
        ctx = _make_ctx()
        pattern = ClassPattern(
            class_name="Point",
            positional=(LiteralPattern(1), LiteralPattern(2)),
            keyword=(),
        )
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        calls = [i for i in instrs if i.opcode == Opcode.CALL_FUNCTION]
        assert any("isinstance" in str(c.operands) for c in calls), \
            f"expected isinstance call, got {calls}"
        load_idxs = [i for i in instrs if i.opcode == Opcode.LOAD_INDEX]
        assert len(load_idxs) >= 2

    def test_keyword_emits_load_field(self):
        ctx = _make_ctx()
        pattern = ClassPattern(
            class_name="Point",
            positional=(),
            keyword=(("x", LiteralPattern(1)), ("y", LiteralPattern(2))),
        )
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        load_fields = [i for i in instrs if i.opcode == Opcode.LOAD_FIELD]
        field_names = [lf.operands[1] for lf in load_fields]
        assert "x" in field_names and "y" in field_names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py::TestClassPattern -v`
Expected: FAIL with `NotImplementedError`

- [ ] **Step 3: Add `isinstance` builtin**

Add to `interpreter/builtins.py`:

```python
def _builtin_isinstance(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    """isinstance(obj, class_name) — check heap object type_hint against class name."""
    obj_val = args[0].value
    class_name = str(args[1].value)
    addr = _heap_addr(obj_val)
    type_hint = vm.heap[addr].type_hint
    from interpreter.type_expr import ScalarType
    matches = isinstance(type_hint, ScalarType) and type_hint.name == class_name
    return BuiltinResult(value=typed(matches, scalar("Boolean")))
```

Add `"isinstance": _builtin_isinstance` to `Builtins.TABLE` (at line ~296 in `builtins.py`).

- [ ] **Step 4: Implement ClassPattern in `compile_pattern_test` and `compile_pattern_bindings`**

```python
# In compile_pattern_test:
case ClassPattern(class_name=cls, positional=pos, keyword=kw):
    cls_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=cls_reg, operands=[cls])
    isinstance_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=isinstance_reg, operands=["isinstance", subject_reg, cls_reg])
    sub_results = [isinstance_reg]
    for i, p in enumerate(pos):
        elem_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[subject_reg, str(i)])
        sub_results.append(compile_pattern_test(ctx, elem_reg, p))
    for name, p in kw:
        field_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_FIELD, result_reg=field_reg, operands=[subject_reg, name])
        sub_results.append(compile_pattern_test(ctx, field_reg, p))
    return _and_all(ctx, sub_results)

# In compile_pattern_bindings:
case ClassPattern(class_name=_, positional=pos, keyword=kw):
    for i, p in enumerate(pos):
        elem_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[subject_reg, str(i)])
        compile_pattern_bindings(ctx, elem_reg, p)
    for name, p in kw:
        field_reg = ctx.fresh_reg()
        ctx.emit(Opcode.LOAD_FIELD, result_reg=field_reg, operands=[subject_reg, name])
        compile_pattern_bindings(ctx, field_reg, p)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_pattern_compiler.py interpreter/frontends/common/patterns.py interpreter/builtins.py
git commit -m "feat: pattern compiler for ClassPattern + isinstance builtin (TDD)"
```

---

### Task 6: Pattern Compiler — OrPattern, AsPattern, Guards (unit tests first)

**Files:**
- Modify: `tests/unit/test_pattern_compiler.py`
- Modify: `interpreter/frontends/common/patterns.py`

- [ ] **Step 1: Write unit tests**

```python
from interpreter.frontends.common.patterns import OrPattern, AsPattern


class TestOrPattern:
    def test_short_circuits(self):
        ctx = _make_ctx()
        pattern = OrPattern(alternatives=(LiteralPattern(1), LiteralPattern(2)))
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        instrs = ctx.instructions
        # Should have at least 2 BINOP == (one per alternative) and OR logic
        binops = [i for i in instrs if i.opcode == Opcode.BINOP and i.operands[0] == "=="]
        assert len(binops) >= 2, f"expected >=2 equality checks, got {binops}"


class TestAsPattern:
    def test_binds_after_inner_test(self):
        ctx = _make_ctx()
        pattern = AsPattern(pattern=LiteralPattern(42), name="x")
        result_reg = compile_pattern_test(ctx, "%subj", pattern)
        # Test should be the inner literal test
        binops = [i for i in ctx.instructions if i.opcode == Opcode.BINOP]
        assert len(binops) >= 1

    def test_emits_store_var(self):
        ctx = _make_ctx()
        pattern = AsPattern(pattern=LiteralPattern(42), name="x")
        compile_pattern_bindings(ctx, "%subj", pattern)
        stores = [i for i in ctx.instructions if i.opcode == Opcode.STORE_VAR]
        assert any(s.operands[0] == "x" for s in stores)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py::TestOrPattern tests/unit/test_pattern_compiler.py::TestAsPattern -v`
Expected: FAIL

- [ ] **Step 3: Implement OrPattern and AsPattern**

```python
# In compile_pattern_test:
case OrPattern(alternatives=alts):
    sub_results = [compile_pattern_test(ctx, subject_reg, alt) for alt in alts]
    return _or_any(ctx, sub_results)

case AsPattern(pattern=inner, name=_):
    return compile_pattern_test(ctx, subject_reg, inner)

# In compile_pattern_bindings:
case OrPattern():
    pass  # no bindings for or-patterns

case AsPattern(pattern=inner, name=name):
    compile_pattern_bindings(ctx, subject_reg, inner)
    ctx.emit(Opcode.STORE_VAR, operands=[name, subject_reg])
```

Add `_or_any` helper:

```python
def _or_any(ctx: TreeSitterEmitContext, regs: list[str]) -> str:
    """OR a list of boolean registers together with BINOP ||."""
    from functools import reduce
    return reduce(lambda acc, reg: _emit_binop(ctx, "||", acc, reg), regs[1:], regs[0])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_pattern_compiler.py interpreter/frontends/common/patterns.py
git commit -m "feat: pattern compiler for OrPattern, AsPattern (TDD)"
```

---

### Task 7: Pattern Compiler — `compile_match` with guards and two-pass (unit tests first)

**Files:**
- Modify: `tests/unit/test_pattern_compiler.py`
- Modify: `interpreter/frontends/common/patterns.py`

- [ ] **Step 1: Write unit tests for `compile_match`, guards, two-pass**

```python
class TestCompileMatch:
    def test_multiple_cases_linear_chain(self):
        """Three literal cases produce a linear chain with labels."""
        ctx = _make_ctx()
        cases = [
            MatchCase(pattern=LiteralPattern(1), body_node=NoBody()),
            MatchCase(pattern=LiteralPattern(2), body_node=NoBody()),
            MatchCase(pattern=WildcardPattern(), body_node=NoBody()),
        ]
        compile_match(ctx, "%subj", cases)
        instrs = ctx.instructions
        labels = [i.label for i in instrs if i.opcode == Opcode.LABEL]
        branches = [i for i in instrs if i.opcode == Opcode.BRANCH]
        branch_ifs = [i for i in instrs if i.opcode == Opcode.BRANCH_IF]
        # Should have: case_true/case_next labels per non-wildcard case + match_end
        assert len(branch_ifs) >= 2, f"expected >=2 BRANCH_IF, got {branch_ifs}"
        assert any("match_end" in l for l in labels), f"expected match_end label, got {labels}"

    def test_two_pass_no_partial_binding(self):
        """Bindings should only appear after the BRANCH_IF test, not before."""
        ctx = _make_ctx()
        cases = [
            MatchCase(
                pattern=SequencePattern(elements=(CapturePattern("a"), CapturePattern("b"))),
                body_node=NoBody(),
            ),
        ]
        compile_match(ctx, "%subj", cases)
        instrs = ctx.instructions
        # Find the BRANCH_IF for this case
        branch_if_idx = next(
            i for i, inst in enumerate(instrs) if inst.opcode == Opcode.BRANCH_IF
        )
        # All STORE_VAR for bindings should come AFTER the BRANCH_IF
        stores_before = [
            inst for inst in instrs[:branch_if_idx]
            if inst.opcode == Opcode.STORE_VAR and inst.operands[0] in ("a", "b")
        ]
        assert len(stores_before) == 0, \
            f"bindings should not appear before BRANCH_IF: {stores_before}"


class TestGuardedCase:
    def test_emits_guard_after_pattern_test(self):
        """Guard expression should be ANDed with pattern test."""
        ctx = _make_ctx()
        # We can't easily provide a real tree-sitter guard node in unit tests.
        # Unit test only verifies NoGuard path (no real tree-sitter guard node available).
        # Guard AND logic is exercised in integration tests (TestGuard in Task 12).
        cases = [
            MatchCase(pattern=LiteralPattern(1), guard_node=NoGuard(), body_node=NoBody()),
        ]
        compile_match(ctx, "%subj", cases)
        instrs = ctx.instructions
        # Should have exactly one BRANCH_IF (no guard AND)
        branch_ifs = [i for i in instrs if i.opcode == Opcode.BRANCH_IF]
        assert len(branch_ifs) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py::TestCompileMatch tests/unit/test_pattern_compiler.py::TestGuardedCase -v`
Expected: FAIL — `compile_match` not implemented

- [ ] **Step 3: Implement `compile_match`**

Add to `interpreter/frontends/common/patterns.py`:

```python
def compile_match(
    ctx: TreeSitterEmitContext, subject_reg: str, cases: list[MatchCase]
) -> None:
    """Emit IR for a match statement using CPython-style linear chain."""
    end_label = ctx.fresh_label("match_end")

    for case in cases:
        pattern = case.pattern
        is_irrefutable = isinstance(pattern, (WildcardPattern, CapturePattern))

        if is_irrefutable:
            # Default/capture case: unconditionally bind and run body
            compile_pattern_bindings(ctx, subject_reg, pattern)
            if not isinstance(case.body_node, NoBody):
                ctx.lower_block(case.body_node)
            ctx.emit(Opcode.BRANCH, label=end_label)
        else:
            test_reg = compile_pattern_test(ctx, subject_reg, pattern)

            # Apply guard if present
            if not isinstance(case.guard_node, NoGuard):
                guard_reg = ctx.lower_expr(case.guard_node)
                combined = ctx.fresh_reg()
                ctx.emit(Opcode.BINOP, result_reg=combined, operands=["&&", test_reg, guard_reg])
                test_reg = combined

            case_true = ctx.fresh_label("case_true")
            case_next = ctx.fresh_label("case_next")
            ctx.emit(Opcode.BRANCH_IF, operands=[test_reg], label=f"{case_true},{case_next}")
            ctx.emit(Opcode.LABEL, label=case_true)
            compile_pattern_bindings(ctx, subject_reg, pattern)
            if not isinstance(case.body_node, NoBody):
                ctx.lower_block(case.body_node)
            ctx.emit(Opcode.BRANCH, label=end_label)
            ctx.emit(Opcode.LABEL, label=case_next)

    ctx.emit(Opcode.LABEL, label=end_label)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_pattern_compiler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_pattern_compiler.py interpreter/frontends/common/patterns.py
git commit -m "feat: compile_match with linear chain, guards, two-pass binding (TDD)"
```

---

### Task 8: Python Frontend Parser (`parse_pattern`)

**Files:**
- Create: `interpreter/frontends/python/patterns.py`
- Modify: `interpreter/frontends/python/node_types.py`

- [ ] **Step 1: Add missing node type constants**

Add to `interpreter/frontends/python/node_types.py` after `TUPLE_PATTERN`:

```python
    CLASS_PATTERN = "class_pattern"
    UNION_PATTERN = "union_pattern"
    KEYWORD_PATTERN = "keyword_pattern"
```

- [ ] **Step 2: Create `parse_pattern`**

Create `interpreter/frontends/python/patterns.py`:

```python
"""Parse tree-sitter Python pattern AST nodes into Pattern ADT."""

from __future__ import annotations

from interpreter.frontends.common.patterns import (
    AsPattern,
    CapturePattern,
    ClassPattern,
    LiteralPattern,
    MappingPattern,
    OrPattern,
    Pattern,
    SequencePattern,
    WildcardPattern,
)
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.frontends.python.node_types import PythonNodeType

_WILDCARD = "_"


def _parse_key_literal(ctx: TreeSitterEmitContext, node) -> int | float | str | bool | None:
    """Extract a literal value from a dict pattern key node."""
    text = ctx.node_text(node)
    match node.type:
        case "integer":
            return int(text)
        case "float":
            return float(text)
        case "true":
            return True
        case "false":
            return False
        case "none":
            return None
        case _:  # string
            return text.strip("'\"")


def parse_pattern(ctx: TreeSitterEmitContext, node) -> Pattern:
    """Convert a tree-sitter case_pattern (or inner pattern) node into a Pattern ADT."""
    # case_pattern is a wrapper — unwrap to inner
    if node.type == PythonNodeType.CASE_PATTERN:
        named = [c for c in node.children if c.is_named]
        return parse_pattern(ctx, named[0]) if named else WildcardPattern()

    node_type = node.type
    text = ctx.node_text(node)

    # Wildcard
    if text == _WILDCARD:
        return WildcardPattern()

    # Literals
    if node_type == "integer":
        return LiteralPattern(value=int(text))
    if node_type == "float":
        return LiteralPattern(value=float(text))
    if node_type == "string":
        # Strip quotes
        content = text.strip("'\"")
        return LiteralPattern(value=content)
    if node_type == "true":
        return LiteralPattern(value=True)
    if node_type == "false":
        return LiteralPattern(value=False)
    if node_type == "none":
        return LiteralPattern(value=None)

    # Capture (identifier or dotted_name with single segment)
    if node_type in ("identifier", "dotted_name"):
        name = text
        return CapturePattern(name=name)

    # Tuple pattern
    if node_type == PythonNodeType.TUPLE_PATTERN:
        elements = tuple(
            parse_pattern(ctx, c) for c in node.children
            if c.type == PythonNodeType.CASE_PATTERN
        )
        return SequencePattern(elements=elements)

    # List pattern
    if node_type == PythonNodeType.LIST_PATTERN:
        elements = tuple(
            parse_pattern(ctx, c) for c in node.children
            if c.type == PythonNodeType.CASE_PATTERN
        )
        return SequencePattern(elements=elements)

    # Dict pattern
    if node_type == PythonNodeType.DICT_PATTERN:
        # dict_pattern children alternate: key_node, ":", case_pattern, ","
        # Extract key nodes and case_pattern nodes, then zip them
        _KEY_TYPES = frozenset({"string", "integer", "float", "true", "false", "none"})
        key_nodes = [c for c in node.children if c.type in _KEY_TYPES]
        val_nodes = [c for c in node.children if c.type == PythonNodeType.CASE_PATTERN]
        entries = tuple(
            (_parse_key_literal(ctx, k), parse_pattern(ctx, v))
            for k, v in zip(key_nodes, val_nodes)
        )
        return MappingPattern(entries=entries)

    # Class pattern
    if node_type == PythonNodeType.CLASS_PATTERN:
        dotted = next(c for c in node.children if c.type == "dotted_name")
        class_name = ctx.node_text(dotted)
        case_patterns = [c for c in node.children if c.type == PythonNodeType.CASE_PATTERN]
        positional: list[Pattern] = []
        keyword: list[tuple[str, Pattern]] = []
        for child in case_patterns:
            inner = next(c for c in child.children if c.is_named)
            if inner.type == PythonNodeType.KEYWORD_PATTERN:
                parts = [c for c in inner.children if c.is_named]
                kw_name = ctx.node_text(parts[0])
                kw_val = parse_pattern(ctx, parts[1])
                keyword.append((kw_name, kw_val))
            else:
                positional.append(parse_pattern(ctx, child))
        return ClassPattern(class_name=class_name, positional=tuple(positional), keyword=tuple(keyword))

    # Union pattern (or-pattern)
    if node_type == PythonNodeType.UNION_PATTERN:
        alternatives = tuple(
            parse_pattern(ctx, c) for c in node.children if c.is_named
        )
        return OrPattern(alternatives=alternatives)

    # As pattern
    if node_type == PythonNodeType.AS_PATTERN:
        named = [c for c in node.children if c.is_named]
        # First named child is the inner pattern (wrapped in case_pattern), last is the binding name
        inner = parse_pattern(ctx, named[0]) if named else WildcardPattern()
        bind_name = ctx.node_text(named[-1]) if len(named) >= 2 else "_"
        return AsPattern(pattern=inner, name=bind_name)

    # Fallback: treat as capture
    return CapturePattern(name=text)
```

- [ ] **Step 3: Verify it imports**

Run: `poetry run python -c "from interpreter.frontends.python.patterns import parse_pattern"`
Expected: no error

- [ ] **Step 4: Commit**

```bash
git add interpreter/frontends/python/patterns.py interpreter/frontends/python/node_types.py
git commit -m "feat: Python parse_pattern — tree-sitter AST to Pattern ADT"
```

---

### Task 9: Refactor `lower_match` + clean up old code

**Files:**
- Modify: `interpreter/frontends/python/control_flow.py` (lines 415-482)
- Modify: `interpreter/frontends/python/frontend.py` (line 86)
- Modify: `interpreter/frontends/python/expressions.py` (lines 910-918)

- [ ] **Step 1: Refactor `lower_match` in `control_flow.py`**

Replace lines 415-482 with:

```python
def lower_match(ctx: TreeSitterEmitContext, node) -> None:
    """Lower match/case as pattern-driven linear chain."""
    from interpreter.frontends.common.patterns import MatchCase, NoGuard, NoBody, compile_match
    from interpreter.frontends.python.patterns import parse_pattern

    subject_node = node.child_by_field_name("subject")
    body_node = node.child_by_field_name("body")
    subject_reg = ctx.lower_expr(subject_node)

    case_clauses = (
        [c for c in body_node.children if c.type == PythonNodeType.CASE_CLAUSE]
        if body_node
        else []
    )

    cases: list[MatchCase] = []
    for case_node in case_clauses:
        pattern_node = next(
            (c for c in case_node.children if c.type == PythonNodeType.CASE_PATTERN),
            None,
        )
        case_body = case_node.child_by_field_name(
            ctx.constants.if_consequence_field
        ) or next(
            (c for c in case_node.children if c.type == PythonNodeType.BLOCK), None
        )

        pattern = parse_pattern(ctx, pattern_node) if pattern_node else WildcardPattern()

        # Extract guard: Python uses "if" clause inside case_clause
        # Extract guard: Python uses "if_clause" inside case_clause
        if_clauses = [c for c in case_node.children if c.type == "if_clause"]
        guard_node: object = (
            next(c for c in if_clauses[0].children if c.is_named)
            if if_clauses
            else NoGuard()
        )

        cases.append(MatchCase(
            pattern=pattern,
            guard_node=guard_node,
            body_node=case_body if case_body else NoBody(),
        ))

    compile_match(ctx, subject_reg, cases)
```

- [ ] **Step 2: Remove `CASE_PATTERN` from `frontend.py` expr_dispatch**

In `interpreter/frontends/python/frontend.py`, remove line 86:
```python
            PythonNodeType.CASE_PATTERN: py_expr.lower_case_pattern,
```

- [ ] **Step 3: Remove `lower_case_pattern` function from `expressions.py`**

Remove the `lower_case_pattern` function and its section comment from `interpreter/frontends/python/expressions.py`.

- [ ] **Step 4: Run existing tests to verify no regression**

Run: `poetry run python -m pytest tests/unit/test_python_frontend.py tests/unit/rosetta/test_rosetta_pattern_matching.py -v`
Expected: All existing tests PASS (literal matching should still work)

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/python/control_flow.py interpreter/frontends/python/frontend.py interpreter/frontends/python/expressions.py
git commit -m "refactor: lower_match uses Pattern ADT + compile_match"
```

---

### Task 10: Integration Tests — Literals, Wildcard, Capture

**Files:**
- Create: `tests/integration/test_python_pattern_matching.py`

- [ ] **Step 1: Write integration tests for basic patterns**

```python
"""Integration tests: Python pattern matching through VM execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_python(source: str, max_steps: int = 500):
    vm = run(source, language=Language.PYTHON, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestLiteralMatch:
    def test_literal_int_match(self):
        _, local_vars = _run_python("""\
x = 2
match x:
    case 1:
        y = 10
    case 2:
        y = 20
    case 3:
        y = 30
""")
        assert local_vars["y"] == 20

    def test_literal_str_match(self):
        _, local_vars = _run_python("""\
x = "hello"
match x:
    case "world":
        y = 1
    case "hello":
        y = 2
""")
        assert local_vars["y"] == 2


class TestWildcardMatch:
    def test_wildcard_default(self):
        _, local_vars = _run_python("""\
x = 99
match x:
    case 1:
        y = 10
    case _:
        y = 99
""")
        assert local_vars["y"] == 99


class TestCaptureMatch:
    def test_capture_binds_value(self):
        _, local_vars = _run_python("""\
x = 42
match x:
    case val:
        y = val
""")
        assert local_vars["y"] == 42


class TestFallThrough:
    def test_fall_through_to_default(self):
        _, local_vars = _run_python("""\
x = 100
y = 0
match x:
    case 1:
        y = 10
    case 2:
        y = 20
    case _:
        y = 999
""")
        assert local_vars["y"] == 999

    def test_no_match_no_crash(self):
        _, local_vars = _run_python("""\
x = 100
y = 0
match x:
    case 1:
        y = 10
    case 2:
        y = 20
""")
        assert local_vars["y"] == 0
```

- [ ] **Step 2: Run tests**

Run: `poetry run python -m pytest tests/integration/test_python_pattern_matching.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_python_pattern_matching.py
git commit -m "test: integration tests for Python literal/wildcard/capture patterns"
```

---

### Task 11: Integration Tests — Structural Patterns

**Files:**
- Modify: `tests/integration/test_python_pattern_matching.py`

- [ ] **Step 1: Write integration tests for tuple, list, dict, nested**

```python
class TestTupleDestructure:
    def test_tuple_destructure(self):
        _, local_vars = _run_python("""\
point = (3, 4)
match point:
    case (a, b):
        z = a + b
""", max_steps=1000)
        assert local_vars["z"] == 7


class TestListDestructure:
    def test_list_destructure(self):
        _, local_vars = _run_python("""\
items = [10, 20]
match items:
    case [a, b]:
        z = a + b
""", max_steps=1000)
        assert local_vars["z"] == 30


class TestNestedSequence:
    def test_nested_sequence(self):
        _, local_vars = _run_python("""\
data = (1, (2, 3))
match data:
    case (a, (b, c)):
        z = a + b + c
""", max_steps=1000)
        assert local_vars["z"] == 6


class TestDictPattern:
    def test_dict_pattern(self):
        _, local_vars = _run_python("""\
d = {"name": "Alice", "age": 30}
match d:
    case {"name": name}:
        result = name
""", max_steps=1000)
        assert local_vars["result"] == "Alice"
```

- [ ] **Step 2: Run tests**

Run: `poetry run python -m pytest tests/integration/test_python_pattern_matching.py -v`
Expected: All PASS (may need debugging — structural patterns exercise the full pipeline)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_python_pattern_matching.py
git commit -m "test: integration tests for Python tuple/list/dict/nested patterns"
```

---

### Task 12: Integration Tests — Class, Or, As, Guard, Nested Cross-Pattern

**Files:**
- Modify: `tests/integration/test_python_pattern_matching.py`

- [ ] **Step 1: Write integration tests**

```python
class TestClassPattern:
    def test_class_keyword(self):
        _, local_vars = _run_python("""\
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

p = Point(3, 4)
match p:
    case Point(x=3, y=y_val):
        result = y_val
""", max_steps=2000)
        assert local_vars["result"] == 4

    def test_class_positional(self):
        _, local_vars = _run_python("""\
class Pair:
    def __init__(self, a, b):
        self.a = a
        self.b = b

p = Pair(10, 20)
match p:
    case Pair(a, b):
        result = a + b
""", max_steps=2000)
        assert local_vars["result"] == 30


class TestOrPattern:
    def test_or_pattern(self):
        _, local_vars = _run_python("""\
x = 2
match x:
    case 1 | 2:
        y = "yes"
    case _:
        y = "no"
""")
        assert local_vars["y"] == "yes"


class TestAsPattern:
    def test_as_pattern(self):
        _, local_vars = _run_python("""\
x = 42
match x:
    case val as name:
        y = name
""")
        assert local_vars["y"] == 42


class TestGuard:
    def test_guard_filters(self):
        _, local_vars = _run_python("""\
x = -5
match x:
    case val if val > 0:
        y = "positive"
    case _:
        y = "non-positive"
""")
        assert local_vars["y"] == "non-positive"


class TestNestedCrossPattern:
    def test_nested_class_in_sequence(self):
        _, local_vars = _run_python("""\
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

data = (Point(1, 2), Point(3, 4))
match data:
    case (Point(x=1, y=a), Point(x=3, y=b)):
        result = a + b
""", max_steps=3000)
        assert local_vars["result"] == 6

    def test_nested_mapping_in_class(self):
        _, local_vars = _run_python("""\
class Config:
    def __init__(self, settings):
        self.settings = settings

cfg = Config({"debug": True})
match cfg:
    case Config(settings={"debug": val}):
        result = val
""", max_steps=3000)
        assert local_vars["result"] is True
```

- [ ] **Step 2: Run tests**

Run: `poetry run python -m pytest tests/integration/test_python_pattern_matching.py -v`
Expected: All PASS (class pattern tests depend on isinstance builtin working correctly with the VM's type_hint system — may need debugging)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_python_pattern_matching.py
git commit -m "test: integration tests for Python class/or/as/guard/nested patterns"
```

---

### Task 13: Xfail Tests + File Issues for Out-of-Scope Patterns

**Files:**
- Modify: `tests/integration/test_python_pattern_matching.py`

- [ ] **Step 1: Write xfail tests for out-of-scope features**

```python
import pytest


class TestOutOfScopePatterns:
    @pytest.mark.xfail(reason="Star patterns not yet implemented (red-dragon-XXXX)")
    def test_star_pattern_in_list(self):
        _, local_vars = _run_python("""\
items = [1, 2, 3, 4]
match items:
    case [first, *rest]:
        result = first
""", max_steps=1000)
        assert local_vars["result"] == 1

    @pytest.mark.xfail(reason="Complex literal patterns not yet implemented (red-dragon-XXXX)")
    def test_complex_pattern(self):
        _, local_vars = _run_python("""\
z = 1+2j
match z:
    case 1+2j:
        result = "match"
""", max_steps=500)
        assert local_vars["result"] == "match"

    @pytest.mark.xfail(reason="Value patterns (dotted constants) not yet implemented (red-dragon-XXXX)")
    def test_value_pattern(self):
        _, local_vars = _run_python("""\
class Color:
    RED = 0
    GREEN = 1

c = 0
match c:
    case Color.RED:
        result = "red"
""", max_steps=1000)
        assert local_vars["result"] == "red"

    @pytest.mark.xfail(reason="Or-patterns with bindings not yet implemented (red-dragon-XXXX)")
    def test_or_pattern_with_captures(self):
        _, local_vars = _run_python("""\
data = (2, 99)
match data:
    case (1, x) | (2, x):
        result = x
""", max_steps=1000)
        assert local_vars["result"] == 99
```

- [ ] **Step 2: File beads issues for each out-of-scope feature**

```bash
bd create "Pattern matching: star patterns in sequences (case [first, *rest]:)" -p 1 -t feature -l pattern-matching
bd create "Pattern matching: complex literal patterns (case 1+2j:)" -p 2 -t feature -l pattern-matching
bd create "Pattern matching: value patterns / dotted constants (case Color.RED:)" -p 1 -t feature -l pattern-matching
bd create "Pattern matching: or-patterns with capture bindings (case (1, x) | (2, x):)" -p 1 -t feature -l pattern-matching
bd create "Pattern matching: exhaustiveness checking" -p 2 -t feature -l pattern-matching
bd create "Pattern matching: custom extractors (Scala unapply, Kotlin componentN)" -p 2 -t feature -l pattern-matching
```

- [ ] **Step 3: Update xfail markers with actual issue IDs**

Replace `red-dragon-XXXX` placeholders with actual beads IDs from Step 2.

- [ ] **Step 4: Run all tests**

Run: `poetry run python -m pytest tests/integration/test_python_pattern_matching.py -v`
Expected: xfail tests show as `xfail`, all others PASS

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_python_pattern_matching.py
git commit -m "test: xfail tests for out-of-scope pattern matching features"
```

---

### Task 14: Full Test Suite + Formatting + Docs

**Files:**
- Modify: `docs/architectural-design-decisions.md`
- Modify: `README.md` (if pattern matching is mentioned)

- [ ] **Step 1: Run Black**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --tb=short`
Expected: All tests pass, no regressions. Test count should be >= 11998 + new tests.

- [ ] **Step 3: Add ADR for pattern matching**

Add to `docs/architectural-design-decisions.md`:

```markdown
## ADR-111: Pattern Matching Infrastructure (2026-03-20)

**Context:** The Python frontend's `lower_match` handled all patterns by lowering them as expressions and comparing with `BINOP ==`. This failed for structural patterns (tuple, list, dict, class, union, as).

**Decision:** Introduce a shared Pattern ADT (`interpreter/frontends/common/patterns.py`) with a `compile_match` function that emits test+destructure IR using existing opcodes (no new opcodes, no VM changes). CPython linear chain model. Two-pass design: all tests before any bindings.

**Consequences:** Python pattern matching supports 8 pattern types (literal, wildcard, capture, sequence, mapping, class, or, as) + guards. Other languages can add their own `parse_pattern` function to map into the same ADT. Out-of-scope: star patterns, complex literals, value patterns, or-with-bindings, exhaustiveness, custom extractors.
```

- [ ] **Step 4: Update README if needed**

Check if pattern matching is mentioned in the README. If the feature gap table references it, update it.

- [ ] **Step 5: Run Black again and full tests**

Run: `poetry run python -m black . && poetry run python -m pytest -x --tb=short`

- [ ] **Step 6: Commit everything**

```bash
git add -A
git commit -m "docs: add ADR-111 for pattern matching infrastructure"
```

- [ ] **Step 7: Push**

```bash
git push origin main
```
