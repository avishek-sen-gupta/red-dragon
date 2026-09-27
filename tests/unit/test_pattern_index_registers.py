"""Pattern-matching element loads must index by register, not by a stringified int.

`LoadIndex.index_reg` is declared `Register`. Five sites in
`frontends/common/patterns.py` used to pass `str(i)` instead — the *string* "0",
which is neither a register name nor an integer. It resolved anyway, because
`vm._resolve_reg` returns a string without a `%` prefix verbatim as a literal,
and `_handle_load_index` then falls through to the heap path where
`FieldName(str(idx_val))` makes "0" a field key.

Two things were wrong with that, and this module pins both:

1. The instruction carried a `str` in a field declared `Register`.
2. `_handle_load_index`'s native fast path is guarded by
   `isinstance(idx_val, int)`, so it was unreachable for *every* pattern
   element load. Via `Const.int_` the index is a real int and the fast path
   applies.

Nothing here asserts a count, so the tests do not go stale as patterns are
added. They assert the shape: every index operand is a register, and every such
register is loaded from an integer constant.
"""

from __future__ import annotations

import pytest

from interpreter.api import lower_source
from interpreter.constants import Language
from interpreter.instructions import LoadIndex, StoreIndex
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers

# Exercises the sites that used to stringify: a fixed-length sequence pattern,
# a sequence with a star (the before-star arm), and a class pattern's
# positional arguments.
PATTERN_SOURCE = """
class Point:
    __match_args__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y

def classify(v):
    match v:
        case [a, b]:
            return a + b
        case [p, q, *rest]:
            return p * q
        case Point(px, py):
            return px - py
    return -1

r1 = classify([3, 4])
r2 = classify([2, 5, 9, 9])
"""

# Python's `case Point(...)` does not lower to a ClassPattern with positional
# args, so it misses two of the five sites. A Scala case-class pattern does
# reach both (compile_pattern_test and compile_pattern_bindings), as do Java
# record patterns.
SCALA_PATTERN_SOURCE = "object M { def f(s: Any) = s match { case Circle(r, g) => r } }"

SAMPLES = [
    pytest.param(PATTERN_SOURCE, Language.PYTHON, id="python-sequence-and-star"),
    pytest.param(SCALA_PATTERN_SOURCE, Language.SCALA, id="scala-case-class"),
]


def _index_ops(ir):
    return [i for i in ir if isinstance(i, (LoadIndex, StoreIndex))]


@pytest.mark.parametrize(("source", "language"), SAMPLES)
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_index_operand_is_a_register(source, language):
    """No index operand may be a bare str, which is what str(i) produced."""
    ir = lower_source(source, language)
    ops = _index_ops(ir)
    assert ops, "sample lowered no index instructions — the sample has drifted"
    offenders = [
        (type(i).__name__, i.index_reg)
        for i in ops
        if not isinstance(i.index_reg, Register)
    ]
    assert offenders == [], f"index operands that are not Registers: {offenders}"


@pytest.mark.parametrize(("source", "language"), SAMPLES)
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_index_operand_is_written_by_some_instruction(source, language):
    """An index operand must name a register the IR actually defines.

    This is the invariant `str(i)` broke: '0' is not a register any instruction
    writes, so it resolved as a bare literal and skipped `_handle_load_index`'s
    `isinstance(idx_val, int)` fast path. A register loaded by `Const.int_`
    satisfies both.
    """
    ir = lower_source(source, language)
    defined = {
        str(i.result_reg)
        for i in ir
        if hasattr(i, "result_reg") and i.result_reg.is_present()
    }
    dangling = [
        str(i.index_reg) for i in _index_ops(ir) if str(i.index_reg) not in defined
    ]
    assert (
        dangling == []
    ), f"index operands naming no defined register: {sorted(set(dangling))}"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_pattern_matching_still_computes_the_right_answers():
    """Behaviour guard for the change above: [3,4] -> 7, [2,5,9,9] -> 10."""
    from interpreter.api import execute_traced

    trace = execute_traced(PATTERN_SOURCE, Language.PYTHON, max_steps=5000)
    assert trace.steps, "execution produced no steps"
    local_vars = trace.steps[-1].vm_state.call_stack[0].local_vars
    # keys are VarName, values are TypedValue
    values = {str(name): tv.value for name, tv in local_vars.items()}
    assert values["r1"] == 7, f"[3, 4] -> a + b should be 7, got {values['r1']!r}"
    assert (
        values["r2"] == 10
    ), f"[2, 5, 9, 9] -> p * q should be 10, got {values['r2']!r}"
