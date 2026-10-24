# pyright: standard
"""An HLASM STCK run through run() with the system clock builtins stores the TOD clock the injected host readings give."""

from interpreter.constants import Language
from interpreter.default_builtins import DEFAULT_BUILTINS
from interpreter.hlasm_run_inputs.clock_builtins import clock_builtins
from interpreter.hlasm_run_inputs.system_machine_clock import SystemMachineClock
from interpreter.run import run
from interpreter.vm.builtins import compose_builtins
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import MAX_STEPS, gpr
from tests.integration.hlasm.miscellaneous_programs import program

START_OF_1972_UNIX_NS = 63_072_000 * 1_000_000_000
START_OF_1972_STCK = 0x8126D60E_46000000
CLOCK_REGISTER = 2
STCK_INTO_R2 = "         STCK   OUT\n         LMG    2,2,OUT\n"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_stck_under_run_stores_the_system_clock_reading():
    clock = SystemMachineClock(wall_ns=lambda: START_OF_1972_UNIX_NS, cpu_ns=lambda: 0)
    vm = run(
        program(STCK_INTO_R2),
        language=Language.HLASM,
        max_steps=MAX_STEPS,
        builtins=compose_builtins(DEFAULT_BUILTINS, clock_builtins(clock)),
    )

    assert gpr(vm, CLOCK_REGISTER) == START_OF_1972_STCK
