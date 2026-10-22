# pyright: standard
"""The BFP operations lowering reaches through builtins, one builtin per operation and layout."""

from enum import Enum

from interpreter.func_name import FuncName
from interpreter.hlasm.bfp_layout import BfpLayout


class BfpOperation(Enum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    MULTIPLY_LENGTHENED = "multiply_lengthened"
    DIVIDE = "divide"
    SQUARE_ROOT = "square_root"
    MULTIPLY_ADD = "multiply_add"
    MULTIPLY_SUBTRACT = "multiply_subtract"
    ROUND_TO_INTEGRAL = "round_to_integral"
    DIVIDE_TO_INTEGER = "divide_to_integer"


def bfp_builtin_name(operation: BfpOperation, layout: BfpLayout) -> FuncName:
    return FuncName(f"__hlasm_bfp_{operation.value}_{layout.suffix}")
