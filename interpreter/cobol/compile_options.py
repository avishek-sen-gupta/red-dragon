"""How one COBOL program is compiled: lenient lowering, the addressing mode, and the
clock its compile stamp is read from."""

from __future__ import annotations

from dataclasses import dataclass, field

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.lp32 import LP32_MODE
from interpreter.cobol.compile_clock import CompileClock
from interpreter.cobol.system_compile_clock import SystemCompileClock


@dataclass(frozen=True)
class CompileOptions:
    tolerant: bool = False
    addressing_mode: AddressingMode = LP32_MODE
    clock: CompileClock = field(default_factory=SystemCompileClock)
