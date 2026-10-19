       IDENTIFICATION DIVISION.
       PROGRAM-ID. CLOSEPH.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT F1 ASSIGN TO DD1.
           SELECT F2 ASSIGN TO DD2.
           SELECT F3 ASSIGN TO DD3.
           SELECT F4 ASSIGN TO DD4.
           SELECT F5 ASSIGN TO DD5.
       DATA DIVISION.
       FILE SECTION.
       FD  F1.
       01  R1 PIC X(4).
       FD  F2.
       01  R2 PIC X(4).
       FD  F3.
       01  R3 PIC X(4).
       FD  F4.
       01  R4 PIC X(4).
       FD  F5.
       01  R5 PIC X(4).
       PROCEDURE DIVISION.
       MAIN-PARA.
           CLOSE F1 REEL F2 UNIT FOR REMOVAL F3 REEL WITH NO REWIND
                 F4 WITH NO REWIND F5 WITH LOCK.
           GOBACK.
