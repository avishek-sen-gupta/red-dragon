# pyright: standard
"""An object-module record the binder does not apply yet: a non-ADDRESS relocation or an external dummy section."""


class UnsupportedBinding(Exception):
    def __init__(self, record: str, module: str) -> None:
        super().__init__(
            f"{record} in module {module} is not bound yet (red-dragon-6uyp.96)"
        )
