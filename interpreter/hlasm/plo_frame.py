# pyright: standard
"""What one PLO function's operands are resolved against: the statement and its D2(B2) and D4(B4) addresses."""

from dataclasses import dataclass

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.register import Register


@dataclass(frozen=True)
class PloFrame:
    emitter: HlasmEmitter
    statement: MachineStatement
    second: Register
    fourth: Register
