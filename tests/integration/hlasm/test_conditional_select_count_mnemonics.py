# pyright: standard
"""The bridge resolves every load/store-on-condition and SELECT extended mnemonic to its base mnemonic and the Figure J-1 mask."""

from collections.abc import Mapping
from pathlib import Path

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.mask_operand import MaskOperand
from interpreter.frontends import get_hlasm_parser
from tests.covers import NotLanguageFeature, covers

SUFFIXES: Mapping[str, int] = {
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
BASES: Mapping[str, str] = {
    "LOC": "1,W",
    "LOCG": "1,W",
    "LOCR": "1,2",
    "LOCGR": "1,2",
    "STOC": "1,W",
    "STOCG": "1,W",
    "LOCFH": "1,W",
    "LOCFHR": "1,2",
    "LOCHI": "1,5",
    "LOCGHI": "1,5",
    "LOCHHI": "1,5",
    "STOCFH": "1,W",
    "SELR": "1,2,3",
    "SELGR": "1,2,3",
    "SELFHR": "1,2,3",
}


def _resolved(tmp_path: Path) -> Mapping[str, tuple[str, list[int]]]:
    lines = "".join(
        f"         {base + suffix:<9} {operands}\n"
        for base, operands in BASES.items()
        for suffix in SUFFIXES
    )
    source = (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        f"{lines}"
        "W        DC    F'1'\n"
        "         END\n"
    ).encode()
    parser = get_hlasm_parser()
    program = parser.read(parser.parse_to_file(source, "c.asm", tmp_path / "c.json"))
    return {
        s.mnemonic: (
            s.base_mnemonic,
            [o.value for o in s.operands if isinstance(o, MaskOperand)],
        )
        for s in program.statements
        if isinstance(s, MachineStatement) and s.base_mnemonic in BASES
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_extended_spellings_reach_their_base_mnemonic_and_mask(tmp_path: Path):
    expected = {
        base + suffix: (base, [mask])
        for base in BASES
        for suffix, mask in SUFFIXES.items()
    }

    assert _resolved(tmp_path) == expected
