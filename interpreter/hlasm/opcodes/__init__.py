# pyright: standard
"""Machine-instruction lowerings, indexed by base mnemonic."""

from collections.abc import Mapping

from interpreter.hlasm.opcodes.boolean import BOOLEAN_LOWERINGS
from interpreter.hlasm.opcodes.branch_and_link import BRANCH_AND_LINK_LOWERINGS
from interpreter.hlasm.opcodes.branch_on_condition import (
    BRANCH_ON_CONDITION_LOWERINGS,
)
from interpreter.hlasm.opcodes.compare import COMPARE_LOWERINGS
from interpreter.hlasm.opcodes.load_address_immediate import (
    LOAD_ADDRESS_IMMEDIATE_LOWERINGS,
)
from interpreter.hlasm.opcodes.load_sign import LOAD_SIGN_LOWERINGS
from interpreter.hlasm.opcodes.load_store import LOAD_STORE_LOWERINGS
from interpreter.hlasm.opcodes.logical_add_subtract import (
    LOGICAL_ADD_SUBTRACT_LOWERINGS,
)
from interpreter.hlasm.opcodes.loop_branch import LOOP_BRANCH_LOWERINGS
from interpreter.hlasm.opcodes.multiply_divide import MULTIPLY_DIVIDE_LOWERINGS
from interpreter.hlasm.opcodes.shift_rotate import SHIFT_ROTATE_LOWERINGS
from interpreter.hlasm.opcodes.signed_add_subtract import (
    SIGNED_ADD_SUBTRACT_LOWERINGS,
)
from interpreter.hlasm.opcodes.svc import SVC_LOWERINGS
from interpreter.hlasm.statement_lowering import StatementLowering

OPCODE_LOWERINGS: Mapping[str, StatementLowering] = {
    **LOAD_STORE_LOWERINGS,
    **LOAD_ADDRESS_IMMEDIATE_LOWERINGS,
    **LOAD_SIGN_LOWERINGS,
    **SIGNED_ADD_SUBTRACT_LOWERINGS,
    **LOGICAL_ADD_SUBTRACT_LOWERINGS,
    **COMPARE_LOWERINGS,
    **BOOLEAN_LOWERINGS,
    **SHIFT_ROTATE_LOWERINGS,
    **MULTIPLY_DIVIDE_LOWERINGS,
    **BRANCH_ON_CONDITION_LOWERINGS,
    **BRANCH_AND_LINK_LOWERINGS,
    **LOOP_BRANCH_LOWERINGS,
    **SVC_LOWERINGS,
}
