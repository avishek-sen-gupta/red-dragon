"""A BINARY receiver's stored integer as IR: the PICTURE's low-order digits, signed only when the item is."""

from __future__ import annotations

from interpreter.instructions import Binop, Const, InstructionBase, Return_
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register


def build_binary_picture_digits_ir(
    func_name: str, digits: int, signed: bool
) -> list[InstructionBase]:
    value = Register("%p_value")

    def reg(role: str) -> Register:
        return Register(f"%{func_name}_{role}")

    sign = reg("sign")
    magnitude = reg("magnitude")
    body: list[InstructionBase] = [
        Const.int_(reg("zero"), 0),
        Binop(
            result_reg=reg("negative"),
            operator=resolve_binop("<"),
            left=value,
            right=reg("zero"),
        ),
        Const.int_(reg("two"), 2),
        Binop(
            result_reg=reg("twice_negative"),
            operator=resolve_binop("*"),
            left=reg("two"),
            right=reg("negative"),
        ),
        Const.int_(reg("one"), 1),
        Binop(
            result_reg=sign,
            operator=resolve_binop("-"),
            left=reg("one"),
            right=reg("twice_negative"),
        ),
        Binop(
            result_reg=reg("absolute"),
            operator=resolve_binop("*"),
            left=value,
            right=sign,
        ),
        Const.int_(reg("modulus"), 10**digits),
        Binop(
            result_reg=magnitude,
            operator=resolve_binop("%"),
            left=reg("absolute"),
            right=reg("modulus"),
        ),
    ]
    if not signed:
        return [*body, Return_(value_reg=magnitude)]
    return [
        *body,
        Binop(
            result_reg=reg("kept"),
            operator=resolve_binop("*"),
            left=magnitude,
            right=sign,
        ),
        Return_(value_reg=reg("kept")),
    ]
