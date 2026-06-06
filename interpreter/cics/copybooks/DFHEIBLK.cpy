      * DFHEIBLK - Execute Interface Block
      * Injected by CICS pre-pass into WORKING-STORAGE SECTION.
       01 DFHEIBLK.
           02 EIBTRNID   PIC X(4).
           02 EIBCALEN   PIC S9(4) COMP.
           02 EIBAID     PIC X(1).
           02 EIBRESP    PIC S9(8) COMP.
           02 EIBRESP2   PIC S9(8) COMP.
           02 EIBDATE    PIC S9(7) COMP-3.
           02 EIBTIME    PIC S9(7) COMP-3.
           02 EIBFN      PIC X(2).
           02 EIBRCODE   PIC X(6).
           02 EIBDS      PIC X(8).
           02 EIBREQID   PIC X(8).
           02 EIBSIG     PIC X(1).
           02 EIBFREE    PIC X(1).
           02 EIBRECV    PIC X(1).
           02 EIBATT     PIC X(1).
           02 EIBEOC     PIC X(1).
           02 EIBFMH     PIC X(1).
           02 EIBCOMPL   PIC X(1).
           02 EIBSYNC    PIC X(1).
           02 EIBSYNCRB  PIC X(1).
           02 EIBNODAT   PIC X(1).
           02 EIBRSRCE   PIC X(8).
           02 EIBSYSID   PIC X(4).
           02 EIBUSER    PIC X(8).
           02 EIBTERM    PIC X(4).
           02 EIBLINK    PIC X(4).
