# pyright: standard
"""Typed operand access: matching operands yield values, mismatches raise the typed error."""

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
    storage_operand,
)
from interpreter.instructions import Const
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers

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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_mismatched_or_missing_operand_raises_error_naming_the_statement():
    with pytest.raises(HlasmLoweringError) as wrong_kind:
        reg_operand(STATEMENT, 1)
    with pytest.raises(HlasmLoweringError) as missing:
        storage_operand(STATEMENT, 5)

    assert str(wrong_kind.value) == (
        "LA in TEST at offset 6 operand 1: expected a register, "
        "found MaskOperand(kind='MASK', value=8)"
    )
    assert str(missing.value) == (
        "LA in TEST at offset 6 operand 5: expected a storage operand, "
        "found no operand"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inline_ir_body_without_final_return_raises_typed_error():
    with pytest.raises(HlasmLoweringError) as bad_body:
        inline_ir(HlasmEmitter(), [Const.int_(Register("%r"), 1)], {})

    assert str(bad_body.value).startswith(
        "inline IR body: expected a final Return_ of a register, found Const("
    )
