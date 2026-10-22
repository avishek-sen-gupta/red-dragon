# pyright: standard
"""Test under mask programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import HIGH_FILL

type Case = tuple[str, Mapping[int, int], int]

SOURCE = 0x01234567_89ABCDEF
CC_ZERO = 0
CC_MIXED_LEFT_ZERO = 1
CC_MIXED_LEFT_ONE = 2
CC_ONES = 3

HALFWORD_CASES: Mapping[str, tuple[tuple[str, int], ...]] = {
    "TMHH": (("0003", 3), ("0140", 2), ("0041", 1), ("0400", 0), ("0000", 0)),
    "TMHL": (("0007", 3), ("4008", 2), ("8001", 1), ("8888", 0), ("0000", 0)),
    "TMLH": (("8001", 3), ("8004", 2), ("4001", 1), ("7000", 0), ("0000", 0)),
    "TMH": (("8002", 3), ("8004", 2), ("4001", 1), ("7000", 0), ("0000", 0)),
    "TMLL": (("C000", 3), ("8010", 2), ("2001", 1), ("0010", 0), ("0000", 0)),
    "TML": (("CDEF", 3), ("8010", 2), ("2001", 1), ("0010", 0), ("0000", 0)),
}

STORAGE_CASES: Mapping[str, tuple[tuple[str, int], ...]] = {
    "TM": (("80", 3), ("81", 1), ("FF", 1), ("7F", 0), ("00", 0)),
    "TMY": (("80", 3), ("C0", 1), ("FF", 1), ("7F", 0), ("00", 0)),
}


def _register_case(mnemonic: str, mask: str, cc: int) -> tuple[str, Case]:
    return (
        f"{mnemonic} {mask}",
        (
            f"         LG    3,SRC\n         {mnemonic:<6}3,X'{mask}'\n",
            {3: SOURCE},
            cc,
        ),
    )


def _storage_case(mnemonic: str, mask: str, cc: int) -> tuple[str, Case]:
    return (
        f"{mnemonic} {mask}",
        (
            f"         {mnemonic:<6}NEG,X'{mask}'\n         L     2,NEG\n",
            {2: HIGH_FILL | 0x80000001},
            cc,
        ),
    )


LAST_STORAGE_BYTE = (
    "         TM    NEG+3,X'81'\n         L     2,NEG\n",
    {2: HIGH_FILL | 0x80000001},
    CC_MIXED_LEFT_ZERO,
)

CASES: Mapping[str, Case] = {
    "TM last byte": LAST_STORAGE_BYTE,
    **dict(
        _register_case(mnemonic, mask, cc)
        for mnemonic, cases in HALFWORD_CASES.items()
        for mask, cc in cases
    ),
    **dict(
        _storage_case(mnemonic, mask, cc)
        for mnemonic, cases in STORAGE_CASES.items()
        for mask, cc in cases
    ),
}
