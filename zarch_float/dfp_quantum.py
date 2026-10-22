# pyright: standard
"""The DFP quantum condition, and the constrained rounding of LFI, QUANTIZE and REROUND."""

from dataclasses import replace

from zarch_float.condition import Condition, raised
from zarch_float.dfp_result import DfpResult
from zarch_float.dfp_value import DfpValue

_CONSTRAINED = frozenset({Condition.INVALID, Condition.INEXACT, Condition.INCREMENTED})


def quantum_differs(result: DfpResult, preferred: int) -> bool:
    off_quantum = result.value.is_finite() and result.value.exponent != preferred
    return Condition.INEXACT in result.conditions or off_quantum


def with_quantum(result: DfpResult, quantum: bool) -> DfpResult:
    return replace(
        result, conditions=result.conditions | raised((Condition.QUANTUM, quantum))
    )


def constrained(result: DfpResult, source: DfpValue) -> DfpResult:
    conditions = result.conditions & _CONSTRAINED
    off_quantum = result.value.is_finite() and result.value.exponent != source.exponent
    final = conditions | raised((Condition.QUANTUM, off_quantum))
    return DfpResult(
        result.value, final, result.value, conditions - {Condition.INVALID}
    )
