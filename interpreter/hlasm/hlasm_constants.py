# pyright: standard
"""Names and sizes of the HLASM machine model and its IR helpers."""

from interpreter.func_name import FuncName
from interpreter.register import Register
from interpreter.var_name import VarName

GPRS_VAR = VarName("__hlasm_gprs")
CC_VAR = VarName("__hlasm_cc")
PROGRAM_MASK_VAR = VarName("__hlasm_pm")

GPR_COUNT = 16
GPR_BYTES = 8
WORD_BYTES = 4
LOW_WORD_OFFSET = 4
BITS_PER_BYTE = 8
INITIAL_CC = 0
INITIAL_PROGRAM_MASK = 0

INT_TO_BINARY_BYTES = FuncName("__int_to_binary_bytes")
BINARY_BYTES_TO_INT = FuncName("__binary_bytes_to_int")
MAKE_LIST = FuncName("__make_list")
LIST_SET = FuncName("__list_set")

PARAM_VALUE = Register("%p_value")
PARAM_LEFT = Register("%p_left")
PARAM_RIGHT = Register("%p_right")

SECTION_VAR_PREFIX = "__hlasm_sect_"
