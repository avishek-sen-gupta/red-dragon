# pyright: standard
"""Typed operand access: matching operands yield values, mismatches raise the typed error."""

from collections.abc import Callable

import pytest

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.hlasm_lowering_error import HlasmLoweringError
from interpreter.hlasm.inline_ir import inline_ir
from interpreter.hlasm.operands import (
    imm_operand,
    mask_operand,
    reg_operand,
    reloc_operand,
    storage_length_operand,
    storage_operand,
    vec_reg_operand,
)
from interpreter.instructions import Const
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers


def _message(accessor: Callable[[MachineStatement, int], object], index: int) -> str:
    with pytest.raises(HlasmLoweringError) as raised:
        accessor(STATEMENT, index)
    return str(raised.value)


STATEMENT = MachineStatement.model_validate(
    {
        "kind": "MACHINE",
        "section": "TEST",
        "offset": 6,
        "label": "",
        "mnemonic": "LA",
        "base_mnemonic": "LA",
        "format": "RX",
        "length": 4,
        "operands": [
            {"kind": "REG", "value": 3},
            {"kind": "MASK", "value": 8},
            {"kind": "IMM", "value": 35},
            {"kind": "STORAGE", "displacement": 4, "index": 0, "base": 12},
            {"kind": "RELOC_IMM", "section": "TEST", "offset": 20},
            {"kind": "STORAGE_LENGTH", "displacement": 2, "length": 7, "base": 9},
            {"kind": "VEC_REG", "value": 17},
        ],
        "origin": {"kind": "OPEN_CODE", "file": "t.asm", "line": 3},
    }
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_accessors_return_matching_operand_values():
    assert reg_operand(STATEMENT, 0) == 3
    assert mask_operand(STATEMENT, 1) == 8
    assert imm_operand(STATEMENT, 2) == 35
    assert storage_operand(STATEMENT, 3).base == 12
    assert reloc_operand(STATEMENT, 4).offset == 20
    assert storage_length_operand(STATEMENT, 5).length == 7
    assert vec_reg_operand(STATEMENT, 6) == 17


REG = "RegOperand(kind='REG', value=3)"
MASK = "MaskOperand(kind='MASK', value=8)"
ACCESSORS = (
    ("a register", reg_operand, 1, MASK),
    ("a mask", mask_operand, 0, REG),
    ("an immediate", imm_operand, 0, REG),
    ("a storage operand", storage_operand, 0, REG),
    ("a relocatable immediate", reloc_operand, 0, REG),
    ("a storage length operand", storage_length_operand, 0, REG),
    ("a vector register", vec_reg_operand, 0, REG),
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_mismatched_or_missing_operand_raises_error_naming_the_statement():
    where = "LA in TEST at offset 6 (t.asm:3) operand"
    messages = [
        (_message(accessor, wrong), _message(accessor, 7))
        for expected, accessor, wrong, found in ACCESSORS
    ]

    assert messages == [
        (
            f"{where} {wrong}: expected {expected}, found {found}",
            f"{where} 7: expected {expected}, found no operand",
        )
        for expected, accessor, wrong, found in ACCESSORS
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inline_ir_body_without_final_return_raises_typed_error():
    with pytest.raises(HlasmLoweringError) as bad_body:
        inline_ir(HlasmEmitter(), [Const.int_(Register("%r"), 1)], {})

    with pytest.raises(HlasmLoweringError) as empty:
        inline_ir(HlasmEmitter(), [], {})

    assert str(bad_body.value).startswith(
        "inline IR body: expected a final Return_ of a register, found Const("
    )
    assert str(empty.value) == (
        "inline IR body: expected a final Return_ of a register, found an empty body"
    )
