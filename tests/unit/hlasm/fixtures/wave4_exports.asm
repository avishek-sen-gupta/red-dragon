         MACRO
         WARN
         MNOTE 4,'CAREFUL'
         MEND
T        CSECT
T        AMODE 31
T        RMODE ANY
         USING T,12
         WARN
         DC    0F
         DC    BL.4'1010',S(FIELD)
READ     CCW   X'02',FIELD,X'20',4
FIELD    DC    FE1'1'
         DC    2A(*)
         END
