# pyright: standard
"""Machine-instruction lowerings, indexed by base mnemonic."""

from collections.abc import Mapping

from interpreter.hlasm.opcodes.load_address_immediate import (
    LOAD_ADDRESS_IMMEDIATE_LOWERINGS,
)
from interpreter.hlasm.opcodes.load_store import LOAD_STORE_LOWERINGS
from interpreter.hlasm.opcodes.seed import SEED_LOWERINGS
from interpreter.hlasm.opcodes.signed_add_subtract import (
    SIGNED_ADD_SUBTRACT_LOWERINGS,
)
from interpreter.hlasm.opcodes.svc import SVC_LOWERINGS
from interpreter.hlasm.statement_lowering import StatementLowering

OPCODE_LOWERINGS: Mapping[str, StatementLowering] = {
    **SEED_LOWERINGS,
    **LOAD_STORE_LOWERINGS,
    **LOAD_ADDRESS_IMMEDIATE_LOWERINGS,
    **SIGNED_ADD_SUBTRACT_LOWERINGS,
    **SVC_LOWERINGS,
}
