       IDENTIFICATION DIVISION.
       PROGRAM-ID. GRPSIGN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  OUTER SIGN TRAILING SEPARATE.
           03  A PIC S9(2).
           03  INNER SIGN LEADING SEPARATE.
               05  B PIC S9(2).
               05  C PIC S9(2) SIGN TRAILING.
               05  D PIC 9(2).
               05  E PIC S9(2) COMP.
       PROCEDURE DIVISION.
           STOP RUN.
