# pyright: standard
"""A job-step PARM holding a character the machine's EBCDIC table has no code for."""


class ParmNotEncodable(Exception):
    def __init__(self, character: str) -> None:
        super().__init__(f"PARM character {character!r} has no EBCDIC code")
