# pyright: standard
"""Programs of several modules that branch between them, and the source file each extra module is linked from."""

from pathlib import Path

from interpreter.project.source_file import SourceFile


def module(name: str, source: str) -> SourceFile:
    return SourceFile(Path(f"{name}.asm"), source.encode("ascii"))


CALLER = """\
MAIN     CSECT
         LR    12,15
         USING MAIN,12
         LR    10,14
         LA    1,PLIST
         L     15,=V(SUB)
         BALR  14,15
         LR    2,15
         L     3,SUM
         LR    14,10
         LA    15,0(2,3)
         BR    14
PLIST    DC    A(ADDEND,SUM)
ADDEND   DC    F'5'
SUM      DS    F
         LTORG
         END   MAIN
"""

CALLEE = """\
SUB      CSECT
         USING SUB,15
         LM    2,3,0(1)
         L     4,0(,2)
         AH    4,=H'37'
         ST    4,0(,3)
         LA    15,100
         BR    14
         LTORG
         END
"""

SKIPPER = """\
A        CSECT
         LR    12,15
         USING A,12
         LR    10,14
         LA    13,SAVEA
         L     15,=V(B)
         BALR  14,15
         LA    5,1
         LR    14,10
         LR    15,6
         BR    14
         ENTRY AGAIN
AGAIN    LA    8,1
         BR    14
SAVEA    DS    18F
         LTORG
         END   A
"""

MIDDLE = """\
B        CSECT
         USING B,15
         STM   14,12,12(13)
         LR    12,15
         DROP  15
         USING B,12
         LA    11,SAVEB
         ST    13,4(,11)
         LR    13,11
         L     15,=V(AGAIN)
         BALR  14,15
         L     15,=V(C)
         BALR  14,15
         LA    7,9
         BR    14
SAVEB    DS    18F
         LTORG
         END
"""

INNER = """\
C        CSECT
         LA    6,77
         L     13,4(,13)
         L     14,12(,13)
         BR    14
         END
"""

SKIPS_A_BRANCH = """\
MAIN     CSECT
         LR    12,15
         USING MAIN,12
         LR    10,14
         L     15,=V(SUB)
         BALR  14,15
         B     BAD
         LA    14,BACK
         L     15,=V(SUB2)
         BR    15
BAD      LA    3,1
BACK     LA    4,0(,15)
         LA    14,BACK2
         L     15,=V(SUB3)
         BR    15
BACK2    LR    14,10
         LA    15,5(,4)
         BR    14
         LTORG
         END   MAIN
"""

SKIPS_ONE = """\
SUB      CSECT
         B     4(,14)
         END
"""

PLAIN_RETURN = """\
SUB2     CSECT
         LA    15,3
         BR    14
         END
"""

MODE_RETURN = """\
SUB3     CSECT
         BSM   0,14
         END
"""
