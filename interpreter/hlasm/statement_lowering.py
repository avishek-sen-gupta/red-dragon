# pyright: standard
"""The shape of a machine instruction's lowering."""

from collections.abc import Callable

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.hlasm_emitter import HlasmEmitter

type StatementLowering = Callable[[HlasmEmitter, MachineStatement], None]
