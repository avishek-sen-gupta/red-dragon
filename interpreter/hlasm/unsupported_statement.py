# pyright: standard
"""An assembler statement the lowering cannot place in storage yet, naming the issue that tracks it."""


class UnsupportedStatement(Exception):
    def __init__(self, mnemonic: str, issue: str) -> None:
        super().__init__(f"{mnemonic} statements are not supported yet — {issue}")
