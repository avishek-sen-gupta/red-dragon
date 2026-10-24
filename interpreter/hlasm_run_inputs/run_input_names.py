# pyright: standard
"""The names of the HLASM run-input builtins and the size of the PARM area they fill."""

from interpreter.func_name import FuncName

TOD_CLOCK_BUILTIN = FuncName("__hlasm_tod_clock")
CPU_TIMER_BUILTIN = FuncName("__hlasm_cpu_timer")
JOB_PARM_BUILTIN = FuncName("__hlasm_job_parm")
PARM_TEXT_BYTES = 100
PARM_LENGTH_BYTES = 2
