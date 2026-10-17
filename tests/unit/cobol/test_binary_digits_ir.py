"""A BINARY receiver's stored integer in IR: scaled by the builtin, cut to the PICTURE digits and signed by IR."""

from __future__ import annotations

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.func_name import FuncName
from interpreter.instructions import Binop, CallFunction, Const
from interpreter.operator_kind import BinopKind
from interpreter.register import Register
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted


def _binary(
    decimals: int, scale: int, signed: bool, digits: int
) -> CobolTypeDescriptor:
    return CobolTypeDescriptor(
        category=CobolDataCategory.BINARY,
        total_digits=digits,
        decimal_digits=decimals,
        signed=signed,
        scale=scale,
    )


def _stored(value: ParamValue, td: CobolTypeDescriptor) -> ParamValue:
    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        (value_reg,) = registers
        return e.ctx.emit_binary_unscaled(value_reg, td, span=None)

    return run_emitted(emit, (value,))


@covers(CobolFeature.USAGE_COMP)
def test_a_binary_receiver_keeps_the_picture_digits():
    assert _stored("123.45", _binary(2, 0, True, 5)) == 12345
    assert _stored("-1.239", _binary(2, 0, True, 3)) == -123
    assert _stored("50000", _binary(0, 0, True, 9)) == 50000
    assert _stored("50000", _binary(0, 0, False, 4)) == 0
    assert _stored("1023", _binary(0, 0, True, 3)) == 23
    assert _stored("-1023.7", _binary(1, 0, True, 3)) == -237
    assert _stored("12300", _binary(0, 2, True, 3)) == 123
    assert _stored("512300", _binary(0, 2, True, 3)) == 123
    assert _stored("-1.239", _binary(2, 0, False, 3)) == 123
    assert _stored("-70717", _binary(0, 0, False, 5)) == 70717


@covers(CobolFeature.USAGE_COMP)
def test_a_symbolic_value_flows_through_the_digit_truncation():
    unscaled = "__cobol_binary_unscaled(v, 0, 0)"
    sign = f"1 BinopKind.SUB 2 BinopKind.MUL {unscaled} BinopKind.LT 0"
    magnitude = f"{unscaled} BinopKind.MUL {sign} BinopKind.MOD 1000"
    signed = _stored(SymbolicValue("v"), _binary(0, 0, True, 3))
    unsigned = _stored(SymbolicValue("v"), _binary(0, 0, False, 3))
    assert isinstance(signed, SymbolicValue)
    assert isinstance(unsigned, SymbolicValue)
    assert signed.constraints == [f"{magnitude} BinopKind.MUL {sign}"]
    assert unsigned.constraints == [magnitude]


@covers(CobolFeature.USAGE_COMP)
def test_the_builtin_only_scales_and_the_truncation_is_ir():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    ctx.emit_binary_unscaled(ctx.fresh_reg(), _binary(1, 2, True, 4), span=None)
    calls = [i for i in ctx.instructions if isinstance(i, CallFunction)]
    binops = [i.operator for i in ctx.instructions if isinstance(i, Binop)]
    consts = [i.value for i in ctx.instructions if isinstance(i, Const)]
    assert [(c.func_name, len(c.args)) for c in calls] == [
        (FuncName(BuiltinName.COBOL_BINARY_UNSCALED), 3)
    ]
    assert binops == [
        BinopKind.LT,
        BinopKind.MUL,
        BinopKind.SUB,
        BinopKind.MUL,
        BinopKind.MOD,
        BinopKind.MUL,
    ]
    assert consts == [1, 2, 0, 2, 1, 10_000]
