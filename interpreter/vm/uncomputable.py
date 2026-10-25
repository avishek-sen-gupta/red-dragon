# pyright: standard
"""The sentinel an operation answers when it cannot compute its result; a leaf, so modules the VM state imports can use it."""


class Uncomputable:
    def __repr__(self) -> str:
        return "UNCOMPUTABLE"


UNCOMPUTABLE = Uncomputable()
