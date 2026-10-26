# pyright: standard
"""The names of the HLASM run-input and wait builtins, the size of the PARM area they fill, and the positions of a DD lookup's facts."""

from interpreter.func_name import FuncName

TOD_CLOCK_BUILTIN = FuncName("__hlasm_tod_clock")
CPU_TIMER_BUILTIN = FuncName("__hlasm_cpu_timer")
WAIT_BUILTIN = FuncName("__hlasm_wait")
JOB_PARM_BUILTIN = FuncName("__hlasm_job_parm")
PARM_TEXT_BYTES = 100
PARM_LENGTH_BYTES = 2
DD_BUILTIN = FuncName("__hlasm_dd")
DD_SUPPLIED_FACT, DD_RECFM_FACT, DD_LRECL_FACT, DD_BLKSIZE_FACT = range(4)
DD_FACTS = 4
DECLARE_FILE_BUILTIN = FuncName("__hlasm_declare_file")
