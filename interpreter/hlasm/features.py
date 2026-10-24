# pyright: standard
"""Semantic feature enumeration for the HLASM frontend's macro language."""

from __future__ import annotations

from enum import Enum


class HlasmFeature(Enum):
    """Macro-language features of IBM High Level Assembler."""

    MACRO_DEFINITION = "MACRO/MEND definitions, nested and inline, with &SYSNDX"
    CONDITIONAL_ASSEMBLY = "AIF, AGO, ANOP and ACTR"
    SET_SYMBOLS = "GBLx/LCLx, SETA/SETB/SETC, created and subscripted SET symbols"
    MACRO_PARAMETERS = "positional, named and sublist parameters, &SYSLIST, N' and K'"
    OPCODE_SUBSTITUTION = "a SET symbol as operation and OPSYN rename and delete"
    AREAD_AINSERT = "AREAD and AINSERT"
    COPY = "COPY members from SYSLIB"
    DATA_ATTRIBUTES = "T', L', S', I', D' and O' of symbols and literals"
    SYSTEM_VARIABLES = "&SYSECT, &SYSLOC, &SYSSEQF, &SYSSTMT, &SYSPARM and the clock"
    USING = "DSECTs, labeled and dependent USING, and literal pools"
    MNOTE = "MNOTE messages from macros"
