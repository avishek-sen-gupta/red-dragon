# pyright: standard
"""Compare programs, one per mnemonic, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import FILL, HIGH_FILL

type Case = tuple[str, Mapping[int, int], int]

EQUAL = 0
LOW = 1
HIGH = 2

SET_HIGH = "         CLI   NEG,0\n"


def _from_high(body: str) -> str:
    return f"{SET_HIGH}{body}"


SIGNED: Mapping[str, Case] = {
    "C": (
        "         L     2,NEG\n" "         C     2,POS\n",
        {2: HIGH_FILL | 0x80000001},
        LOW,
    ),
    "CY": (
        _from_high("         L     3,POS\n" "         CY    3,POS\n"),
        {3: HIGH_FILL | 0x7FFF7FFE},
        EQUAL,
    ),
    "CR": (
        "         LHI   4,-1\n" "         LHI   5,1\n" "         CR    4,5\n",
        {4: HIGH_FILL | 0xFFFFFFFF, 5: HIGH_FILL | 0x00000001},
        LOW,
    ),
    "CFI": (
        "         L     5,POS\n" "         CFI   5,-1\n",
        {5: HIGH_FILL | 0x7FFF7FFE},
        HIGH,
    ),
    "CRL": (
        "         L     2,POS\n" "         CRL   2,NEG\n",
        {2: HIGH_FILL | 0x7FFF7FFE},
        HIGH,
    ),
    "CH": (
        _from_high("         LHI   2,-32768\n" "         CH    2,NEG\n"),
        {2: HIGH_FILL | 0xFFFF8000},
        EQUAL,
    ),
    "CHY": (
        "         L     3,ZERO\n" "         CHY   3,POS\n",
        {3: HIGH_FILL},
        LOW,
    ),
    "CHI": (
        "         LHI   4,5\n" "         CHI   4,-5\n",
        {4: HIGH_FILL | 0x00000005},
        HIGH,
    ),
    "CHRL": (
        "         LHI   2,-1\n" "         CHRL  2,NEG+2\n",
        {2: HIGH_FILL | 0xFFFFFFFF},
        LOW,
    ),
    "CHSI": ("         CHSI  NEG,-1\n", {2: FILL}, LOW),
    "CHHSI": (_from_high("         CHHSI NEG+2,1\n"), {2: FILL}, EQUAL),
    "CG": (
        "         LG    2,DNEG\n" "         CG    2,DPOS\n",
        {2: 0x80000000_00000081},
        LOW,
    ),
    "CGR": (
        _from_high(
            "         LGHI  3,-1\n" "         LGHI  4,-1\n" "         CGR   3,4\n"
        ),
        {3: 0xFFFFFFFF_FFFFFFFF, 4: 0xFFFFFFFF_FFFFFFFF},
        EQUAL,
    ),
    "CGRL": (
        "         LG    2,DPOS\n" "         CGRL  2,DNEG\n",
        {2: 0x7FFFFFFF_FFFFFF7E},
        HIGH,
    ),
    "CGF": (
        "         LGHI  2,-1\n" "         CGF   2,NEG\n",
        {2: 0xFFFFFFFF_FFFFFFFF},
        HIGH,
    ),
    "CGFR": (
        "         LG    3,DNEG\n" "         L     4,NEG\n" "         CGFR  3,4\n",
        {3: 0x80000000_00000081, 4: HIGH_FILL | 0x80000001},
        LOW,
    ),
    "CGFI": (
        _from_high("         LGHI  4,-1\n" "         CGFI  4,-1\n"),
        {4: 0xFFFFFFFF_FFFFFFFF},
        EQUAL,
    ),
    "CGFRL": (
        "         LGHI  2,-2\n" "         CGFRL 2,NEG\n",
        {2: 0xFFFFFFFF_FFFFFFFE},
        HIGH,
    ),
    "CGH": (
        _from_high("         LGHI  2,-32768\n" "         CGH   2,NEG\n"),
        {2: 0xFFFFFFFF_FFFF8000},
        EQUAL,
    ),
    "CGHI": (
        "         LG    3,DNEG\n" "         CGHI  3,-1\n",
        {3: 0x80000000_00000081},
        LOW,
    ),
    "CGHRL": (
        _from_high("         LGHI  2,32767\n" "         CGHRL 2,POS\n"),
        {2: 0x00000000_00007FFF},
        EQUAL,
    ),
    "CGHSI": ("         CGHSI DPOS,-1\n", {2: FILL}, HIGH),
}

LOGICAL: Mapping[str, Case] = {
    "CL": (
        "         L     2,NEG\n" "         CL    2,POS\n",
        {2: HIGH_FILL | 0x80000001},
        HIGH,
    ),
    "CLY": (
        _from_high("         L     3,ZERO\n" "         CLY   3,ZERO\n"),
        {3: HIGH_FILL},
        EQUAL,
    ),
    "CLR": (
        "         LHI   4,-1\n" "         LHI   5,1\n" "         CLR   4,5\n",
        {4: HIGH_FILL | 0xFFFFFFFF, 5: HIGH_FILL | 0x00000001},
        HIGH,
    ),
    "CLFI": (
        "         L     5,POS\n" "         CLFI  5,X'FFFFFFFF'\n",
        {5: HIGH_FILL | 0x7FFF7FFE},
        LOW,
    ),
    "CLRL": (
        "         L     2,POS\n" "         CLRL  2,NEG\n",
        {2: HIGH_FILL | 0x7FFF7FFE},
        LOW,
    ),
    "CLHRL": (
        "         LHI   2,-32768\n" "         CLHRL 2,NEG\n",
        {2: HIGH_FILL | 0xFFFF8000},
        HIGH,
    ),
    "CLFHSI": ("         CLFHSI POS,X'FFFF'\n", {2: FILL}, HIGH),
    "CLHHSI": (_from_high("         CLHHSI NEG,X'8000'\n"), {2: FILL}, EQUAL),
    "CLI": (_from_high("         CLI   NEG,X'80'\n"), {2: FILL}, EQUAL),
    "CLIY": ("         CLIY  POS,X'80'\n", {2: FILL}, LOW),
    "CLG": (
        "         LG    2,DPOS\n" "         CLG   2,DNEG\n",
        {2: 0x7FFFFFFF_FFFFFF7E},
        LOW,
    ),
    "CLGR": (
        "         LGHI  3,-1\n" "         LGHI  4,1\n" "         CLGR  3,4\n",
        {3: 0xFFFFFFFF_FFFFFFFF, 4: 1},
        HIGH,
    ),
    "CLGRL": (
        _from_high("         LG    2,DNEG\n" "         CLGRL 2,DNEG\n"),
        {2: 0x80000000_00000081},
        EQUAL,
    ),
    "CLGF": (
        "         LG    2,SRC\n" "         CLGF  2,NEG\n",
        {2: 0x01234567_89ABCDEF},
        HIGH,
    ),
    "CLGFR": (
        "         LGHI  3,5\n" "         L     4,NEG\n" "         CLGFR 3,4\n",
        {3: 5, 4: HIGH_FILL | 0x80000001},
        LOW,
    ),
    "CLGFI": (
        "         LGHI  4,-1\n" "         CLGFI 4,X'FFFFFFFF'\n",
        {4: 0xFFFFFFFF_FFFFFFFF},
        HIGH,
    ),
    "CLGFRL": (
        _from_high("         LLGF  2,NEG\n" "         CLGFRL 2,NEG\n"),
        {2: 0x00000000_80000001},
        EQUAL,
    ),
    "CLGHRL": (
        "         LG    2,SRC\n" "         CLGHRL 2,NEG\n",
        {2: 0x01234567_89ABCDEF},
        HIGH,
    ),
    "CLGHSI": ("         CLGHSI DNEG,X'FFFF'\n", {2: FILL}, HIGH),
}

UNDER_MASK: Mapping[str, Case] = {
    "CLM": (
        "         L     2,NEG\n" "         CLM   2,B'1001',NEG\n",
        {2: HIGH_FILL | 0x80000001},
        HIGH,
    ),
    "CLMY": (
        _from_high("         L     3,POS\n" "         CLMY  3,B'0110',POS+1\n"),
        {3: HIGH_FILL | 0x7FFF7FFE},
        EQUAL,
    ),
    "CLM mask 0": (
        _from_high("         L     4,NEG\n" "         CLM   4,0,POS\n"),
        {4: HIGH_FILL | 0x80000001},
        EQUAL,
    ),
    "CLMY low": (
        "         L     5,ZERO\n" "         CLMY  5,B'1100',NEG\n",
        {5: HIGH_FILL},
        LOW,
    ),
    "CLM mask 1111": (
        "         L     2,NEG\n" "         CLM   2,B'1111',POS\n",
        {2: HIGH_FILL | 0x80000001},
        HIGH,
    ),
    "CLM mask 0001": (
        "         L     2,NEG\n" "         CLM   2,B'0001',POS+3\n",
        {2: HIGH_FILL | 0x80000001},
        LOW,
    ),
    "CLM first byte decides": (
        "         L     3,POS\n" "         CLM   3,B'1010',NEG\n",
        {3: HIGH_FILL | 0x7FFF7FFE},
        LOW,
    ),
}

CASES: Mapping[str, Case] = {**SIGNED, **LOGICAL, **UNDER_MASK}

MISALIGNED = (
    "         CRL   2,NEG+2\n",
    "         CGRL  2,POS\n",
    "         CGFRL 2,NEG+2\n",
    "         CLRL  2,NEG+2\n",
    "         CLGRL 2,POS\n",
    "         CLGFRL 2,NEG+2\n",
)
