# pyright: standard
"""Macro-language programs, one per feature, shared by the VM tests and the z390 differential tests."""

from collections.abc import Mapping

from tests.integration.hlasm.hlasm_machine import HlasmMachine

LOW_WORD = 0xFFFFFFFF
COMPLETED = "U0001"

USING_PROGRAMS: Mapping[str, tuple[str, Mapping[int, int]]] = {
    "DSECT labeled and dependent USING": (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LA    3,REC\n"
        "         USING RECD,3\n"
        "         L     4,RF2\n"
        "         LA    5,REC2\n"
        "OUT      USING RECD,5\n"
        "         L     6,OUT.RF2\n"
        "         L     7,RF1\n"
        "         USING INNERD,RINNER\n"
        "         L     8,IF2\n"
        "         LA    9,L'RINNER\n"
        "         ABEND 1\n"
        "REC      DC    F'1',F'2',F'3',F'4'\n"
        "REC2     DC    F'5',F'6',F'7',F'8'\n"
        "RECD     DSECT\n"
        "RF1      DS    F\n"
        "RF2      DS    F\n"
        "RINNER   DS    XL8\n"
        "INNERD   DSECT\n"
        "IF1      DS    F\n"
        "IF2      DS    F\n"
        "         END\n",
        {4: 2, 6: 6, 7: 1, 8: 4, 9: 8},
    ),
    "S-constant literals pooled across LOCTR and ORG": (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LH    2,=S(FLD)\n"
        "         J     GO\n"
        "P1       LOCTR\n"
        "         LTORG\n"
        "T        LOCTR\n"
        "GO       LA    11,2(,12)\n"
        "         DROP  12\n"
        "         USING T+4,11\n"
        "         LH    3,=S(FLD+1)\n"
        "         J     GO2\n"
        "P1       LOCTR\n"
        "         LTORG\n"
        "T        LOCTR\n"
        "         ORG   *+8\n"
        "GO2      DS    0H\n"
        "         DROP  11\n"
        "         USING T+2,12\n"
        "         LH    4,=S(FLD+2)\n"
        "         ABEND 1\n"
        "FLD      DC    F'0'\n"
        "         END\n",
        {2: 0xFFFFC026, 3: 0xFFFFB025, 4: 0xFFFFC028},
    ),
}


STDOUT_PROGRAMS: Mapping[str, tuple[str, str]] = {
    "length scale integer and defined attributes": (
        "         MACRO\n"
        "         ATTR  &S\n"
        "         LCLC  &T\n"
        "         LCLA  &L,&SC,&I\n"
        "         LCLB  &D\n"
        "&T       SETC  T'&S\n"
        "&L       SETA  L'&S\n"
        "&SC      SETA  S'&S\n"
        "&I       SETA  I'&S\n"
        "&D       SETB  (D'&S)\n"
        "         WTO   '&S T=&T L=&L S=&SC I=&I D=&D'\n"
        "         MEND\n"
        "MAIN     CSECT\n"
        "         J     GO\n"
        "PK       DC    PL5'1.25'\n"
        "ZN       DC    ZL6'12.345'\n"
        "GO       DS    0H\n"
        "         ATTR  PK\n"
        "         ATTR  ZN\n"
        "         ATTR  FW\n"
        "         ATTR  HW\n"
        "         ATTR  FX\n"
        "         ATTR  FL\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "FW       DC    F'1'\n"
        "HW       DC    HS4'2'\n"
        "FX       DC    FS8'3'\n"
        "FL       DC    D'1.5'\n"
        "         END   MAIN\n",
        "PK T=P L=5 S=2 I=7 D=1\n"
        "ZN T=Z L=6 S=3 I=3 D=1\n"
        "FW T=F L=4 S=0 I=31 D=0\n"
        "HW T=H L=2 S=4 I=11 D=0\n"
        "FX T=F L=4 S=8 I=23 D=0\n"
        "FL T=D L=8 S=0 I=14 D=0\n",
    ),
    "type and opcode attributes": (
        "         MACRO\n"
        "         TYPE  &S,&N\n"
        "         LCLC  &T\n"
        "&T       SETC  T'&S\n"
        "         WTO   '&N T=&T'\n"
        "         MEND\n"
        "         MACRO\n"
        "         OPER  &S\n"
        "         LCLC  &O\n"
        "&O       SETC  O'&S\n"
        "         WTO   '&S O=&O'\n"
        "         MEND\n"
        "MAIN     CSECT\n"
        "         TYPE  XX,XX\n"
        "         TYPE  AD,AD\n"
        "         TYPE  MAIN,MAIN\n"
        "         TYPE  LAB,LAB\n"
        "         TYPE  EQ,EQ\n"
        "         TYPE  12,N12\n"
        "         TYPE  'Q',QUOTED\n"
        "         TYPE  NOPE,NOPE\n"
        "         TYPE  DS1,DS1\n"
        "         TYPE  ,OMITTED\n"
        "         OPER  LR\n"
        "         OPER  WTO\n"
        "         OPER  DC\n"
        "         OPER  NOPE\n"
        "         SR    15,15\n"
        "LAB      BR    14\n"
        "XX       DC    X'0102'\n"
        "AD       DC    A(MAIN)\n"
        "EQ       EQU   5\n"
        "DS1      DS    CL4\n"
        "         END   MAIN\n",
        "XX T=X\nAD T=A\nMAIN T=J\nLAB T=I\nEQ T=U\nN12 T=N\nQUOTED T=U\n"
        "NOPE T=U\nDS1 T=C\nOMITTED T=O\nLR O=O\nWTO O=M\nDC O=A\nNOPE O=U\n",
    ),
    "type attribute of literals": (
        "         MACRO\n"
        "         TYPE  &S,&N\n"
        "         LCLC  &T\n"
        "&T       SETC  T'&S\n"
        "         WTO   '&N T=&T'\n"
        "         MEND\n"
        "MAIN     CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         L     2,=F'7'\n"
        "         TYPE  =F'7',USED\n"
        "         TYPE  =F'8',UNUSED\n"
        "         TYPE  =CL3'AB',UNUSEDC\n"
        "         L     2,=F'8'\n"
        "         TYPE  =F'8',LATER\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         LTORG\n"
        "         END   MAIN\n",
        "USED T=F\nUNUSED T=U\nUNUSEDC T=U\nLATER T=F\n",
    ),
}
Z390_STDOUT: Mapping[str, str] = {
    "length scale integer and defined attributes": (
        "PK T=P L=5 S=2 I=0 D=1\n"
        "ZN T=Z L=6 S=3 I=0 D=1\n"
        "FW T=F L=4 S=0 I=0 D=0\n"
        "HW T=H L=2 S=0 I=0 D=0\n"
        "FX T=F L=4 S=0 I=0 D=0\n"
        "FL T=D L=8 S=0 I=0 D=0\n"
    ),
    "type attribute of literals": "USED T=U\nUNUSED T=U\nUNUSEDC T=U\nLATER T=U\n",
}


def low_words(machine: HlasmMachine, registers: Mapping[int, int]) -> Mapping[int, int]:
    return {r: machine.gprs[r] & LOW_WORD for r in registers}
