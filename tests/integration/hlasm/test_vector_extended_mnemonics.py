# pyright: standard
"""The bridge resolves VZERO and VONE to VGBM of their own register with an all-zero and an all-one byte mask, and VACQ and VACCCQ to VAC and VACCC with their own fourth register and M5 4."""

from pathlib import Path

from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.mask_operand import MaskOperand
from hlasm_asg.program.vec_reg_operand import VecRegOperand
from interpreter.frontends import get_hlasm_parser
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import BARE_ASSEMBLY


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_vzero_and_vone_are_vgbm_of_their_register(tmp_path: Path):
    source = b"T        CSECT\n         VZERO 5\n         VONE  20\n         END\n"
    parser = get_hlasm_parser()
    program = parser.read(
        parser.parse_to_file(source, "v.asm", tmp_path / "v.json", BARE_ASSEMBLY)
    )

    assert [
        (s.mnemonic, s.base_mnemonic, s.operands)
        for s in program.statements
        if isinstance(s, MachineStatement)
    ] == [
        (
            "VZERO",
            "VGBM",
            (
                VecRegOperand(kind="VEC_REG", value=5),
                ImmOperand(kind="IMM", value=0),
            ),
        ),
        (
            "VONE",
            "VGBM",
            (
                VecRegOperand(kind="VEC_REG", value=20),
                ImmOperand(kind="IMM", value=65535),
            ),
        ),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_vacq_and_vacccq_keep_their_fourth_register_and_append_m5_4(tmp_path: Path):
    source = b"T        CSECT\n         VACQ  1,2,3,27\n         VACCCQ 5,6,7,9\n         END\n"
    parser = get_hlasm_parser()
    program = parser.read(
        parser.parse_to_file(source, "v.asm", tmp_path / "v.json", BARE_ASSEMBLY)
    )

    def registers(*numbers: int) -> tuple[VecRegOperand, ...]:
        return tuple(VecRegOperand(kind="VEC_REG", value=n) for n in numbers)

    assert [
        (s.mnemonic, s.base_mnemonic, s.operands)
        for s in program.statements
        if isinstance(s, MachineStatement)
    ] == [
        ("VACQ", "VAC", (*registers(1, 2, 3, 27), MaskOperand(kind="MASK", value=4))),
        (
            "VACCCQ",
            "VACCC",
            (*registers(5, 6, 7, 9), MaskOperand(kind="MASK", value=4)),
        ),
    ]
