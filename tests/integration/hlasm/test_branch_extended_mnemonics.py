# pyright: standard
"""The bridge resolves every branch on condition extended mnemonic to its base mnemonic and mask."""

from collections.abc import Mapping
from pathlib import Path

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.frontends import get_hlasm_parser
from interpreter.hlasm.operands import mask_operand
from tests.covers import NotLanguageFeature, covers

CONDITIONS: Mapping[str, int] = {
    "O": 1,
    "H": 2,
    "P": 2,
    "L": 4,
    "M": 4,
    "NE": 7,
    "NZ": 7,
    "E": 8,
    "Z": 8,
    "NL": 11,
    "NM": 11,
    "NH": 13,
    "NP": 13,
    "NO": 14,
}
JC_MASK = 6
JLC_MASK = 9

SPELLINGS: Mapping[str, tuple[str, int, str]] = {
    "B": ("BC", 15, "TGT"),
    "NOP": ("BC", 0, "TGT"),
    **{f"B{c}": ("BC", m, "TGT") for c, m in CONDITIONS.items()},
    "BR": ("BCR", 15, "14"),
    "NOPR": ("BCR", 0, "14"),
    **{f"B{c}R": ("BCR", m, "14") for c, m in CONDITIONS.items()},
    "BI": ("BIC", 15, "DW"),
    **{f"BI{c}": ("BIC", m, "DW") for c, m in CONDITIONS.items()},
    "BRU": ("BRC", 15, "TGT"),
    "J": ("BRC", 15, "TGT"),
    "JNOP": ("BRC", 0, "TGT"),
    "JC": ("BRC", JC_MASK, f"{JC_MASK},TGT"),
    **{f"BR{c}": ("BRC", m, "TGT") for c, m in CONDITIONS.items()},
    **{f"J{c}": ("BRC", m, "TGT") for c, m in CONDITIONS.items()},
    "BRUL": ("BRCL", 15, "TGT"),
    "JLU": ("BRCL", 15, "TGT"),
    "JLNOP": ("BRCL", 0, "TGT"),
    "JLC": ("BRCL", JLC_MASK, f"{JLC_MASK},TGT"),
    **{f"BR{c}L": ("BRCL", m, "TGT") for c, m in CONDITIONS.items()},
    **{f"JL{c}": ("BRCL", m, "TGT") for c, m in CONDITIONS.items()},
}


def _source() -> bytes:
    lines = "".join(
        f"         {spelling:<6}{operands}\n"
        for spelling, (*_, operands) in SPELLINGS.items()
    )
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        f"{lines}"
        "TGT      BR    14\n"
        "         DS    0D\n"
        "DW       DC    A(0),A(TGT)\n"
        "         END\n"
    ).encode()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_extended_spelling_reaches_its_base_mnemonic_and_mask(tmp_path: Path):
    parser = get_hlasm_parser()
    program = parser.read(
        parser.parse_to_file(_source(), "branches.asm", tmp_path / "branches.json")
    )
    resolved = {
        s.mnemonic: (s.base_mnemonic, mask_operand(s, 0))
        for s in program.statements
        if isinstance(s, MachineStatement) and s.mnemonic in SPELLINGS
    }

    assert resolved == {
        spelling: (base, mask) for spelling, (base, mask, _) in SPELLINGS.items()
    }
