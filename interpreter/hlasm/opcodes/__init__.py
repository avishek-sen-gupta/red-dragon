# pyright: standard
"""Machine-instruction lowerings, indexed by base mnemonic; those whose byte 1 is a data field also by that field, for EX."""

from collections.abc import Mapping

from interpreter.hlasm.field_lowering import FieldLowering
from interpreter.hlasm.opcodes.bfp_arithmetic import BFP_ARITHMETIC_LOWERINGS
from interpreter.hlasm.opcodes.bfp_class import BFP_CLASS_LOWERINGS
from interpreter.hlasm.opcodes.bfp_conversion import BFP_CONVERSION_LOWERINGS
from interpreter.hlasm.opcodes.bfp_sign import BFP_SIGN_LOWERINGS
from interpreter.hlasm.opcodes.boolean import (
    BOOLEAN_FIELD_LOWERINGS,
    BOOLEAN_LOWERINGS,
)
from interpreter.hlasm.opcodes.branch_and_link import BRANCH_AND_LINK_LOWERINGS
from interpreter.hlasm.opcodes.branch_on_condition import (
    BRANCH_ON_CONDITION_LOWERINGS,
)
from interpreter.hlasm.opcodes.compare import (
    COMPARE_FIELD_LOWERINGS,
    COMPARE_LOWERINGS,
)
from interpreter.hlasm.opcodes.compare_branch_trap import (
    COMPARE_BRANCH_TRAP_LOWERINGS,
)
from interpreter.hlasm.opcodes.conditional_select_count import (
    CONDITIONAL_SELECT_COUNT_LOWERINGS,
)
from interpreter.hlasm.opcodes.decimal_conversion import (
    DECIMAL_CONVERSION_FIELD_LOWERINGS,
    DECIMAL_CONVERSION_LOWERINGS,
)
from interpreter.hlasm.opcodes.dfp_arithmetic import DFP_ARITHMETIC_LOWERINGS
from interpreter.hlasm.opcodes.dfp_class import DFP_CLASS_LOWERINGS
from interpreter.hlasm.opcodes.dfp_compare import DFP_COMPARE_LOWERINGS
from interpreter.hlasm.opcodes.dfp_conversion import DFP_CONVERSION_LOWERINGS
from interpreter.hlasm.opcodes.dfp_decimal import DFP_DECIMAL_LOWERINGS
from interpreter.hlasm.opcodes.dfp_exponent import DFP_EXPONENT_LOWERINGS
from interpreter.hlasm.opcodes.dfp_rounding import DFP_ROUNDING_LOWERINGS
from interpreter.hlasm.opcodes.dfp_shift import DFP_SHIFT_LOWERINGS
from interpreter.hlasm.opcodes.edit import EDIT_FIELD_LOWERINGS, EDIT_LOWERINGS
from interpreter.hlasm.opcodes.floating_point_support import (
    FLOATING_POINT_SUPPORT_LOWERINGS,
)
from interpreter.hlasm.opcodes.hfp_arithmetic import HFP_ARITHMETIC_LOWERINGS
from interpreter.hlasm.opcodes.hfp_conversion import HFP_CONVERSION_LOWERINGS
from interpreter.hlasm.opcodes.hfp_sign import HFP_SIGN_LOWERINGS
from interpreter.hlasm.opcodes.high_word import HIGH_WORD_LOWERINGS
from interpreter.hlasm.opcodes.interlocked import (
    INTERLOCKED_FIELD_LOWERINGS,
    INTERLOCKED_LOWERINGS,
)
from interpreter.hlasm.opcodes.load_address_immediate import (
    LOAD_ADDRESS_IMMEDIATE_LOWERINGS,
)
from interpreter.hlasm.opcodes.load_sign import LOAD_SIGN_LOWERINGS
from interpreter.hlasm.opcodes.load_store import LOAD_STORE_LOWERINGS
from interpreter.hlasm.opcodes.logical_add_subtract import (
    LOGICAL_ADD_SUBTRACT_FIELD_LOWERINGS,
    LOGICAL_ADD_SUBTRACT_LOWERINGS,
)
from interpreter.hlasm.opcodes.loop_branch import LOOP_BRANCH_LOWERINGS
from interpreter.hlasm.opcodes.miscellaneous import (
    MISCELLANEOUS_FIELD_LOWERINGS,
    MISCELLANEOUS_LOWERINGS,
)
from interpreter.hlasm.opcodes.multiply_divide import MULTIPLY_DIVIDE_LOWERINGS
from interpreter.hlasm.opcodes.packed_arithmetic import (
    PACKED_ARITHMETIC_FIELD_LOWERINGS,
    PACKED_ARITHMETIC_LOWERINGS,
)
from interpreter.hlasm.opcodes.packed_compare_test import (
    PACKED_COMPARE_TEST_FIELD_LOWERINGS,
    PACKED_COMPARE_TEST_LOWERINGS,
)
from interpreter.hlasm.opcodes.shift_rotate import SHIFT_ROTATE_LOWERINGS
from interpreter.hlasm.opcodes.signed_add_subtract import (
    SIGNED_ADD_SUBTRACT_FIELD_LOWERINGS,
    SIGNED_ADD_SUBTRACT_LOWERINGS,
)
from interpreter.hlasm.opcodes.ss_compare import (
    SS_COMPARE_FIELD_LOWERINGS,
    SS_COMPARE_LOWERINGS,
)
from interpreter.hlasm.opcodes.ss_move import (
    SS_MOVE_FIELD_LOWERINGS,
    SS_MOVE_LOWERINGS,
)
from interpreter.hlasm.opcodes.svc import SVC_FIELD_LOWERINGS, SVC_LOWERINGS
from interpreter.hlasm.opcodes.translate import (
    TRANSLATE_FIELD_LOWERINGS,
    TRANSLATE_LOWERINGS,
)
from interpreter.hlasm.opcodes.under_mask import (
    TEST_UNDER_MASK_FIELD_LOWERINGS,
    TEST_UNDER_MASK_LOWERINGS,
)
from interpreter.hlasm.opcodes.unicode_string_search import (
    UNICODE_STRING_SEARCH_LOWERINGS,
)
from interpreter.hlasm.statement_lowering import StatementLowering

