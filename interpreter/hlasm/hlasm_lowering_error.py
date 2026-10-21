# pyright: standard
"""A statement or IR body whose shape the lowering cannot accept, naming where and what."""


class HlasmLoweringError(Exception):
    def __init__(self, where: str, expected: str, found: str) -> None:
        super().__init__(f"{where}: expected {expected}, found {found}")
