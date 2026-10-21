# pyright: standard
"""A bitwise connective: a binop on the left operand and the right, either of the right or the result complemented."""

from dataclasses import dataclass

from interpreter.operator_kind import BinopKind


@dataclass(frozen=True)
class BooleanConnective:
    operator: BinopKind
    complements_right: bool
    complements_result: bool


AND = BooleanConnective(BinopKind.BIT_AND, False, False)
OR = BooleanConnective(BinopKind.BIT_OR, False, False)
XOR = BooleanConnective(BinopKind.BIT_XOR, False, False)
AND_WITH_COMPLEMENT = BooleanConnective(BinopKind.BIT_AND, True, False)
OR_WITH_COMPLEMENT = BooleanConnective(BinopKind.BIT_OR, True, False)
NAND = BooleanConnective(BinopKind.BIT_AND, False, True)
NOR = BooleanConnective(BinopKind.BIT_OR, False, True)
NOT_XOR = BooleanConnective(BinopKind.BIT_XOR, False, True)
