# pyright: standard
"""A job-step PARM longer than the 100 characters z/OS allows."""


class ParmTooLong(Exception):
    def __init__(self, parm: str) -> None:
        super().__init__(f"PARM of {len(parm)} characters exceeds 100")