OPCODE_LOWERINGS: Mapping[str, StatementLowering] = {
    **LOAD_STORE_LOWERINGS,
    **LOAD_ADDRESS_IMMEDIATE_LOWERINGS,
    **LOAD_SIGN_LOWERINGS,
    **SIGNED_ADD_SUBTRACT_LOWERINGS,
    **LOGICAL_ADD_SUBTRACT_LOWERINGS,
    **COMPARE_LOWERINGS,
    **COMPARE_BRANCH_TRAP_LOWERINGS,
    **BOOLEAN_LOWERINGS,
    **SHIFT_ROTATE_LOWERINGS,
    **MULTIPLY_DIVIDE_LOWERINGS,
    **BRANCH_ON_CONDITION_LOWERINGS,
    **BRANCH_AND_LINK_LOWERINGS,
    **LOOP_BRANCH_LOWERINGS,
    **SVC_LOWERINGS,
    **TEST_UNDER_MASK_LOWERINGS,
    **SS_MOVE_LOWERINGS,
    **SS_COMPARE_LOWERINGS,
    **TRANSLATE_LOWERINGS,
    **CONDITIONAL_SELECT_COUNT_LOWERINGS,
    **INTERLOCKED_LOWERINGS,
    **UNICODE_STRING_SEARCH_LOWERINGS,
    **HIGH_WORD_LOWERINGS,
    **MISCELLANEOUS_LOWERINGS,
    **PACKED_ARITHMETIC_LOWERINGS,
    **PACKED_COMPARE_TEST_LOWERINGS,
    **DECIMAL_CONVERSION_LOWERINGS,
    **EDIT_LOWERINGS,
    **FLOATING_POINT_SUPPORT_LOWERINGS,
    **BFP_ARITHMETIC_LOWERINGS,
    **BFP_CLASS_LOWERINGS,
    **BFP_CONVERSION_LOWERINGS,
    **BFP_SIGN_LOWERINGS,
    **HFP_ARITHMETIC_LOWERINGS,
    **HFP_CONVERSION_LOWERINGS,
    **HFP_SIGN_LOWERINGS,
    **DFP_ARITHMETIC_LOWERINGS,
    **DFP_COMPARE_LOWERINGS,
    **DFP_EXPONENT_LOWERINGS,
    **DFP_ROUNDING_LOWERINGS,
    **DFP_CONVERSION_LOWERINGS,
    **DFP_DECIMAL_LOWERINGS,
    **DFP_SHIFT_LOWERINGS,
    **DFP_CLASS_LOWERINGS,
}

DATA_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    **SIGNED_ADD_SUBTRACT_FIELD_LOWERINGS,
    **LOGICAL_ADD_SUBTRACT_FIELD_LOWERINGS,
    **COMPARE_FIELD_LOWERINGS,
    **BOOLEAN_FIELD_LOWERINGS,
    **SVC_FIELD_LOWERINGS,
    **TEST_UNDER_MASK_FIELD_LOWERINGS,
    **SS_MOVE_FIELD_LOWERINGS,
    **SS_COMPARE_FIELD_LOWERINGS,
    **TRANSLATE_FIELD_LOWERINGS,
    **INTERLOCKED_FIELD_LOWERINGS,
    **MISCELLANEOUS_FIELD_LOWERINGS,
    **PACKED_ARITHMETIC_FIELD_LOWERINGS,
    **PACKED_COMPARE_TEST_FIELD_LOWERINGS,
    **DECIMAL_CONVERSION_FIELD_LOWERINGS,
    **EDIT_FIELD_LOWERINGS,
}
