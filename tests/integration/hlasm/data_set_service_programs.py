# pyright: standard
"""DCB, DCBD, OPEN, CLOSE, GET and PUT programs shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping
from functools import reduce


def continued(first: str, rest: str) -> str:
    return f"{first.ljust(71)}X\n               {rest}\n"


DCB_IMAGE = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         LA    2,EOF\n"
    "         LA    3,ERR\n"
    "         ABEND 1\n"
    "EOF      DC    H'0'\n"
    "ERR      DC    H'0'\n"
    "MYDCB    DS    0F\n"
    + continued(
        "         DCB   DSORG=PS,MACRF=(GL,PM),RECFM=FB,LRECL=80,BLKSIZE=800,",
        "DDNAME=INDD,EODAD=EOF,SYNAD=ERR",
    )
    + "         END\n"
)
DCB_IMAGE_AT = 0x14


def dcb_image(eodad: int, synad: int) -> bytes:
    fields: Mapping[int, bytes] = {
        26: bytes([0x40, 0]),
        33: eodad.to_bytes(3, "big"),
        36: bytes([0x90]),
        40: "INDD    ".encode("cp037"),
        50: bytes([0x48, 0x50]),
        57: synad.to_bytes(3, "big"),
        62: (800).to_bytes(2, "big"),
        82: (80).to_bytes(2, "big"),
    }
    return reduce(
        lambda image, field: image[: field[0]]
        + field[1]
        + image[field[0] + len(field[1]) :],
        fields.items(),
        bytes(96),
    )


DCBD_FIELDS = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         LA    5,MYDCB\n"
    "         USING IHADCB,5\n"
    "         LH    2,DCBDSORG\n"
    "         L     3,DCBEODAD\n"
    "         IC    4,DCBRECFM\n"
    "         CLC   DCBDDNAM,=CL8'OUTDD'\n"
    "         IPM   6\n"
    "         SRL   6,28\n"
    "         IC    7,DCBOFLGS\n"
    "         LH    8,DCBMACRF\n"
    "         L     9,DCBSYNAD\n"
    "         LH    10,DCBBLKSI\n"
    "         LH    11,DCBLRECL\n"
    "         LA    13,DCBRECV+DCBRECBR+DCBOFOPN+DCBDSGPS+DCBRECF\n"
    "         ABEND 1\n"
    "         LTORG\n"
    + continued(
        "MYDCB    DCB   DSORG=PS,MACRF=PL,RECFM=VB,LRECL=104,BLKSIZE=1000,",
        "DDNAME=OUTDD",
    )
    + "         DCBD\n"
    "         END\n"
)
DCBD_REGISTERS: Mapping[int, int] = {
    2: 0x4000,
    3: 1,
    4: 0x50,
    6: 0,
    7: 0,
    8: 0x0048,
    9: 1,
    10: 1000,
    11: 104,
    13: 0x40 + 0x10 + 0x10 + 0x40 + 0x80,
}

BAD_DCBS = (
    "T        CSECT\n"
    "         DCB   DSORG=DA,DDNAME=X\n"
    "         DCB   MACRF=R,DDNAME=X\n"
    "         DCB   RECFM=U,DDNAME=X\n"
    "         DCB   DDNAME=X,EODAD=X'1000000'\n"
    "         DCB   DDNAME=X,SYNAD=16777216\n"
    "         DCB   DDNAME=X,EODAD=X'FFFFFF'\n"
    "         END\n"
)
BAD_DCB_REFUSALS = (
    ("DCB: DSORG MUST BE PS", 2),
    ("DCB: MACRF MUST BE GM, GL, PM OR PL", 3),
    ("DCB: RECFM MUST BE F, FB, V OR VB", 4),
    ("DCB: EODAD MUST BE BELOW 16M", 5),
    ("DCB: SYNAD MUST BE BELOW 16M", 6),
)
