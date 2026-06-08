       IDENTIFICATION DIVISION.
       PROGRAM-ID. REFMOD.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-FIELD PIC X(50).
       01 WS-OUT   PIC X(20).
       01 WS-A     PIC 9 VALUE 2.
       01 WS-B     PIC 9 VALUE 3.
       01 WS-C     PIC 9 VALUE 4.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-FIELD(2:3) TO WS-OUT.
           MOVE WS-FIELD(WS-A:WS-B) TO WS-OUT.
           MOVE WS-FIELD(WS-A + 1:WS-B - 1) TO WS-OUT.
           MOVE WS-FIELD(WS-A * WS-B:WS-C + WS-A) TO WS-OUT.
           MOVE WS-FIELD((WS-A + 1) * 2:(WS-C - WS-B) * WS-A) TO WS-OUT.
           MOVE WS-FIELD(WS-A + WS-B * WS-C:) TO WS-OUT.
           MOVE WS-FIELD((WS-A + WS-B) * (WS-C - WS-A):3) TO WS-OUT.
           MOVE WS-A TO WS-OUT.
           MOVE WS-FIELD TO WS-OUT(LENGTH OF WS-A + 1:LENGTH OF WS-B).
           STOP RUN.
