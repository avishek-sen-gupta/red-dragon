       IDENTIFICATION DIVISION.
       PROGRAM-ID. EXECSQLWS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-COUNT       PIC 9(3) VALUE ZERO.
       01 WS-START-KEY   PIC X(2) VALUE SPACES.
       01 WS-GROUP.
           EXEC SQL
                DECLARE CARDDEMO.TRANSACTION_TYPE TABLE
                    ( TR_TYPE CHAR(2) NOT NULL,
                      TR_DESCRIPTION VARCHAR(50) NOT NULL )
           END-EXEC.
           EXEC SQL
                DECLARE C-TR-TYPE-FORWARD CURSOR FOR
                    SELECT TR_TYPE FROM CARDDEMO.TRANSACTION_TYPE
                    WHERE TR_TYPE >= :WS-START-KEY
                    ORDER BY TR_TYPE
           END-EXEC.
           EXEC SQL
                DECLARE C-TR-TYPE-BACKWARD CURSOR FOR
                    SELECT TR_TYPE FROM CARDDEMO.TRANSACTION_TYPE
                    WHERE TR_TYPE < :WS-START-KEY
                    ORDER BY TR_TYPE DESC
           END-EXEC.
       PROCEDURE DIVISION.
           ADD 1 TO WS-COUNT.
           STOP RUN.
