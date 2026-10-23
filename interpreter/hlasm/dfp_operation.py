# pyright: standard
"""The DFP operations lowering reaches through builtins, one builtin per operation and layout."""

from enum import Enum

from interpreter.func_name import FuncName
from interpreter.hlasm.dfp_layout import DfpLayout


class DfpOperation(Enum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"
    QUANTIZE = "quantize"
    REROUND = "reround"
    ROUND_TO_INTEGRAL = "round_to_integral"


def dfp_builtin_name(operation: DfpOperation, layout: DfpLayout) -> FuncName:
    return FuncName(f"__hlasm_dfp_{operation.value}_{layout.suffix}")
