# pyright: standard
"""Storage compare programs, one or more per mnemonic, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.load_store_programs import ABEND, HIGH_FILL, based_program

type Case = tuple[str, Mapping[int, int], int]

CC_EQUAL = 0
CC_LOW = 1
CC_HIGH = 2
CC_ZERO_DIFFERENCE = 2

COMPARE_DATA = (
    "         DS    0F\n"
    "LEN6     DC    X'AB000006'\n"
    "PAD2     DC    X'40000002'\n"
    "PAD6     DC    X'40000006'\n"
    "CMPA     DC    X'C1C2C3C4C5C6'\n"
    "CMPB     DC    X'C1C2C3E7C5C6'\n"
    "PADDED   DC    X'C1C24040'\n"
    "STRA     DC    X'C1C2C300'\n"
    "STRA2    DC    X'C1C2C300'\n"
    "STRB     DC    X'C1C2C400'\n"
    "STRC     DC    X'C1C200'\n"
    "CUSA     DC    X'E7E8C1C2C3C4'\n"
    "CUSB     DC    X'E9E6C1C2C3C5'\n"
    "BIG      DC    264X'00'\n"
)


def compare_program(body: str) -> str:
    return based_program(body, ABEND + COMPARE_DATA)


def _pairs(first: str, second: str) -> str:
    return f"         LA    2,{first}\n" f"         LA    4,{second}\n"


def _offsets(first: str, second: str) -> str:
    return (
        f"         LA    9,{first}\n"
        "         SLR   2,9\n"
        f"         LA    9,{second}\n"
        "         SLR   4,9\n"
    )


ADDRESSES_MATCH = {2: HIGH_FILL, 4: HIGH_FILL}

CHARACTER_COMPARES: Mapping[str, Case] = {
    "CLC equal": ("         CLC   SRC(8),SRC\n", {}, CC_EQUAL),
    "CLC low": ("         CLC   SRC(8),SRCP\n", {}, CC_LOW),
    "CLC high": ("         CLC   SRCP(4),SRC\n", {}, CC_HIGH),
    "CLC length 0": ("         CLC   CMPA(0),CMPB\n", {}, CC_EQUAL),
    "CLC length 4": ("         CLC   CMPB(4),CMPA\n", {}, CC_HIGH),
    "CLC 256 equal": ("         CLC   BIG(256),BIG+8\n", {}, CC_EQUAL),
    "CLC 256 last byte": (
        "         MVI   BIG+263,X'01'\n" "         CLC   BIG(256),BIG+8\n",
        {},
        CC_LOW,
    ),
}

LONG_COMPARES: Mapping[str, Case] = {
    "CLCL equal": (
        _pairs("CMPA", "CMPA") + "         LHI   3,6\n"
        "         LHI   5,6\n"
        "         CLCL  2,4\n",
        {3: HIGH_FILL, 5: HIGH_FILL},
        CC_EQUAL,
    ),
    "CLCL unequal": (
        _pairs("CMPA", "CMPB") + "         L     3,LEN6\n"
        "         LHI   5,6\n"
        "         CLCL  2,4\n",
        {3: HIGH_FILL | 0xAB000003, 5: HIGH_FILL | 3},
        CC_LOW,
    ),
    "CLCL unequal registers": (
        _pairs("CMPA", "CMPB") + "         L     3,LEN6\n"
        "         LHI   5,6\n"
        "         CLCL  2,4\n" + _offsets("CMPA+3", "CMPB+3"),
        ADDRESSES_MATCH,
        CC_ZERO_DIFFERENCE,
    ),
    "CLCL against the pad": (
        _pairs("CMPA", "CMPA") + "         LHI   3,6\n"
        "         L     5,PAD2\n"
        "         CLCL  2,4\n",
        {3: HIGH_FILL | 4, 5: HIGH_FILL | 0x40000000},
        CC_HIGH,
    ),
    "CLCL pad low": (
        _pairs("CMPA", "CMPA") + "         LHI   3,2\n"
        "         L     5,PAD6\n"
        "         CLCL  2,4\n",
        {3: HIGH_FILL, 5: HIGH_FILL | 0x40000004},
        CC_LOW,
    ),
    "CLCL pad equal": (
        _pairs("PADDED", "CMPA") + "         LHI   3,4\n"
        "         L     5,PAD2\n"
        "         CLCL  2,4\n",
        {3: HIGH_FILL, 5: HIGH_FILL | 0x40000000},
        CC_EQUAL,
    ),
    "CLCL pad equal registers": (
        _pairs("PADDED", "CMPA") + "         LHI   3,4\n"
        "         L     5,PAD2\n"
        "         CLCL  2,4\n" + _offsets("PADDED+4", "CMPA+2"),
        ADDRESSES_MATCH,
        CC_ZERO_DIFFERENCE,
    ),
    "CLCL lengths zero": (
        _pairs("CMPA", "CMPB") + "         LHI   3,0\n"
        "         LHI   5,0\n"
        "         CLCL  2,4\n",
        {3: HIGH_FILL, 5: HIGH_FILL},
        CC_EQUAL,
    ),
    "CLCLE": (
        _pairs("CMPA", "CMPA") + "         LHI   3,6\n"
        "         LHI   5,2\n"
        "         CLCLE 2,4,X'C3'\n",
        {3: HIGH_FILL | 3, 5: HIGH_FILL},
        CC_HIGH,
    ),
    "CLCLE registers": (
        _pairs("CMPA", "CMPA") + "         LHI   3,6\n"
        "         LHI   5,2\n"
        "         CLCLE 2,4,X'C3'\n" + _offsets("CMPA+3", "CMPA+2"),
        ADDRESSES_MATCH,
        CC_ZERO_DIFFERENCE,
    ),
    "CLCLE unequal": (
        _pairs("CMPA", "CMPB") + "         LHI   3,6\n"
        "         LHI   5,6\n"
        "         CLCLE 2,4,0\n",
        {3: HIGH_FILL | 3, 5: HIGH_FILL | 3},
        CC_LOW,
    ),
    "CLCLE pad equal": (
        _pairs("PADDED", "CMPA") + "         LHI   3,4\n"
        "         LHI   5,2\n"
        "         CLCLE 2,4,X'40'\n",
        {3: HIGH_FILL, 5: HIGH_FILL},
        CC_EQUAL,
    ),
    "CLCLU": (
        _pairs("CMPA", "CMPB") + "         LHI   3,6\n"
        "         LHI   5,6\n"
        "         CLCLU 2,4,0\n",
        {3: HIGH_FILL | 4, 5: HIGH_FILL | 4},
        CC_LOW,
    ),
    "CLCLU registers": (
        _pairs("CMPA", "CMPB") + "         LHI   3,6\n"
        "         LHI   5,6\n"
        "         CLCLU 2,4,0\n" + _offsets("CMPA+2", "CMPB+2"),
        ADDRESSES_MATCH,
        CC_ZERO_DIFFERENCE,
    ),
    "CLCLU pad equal": (
        _pairs("PADDED", "CMPA") + "         LHI   3,4\n"
        "         LHI   5,2\n"
        "         CLCLU 2,4,X'4040'\n",
        {3: HIGH_FILL, 5: HIGH_FILL},
        CC_EQUAL,
    ),
    "CLCLU pad high": (
        _pairs("CMPA", "PADDED") + "         LHI   3,2\n"
        "         LHI   5,4\n"
        "         CLCLU 2,4,X'4041'\n",
        {3: HIGH_FILL, 5: HIGH_FILL | 2},
        CC_HIGH,
    ),
}

STRING_COMPARES: Mapping[str, Case] = {
    "CLST equal": (
        "         LHI   0,0\n" + _pairs("STRA", "STRA2") + "         CLST  2,4\n",
        {},
        CC_EQUAL,
    ),
    "CLST equal registers": (
        "         LHI   0,0\n"
        + _pairs("STRA", "STRA2")
        + "         CLST  2,4\n"
        + _offsets("STRA", "STRA2"),
        ADDRESSES_MATCH,
        CC_ZERO_DIFFERENCE,
    ),
    "CLST first ends first": (
        "         LHI   0,0\n" + _pairs("STRC", "STRA") + "         CLST  2,4\n",
        {},
        CC_LOW,
    ),
    "CLST first ends first registers": (
        "         LHI   0,0\n"
        + _pairs("STRC", "STRA")
        + "         CLST  2,4\n"
        + _offsets("STRC+2", "STRA+2"),
        ADDRESSES_MATCH,
        CC_ZERO_DIFFERENCE,
    ),
    "CLST second ends first": (
        "         LHI   0,0\n" + _pairs("STRA", "STRC") + "         CLST  2,4\n",
        {},
        CC_HIGH,
    ),
    "CLST unequal bytes": (
        "         LHI   0,0\n" + _pairs("STRB", "STRA") + "         CLST  2,4\n",
        {},
        CC_HIGH,
    ),
    "CLST high ending character": (
        "         LHI   0,X'C4'\n" + _pairs("STRB", "STRA") + "         CLST  2,4\n",
        {},
        CC_LOW,
    ),
}

SUBSTRING_COMPARES: Mapping[str, Case] = {
    "CUSE found": (
        "         LHI   0,X'102'\n"
        "         LHI   1,X'40'\n" + _pairs("CUSA", "CUSB") + "         LHI   3,6\n"
        "         LHI   5,6\n"
        "         CUSE  2,4\n",
        {3: HIGH_FILL | 4, 5: HIGH_FILL | 4},
        CC_EQUAL,
    ),
    "CUSE found registers": (
        "         LHI   0,2\n"
        "         LHI   1,X'40'\n" + _pairs("CUSA", "CUSB") + "         LHI   3,6\n"
        "         LHI   5,6\n"
        "         CUSE  2,4\n" + _offsets("CUSA+2", "CUSB+2"),
        ADDRESSES_MATCH,
        CC_ZERO_DIFFERENCE,
    ),
    "CUSE end equal": (
        "         LHI   0,4\n"
        "         LHI   1,X'40'\n" + _pairs("CUSA", "CUSB") + "         LHI   3,5\n"
        "         LHI   5,5\n"
        "         CUSE  2,4\n",
        {3: HIGH_FILL | 3, 5: HIGH_FILL | 3},
        CC_LOW,
    ),
    "CUSE end unequal": (
        "         LHI   0,4\n"
        "         LHI   1,X'40'\n" + _pairs("CUSA", "CUSB") + "         LHI   3,6\n"
        "         LHI   5,6\n"
        "         CUSE  2,4\n",
        {3: HIGH_FILL, 5: HIGH_FILL},
        CC_HIGH,
    ),
    "CUSE pad": (
        "         LHI   0,2\n"
        "         LHI   1,X'40'\n" + _pairs("PADDED", "CMPA") + "         LHI   3,4\n"
        "         LHI   5,1\n"
        "         CUSE  2,4\n",
        {3: HIGH_FILL | 2, 5: HIGH_FILL},
        CC_EQUAL,
    ),
    "CUSE pad registers": (
        "         LHI   0,2\n"
        "         LHI   1,X'40'\n" + _pairs("PADDED", "CMPA") + "         LHI   3,4\n"
        "         LHI   5,1\n"
        "         CUSE  2,4\n" + _offsets("PADDED+2", "CMPA+1"),
        ADDRESSES_MATCH,
        CC_ZERO_DIFFERENCE,
    ),
    "CUSE zero substring": (
        "         LHI   0,0\n"
        "         LHI   1,X'40'\n" + _pairs("CUSA", "CUSB") + "         LHI   3,6\n"
        "         LHI   5,6\n"
        "         CUSE  2,4\n",
        {3: HIGH_FILL | 6, 5: HIGH_FILL | 6},
        CC_EQUAL,
    ),
    "CUSE negative length": (
        "         LHI   0,1\n"
        "         LHI   1,X'40'\n" + _pairs("CUSA", "CUSB") + "         LHI   3,-1\n"
        "         LHI   5,2\n"
        "         CUSE  2,4\n",
        {3: HIGH_FILL | 0xFFFFFFFF, 5: HIGH_FILL},
        CC_HIGH,
    ),
    "CUSE lengths zero": (
        "         LHI   0,1\n"
        "         LHI   1,X'40'\n" + _pairs("CUSA", "CUSB") + "         LHI   3,0\n"
        "         LHI   5,0\n"
        "         CUSE  2,4\n",
        {3: HIGH_FILL, 5: HIGH_FILL},
        CC_HIGH,
    ),
}

CASES: Mapping[str, Case] = {
    **CHARACTER_COMPARES,
    **LONG_COMPARES,
    **STRING_COMPARES,
    **SUBSTRING_COMPARES,
}

SPECIFICATION_EXCEPTIONS: Mapping[str, Case] = {
    "CLCLU odd length": (
        _pairs("CMPA", "CMPB") + "         LHI   3,5\n"
        "         LHI   5,6\n"
        "         CLCLU 2,4,0\n",
        {3: HIGH_FILL | 5, 5: HIGH_FILL | 6},
        CC_EQUAL,
    ),
    "CLST reserved GR0 bits": (
        "         LHI   0,X'100'\n" + _pairs("STRA", "STRB") + "         CLST  2,4\n",
        {},
        CC_EQUAL,
    ),
}
