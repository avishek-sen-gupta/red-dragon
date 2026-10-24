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
    "         OPEN  (X,(UPDAT))\n"
    "         END\n"
)
BAD_DCB_REFUSALS = (
    ("DCB: DSORG MUST BE PS", 2),
    ("DCB: MACRF MUST BE GM, GL, PM OR PL", 3),
    ("DCB: RECFM MUST BE F, FB, V OR VB", 4),
    ("DCB: EODAD MUST BE BELOW 16M", 5),
    ("DCB: SYNAD MUST BE BELOW 16M", 6),
    ("OPEN: OPTION MUST BE INPUT, OUTPUT OR EXTEND", 8),
)


def fixed_records(*texts: str) -> bytes:
    return b"".join(text.ljust(80).encode("cp037") for text in texts)


def variable_records(*texts: str) -> bytes:
    return b"".join(
        (len(text) + 4).to_bytes(2, "big") + bytes(2) + text.encode("cp037")
        for text in texts
    )


FIXED_INPUT = fixed_records("FIRST RECORD", "SECOND RECORD", "THIRD RECORD")
VARIABLE_INPUT = variable_records("AB", "HELLO, WORLD", "Z")

COPY_MOVE = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         SR    2,2\n"
    "         SR    9,9\n"
    "         OPEN  (INDCB,(INPUT),OUTDCB,(OUTPUT))\n"
    "         LR    7,15\n"
    "LOOP     GET   INDCB,REC\n"
    "AFTERGET LA    5,AFTERGET\n"
    "         PUT   OUTDCB,REC\n"
    "         LA    2,1(,2)\n"
    "         B     LOOP\n"
    "EOF      LR    6,14\n"
    "         CLOSE (INDCB,,OUTDCB)\n"
    "         LR    8,15\n"
    "         IC    9,INDCB+48\n"
    "         ABEND 1\n"
    "         LTORG\n"
    "REC      DS    CL80\n"
    + continued(
        "INDCB    DCB   DSORG=PS,MACRF=GM,RECFM=FB,LRECL=80,BLKSIZE=800,",
        "DDNAME=INDD,EODAD=EOF",
    )
    + continued(
        "OUTDCB   DCB   DSORG=PS,MACRF=PM,RECFM=FB,LRECL=80,BLKSIZE=800,",
        "DDNAME=OUTDD",
    )
    + "         END\n"
)
COPY_MOVE_REGISTERS = {2: 3, 7: 0, 8: 0, 9: 0}

COPY_LOCATE = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         SR    2,2\n"
    "         OPEN  (INDCB,(INPUT),OUTDCB,(OUTPUT))\n"
    "LOOP     GET   INDCB\n"
    "         LR    3,1\n"
    "         PUT   OUTDCB\n"
    "         MVC   0(80,1),0(3)\n"
    "         LA    2,1(,2)\n"
    "         B     LOOP\n"
    "EOF      CLOSE (INDCB,,OUTDCB)\n"
    "         ABEND 1\n"
    + continued(
        "INDCB    DCB   DSORG=PS,MACRF=GL,RECFM=FB,LRECL=80,BLKSIZE=800,",
        "DDNAME=INDD,EODAD=EOF",
    )
    + continued(
        "OUTDCB   DCB   DSORG=PS,MACRF=PL,RECFM=FB,LRECL=80,BLKSIZE=800,",
        "DDNAME=OUTDD",
    )
    + "         END\n"
)

COPY_VARIABLE = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         OPEN  (INDCB,(INPUT),OUTDCB,(OUTPUT))\n"
    "         GET   INDCB,REC\n"
    "         LH    4,REC\n"
    "         PUT   OUTDCB,REC\n"
    "LOOP     GET   INDCB,REC\n"
    "         PUT   OUTDCB,REC\n"
    "         B     LOOP\n"
    "EOF      CLOSE (INDCB,,OUTDCB)\n"
    "         ABEND 1\n"
    "REC      DS    CL104\n"
    + continued(
        "INDCB    DCB   DSORG=PS,MACRF=GM,RECFM=V,LRECL=104,",
        "DDNAME=INDD,EODAD=EOF",
    )
    + continued(
        "OUTDCB   DCB   DSORG=PS,MACRF=PM,RECFM=V,LRECL=104,",
        "DDNAME=OUTDD",
    )
    + "         END\n"
)
FIRST_DESCRIPTOR = 2 + 4

NO_EODAD = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         OPEN  (INDCB,(INPUT))\n"
    "         GET   INDCB,REC\n"
    "         GET   INDCB,REC\n"
    "         ABEND 1\n"
    "REC      DS    CL80\n"
    "INDCB    DCB   DSORG=PS,MACRF=GM,RECFM=F,LRECL=80,DDNAME=INDD\n"
    "         END\n"
)
NOT_OPENED = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         GET   INDCB,REC\n"
    "         ABEND 1\n"
    "REC      DS    CL80\n"
    "INDCB    DCB   DSORG=PS,MACRF=GM,RECFM=F,LRECL=80,DDNAME=INDD\n"
    "         END\n"
)

OPEN_FROM_DDS = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         OPEN  (INDCB,(INPUT),NODCB,(INPUT))\n"
    "         LR    2,15\n"
    "         LA    10,INDCB\n"
    "         USING IHADCB,10\n"
    "         IC    3,DCBOFLGS\n"
    "         IC    5,DCBRECFM\n"
    "         LH    6,DCBLRECL\n"
    "         LH    7,DCBBLKSI\n"
    "         LA    10,NODCB\n"
    "         IC    4,DCBOFLGS\n"
    "         ABEND 1\n"
    "INDCB    DCB   DSORG=PS,MACRF=GM,RECFM=F,DDNAME=INDD\n"
    "NODCB    DCB   DSORG=PS,MACRF=GM,DDNAME=NODD\n"
    "         DCBD\n"
    "         END\n"
)
OPEN_FROM_DDS_REGISTERS = {2: 8, 3: 0x10, 4: 0, 5: 0x80, 6: 80, 7: 800}
