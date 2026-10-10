"""UnwrittenRegisterRead — raised when an instruction reads a register nothing has written."""

from __future__ import annotations

from interpreter.func_name import FuncName
from interpreter.register import Register


class UnwrittenRegisterRead(Exception):
    def __init__(self, register: Register, function_name: FuncName) -> None:
        super().__init__(
            f"read of unwritten register {register} in frame {function_name}"
        )
