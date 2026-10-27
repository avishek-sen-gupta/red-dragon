       IDENTIFICATION DIVISION.
       PROGRAM-ID. UNDECL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A            PIC X(10).
       01  WS-IDX          PIC 9(4) COMP VALUE 1.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-A TO CPY-ROW(2)
           MOVE WS-A TO CPY-ROW(WS-IDX)
           MOVE WS-A TO CPY-CELL(1, 2)
           MOVE CPY-ROW(3) TO WS-A
           GOBACK.
