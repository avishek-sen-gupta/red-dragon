# pyright: standard
"""Per-language valid operator sets and lint pass.

Each language frontend may only emit operators from its valid set.
The lint_operators() function checks emitted IR and reports violations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from interpreter.instructions import Binop, InstructionBase, Unop
from interpreter.ir import Opcode
from interpreter.operator_kind import BinopKind, UnopKind

# ── Per-language valid binary operators ───────────────────────────

# Derived empirically by compiling representative programs through each
# frontend and recording the emitted operators.  Includes operators from
# common/ and _base.py (string interpolation "+", for-loop "<"/"+", etc.).

_C_LIKE_BINOPS: frozenset[BinopKind] = frozenset(
    {
        BinopKind.ADD,
        BinopKind.SUB,
        BinopKind.MUL,
        BinopKind.DIV,
        BinopKind.MOD,
        BinopKind.EQ,
        BinopKind.NE,
        BinopKind.LT,
        BinopKind.GT,
        BinopKind.LE,
        BinopKind.GE,
        BinopKind.LOGICAL_AND_SYM,
        BinopKind.LOGICAL_OR_SYM,
        BinopKind.BIT_AND,
        BinopKind.BIT_OR,
        BinopKind.BIT_XOR,
        BinopKind.LSHIFT,
        BinopKind.RSHIFT,
    }
)

VALID_BINOPS: dict[str, frozenset[BinopKind]] = {
    "python": frozenset(
        {
            BinopKind.ADD,
            BinopKind.SUB,
            BinopKind.MUL,
            BinopKind.DIV,
            BinopKind.FLOOR_DIV,
            BinopKind.MOD,
            BinopKind.POWER,
            BinopKind.EQ,
            BinopKind.NE,
            BinopKind.LT,
            BinopKind.GT,
            BinopKind.LE,
            BinopKind.GE,
            BinopKind.AND,
            BinopKind.OR,
            BinopKind.IN,
            BinopKind.BIT_AND,
            BinopKind.BIT_OR,
            BinopKind.BIT_XOR,
            BinopKind.LSHIFT,
            BinopKind.RSHIFT,
        }
    ),
    "java": _C_LIKE_BINOPS,
    "javascript": _C_LIKE_BINOPS | {BinopKind.POWER, BinopKind.STRICT_EQ},
    "typescript": _C_LIKE_BINOPS | {BinopKind.POWER, BinopKind.STRICT_EQ},
    "kotlin": frozenset(
        {
            BinopKind.ADD,
            BinopKind.SUB,
            BinopKind.MUL,
            BinopKind.DIV,
            BinopKind.MOD,
            BinopKind.EQ,
            BinopKind.NE,
            BinopKind.LT,
            BinopKind.GT,
            BinopKind.LE,
            BinopKind.GE,
            BinopKind.LOGICAL_AND_SYM,
            BinopKind.LOGICAL_OR_SYM,
            BinopKind.NULLISH_COALESCE,
            BinopKind.BIT_AND,
            BinopKind.BIT_OR,
            BinopKind.BIT_XOR,
            BinopKind.LSHIFT,
            BinopKind.RSHIFT,
        }
    ),
    "ruby": _C_LIKE_BINOPS | {BinopKind.POWER},
    "lua": frozenset(
        {
            BinopKind.ADD,
            BinopKind.SUB,
            BinopKind.MUL,
            BinopKind.DIV,
            BinopKind.FLOOR_DIV,
            BinopKind.MOD,
            BinopKind.EQ,
            BinopKind.NE_LUA,
            BinopKind.LT,
            BinopKind.GT,
            BinopKind.LE,
            BinopKind.GE,
            BinopKind.AND,
            BinopKind.OR,
            BinopKind.BIT_XOR,
            BinopKind.BIT_XOR_LUA,
            BinopKind.BIT_AND,
            BinopKind.BIT_OR,
            BinopKind.LSHIFT,
            BinopKind.RSHIFT,
            BinopKind.CONCAT_LUA,
        }
    ),
    "go": _C_LIKE_BINOPS,
    "rust": _C_LIKE_BINOPS,
    "c": _C_LIKE_BINOPS,
    "cpp": _C_LIKE_BINOPS,
    "csharp": _C_LIKE_BINOPS | {BinopKind.NULLISH_COALESCE_CSHARP},
    "php": _C_LIKE_BINOPS | {BinopKind.POWER, BinopKind.STRICT_EQ},
    "pascal": frozenset(
        {
            BinopKind.ADD,
            BinopKind.SUB,
            BinopKind.MUL,
            BinopKind.DIV,
            BinopKind.MOD_WORD,
            BinopKind.EQ,
            BinopKind.NE,
            BinopKind.LT,
            BinopKind.GT,
            BinopKind.LE,
            BinopKind.GE,
            BinopKind.AND,
            BinopKind.OR,
            BinopKind.BIT_AND,
            BinopKind.BIT_OR,
            BinopKind.BIT_XOR,
            BinopKind.CONCAT_PASCAL,
        }
    ),
    "scala": _C_LIKE_BINOPS,
}


# ── Per-language valid unary operators ────────────────────────────

_C_LIKE_UNOPS: frozenset[UnopKind] = frozenset(
    {
        UnopKind.NEG,
        UnopKind.BANG,
        UnopKind.BIT_NOT,
    }
)

VALID_UNOPS: dict[str, frozenset[UnopKind]] = {
    "python": frozenset({UnopKind.NEG, UnopKind.POS, UnopKind.NOT, UnopKind.BIT_NOT}),
    "java": _C_LIKE_UNOPS,
    "javascript": _C_LIKE_UNOPS,
    "typescript": _C_LIKE_UNOPS,
    "kotlin": frozenset({UnopKind.NEG, UnopKind.BANG, UnopKind.DOUBLE_BANG}),
    "ruby": frozenset({UnopKind.NEG, UnopKind.BANG}),
    "lua": frozenset({UnopKind.NEG, UnopKind.NOT, UnopKind.LEN, UnopKind.BIT_NOT}),
    "go": frozenset(
        {UnopKind.NEG, UnopKind.BANG, UnopKind.CHAN_RECEIVE, UnopKind.BIT_NOT}
    ),
    "rust": frozenset({UnopKind.NEG, UnopKind.BANG, UnopKind.ADDR_OF}),
    "c": frozenset({UnopKind.NEG, UnopKind.BANG, UnopKind.BIT_NOT, UnopKind.ADDR_OF}),
    "cpp": frozenset({UnopKind.NEG, UnopKind.BANG, UnopKind.BIT_NOT, UnopKind.ADDR_OF}),
    "csharp": _C_LIKE_UNOPS,
    "php": _C_LIKE_UNOPS,
    "pascal": frozenset({UnopKind.NEG, UnopKind.NOT}),
    "scala": frozenset({UnopKind.NEG, UnopKind.BANG}),
}


# ── Lint pass ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class OperatorViolation:
    """A single invalid-operator finding."""

    kind: str  # "binop" or "unop"
    operator: BinopKind | UnopKind
    instruction_index: int


def lint_operators(
    instructions: Sequence[InstructionBase],
    language: str,
) -> list[OperatorViolation]:
    """Check that every BINOP/UNOP operator is valid for the given language.

    Returns a list of violations (empty = clean).
    """
    valid_binops = VALID_BINOPS.get(language, frozenset())
    valid_unops = VALID_UNOPS.get(language, frozenset())
    violations: list[OperatorViolation] = []

    for idx, inst in enumerate(instructions):
        if inst.opcode == Opcode.BINOP and isinstance(inst, Binop):  # type: ignore[union-attr]  # see red-dragon-tvis
            if (
                isinstance(inst.operator, BinopKind)
                and inst.operator not in valid_binops
            ):
                violations.append(
                    OperatorViolation(
                        kind="binop", operator=inst.operator, instruction_index=idx
                    )
                )
        elif inst.opcode == Opcode.UNOP and isinstance(inst, Unop):  # type: ignore[union-attr]  # see red-dragon-tvis
            if isinstance(inst.operator, UnopKind) and inst.operator not in valid_unops:
                violations.append(
                    OperatorViolation(
                        kind="unop", operator=inst.operator, instruction_index=idx
                    )
                )

    return violations
