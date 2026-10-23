# pyright: standard
"""The HFP operations lowering reaches through builtins, one builtin per operation and source layout."""

from enum import Enum

from interpreter.func_name import FuncName
from interpreter.hlasm.hfp_layout import HfpLayout


class HfpOperation(Enum):
    ADD = "add"
    ADD_UNNORMALIZED = "add_unnormalized"
    SUBTRACT = "subtract"
    SUBTRACT_UNNORMALIZED = "subtract_unnormalized"
    COMPARE = "compare"
    MULTIPLY = "multiply"
    MULTIPLY_LENGTHENED = "multiply_lengthened"
    DIVIDE = "divide"
    HALVE = "halve"
    SQUARE_ROOT = "square_root"
    LOAD_FP_INTEGER = "load_fp_integer"
    MULTIPLY_ADD = "multiply_add"
    MULTIPLY_SUBTRACT = "multiply_subtract"
    MULTIPLY_UNNORMALIZED = "multiply_unnormalized"
    MULTIPLY_ADD_UNNORMALIZED = "multiply_add_unnormalized"


def hfp_builtin_name(operation: HfpOperation, layout: HfpLayout) -> FuncName:
    return FuncName(f"__hlasm_hfp_{operation.value}_{layout.suffix}")
