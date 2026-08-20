       IDENTIFICATION DIVISION.
       PROGRAM-ID. EDITWIDTHS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
      * Each edited field is followed by a PIC X(4) sentinel, so the gap
      * between consecutive offsets is exactly the edited field's width.
      * Widths: 8, 4, 8, 4, 5, 4, 7, 4 (red-dragon-ilb6).
       01  WS-REC.
           05  WS-BLANK-INS   PIC 9(5)BB9.
           05  WS-SENT-A      PIC X(4).
           05  WS-SLASH-DATE  PIC 99/99/99.
           05  WS-SENT-B      PIC X(4).
           05  WS-ZERO-INS    PIC 9(3)09.
           05  WS-SENT-C      PIC X(4).
           05  WS-ALL-FLOAT   PIC $$$$.$$.
           05  WS-SENT-D      PIC X(4).
       PROCEDURE DIVISION.
       MAIN-PARA.
           STOP RUN.
