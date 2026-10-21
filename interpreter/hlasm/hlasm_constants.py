# pyright: standard
"""Names and sizes of the HLASM machine model and its IR helpers."""

from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName

GPRS_VAR = VarName("__hlasm_gprs")
CC_VAR = VarName("__hlasm_cc")
PROGRAM_MASK_VAR = VarName("__hlasm_pm")

GPR_COUNT = 16
GPR_BYTES = 8
DOUBLEWORD_BYTES = 8
WORD_BYTES = 4
LOW_WORD_OFFSET = 4
BITS_PER_BYTE = 8
INITIAL_CC = 0
INITIAL_PROGRAM_MASK = 0b0110

INT_TO_BINARY_BYTES = FuncName("__int_to_binary_bytes")
BINARY_BYTES_TO_INT = FuncName("__binary_bytes_to_int")
MAKE_LIST = FuncName("__make_list")
LIST_SET = FuncName("__list_set")
LIST_CONCAT = FuncName("__list_concat")
BYTES_TO_STRING = FuncName("__bytes_to_string")
STRING_SLICE = FuncName("__string_slice")
STRING_ZFILL = FuncName("__string_zfill")
STRING_CONCAT_PAIR = FuncName("__string_concat_pair")
TO_STRING = FuncName("str")
PRINTLN = FuncName("println")
EBCDIC = "ebcdic"

PARAM_VALUE = Register("%p_value")
PARAM_LEFT = Register("%p_left")
PARAM_RIGHT = Register("%p_right")

SECTION_VAR_PREFIX = "__hlasm_sect_"

ABEND_VAR = VarName("__hlasm_abend")
TARGET_VAR = VarName("__hlasm_target")
NO_ABEND = ""
OPERATION_EXCEPTION_ABEND = "S0C1"
SPECIFICATION_EXCEPTION_ABEND = "S0C6"
FIXED_POINT_OVERFLOW_ABEND = "S0C8"
FIXED_POINT_OVERFLOW_MASK = 0b1000
OVERFLOW_CC = 3
USER_ABEND_PREFIX = "U"
SYSTEM_ABEND_PREFIX = "S"
USER_ABEND_DIGITS = 4
SYSTEM_ABEND_DIGITS = 3
HEX_DIGITS = "0123456789ABCDEF"
NIBBLE_BITS = 4
NIBBLE_MASK = 0xF
COMPLETION_CODE_BITS = 12
COMPLETION_CODE_MASK = 0xFFF

WTO_SVC = 35
ABEND_SVC = 13
SVC_PARAMETER_REGISTER = 1
WTO_HEADER_BYTES = 4
WTO_LENGTH_BYTES = 2
WTO_TEXT_VAR = VarName("__hlasm_wto_text")
WTO_AT_VAR = VarName("__hlasm_wto_at")

RETURN_SENTINEL = 0x00000FF0
ADDRESS_MASK_31 = 0x7FFFFFFF
AMODE_31_LINK_BIT = 0x80000000
SAVE_AREA_BYTES = 72
ENTRY_SAVE_AREA_REGISTER = 13
ENTRY_RETURN_REGISTER = 14
ENTRY_ADDRESS_REGISTER = 15
ENTRY_PARAMETER_REGISTER = 1
RETURN_CODE_REGISTER = 15

DISPATCH_LABEL = CodeLabel("hl_dispatch")
RETURN_LABEL = CodeLabel("hl_return")
