# pyright: standard
"""Programs that reach other modules through CALL, LINK, LOAD and DELETE, and those services' refusals."""

CALLER = """\
MAIN     CSECT
         LR    12,15
         USING MAIN,12
         LR    10,14
         LR    0,0
         CALL  SUB,(ADDEND,SUM),VL
         LR    2,15
         LR    7,6
         CALL  SUB,(ADDEND2,SUM2),VL,MF=(E,PLIST)
         L     3,SUM
         A     3,SUM2
         LR    14,10
         LA    15,0(2,3)
         BR    14
PLIST    CALL  ,(ADDEND,SUM),MF=L
ADDEND   DC    F'5'
ADDEND2  DC    F'1'
SUM      DS    F
SUM2     DS    F
         LTORG
         END   MAIN
"""
ADDER = """\
SUB      CSECT
         USING SUB,15
         LM    5,6,0(1)
         L     4,0(,5)
         AH    4,=H'37'
         ST    4,0(,6)
         LA    15,100
         BR    14
         LTORG
         END
"""
LOADER = """\
MAIN     CSECT
         LR    12,15
         USING MAIN,12
         LR    10,14
         LOAD  EP=SUB
         LR    7,0
         L     3,=V(SUB)
         XR    7,3
         LR    8,1
         LR    15,0
         CALL  (15)
         LR    9,15
         DELETE EP=SUB
         LR    4,15
         DELETE EP=SUB
         LR    5,15
         DELETE EP=OTHER
         LR    14,10
         BR    14
         LTORG
         END   MAIN
"""
RETURNS_23 = """\
SUB      CSECT
         LA    15,23
         BR    14
         END
"""
LINKER = """\
MAIN     CSECT
         LR    12,15
         USING MAIN,12
         LR    10,14
         LA    7,7
         LINK  EP=SUB,PARAM=(ADDEND,SUM),VL=1
         LR    14,10
         A     15,SUM
         BR    14
ADDEND   DC    F'5'
SUM      DS    F
         LTORG
         END   MAIN
"""
CLOBBERS = """\
SUB      CSECT
         USING SUB,15
         LM    5,6,0(1)
         L     4,0(,5)
         AH    4,=H'37'
         ST    4,0(,6)
         LA    7,99
         LR    9,6
         LA    15,100
         BR    14
         LTORG
         END
"""
LINK_FORMS = """\
MAIN     CSECT
         LR    12,15
         USING MAIN,12
         LR    10,14
         LINK  EPLOC=NAME
         LR    3,15
         LA    2,NAME
         LINK  EPLOC=(2)
         AR    3,15
         LA    15,CONTROL
         SVC   6
         AR    3,15
         LR    14,10
         LR    15,3
         BR    14
NAME     DC    CL8'SUB'
CONTROL  DC    A(NAME,0)
         LTORG
         END   MAIN
"""
LINKS_THEN_EXITS = """\
A        CSECT
         LR    12,15
         USING A,12
         ST    14,EXIT
         LINK  EP=B
         L     14,EXIT
         LA    15,4(,15)
         BR    14
         ENTRY ACB,ACB2
ACB      BR    14
ACB2     L     14,EXIT
         LA    15,3
         BR    14
EXIT     DS    F
         LTORG
         END   A
"""
CALLS_BACK_AND_EXITS = """\
B        CSECT
         USING B,15
         L     14,=V(ACB2)
         L     15,=V(ACB)
         BR    15
         LTORG
         END
"""
LINKS_MISSING = """\
MAIN     CSECT
         LINK  EP=nope
         BR    14
         END   MAIN
"""
LOADS_MISSING = """\
MAIN     CSECT
         LR    12,15
         USING MAIN,12
         LOAD  EP=NOPE
         BR    14
         END   MAIN
"""
LOADS_MISSING_BY_HAND = """\
MAIN     CSECT
         LR    12,15
         USING MAIN,12
         LA    15,ERR
         LA    0,NAME
         SR    1,1
         SVC   8
ERR      BR    14
NAME     DC    CL8'NOPE'
         END   MAIN
"""
LOADS_MISSING_WITH_EXIT = """\
MAIN     CSECT
         LR    12,15
         USING MAIN,12
         LOAD  EP=NOPE,ERRET=ERR
         LA    15,1
         BR    14
ERR      LR    2,1
         LR    3,15
         LA    15,9
         BR    14
         END   MAIN
"""
BAD_OPERANDS = """\
MAIN     CSECT
         CALL  SUB,(A),XL
         CALL  SUB,(A),MF=X
         CALL  ,MF=L
         CALL  ,(A)
         CALL  (16)
         LINK  EP=SUB,VL=2
         LINK  PARAM=(A)
         LINK  EPLOC=(15)
         LOAD  EPLOC=(1)
         LOAD  EP=SUB,EPLOC=NAME
         DELETE EP=TOOLONGNAME
A        DS    F
NAME     DC    CL8'SUB'
         END   MAIN
"""
BAD_OPERAND_REFUSALS = (
    ("CALL: THIRD OPERAND MUST BE VL", 2),
    ("CALL: MF MUST BE L OR (E,LIST)", 3),
    ("CALL: MF=L NEEDS A PARAMETER LIST", 4),
    ("CALL: ENTRY MISSING", 5),
    ("CALL: INVALID REGISTER", 6),
    ("LINK: VL MUST BE 1", 7),
    ("LINK: EP OR EPLOC MISSING", 8),
    ("LINK: EPLOC REGISTER MUST BE 2 TO 12", 9),
    ("LOAD: EPLOC REGISTER MUST BE 2 TO 12", 10),
    ("LOAD: EP AND EPLOC BOTH GIVEN", 11),
    ("DELETE: EP LONGER THAN 8 CHARACTERS", 12),
)
