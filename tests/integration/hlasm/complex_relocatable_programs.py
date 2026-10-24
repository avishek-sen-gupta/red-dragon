# pyright: standard
"""A program checking A(X-Y) and Y(X-Y) across two of its sections and A(E1-E2) across two other modules, shared by the VM tests and the z390 differential tests; it returns 7 when every constant matches the addresses it computes, 1 otherwise."""

SPANS = """\
MAIN     CSECT
         USING MAIN,15
         LA    2,X
         L     3,YADDR
         SR    2,3
         C     2,SPAN
         BNE   BAD
         CH    2,HSPAN
         BNE   BAD
         L     5,VE1
         S     5,VE2
         C     5,ESPAN
         BNE   BAD
         LA    15,7
         BR    14
BAD      LA    15,1
         BR    14
X        DC    F'0'
YADDR    DC    A(Y)
VE1      DC    V(E1)
VE2      DC    V(E2)
SPAN     DC    A(X-Y)
HSPAN    DC    Y(X-Y)
ESPAN    DC    A(E1-E2)
         DC    V(BMOD),V(CMOD)
         EXTRN E1,E2
DATA     CSECT
         DC    F'0'
Y        DC    F'0'
         END   MAIN
"""
FIRST_ENTRY = """\
BMOD     CSECT
         ENTRY E1
         DC    F'0'
E1       DC    F'0'
         END
"""
SECOND_ENTRY = """\
CMOD     CSECT
         ENTRY E2
         DC    2F'0'
E2       DC    F'0'
         END
"""
