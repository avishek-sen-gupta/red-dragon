"""Two builtins tables being composed both define the same name."""

from __future__ import annotations

from interpreter.func_name import FuncName


class DuplicateBuiltinError(ValueError):
    def __init__(self, name: FuncName) -> None:
        super().__init__(f"two builtins tables both define {name}")
        self.name = name
