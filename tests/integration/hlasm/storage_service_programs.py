# pyright: standard
"""GETMAIN, FREEMAIN, STORAGE and TIME programs shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

AREA_BYTES = 24
DOUBLEWORD_MASK = 7
PAGE_MASK = 4095
FIRST_DATA = 1234
SECOND_DATA = 5678
FIXED_DEC_TIME = 0x01112935
FIXED_BIN_TIME = 428935
FIXED_DATE = 0x0123279F

PAIR = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         LA    15,99\n"
    "{obtain1}"
    "         LR    6,15\n"
    "         LR    2,1\n"
    "{obtain2}"
    "         LR    7,1\n"
    "         MVC   0(4,2),DATA1\n"
    "         MVC   0(4,7),DATA2\n"
    "         L     3,0(,2)\n"
    "         L     8,0(,7)\n"
    "         LR    4,2\n"
    "         OR    4,7\n"
    "         LA    5,{mask}\n"
    "         NR    4,5\n"
    "         LR    5,7\n"
    "         SR    5,2\n"
    "         LPR   5,5\n"
    "         SR    9,9\n"
    "         L     10,=A({length})\n"
    "         CR    5,10\n"
    "         BL    NEAR\n"
    "         LA    9,1\n"
    "NEAR     DS    0H\n"
    "{release1}"
    "{release2}"
    "         LR    10,15\n"
    "         ABEND 1\n"
    "DATA1    DC    F'1234'\n"
    "DATA2    DC    F'5678'\n"
    "AREA1    DC    F'0'\n"
    "AREA2    DC    F'0'\n"
    "         END\n"
)


def pair(
    obtain: str, release: str, length: int = AREA_BYTES, mask: int = DOUBLEWORD_MASK
) -> str:
    return PAIR.format(
        obtain1=obtain.format(r=2, area="AREA1"),
        obtain2=obtain.format(r=7, area="AREA2"),
        release1=release.format(r=2, area="AREA1"),
        release2=release.format(r=7, area="AREA2"),
        length=length,
        mask=mask,
    )


CHECKED = (3, 4, 6, 8, 9, 10)


def pair_view(gprs: Mapping[int, int]) -> Mapping[int, int]:
    return {r: gprs[r] & 0xFFFFFFFF for r in CHECKED}


def pair_registers(r6: int, r10: int) -> Mapping[int, int]:
    return {3: FIRST_DATA, 4: 0, 6: r6, 8: SECOND_DATA, 9: 1, 10: r10}


type PairCase = tuple[str, Mapping[int, int]]

UNTOUCHED = 99
R15_WITH_SUBPOOL_9 = 0x09000000

PAIR_CASES: Mapping[str, PairCase] = {
    "getmain_r": (
        pair(
            "         GETMAIN R,LV=24\n",
            "         FREEMAIN R,LV=24,A=({r})\n",
        ),
        pair_registers(UNTOUCHED, UNTOUCHED),
    ),
    "getmain_r_rounds_the_length": (
        pair(
            "         GETMAIN R,LV=13\n",
            "         FREEMAIN R,LV=16,A=({r})\n",
            length=16,
        ),
        pair_registers(UNTOUCHED, UNTOUCHED),
    ),
    "getmain_ru": (
        pair(
            "         GETMAIN RU,LV=24\n",
            "         FREEMAIN RU,LV=24,A=({r})\n",
        ),
        pair_registers(0, 0),
    ),
    "getmain_rc": (
        pair(
            "         GETMAIN RC,LV=24\n",
            "         FREEMAIN RC,LV=24,A=({r})\n",
        ),
        pair_registers(0, 0),
    ),
    "storage": (
        pair(
            "         STORAGE OBTAIN,LENGTH=24,ADDR={area}\n",
            "         STORAGE RELEASE,LENGTH=24,ADDR={area}\n",
        ),
        pair_registers(0, 0),
    ),
    "storage_cond": (
        pair(
            "         STORAGE OBTAIN,LENGTH=24,ADDR={area},COND=YES,LOC=ANY\n",
            "         STORAGE RELEASE,LENGTH=24,ADDR={area},COND=YES\n",
        ),
        pair_registers(0, 0),
    ),
}

VM_ONLY_PAIR_CASES: Mapping[str, PairCase] = {
    "storage_page": (
        pair(
            "         STORAGE OBTAIN,LENGTH=24,ADDR={area},BNDRY=PAGE\n",
            "         STORAGE RELEASE,LENGTH=24,ADDR={area}\n",
            mask=PAGE_MASK,
        ),
        pair_registers(0, 0),
    ),
    "getmain_ru_page": (
        pair(
            "         GETMAIN RU,LV=5000,BNDRY=PAGE\n",
            "         FREEMAIN RU,LV=5000,A=({r})\n",
            length=5000,
            mask=PAGE_MASK,
        ),
        pair_registers(0, 0),
    ),
    "registers_and_subpool": (
        pair(
            "         LA    11,24\n         GETMAIN R,LV=(11),SP=5\n",
            "         LA    11,24\n         FREEMAIN R,LV=(11),A=({r}),SP=5\n",
        ),
        pair_registers(UNTOUCHED, UNTOUCHED),
    ),
    "length_and_subpool_in_r0": (
        pair(
            "         IILF  0,X'05000018'\n         GETMAIN R,LV=(0)\n",
            "         FREEMAIN R,LV=24,A=({r}),SP=5\n",
        ),
        pair_registers(UNTOUCHED, UNTOUCHED),
    ),
    "subpool_registers_match_literal_subpools": (
        pair(
            "         LA    5,9\n         GETMAIN R,LV=24,SP=(5)\n",
            "         FREEMAIN R,LV=24,A=({r}),SP=9\n",
        ),
        pair_registers(R15_WITH_SUBPOOL_9, R15_WITH_SUBPOOL_9),
    ),
    "storage_subpool_register": (
        pair(
            "         LA    5,X'109'\n"
            "         STORAGE OBTAIN,LENGTH=24,ADDR=({r}),SP=(5)\n",
            "         STORAGE RELEASE,LENGTH=24,ADDR=({r}),SP=9\n",
        ),
        pair_registers(0, 0),
    ),
    "storage_register_operands": (
        pair(
            "         LA    11,24\n"
            "         STORAGE OBTAIN,LENGTH=(11),ADDR=({r}),SP=7\n",
            "         LA    11,24\n"
            "         STORAGE RELEASE,LENGTH=(11),ADDR=({r}),SP=7\n",
        ),
        pair_registers(0, 0),
    ),
}

LAST_BYTE = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         GETMAIN RU,LV=4096,BNDRY=PAGE\n"
    "         LR    2,1\n"
    "         MVI   4095(2),X'5A'\n"
    "         SR    3,3\n"
    "         IC    3,4095(,2)\n"
    "         LR    4,2\n"
    "         N     4,=F'4095'\n"
    "         FREEMAIN RU,LV=4096,A=(2)\n"
    "         ABEND 1\n"
    "         END\n"
)

BAD_RELEASE = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "{obtain}"
    "         LR    2,1\n"
    "{release}"
    "         ABEND 1\n"
    "         END\n"
)


def bad_release(obtain: str, release: str) -> str:
    return BAD_RELEASE.format(obtain=obtain, release=release)


type BadRelease = tuple[str, str, list[tuple[int, int]]]

BAD_RELEASES: Mapping[str, BadRelease] = {
    "freemain_unknown_address": (
        bad_release(
            "         GETMAIN R,LV=24\n         LA    2,8(,1)\n",
            "         FREEMAIN R,LV=16,A=(2)\n",
        ),
        "SA0A",
        [(24, 0)],
    ),
    "freemain_wrong_length": (
        bad_release(
            "         GETMAIN R,LV=24\n",
            "         FREEMAIN R,LV=32,A=(2)\n",
        ),
        "SA0A",
        [(24, 0)],
    ),
    "freemain_twice": (
        bad_release(
            "         GETMAIN R,LV=24\n",
            "         FREEMAIN R,LV=24,A=(2)\n         FREEMAIN R,LV=24,A=(2)\n",
        ),
        "SA0A",
        [(-1, 0)],
    ),
    "freemain_wrong_subpool": (
        bad_release(
            "         GETMAIN R,LV=24,SP=1\n",
            "         FREEMAIN R,LV=24,A=(2)\n",
        ),
        "SA0A",
        [(24, 1)],
    ),
    "freemain_ru_unknown_address": (
        bad_release(
            "         GETMAIN RU,LV=24\n         LA    2,8(,1)\n",
            "         FREEMAIN RU,LV=16,A=(2)\n",
        ),
        "SA78",
        [(24, 0)],
    ),
    "storage_release_wrong_subpool": (
        bad_release(
            "         STORAGE OBTAIN,LENGTH=24,ADDR=(2),SP=3\n",
            "         STORAGE RELEASE,LENGTH=24,ADDR=(2)\n",
        ),
        "SA78",
        [(24, 3)],
    ),
    "storage_release_wrong_length": (
        bad_release(
            "         STORAGE OBTAIN,LENGTH=24,ADDR=(2)\n",
            "         STORAGE RELEASE,LENGTH=8,ADDR=(2)\n",
        ),
        "SA78",
        [(24, 0)],
    ),
}

TIME = (
    "T        CSECT\n"
    "         LA    15,99\n"
    "         TIME  DEC\n"
    "         LR    2,0\n"
    "         LR    3,1\n"
    "         LR    6,15\n"
    "         TIME  BIN\n"
    "         LR    4,0\n"
    "         LR    5,1\n"
    "         TIME  ,LINKAGE=SVC\n"
    "         LR    7,0\n"
    "         LA    0,1\n"
    "         LA    1,2\n"
    "         SVC   11\n"
    "         LR    8,0\n"
    "         SR    0,0\n"
    "         LA    1,1\n"
    "         SVC   11\n"
    "         LR    9,0\n"
    "         ABEND 1\n"
    "         END\n"
)
TIME_CHECKED = (2, 3, 4, 5, 6, 7, 8, 9)


def time_view(gprs: Mapping[int, int]) -> Mapping[int, int]:
    return {r: gprs[r] & 0xFFFFFFFF for r in TIME_CHECKED}


FIXED_TIME_REGISTERS = {
    2: FIXED_DEC_TIME,
    3: FIXED_DATE,
    4: FIXED_BIN_TIME,
    5: FIXED_DATE,
    6: 0,
    7: FIXED_DEC_TIME,
    8: FIXED_DEC_TIME,
    9: FIXED_BIN_TIME,
}

BAD_OPERANDS = (
    "T        CSECT\n"
    "         GETMAIN X,LV=8\n"
    "         GETMAIN R\n"
    "         GETMAIN R,LV=8,BNDRY=PAGE\n"
    "         GETMAIN RU,LV=8,BNDRY=QUAD\n"
    "         FREEMAIN R,LV=8\n"
    "         FREEMAIN RU,A=(2)\n"
    "         STORAGE FETCH,LENGTH=8,ADDR=(2)\n"
    "         STORAGE OBTAIN,LENGTH=8,ADDR=(2),COND=MAYBE\n"
    "         STORAGE OBTAIN,ADDR=(2)\n"
    "         STORAGE RELEASE,LENGTH=8\n"
    "         TIME  MIC\n"
    "         TIME  DEC,LINKAGE=SYSTEM\n"
    "         GETMAIN R,LV=(0),SP=5\n"
    "         GETMAIN RU,LV=8,SP=(1)\n"
    "         FREEMAIN R,LV=(1),A=(2)\n"
    "         STORAGE RELEASE,LENGTH=(1),ADDR=(2)\n"
    "         END\n"
)
BAD_OPERAND_REFUSALS = (
    ("GETMAIN: TYPE MUST BE R, RU OR RC", 2),
    ("GETMAIN: LV MISSING", 3),
    ("GETMAIN: BNDRY=PAGE NEEDS RU OR RC", 4),
    ("GETMAIN: BNDRY MUST BE DBLWD OR PAGE", 5),
    ("FREEMAIN: A MISSING", 6),
    ("FREEMAIN: LV MISSING", 7),
    ("STORAGE: FIRST OPERAND MUST BE OBTAIN OR RELEASE", 8),
    ("STORAGE: COND MUST BE YES OR NO", 9),
    ("STORAGE: LENGTH MISSING", 10),
    ("STORAGE: ADDR MISSING", 11),
    ("TIME: TYPE MUST BE DEC OR BIN", 12),
    ("TIME: LINKAGE MUST BE SVC", 13),
    ("GETMAIN: SP NOT ALLOWED WITH LV=(0)", 14),
    ("GETMAIN: SP REGISTER MUST BE 2 TO 12", 15),
    ("FREEMAIN: LV=(1) NOT ALLOWED ON A RELEASE", 16),
    ("STORAGE: LENGTH=(1) NOT ALLOWED ON A RELEASE", 17),
)
