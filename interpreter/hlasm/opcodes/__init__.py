# pyright: standard
"""Machine-instruction lowerings, indexed by base mnemonic."""

from collections.abc import Mapping

from interpreter.hlasm.opcodes.seed import SEED_LOWERINGS
from interpreter.hlasm.opcodes.svc import SVC_LOWERINGS
from interpreter.hlasm.statement_lowering import StatementLowering

OPCODE_LOWERINGS: Mapping[str, StatementLowering] = {**SEED_LOWERINGS, **SVC_LOWERINGS}
