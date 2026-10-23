# pyright: standard
"""The bridge resolves VZERO and VONE to VGBM of their own register with an all-zero and an all-one byte mask."""

from pathlib import Path

from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.vec_reg_operand import VecRegOperand
from interpreter.frontends import get_hlasm_parser
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_vzero_and_vone_are_vgbm_of_their_register(tmp_path: Path):
    source = b"T        CSECT\n         VZERO 5\n         VONE  20\n         END\n"
    parser = get_hlasm_parser()
    program = parser.read(parser.parse_to_file(source, "v.asm", tmp_path / "v.json"))

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
