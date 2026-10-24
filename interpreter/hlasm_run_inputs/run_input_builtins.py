# pyright: standard
"""The clock and PARM run-input builtins, and the run inputs a run gets when its caller supplies none: the host clock, an empty PARM and no DD definitions."""

import time
from collections.abc import Mapping

from interpreter.func_name import FuncName
from interpreter.hlasm_run_inputs.clock_builtins import clock_builtins
from interpreter.hlasm_run_inputs.dd_builtins import NO_DDS, dd_builtins
from interpreter.hlasm_run_inputs.job_parm_builtins import NO_PARM, job_parm_builtins
from interpreter.hlasm_run_inputs.machine_clock import MachineClock
from interpreter.hlasm_run_inputs.system_machine_clock import SystemMachineClock
from interpreter.vm.builtin import Builtin
from interpreter.vm.builtins import compose_builtins


def run_input_builtins(clock: MachineClock, parm: str) -> Mapping[FuncName, Builtin]:
    return compose_builtins(clock_builtins(clock), job_parm_builtins(parm))


def unsupplied_run_input_builtins() -> Mapping[FuncName, Builtin]:
    clock = SystemMachineClock(wall_ns=time.time_ns, cpu_ns=time.process_time_ns)
    return compose_builtins(run_input_builtins(clock, NO_PARM), dd_builtins(NO_DDS))
