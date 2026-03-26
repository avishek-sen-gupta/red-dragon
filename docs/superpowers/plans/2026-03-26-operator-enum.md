# BinopKind / UnopKind Enum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `Binop.operator: str` and `Unop.operator: str` with `BinopKind` and `UnopKind` enums. Invalid operators become construction-time errors. Per-language valid operator sets enable a lint pass.

**Architecture:** Bridge-first. Define the enums as `str, Enum` (like `Opcode`) so `str(BinopKind.ADD)` returns `"+"`. Wrap all frontend emit sites with the enum constructor while the field is still `str`. Then change the field type. Finally, add per-language valid operator sets and a lint pass. Remove `str` compatibility at the end.

**Tech Stack:** Python 3.13+, pytest, Poetry

**Issue:** red-dragon-5kcc

---

## Task 1: Define BinopKind and UnopKind enums

**Files:**
- Create: `interpreter/operator_kind.py`
- Test: `tests/unit/test_operator_kind.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for BinopKind and UnopKind enums."""
from interpreter.operator_kind import BinopKind, UnopKind


class TestBinopKind:
    def test_str_returns_symbol(self):
        assert str(BinopKind.ADD) == "+"
        assert str(BinopKind.EQ) == "=="
        assert str(BinopKind.AND) == "and"

    def test_equality_with_string(self):
        assert BinopKind.ADD == "+"
        assert BinopKind.POWER == "**"

    def test_all_vm_operators_covered(self):
        """Every operator in the VM's BINOP_TABLE must have a BinopKind."""
        from interpreter.vm.vm import Operators
        for op in Operators.BINOP_TABLE:
            assert op in [str(k) for k in BinopKind], f"Missing BinopKind for '{op}'"


class TestUnopKind:
    def test_str_returns_symbol(self):
        assert str(UnopKind.NEG) == "-"
        assert str(UnopKind.NOT) == "not"
        assert str(UnopKind.BANG) == "!"

    def test_all_vm_operators_covered(self):
        """Every unary operator the VM handles must have an UnopKind."""
        expected = {"-", "+", "not", "~", "#", "!", "!!", "&"}
        for op in expected:
            assert op in [str(k) for k in UnopKind], f"Missing UnopKind for '{op}'"
```

- [ ] **Step 2: Implement enums**

Create `interpreter/operator_kind.py`:

```python
"""Typed operator enums for BINOP and UNOP instructions."""
from enum import Enum


class BinopKind(str, Enum):
    """Binary operator — the superset of operators across all 15 frontends."""
    # Arithmetic
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"
    FLOOR_DIV = "//"
    MOD = "%"
    MOD_WORD = "mod"
    POWER = "**"
    # Comparison
    EQ = "=="
    NE = "!="
    NE_LUA = "~="
    LT = "<"
    GT = ">"
    LE = "<="
    GE = ">="
    STRICT_EQ = "==="
    # Logical
    AND = "and"
    OR = "or"
    IN = "in"
    # Bitwise
    BIT_AND = "&"
    BIT_OR = "|"
    BIT_XOR = "^"
    BIT_XOR_LUA = "~"
    LSHIFT = "<<"
    RSHIFT = ">>"
    # String concat
    CONCAT_LUA = ".."
    CONCAT_PASCAL = "."
    # Null coalescing / ternary
    NULLISH_COALESCE = "?:"
    LOGICAL_OR_SYM = "||"
    LOGICAL_AND_SYM = "&&"


class UnopKind(str, Enum):
    """Unary operator — the superset of operators across all 15 frontends."""
    NEG = "-"
    POS = "+"
    NOT = "not"
    BIT_NOT = "~"
    LEN = "#"
    BANG = "!"
    DOUBLE_BANG = "!!"
    ADDR_OF = "&"
```

- [ ] **Step 3: Run tests, verify, commit**

---

## Task 2: Wrap frontend emit sites with enum constructors (bridge)

**Files:**
- Modify: `interpreter/frontends/common/expressions.py` and all 15 frontend expression files
- Modify: `interpreter/frontends/_base.py` (if it emits BINOP/UNOP)
- Modify: `interpreter/cobol/ir_encoders.py`, `emit_context.py`, `lower_string_inspect.py`, `condition_lowering.py`, `lower_arithmetic.py`, `lower_perform.py`, `lower_search.py` — COBOL frontend also emits Binop directly

