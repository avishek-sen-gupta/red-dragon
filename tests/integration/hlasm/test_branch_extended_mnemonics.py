# pyright: standard
"""The bridge resolves every branch, compare-and-branch and compare-and-trap extended mnemonic to its base mnemonic, with its mask or its first register."""

from collections.abc import Mapping
from pathlib import Path

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.mask_operand import MaskOperand
from interpreter.frontends import get_hlasm_parser
from interpreter.hlasm.operands import mask_operand, reg_operand
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

REGISTER_SPELLINGS: Mapping[str, tuple[str, int, str]] = {
    "JCT": ("BRCT", 3, "3,TGT"),
    "JCTG": ("BRCTG", 3, "3,TGT"),
    "JXH": ("BRXH", 4, "4,6,TGT"),
    "JXHG": ("BRXHG", 4, "4,6,TGT"),
    "JXLE": ("BRXLE", 4, "4,6,TGT"),
    "JXLEG": ("BRXLG", 4, "4,6,TGT"),
    "JAS": ("BRAS", 14, "14,TGT"),
    "JASL": ("BRASL", 14, "14,TGT"),
}


def _source() -> bytes:
    lines = "".join(
        f"         {spelling:<6}{operands}\n"
        for spelling, (*_, operands) in {**SPELLINGS, **REGISTER_SPELLINGS}.items()
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
    machine = [s for s in program.statements if isinstance(s, MachineStatement)]
    masked = {
        s.mnemonic: (s.base_mnemonic, mask_operand(s, 0))
        for s in machine
        if s.mnemonic in SPELLINGS
    }
    registered = {
        s.mnemonic: (s.base_mnemonic, reg_operand(s, 0))
        for s in machine
        if s.mnemonic in REGISTER_SPELLINGS
    }

    assert masked == {
        spelling: (base, mask) for spelling, (base, mask, _) in SPELLINGS.items()
    }
    assert registered == {
        spelling: (base, r) for spelling, (base, r, _) in REGISTER_SPELLINGS.items()
    }


COMPARE_SUFFIXES: Mapping[str, int] = {
    "E": 8,
    "H": 2,
    "L": 4,
    "NE": 6,
    "NH": 12,
    "NL": 10,
}
COMPARE_BASES: Mapping[str, str] = {
    **{base: "3,4,TGT" for base in ("CRJ", "CGRJ", "CLRJ", "CLGRJ")},
    **{base: "3,7,TGT" for base in ("CIJ", "CGIJ", "CLIJ", "CLGIJ")},
    **{base: "3,4,TGT" for base in ("CRB", "CGRB", "CLRB", "CLGRB")},
    **{base: "3,7,TGT" for base in ("CIB", "CGIB", "CLIB", "CLGIB")},
    **{base: "3,4" for base in ("CRT", "CGRT", "CLRT", "CLGRT")},
    **{base: "3,7" for base in ("CIT", "CGIT", "CLFIT", "CLGIT")},
    **{base: "3,DW" for base in ("CLT", "CLGT")},
}


def _compare_source() -> bytes:
    lines = "".join(
        f"         {base + suffix:<8}{operands}\n"
        for base, operands in COMPARE_BASES.items()
        for suffix in COMPARE_SUFFIXES
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
def test_compare_branch_and_trap_spellings_reach_their_base_mnemonic_and_m3(
    tmp_path: Path,
):
    parser = get_hlasm_parser()
    program = parser.read(
        parser.parse_to_file(_compare_source(), "compares.asm", tmp_path / "c.json")
    )
    resolved = {
        s.mnemonic: (
            s.base_mnemonic,
            [o.value for o in s.operands if isinstance(o, MaskOperand)],
        )
        for s in program.statements
        if isinstance(s, MachineStatement) and s.base_mnemonic in COMPARE_BASES
    }

    assert resolved == {
        base + suffix: (base, [mask])
        for base in COMPARE_BASES
        for suffix, mask in COMPARE_SUFFIXES.items()
    }
