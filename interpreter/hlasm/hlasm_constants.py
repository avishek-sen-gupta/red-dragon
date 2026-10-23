# pyright: standard
"""Names and sizes of the HLASM machine model and its IR helpers."""

from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName

GPRS_VAR = VarName("__hlasm_gprs")
CC_VAR = VarName("__hlasm_cc")
PROGRAM_MASK_VAR = VarName("__hlasm_pm")
ACCESS_REGISTERS_VAR = VarName("__hlasm_ars")
FLOATING_POINT_REGISTERS_VAR = VarName("__hlasm_fprs")
FPC_VAR = VarName("__hlasm_fpc")
TOD_LAST_VAR = VarName("__hlasm_tod_last")

GPR_COUNT = 16
GPR_BYTES = 8
ACCESS_REGISTER_BYTES = 4
FLOATING_POINT_REGISTER_BYTES = 8
ONE_BYTE = 1
DOUBLEWORD_BYTES = 8
WORD_BYTES = 4
QUADWORD_BYTES = 16
OCTOWORD_BYTES = 32
HALFWORD_BYTES = 2
HALFWORD_BITS = 16
WORD_BITS = 32
DOUBLEWORD_BITS = 64
LOW_WORD_OFFSET = 4
BITS_PER_BYTE = 8
BYTE_MASK = 0xFF
HALFWORD_MASK = 0xFFFF
LOW_WORD_MASK = 0xFFFFFFFF
REGISTER_MASK = 0xFFFFFFFF_FFFFFFFF
INITIAL_CC = 0
INITIAL_PROGRAM_MASK = 0b0110
INITIAL_FPC = 0

INT_TO_BINARY_BYTES = FuncName("__int_to_binary_bytes")
BINARY_BYTES_TO_INT = FuncName("__binary_bytes_to_int")
MAKE_LIST = FuncName("__make_list")
LIST_SET = FuncName("__list_set")
LIST_GET = FuncName("__list_get")
LIST_CONCAT = FuncName("__list_concat")
BYTES_TO_STRING = FuncName("__bytes_to_string")
STRING_SLICE = FuncName("__string_slice")
STRING_ZFILL = FuncName("__string_zfill")
STRING_CONCAT_PAIR = FuncName("__string_concat_pair")
TO_STRING = FuncName("str")
PRINTLN = FuncName("println")
EBCDIC = "ebcdic"
TOD_CLOCK_BUILTIN = FuncName("__hlasm_tod_clock")
CPU_TIMER_BUILTIN = FuncName("__hlasm_cpu_timer")

PARAM_VALUE = Register("%p_value")
PARAM_LEFT = Register("%p_left")
PARAM_RIGHT = Register("%p_right")
PARAM_CARRY = Register("%p_carry")

SECTION_VAR_PREFIX = "__hlasm_sect_"

ABEND_VAR = VarName("__hlasm_abend")
TARGET_VAR = VarName("__hlasm_target")
NO_ABEND = ""
OPERATION_EXCEPTION_ABEND = "S0C1"
EXECUTE_EXCEPTION_ABEND = "S0C3"
SPECIFICATION_EXCEPTION_ABEND = "S0C6"
DATA_EXCEPTION_ABEND = "S0C7"
FIXED_POINT_OVERFLOW_ABEND = "S0C8"
FIXED_POINT_OVERFLOW_MASK = 0b1000
FIXED_POINT_DIVIDE_ABEND = "S0C9"
DECIMAL_OVERFLOW_ABEND = "S0CA"
DECIMAL_OVERFLOW_MASK = 0b0100
DECIMAL_DIVIDE_ABEND = "S0CB"
HFP_EXPONENT_OVERFLOW_ABEND = "S0CC"
HFP_EXPONENT_UNDERFLOW_ABEND = "S0CD"
HFP_SIGNIFICANCE_ABEND = "S0CE"
HFP_DIVIDE_ABEND = "S0CF"
HFP_SQUARE_ROOT_ABEND = "S0DD"
SPECIAL_OPERATION_ABEND = "S0D3"
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
BYTE_LOOP_AT_VAR = VarName("__hlasm_ss_at")
BYTES_COMBINED_VAR = VarName("__hlasm_ss_any")
SUBSTRING_START_VAR = VarName("__hlasm_cuse_start")
SPAN_VALUE_VAR = VarName("__hlasm_ss_value")
OFFSET_CARRY_VAR = VarName("__hlasm_mvo_carry")
MASK_LOOP_REST_VAR = VarName("__hlasm_bits_rest")
MASK_LOOP_RESULT_VAR = VarName("__hlasm_bits_result")
MASK_LOOP_CURSOR_VAR = VarName("__hlasm_bits_cursor")
CONVERT_SOURCE_AT_VAR = VarName("__hlasm_cu_source_at")
CONVERT_TARGET_AT_VAR = VarName("__hlasm_cu_target_at")
CONVERT_NEXT_SOURCE_VAR = VarName("__hlasm_cu_next_source")
CODE_POINT_VAR = VarName("__hlasm_cu_code_point")
CHECKSUM_VAR = VarName("__hlasm_cksm_sum")
CHECKSUM_TAIL_VAR = VarName("__hlasm_cksm_tail")
DECIMAL_VALUE_VAR = VarName("__hlasm_dec_value")
DECIMAL_INVALID_VAR = VarName("__hlasm_dec_invalid")
UNPACK_BYTE_VAR = VarName("__hlasm_unpk_byte")
PFPO_FORMAT_VAR = VarName("__hlasm_pfpo_format")
EDIT_SOURCE_AT_VAR = VarName("__hlasm_ed_source_at")
EDIT_PENDING_VAR = VarName("__hlasm_ed_pending")
EDIT_DIGIT_VAR = VarName("__hlasm_ed_digit")
EDIT_PLUS_VAR = VarName("__hlasm_ed_plus")
EDIT_SIGNIFICANCE_VAR = VarName("__hlasm_ed_significance")
EDIT_NONZERO_VAR = VarName("__hlasm_ed_nonzero")
EDIT_MARK_VAR = VarName("__hlasm_ed_mark")

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
