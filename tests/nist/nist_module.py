"""The CCVS module a NIST program belongs to, the first two letters of its name."""

from __future__ import annotations

from enum import Enum


class NistModule(Enum):
    """The CCVS module a NIST program belongs to."""

    CM = "CM"
    DB = "DB"
    EX = "EX"
    IC = "IC"
    IF = "IF"
    IX = "IX"
    NC = "NC"
    OB = "OB"
    RL = "RL"
    RW = "RW"
    SG = "SG"
    SM = "SM"
    SQ = "SQ"
    ST = "ST"