The field is still `str`. This is a no-op: `str(BinopKind.ADD)` returns `"+"`.

Pattern:
```python
# Before
operator=op  # where op is ctx.node_text(operator_node)

# After — need a lookup function
operator=resolve_binop(op)
```

Add to `interpreter/operator_kind.py`:

```python
_BINOP_LOOKUP: dict[str, BinopKind] = {str(k): k for k in BinopKind}
_UNOP_LOOKUP: dict[str, UnopKind] = {str(k): k for k in UnopKind}

def resolve_binop(op: str) -> BinopKind | str:
    """Convert a string operator to BinopKind. Returns str as-is if not found (bridge period)."""
    return _BINOP_LOOKUP.get(op, op)

def resolve_unop(op: str) -> UnopKind | str:
    """Convert a string operator to UnopKind. Returns str as-is if not found (bridge period)."""
    return _UNOP_LOOKUP.get(op, op)
```

- [ ] **Step 1: Add resolve functions and wrap common/expressions.py**
- [ ] **Step 2: Wrap all 15 frontend expression files**
- [ ] **Step 3: Run full test suite, verify, commit**

---

## Task 3: Change field types to BinopKind / UnopKind

**Files:**
- Modify: `interpreter/instructions.py` — `Binop.operator: BinopKind`, `Unop.operator: UnopKind`
- Modify: `interpreter/vm/vm.py` — `BINOP_TABLE` key type, `eval_binop`/`eval_unop` signatures
- Modify: `interpreter/handlers/arithmetic.py` — handler reads typed operator

- [ ] **Step 1: Change field types in instructions.py**

```python
class Binop(InstructionBase):
    operator: BinopKind = BinopKind.ADD
    # operands property: str(self.operator) for __str__ compat

class Unop(InstructionBase):
    operator: UnopKind = UnopKind.NEG
    # operands property: str(self.operator) for __str__ compat
```

- [ ] **Step 2: Update VM BINOP_TABLE to BinopKind keys**

```python
BINOP_TABLE: dict[BinopKind, Any] = {
    BinopKind.ADD: lambda a, b: a + b,
    BinopKind.SUB: lambda a, b: a - b,
    ...
}
```

- [ ] **Step 3: Update eval_binop/eval_unop signatures**
- [ ] **Step 4: Update _to_typed converters**
- [ ] **Step 5: Note for follow-up: `interpreter/types/coercion/binop_coercion.py` and `unop_coercion.py` have `op: str` signatures and `frozenset[str]` operator sets. These work during bridge period (BinopKind is str subtype) but should be updated to use the enum types after Task 4.**
- [ ] **Step 6: Run full test suite, verify, commit**

---

## Task 4: Remove resolve_binop/resolve_unop bridge (make strict)

**Files:**
- Modify: `interpreter/operator_kind.py` — remove fallback, raise on unknown
- Modify: Frontend emit sites — ensure all pass enum values directly

- [ ] **Step 1: Change resolve functions to raise on unknown operators**
- [ ] **Step 2: Fix any remaining string-passing sites**
- [ ] **Step 3: Run full test suite, verify, commit**

---

## Task 5: Per-language valid operator sets + lint pass

**Files:**
- Create: `interpreter/frontends/operator_sets.py` — per-language `VALID_BINOPS` and `VALID_UNOPS`
- Create: `tests/unit/test_operator_lint.py`

- [ ] **Step 1: Define per-language operator sets**

```python
VALID_BINOPS: dict[str, frozenset[BinopKind]] = {
    "python": frozenset({BinopKind.ADD, BinopKind.SUB, ..., BinopKind.POWER, BinopKind.IN}),
    "javascript": frozenset({..., BinopKind.STRICT_EQ}),
    "lua": frozenset({..., BinopKind.CONCAT_LUA, BinopKind.NE_LUA}),
    # etc.
}
```

- [ ] **Step 2: Write lint function that checks emitted IR against valid sets**
- [ ] **Step 3: Write tests that verify lint catches invalid operators**
- [ ] **Step 4: Run full test suite, verify, commit, close issue**
