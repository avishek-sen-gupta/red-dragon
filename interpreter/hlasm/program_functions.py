# pyright: standard
"""The IR functions a program's machine statements call, each defined once in its lowering: the DPD codec when any statement is a DFP instruction."""

from collections.abc import Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.statement import Statement
from interpreter.hlasm.ir_function import IrFunction
from interpreter.hlasm.opcodes.dfp_arithmetic import DFP_ARITHMETIC_LOWERINGS
from interpreter.hlasm.opcodes.dfp_codec import DFP_CODEC_FUNCTIONS
from interpreter.hlasm.opcodes.dfp_compare import DFP_COMPARE_LOWERINGS
from interpreter.hlasm.opcodes.dfp_exponent import DFP_EXPONENT_LOWERINGS
from interpreter.hlasm.opcodes.dfp_rounding import DFP_ROUNDING_LOWERINGS

DFP_MNEMONICS = frozenset(
    {
        **DFP_ARITHMETIC_LOWERINGS,
        **DFP_COMPARE_LOWERINGS,
        **DFP_EXPONENT_LOWERINGS,
        **DFP_ROUNDING_LOWERINGS,
    }
)


def _uses_dfp(statement: Statement) -> bool:
    return (
        isinstance(statement, MachineStatement)
        and statement.base_mnemonic in DFP_MNEMONICS
    )


def program_functions(statements: Sequence[Statement]) -> tuple[IrFunction, ...]:
    return DFP_CODEC_FUNCTIONS if any(map(_uses_dfp, statements)) else ()
