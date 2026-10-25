# pyright: standard
"""PFPO lowering: GR0's word checked by an IR function, the source decoded and the result encoded by per-program IR functions holding the format dispatches, one builtin between them, the shared ladder with PFPO's own end, and GR1 written; the statement itself stays small and no SYMBOLIC is left."""

from collections.abc import Sequence

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import IrFunction
from interpreter.hlasm.opcodes.pfpo_codec import PFPO_DECODE, PFPO_ENCODE
from interpreter.instructions import CallFunction, Symbolic
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import (
    DATA,
    READ_FPC,
    SPECIFICATION,
    WRITE_FPC,
    lowered_ir,
    trace,
)

PFPO_STATEMENT_SIZE = 211


def _calls(function: IrFunction) -> list[str]:
    emitter = HlasmEmitter()
    parameters: Sequence[Register] = [
        Register(f"%p{at}") for at in range(function.arity)
    ]
    function.body(emitter, parameters)
    names = (
        str(i.func_name) for i in emitter.instructions() if isinstance(i, CallFunction)
    )
    return sorted({name for name in names if name.startswith("__hlasm_dfp_")})


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_pfpo_calls_its_functions_around_one_builtin_and_the_shared_ladder():
    assert trace("PFPO", ()) == [
        "read gpr 4+4",
        "call pfpo_valid",
        "StoreVar __hlasm_cc reg",
        "write gpr 12+4",
        SPECIFICATION,
        "read vr 64+8",
        "read vr 96+8",
        "call pfpo_decode",
        READ_FPC,
        "call pfpo_method",
        "call pfpo",
        READ_FPC,
        WRITE_FPC,
        DATA,
        "read vr 0+8",
        "read vr 32+8",
        "call pfpo_encode",
        "write vr 0+8",
        "write vr 32+8",
        "write gpr 12+4",
        WRITE_FPC,
        "StoreVar __hlasm_cc 2",
        WRITE_FPC,
        DATA,
        WRITE_FPC,
        WRITE_FPC,
        DATA,
        "StoreVar __hlasm_cc reg",
    ]
    ir = lowered_ir("PFPO", ())
    assert (len(ir), [i for i in ir if isinstance(i, Symbolic)]) == (
        PFPO_STATEMENT_SIZE,
        [],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_codec_functions_hold_every_format_s_decoding_and_encoding():
    assert (_calls(PFPO_DECODE), _calls(PFPO_ENCODE)) == (
        [
            "__hlasm_dfp_decode_extended",
            "__hlasm_dfp_decode_long",
            "__hlasm_dfp_decode_short",
        ],
        [
            "__hlasm_dfp_encode_extended",
            "__hlasm_dfp_encode_long",
            "__hlasm_dfp_encode_short",
        ],
    )
