# pyright: standard
"""The bridge resolves the RISBG-family extended mnemonics to their base mnemonic and the Principles of Operation immediates."""

from collections.abc import Mapping
from pathlib import Path

from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.frontends import get_hlasm_parser
from tests.covers import NotLanguageFeature, covers

ZERO_REMAINING = 0x80
TEST_RESULTS = 0x80

SPELLINGS: Mapping[str, tuple[str, str, tuple[int, ...]]] = {
    "LHHR": ("5,3", "RISBHG", (0, 31)),
    "LLCHLR": ("5,3", "RISBHG", (24, ZERO_REMAINING | 31, 32)),
    "LLHFR": ("5,3", "RISBLG", (0, 31, 32)),
    "SLLHH": ("5,3,4", "RISBHG", (0, ZERO_REMAINING | 27, 4)),
    "SRLHH": ("5,3,4", "RISBHG", (4, ZERO_REMAINING | 31, 60)),
    "SRLLH": ("5,3,4", "RISBLG", (4, ZERO_REMAINING | 31, 28)),
    "NHHR": ("5,3", "RNSBG", (0, 31)),
    "OLHR": ("5,3", "ROSBG", (32, 63, 32)),
    "XHLR": ("5,3", "RXSBG", (0, 31, 32)),
    "RNSBGT": ("5,3,40,43", "RNSBG", (TEST_RESULTS | 40, 43)),
    "RISBGZ": ("5,3,40,43,4", "RISBG", (40, ZERO_REMAINING | 43, 4)),
    "RISBGNZ": ("5,3,40,43", "RISBGN", (40, ZERO_REMAINING | 43)),
}


def _source() -> bytes:
    lines = "".join(
        f"         {spelling:<8}{operands}\n"
        for spelling, (operands, *_) in SPELLINGS.items()
    )
    return ("T        CSECT\n" f"{lines}" "         END\n").encode()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_extended_spellings_reach_their_base_mnemonic_and_immediates(tmp_path: Path):
    parser = get_hlasm_parser()
    program = parser.read(
        parser.parse_to_file(_source(), "shifts.asm", tmp_path / "shifts.json")
    )
    resolved = {
        s.mnemonic: (
            s.base_mnemonic,
            tuple(o.value for o in s.operands if isinstance(o, ImmOperand)),
        )
        for s in program.statements
        if isinstance(s, MachineStatement)
    }

    assert resolved == {
        spelling: (base, immediates)
        for spelling, (_, base, immediates) in SPELLINGS.items()
    }
