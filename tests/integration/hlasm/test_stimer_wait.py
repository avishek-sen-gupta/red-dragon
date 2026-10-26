# pyright: standard
"""STIMER WAIT from our maclib, run on the system clock: the run pauses for the BINTVL interval, so TIME BIN after it reads at least that many hundredths later."""

import time

from interpreter.constants import Language
from interpreter.default_builtins import DEFAULT_BUILTINS
from interpreter.hlasm_run_inputs.clock_builtins import clock_builtins
from interpreter.hlasm_run_inputs.system_machine_clock import SystemMachineClock
from interpreter.run import run
from interpreter.vm.builtins import compose_builtins
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import MAX_STEPS, gpr

WAIT_HUNDREDTHS = 20
BEFORE_REGISTER = 2
AFTER_REGISTER = 3
RETURN_CODE_REGISTER = 15
WAIT_BETWEEN_TIMES = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         TIME  BIN\n"
    "         LR    2,0\n"
    "         LA    15,99\n"
    "         STIMER WAIT,BINTVL=INTERVAL\n"
    "         TIME  BIN\n"
    "         LR    3,0\n"
    "         BR    14\n"
    f"INTERVAL DC    F'{WAIT_HUNDREDTHS}'\n"
    "         END\n"
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_stimer_wait_pauses_the_run_for_its_binary_interval():
    clock = SystemMachineClock(
        wall_ns=time.time_ns, cpu_ns=time.process_time_ns, sleep=time.sleep
    )
    vm = run(
        WAIT_BETWEEN_TIMES,
        language=Language.HLASM,
        max_steps=MAX_STEPS,
        builtins=compose_builtins(DEFAULT_BUILTINS, clock_builtins(clock)),
    )

    waited = gpr(vm, AFTER_REGISTER) - gpr(vm, BEFORE_REGISTER)
    assert (gpr(vm, RETURN_CODE_REGISTER), waited >= WAIT_HUNDREDTHS) == (0, True)
