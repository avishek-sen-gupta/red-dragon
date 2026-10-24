# pyright: standard
"""Macro-language programs, one per feature, shared by the VM tests and the z390 differential tests."""

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

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


LIBRARY: Mapping[str, str] = {
    "MEMBER": (
        "         MACRO\n"
        "         HELLO &W\n"
        "         WTO   'HELLO &W'\n"
        "         MEND\n"
        "         HELLO COPY\n"
        "         WTO   'FROM COPY'\n"
    ),
    "SEQMEM": "         SEQ" + " " * 60 + "SEQ00500\n",
    "LSEQ": (
        "         MACRO\n"
        "         LSEQ\n"
        "         GBLC  &SEQS\n"
        "&SEQS    SETC  '&SEQS L/&SYSSTMT'\n"
        "         MEND\n"
    ),
}
STDOUT_PROGRAMS: Mapping[str, tuple[str, str]] = {
    "SYSECT and SYSLOC": (
        "         MACRO\n"
        "         WHERE\n"
        "         GBLC  &LOCS\n"
        "&LOCS    SETC  '&LOCS &SYSECT/&SYSLOC'\n"
        "         MEND\n"
        "         GBLC  &LOCS\n"
        "MAIN     CSECT\n"
        "         WHERE\n"
        "PART2    LOCTR\n"
        "         WHERE\n"
        "OTHER    CSECT\n"
        "         WHERE\n"
        "PART3    LOCTR\n"
        "         WHERE\n"
        "MAIN     LOCTR\n"
        "         WTO   'LOC&LOCS'\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n",
        "LOC MAIN/MAIN MAIN/PART2 OTHER/OTHER OTHER/PART3\n",
    ),
    "SYSSEQF and SYSSTMT from open code, a COPY member and after lookahead": (
        "         MACRO\n"
        "         SEQ\n"
        "         GBLC  &SEQS\n"
        "&SEQS    SETC  '&SEQS &SYSSEQF/&SYSSTMT'\n"
        "         MEND\n"
        "         GBLC  &SEQS\n"
        "MAIN     CSECT\n"
        "         SEQ                                                            SEQ00100\n"
        "         COPY  SEQMEM\n"
        "         AIF   (T'LATER EQ 'F').GO                                      SEQ00300\n"
        ".GO      ANOP                                                           SEQ00400\n"
        "         SEQ                                                            SEQ00600\n"
        "         LSEQ\n"
        "         WTO   'SEQ&SEQS'\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "LATER    DC    F'1'\n"
        "         END   MAIN\n",
        "SEQ SEQ00100/00000011 SEQ00500/00000016 SEQ00600/00000022 L/00000026\n",
    ),
    "nested and inline macros with SYSNDX labels": (
        "         MACRO\n"
        "         INNER &X\n"
        "         J     L&SYSNDX\n"
        "         WTO   'SKIPPED'\n"
        "L&SYSNDX DS    0H\n"
        "         WTO   'INNER &X &SYSNDX'\n"
        "         MEND\n"
        "         MACRO\n"
        "         OUTER &Y\n"
        "         INNER &Y.A\n"
        "         INNER &Y.B\n"
        "         MACRO\n"
        "         MADE\n"
        "         WTO   'MADE BY OUTER'\n"
        "         MEND\n"
        "         MEND\n"
        "MAIN     CSECT\n"
        "         OUTER P\n"
        "         MADE\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n",
        "INNER PA 0002\n" "INNER PB 0005\n" "MADE BY OUTER\n",
    ),
    "AIF AGO ACTR and ANOP loop": (
        "         MACRO\n"
        "         LOOP  &N\n"
        "         LCLA  &I\n"
        "         ACTR  20\n"
        "&I       SETA  1\n"
        ".TOP     AIF   (&I GT &N).DONE\n"
        "         WTO   'ITER &I'\n"
        "&I       SETA  &I+1\n"
        "         AGO   .TOP\n"
        ".DONE    ANOP\n"
        "         WTO   'LOOPED &N'\n"
        "         MEND\n"
        "MAIN     CSECT\n"
        "         LOOP  3\n"
        "         LOOP  0\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n",
        "ITER 1\n" "ITER 2\n" "ITER 3\n" "LOOPED 3\n" "LOOPED 0\n",
    ),
    "global and local SET symbol scope": (
        "         MACRO\n"
        "         BUMP\n"
        "         GBLA  &GA\n"
        "         GBLB  &GB\n"
        "         GBLC  &GC\n"
        "         LCLA  &LA\n"
        "&GA      SETA  &GA+5\n"
        "&GB      SETB  (NOT &GB)\n"
        "&GC      SETC  '&GC.X'\n"
        "&LA      SETA  &LA+1\n"
        "         WTO   'BUMP &GA &GB &GC &LA'\n"
        "         MEND\n"
        "         MACRO\n"
        "         SHOWG\n"
        "         GBLA  &GA\n"
        "         LCLA  &LA\n"
        "         WTO   'SHOWG &GA &LA'\n"
        "         MEND\n"
        "         GBLA  &GA\n"
        "         LCLA  &LA\n"
        "&LA      SETA  9\n"
        "MAIN     CSECT\n"
        "         BUMP\n"
        "         BUMP\n"
        "         SHOWG\n"
        "         WTO   'OPEN &GA &LA'\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n",
        "BUMP 5 1 X 1\n" "BUMP 10 0 XX 1\n" "SHOWG 10 0\n" "OPEN 10 9\n",
    ),
    "SETA SETB and SETC expressions, substrings and duplication": (
        "         LCLA  &A,&B,&C\n"
        "         LCLB  &T,&F\n"
        "         LCLC  &S,&D,&U\n"
        "&A       SETA  7*3-4/2+(10-3)*2\n"
        "&B       SETA  &A/4\n"
        "&C       SETA  ((&A AND 12) OR 64)+(&A XOR 5)+(NOT 0)\n"
        "&T       SETB  (&A GT 30 AND NOT (&B EQ 0))\n"
        "&F       SETB  (&A LT 30 OR '&S' NE '')\n"
        "&S       SETC  'ABCDEFGH'\n"
        "&D       SETC  '&S'(3,4).'-'.(3)'XY'.'&S'(7,*)\n"
        "&U       SETC  (UPPER 'abc').'&S'(K'&S,1)\n"
        "MAIN     CSECT\n"
        "         WTO   'A &A B &B C &C T &T F &F'\n"
        "         WTO   'S &D &U'\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n",
        "A 33 B 8 C 99 T 1 F 0\n" "S CDEF-XYXYXYGH ABCH\n",
    ),
    "created and subscripted SET symbols": (
        "         LCLC  &NAME\n"
        "         LCLA  &ARR(3)\n"
        "         LCLC  &CS(2)\n"
        "&NAME    SETC  'DYN'\n"
        "&(&NAME) SETA  42\n"
        "&(&NAME.2) SETC 'TWO'\n"
        "&ARR(2)  SETA  &DYN*2\n"
        "&ARR(3)  SETA  &ARR(2)+1\n"
        "&CS(1)   SETC  'P'\n"
        "&CS(2)   SETC  '&CS(1)'.'Q'\n"
        "MAIN     CSECT\n"
        "         WTO   'DYN &DYN &DYN2 ARR &ARR(1) &ARR(2) &ARR(3)'\n"
        "         WTO   'CS &CS(2)'\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n",
        "DYN 42 TWO ARR 0 84 85\n" "CS PQ\n",
    ),
    "positional keyword and sublist parameters": (
        "         MACRO\n"
        "&L       PARMS &P1,&P2,&K1=DEF,&K2=\n"
        "         LCLA  &N,&KP,&KK,&NP,&NS\n"
        "&N       SETA  N'&SYSLIST\n"
        "&KP      SETA  K'&P1\n"
        "&KK      SETA  K'&K2\n"
        "&NP      SETA  N'&P2\n"
        "&NS      SETA  N'&SYSLIST(2)\n"
        "         WTO   'L &L P1 &P1 P2 &P2 K1 &K1 K2 &K2.;'\n"
        "         WTO   'S &SYSLIST(1) &SYSLIST(3) &SYSLIST(2,3).;'\n"
        "         WTO   'N &N K &KP &KK N &NP &NS SUB &P2(2).;'\n"
        "         MEND\n"
        "MAIN     CSECT\n"
        "LBL      PARMS ABC,(X,YY,ZZZ),EXTRA,K2=KEY\n"
        "         PARMS Q,K1=OVR\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n",
        "L LBL P1 ABC P2 (X,YY,ZZZ) K1 DEF K2 KEY;\n"
        "S ABC EXTRA ZZZ;\n"
        "N 3 K 3 3 N 3 3 SUB YY;\n"
        "L  P1 Q P2  K1 OVR K2 ;\n"
        "S Q  ;\n"
        "N 1 K 1 0 N 0 0 SUB ;\n",
    ),
    "opcode substitution and OPSYN": (
        "         MACRO\n"
        "         DOOP  &OP,&R,&V\n"
        "         &OP   &R,&V\n"
        "         MEND\n"
        "         MACRO\n"
        "         SAYOP &OP\n"
        "         &OP   'SUBSTITUTED'\n"
        "         MEND\n"
        "         MACRO\n"
        "         OPS   &NAME\n"
        "         LCLC  &O\n"
        "&O       SETC  O'&NAME\n"
        "         WTO   'O &NAME &O'\n"
        "         MEND\n"
        "MAIN     CSECT\n"
        "         SAYOP WTO\n"
        "SAY      OPSYN WTO\n"
        "         SAY   'RENAMED'\n"
        "         OPS   SAY\n"
        "         OPS   LHI\n"
        "LHI      OPSYN\n"
        "         OPS   LHI\n"
        "         LA    15,9\n"
        "         DOOP  LA,15,0\n"
        "         BR    14\n"
        "         END   MAIN\n",
        "SUBSTITUTED\n" "RENAMED\n" "O SAY M\n" "O LHI O\n" "O LHI U\n",
    ),
    "AREAD and AINSERT": (
        "         MACRO\n"
        "         READ\n"
        "         LCLC  &CARD,&HEAD\n"
        "&CARD    AREAD\n"
        "&HEAD    SETC  '&CARD'(1,9)\n"
        "         WTO   'READ &HEAD'\n"
        "         MEND\n"
        "         MACRO\n"
        "         INS\n"
        "         AINSERT '         WTO   ''INSERTED BACK''',BACK\n"
        "         AINSERT '         WTO   ''INSERTED FRONT''',FRONT\n"
        "         MEND\n"
        "MAIN     CSECT\n"
        "         READ\n"
        "THIS CARD IS DATA\n"
        "         INS\n"
        "         WTO   'AFTER'\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n",
        "READ THIS CARD\n" "INSERTED FRONT\n" "INSERTED BACK\n" "AFTER\n",
    ),
    "COPY from SYSLIB": (
        "MAIN     CSECT\n"
        "         COPY  MEMBER\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n",
        "HELLO COPY\n" "FROM COPY\n",
    ),
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
    "type and defined attributes of literals": (
        "         MACRO\n"
        "         TYPE  &S,&N\n"
        "         LCLC  &T\n"
        "         LCLB  &D\n"
        "&T       SETC  T'&S\n"
        "&D       SETB  (D'&S)\n"
        "         WTO   '&N T=&T D=&D'\n"
        "         MEND\n"
        "         MACRO\n"
        "         LCLC  &T\n"
        "&T       SETC  T'=F'9'\n"
        "         WTO   'BODY T=&T'\n"
        "         MEND\n"
        "MAIN     CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         TYPE  =F'7',BEFORE\n"
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
        "BEFORE T=U D=0\nUSED T=F D=1\nUNUSED T=U D=0\nUNUSEDC T=U D=0\nLATER T=F D=1\n",
    ),
    "type attribute of a literal written in a macro body": (
        "         MACRO\n"
        "         BODY\n"
        "         LCLC  &T\n"
        "&T       SETC  T'=F'9'\n"
        "         WTO   'BODY T=&T'\n"
        "         MEND\n"
        "MAIN     CSECT\n"
        "         BODY\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END   MAIN\n",
        "BODY T=F\n",
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
    "SYSSEQF and SYSSTMT from open code, a COPY member and after lookahead": (
        "SEQ /00000008 /00000011 /00000013 L/00000015\n"
    ),
    "type and defined attributes of literals": (
        "BEFORE T=U D=0\nUSED T=U D=0\nUNUSED T=U D=0\nUNUSEDC T=U D=0\nLATER T=U D=0\n"
    ),
}


def low_words(machine: HlasmMachine, registers: Mapping[int, int]) -> Mapping[int, int]:
    return {r: machine.gprs[r] & LOW_WORD for r in registers}


Z390_REFUSES = frozenset({"type attribute of a literal written in a macro body"})
ACTR_PROGRAM = (
    "         MACRO\n"
    "         SPIN\n"
    "         LCLA  &I\n"
    "         ACTR  3\n"
    ".TOP     ANOP\n"
    "&I       SETA  &I+1\n"
    "         AGO   .TOP\n"
    "         MEND\n"
    "MAIN     CSECT\n"
    "         SPIN\n"
    "         SR    15,15\n"
    "         BR    14\n"
    "         END   MAIN\n"
)
ACTR_REFUSAL = [("E056", 5, "ACTR counter exceeded")]


def library_in(directory: Path, suffix: str) -> Path:
    directory.mkdir(exist_ok=True)
    for name, text in LIBRARY.items():
        (directory / name).with_suffix(suffix).write_text(text, encoding="ascii")
    return directory


SYSPARM_PROGRAM = (
    "MAIN     CSECT\n"
    "         WTO   'P=&SYSPARM;'\n"
    "         SR    15,15\n"
    "         BR    14\n"
    "         END   MAIN\n"
)
SYSPARM_PRINTS: Mapping[str, str] = {"": "P=;\n", "ALPHA": "P=ALPHA;\n"}
CLOCK_PROGRAM = (
    "         MACRO\n"
    "         STAMP\n"
    "         WTO   '&SYSDATC &SYSTIME &SYSDATE'\n"
    "         MEND\n"
    "MAIN     CSECT\n"
    "         STAMP\n"
    "         SR    15,15\n"
    "         BR    14\n"
    "         END   MAIN\n"
)
CLOCK = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
CLOCK_PRINTS = "20260304 05.06 03/04/26\n"
MNOTE_PROGRAM = (
    "         MACRO\n"
    "         NOTE  &WHAT\n"
    "         MNOTE 4,'CHECK &WHAT'\n"
    "         MNOTE *,'SEEN &WHAT'\n"
    "         MEND\n"
    "MAIN     CSECT\n"
    "         NOTE  FIELD\n"
    "         SR    15,15\n"
    "         BR    14\n"
    "         END   MAIN\n"
)
MNOTE_LOG: Sequence[tuple[int, str]] = (
    (
        logging.WARNING,
        "__main__.asm:3: MNOTE 4,CHECK FIELD (called from __main__.asm:7)",
    ),
    (logging.INFO, "__main__.asm:4: MNOTE *,SEEN FIELD (called from __main__.asm:7)"),
)
