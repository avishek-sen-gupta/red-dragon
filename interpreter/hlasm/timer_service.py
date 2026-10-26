# pyright: standard
"""SVC 47 in IR: STIMER WAIT for the binary interval, in hundredths of a second, in the fullword at R1."""

from interpreter.hlasm.hlasm_constants import ADDRESS_MASK_31, SVC_PARAMETER_REGISTER
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm_run_inputs.run_input_names import WAIT_BUILTIN
from interpreter.operator_kind import BinopKind

INTERVAL_BYTES = 4
RETURN_CODE_REGISTER = 15


def emit_stimer_wait(emitter: HlasmEmitter) -> None:
    interval_at = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(SVC_PARAMETER_REGISTER),
        emitter.int_(ADDRESS_MASK_31),
    )
    interval = emitter.load_storage(interval_at, 0, INTERVAL_BYTES)
    emitter.call(WAIT_BUILTIN, (interval,))
    emitter.store_gr32(RETURN_CODE_REGISTER, emitter.int_(0))
