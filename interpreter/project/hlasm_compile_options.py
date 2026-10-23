# pyright: standard
"""How one HLASM program is assembled: the system-variable values it is given, and the clock it reads once."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from hlasm_asg.assembly_clock import AssemblyClock
from hlasm_asg.assembly_input import AssemblyInput
from hlasm_asg.system_assembly_clock import SystemAssemblyClock


@dataclass(frozen=True)
class HlasmCompileOptions:
    names: Mapping[AssemblyInput, str] = field(default_factory=dict)
    clock: AssemblyClock = field(default_factory=SystemAssemblyClock)
