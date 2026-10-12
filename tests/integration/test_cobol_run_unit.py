"""The run-unit region: allocated, zero-filled, before any program runs."""

from interpreter.address import Address
from interpreter.cobol.run_unit import RUN_UNIT_VAR
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import run_cobol, run_cobol_programs

_QUIET = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. RUQUIET.",
    "PROCEDURE DIVISION.",
    "    GOBACK.",
]


def _run_unit_address(vm) -> Address:
    return Address(str(vm.call_stack[0].local_vars[RUN_UNIT_VAR].value))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_single_program_run_has_the_run_unit_region():
    vm = run_cobol(_QUIET)
    assert vm.region_get(_run_unit_address(vm)) == bytearray(6)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linked_run_has_one_run_unit_region_allocated_first():
    caller = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RUCALLER.",
        "PROCEDURE DIVISION.",
        "    CALL 'RUQUIET'.",
        "    GOBACK.",
    ]
    vm = run_cobol_programs(caller, {"RUQUIET": _QUIET})
    allocated = tuple(vm.region_keys())
    assert allocated[0] == _run_unit_address(vm)
    assert vm.region_get(_run_unit_address(vm)) == bytearray(6)
