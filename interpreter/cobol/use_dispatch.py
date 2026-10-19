"""UseDispatch — what every USE candidate of one I/O statement tests and where it goes: the file's open mode, the I-O status, the statement's own handled classes and the join label."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from interpreter.cobol.status_class import StatusClass
from interpreter.ir import CodeLabel
from interpreter.register import Register


@dataclass(frozen=True)
class UseDispatch:
    mode_reg: Register
    status_reg: Register
    handled: Sequence[StatusClass]
    done: CodeLabel
