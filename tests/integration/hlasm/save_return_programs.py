# pyright: standard
"""SAVE, RETURN and YREGS programs shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

CALLER = (
    "T        CSECT\n"
    "         BASR  11,0\n"
    "         USING *,11\n"
    "         LA    13,AREA\n"
    "         LA    2,102\n"
    "         LA    3,103\n"
    "         LA    4,104\n"
    "         LA    5,105\n"
    "         SR    6,6\n"
    "         LA    15,5\n"
    "         LA    8,BACK\n"
    "         BAL   14,SUB\n"
    "BACK     LA    7,0(,14)\n"
    "         SR    7,8\n"
    "         L     9,16(,13)\n"
    "         CLI   12(13),X'FF'\n"
    "         BNE   DONE\n"
    "         LA    6,1\n"
    "DONE     DS    0H\n"
    "         ABEND 1\n"
    "SUB      DS    0H\n"
    "{body}"
    "AREA     DC    18F'0'\n"
    "         END\n"
)
CLOBBER = (
    "         LA    2,1\n         LA    3,1\n         LA    4,1\n         LA    5,1\n"
)
FLAG_REGISTER = 6
CHECKED = (2, 3, 4, 5, 6, 7, 9, 15)
MARKERS = {2: 102, 3: 103, 4: 104, 5: 105}
FLAGGED = 1

type SubCase = tuple[str, Mapping[int, int]]

SUB_CASES: Mapping[str, SubCase] = {
    "whole_range_t_id_rc": (
        "         SAVE  (14,12),T,*\n"
        + CLOBBER
        + "         LA    15,9\n"
        + "         RETURN (14,12),T,RC=7\n",
        {**MARKERS, 6: FLAGGED, 7: 0, 9: 5, 15: 7},
    ),
    "rc_register_keeps_r15": (
        "         SAVE  (14,12)\n"
        + CLOBBER
        + "         LA    15,9\n"
        + "         RETURN (14,12),RC=(15)\n",
        {**MARKERS, 6: 0, 7: 0, 9: 5, 15: 9},
    ),
    "no_rc_reloads_r15": (
        "         SAVE  (14,12)\n"
        + CLOBBER
        + "         LA    15,9\n"
        + "         RETURN (14,12)\n",
        {**MARKERS, 6: 0, 7: 0, 9: 5, 15: 5},
    ),
    "partial_range_with_t_saves_14_15": (
        "         SAVE  (2,5),T\n"
        + CLOBBER
        + "         LA    15,9\n"
        + "         RETURN (2,5),T,RC=(15)\n",
        {**MARKERS, 6: FLAGGED, 7: 0, 9: 5, 15: 9},
    ),
    "range_from_r0": (
        "         SAVE  (0,12)\n" + CLOBBER + "         RETURN (0,12),RC=2\n",
        {**MARKERS, 6: 0, 7: 0, 9: 0, 15: 2},
    ),
}


def caller(body: str) -> str:
    return CALLER.format(body=body)


def machine_view(gprs: Mapping[int, int]) -> Mapping[int, int]:
    return {r: gprs[r] & 0xFFFFFFFF for r in CHECKED}


STANDARD = (
    "         YREGS\n"
    "MAIN     CSECT\n"
    "         J     GO\n"
    "SA       DS    18F\n"
    "GO       SAVE  (R14,R12),T,*\n"
    "         LR    R12,R15\n"
    "         USING MAIN,R12\n"
    "         ST    R13,SA+4\n"
    "         LA    R2,SA\n"
    "         ST    R2,8(,R13)\n"
    "         LR    R13,R2\n"
    "         L     R13,4(,R13)\n"
    "         RETURN (R14,R12),T,RC=7\n"
    "         END   MAIN\n"
)

NESTED = (
    "         YREGS\n"
    "MAIN     CSECT\n"
    "         J     GO\n"
    "SA       DS    18F\n"
    "ISA      DS    18F\n"
    "KEEP     DS    F\n"
    "BASE     DS    F\n"
    "GO       SAVE  (R14,R12)\n"
    "         LR    R12,R15\n"
    "         USING MAIN,R12\n"
    "         ST    R12,BASE\n"
    "         ST    R13,SA+4\n"
    "         LA    R2,SA\n"
    "         ST    R2,8(,R13)\n"
    "         LR    R13,R2\n"
    "         LA    R3,33\n"
    "         LA    R8,BACK\n"
    "         ST    R8,KEEP\n"
    "         BAL   R14,INNER\n"
    "BACK     L     R13,4(,R13)\n"
    "         RETURN (R14,R12),RC=(15)\n"
    "INNER    SAVE  (R14,R12)\n"
    "         ST    R13,ISA+4\n"
    "         LA    R2,ISA\n"
    "         ST    R2,8(,R13)\n"
    "         LR    R13,R2\n"
    "         LA    R3,1\n"
    "         L     R13,4(,R13)\n"
    "         RETURN (R14,R12),RC=3\n"
    "         END   MAIN\n"
)
NESTED_SPAN = (4, 156)
SA_BACK_CHAIN = 4
SA_FORWARD_CHAIN = 8
SA_RETURN = 12
ISA_OFFSET = 76
SAVED_ID_OFFSET = 84
STANDARD_SAVE_SPAN = (76, 94)
BAD_OPERANDS = (
    "MAIN     CSECT\n"
    "         SAVE  (14,99)\n"
    "         RETURN (14,12),RC=(3)\n"
    "         SAVE  (14,12),X\n"
    "         END\n"
)
BAD_OPERAND_REFUSALS = (
    ("SAVE: INVALID REGISTER", 2),
    ("RETURN: RC REGISTER MUST BE 15", 3),
    ("SAVE: SECOND OPERAND MUST BE T", 4),
)
