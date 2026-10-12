"""The run-unit region: allocated, zero-filled, before any program runs."""

from interpreter.address import Address
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.run_unit import RUN_UNIT_VAR, advanced, restarted, value_of
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned,
    run_cobol,
    run_cobol_programs,
    ws_region,
)

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


_RANDOM_NEXT = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. RNNEXT.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-R PIC V9(9).",
    "PROCEDURE DIVISION.",
    "    COMPUTE WS-R = FUNCTION RANDOM.",
    "    GOBACK.",
]
_RANDOM_SEED = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. RNSEED.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-R PIC V9(9).",
    "PROCEDURE DIVISION.",
    "    COMPUTE WS-R = FUNCTION RANDOM(42).",
    "    CALL 'RNNEXT'.",
    "    GOBACK.",
]


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_random_is_one_reproducible_sequence_for_the_whole_run_unit():
    """A seed set in the caller continues in the callee, and two runs agree."""
    first = run_cobol_programs(_RANDOM_SEED, {"RNNEXT": _RANDOM_NEXT})
    second = run_cobol_programs(_RANDOM_SEED, {"RNNEXT": _RANDOM_NEXT})
    after_two = advanced(restarted(42))
    assert first.region_get(_run_unit_address(first))[2:6] == bytearray(
        after_two.to_bytes(4, "big")
    )
    assert decode_zoned_unsigned(ws_region(first, "RNSEED"), 0, 9) == int(
        value_of(restarted(42)) * 10**9
    )
    assert decode_zoned_unsigned(ws_region(first, "RNNEXT"), 0, 9) == int(
        value_of(after_two) * 10**9
    )
    assert ws_region(first, "RNNEXT") == ws_region(second, "RNNEXT")
    assert ws_region(first, "RNSEED") != ws_region(first, "RNNEXT")
