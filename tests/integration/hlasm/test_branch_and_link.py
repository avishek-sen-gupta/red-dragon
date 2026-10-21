# pyright: standard
"""Branch and link instructions run on the VM save the AMODE 31 link, take their path, and keep the machine in AMODE 31."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import branch_and_link_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm, run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
OPERATION_EXCEPTION = HlasmRun(return_code=0, abend="S0C1", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.LINK_CASES))
def test_link_forms_save_the_next_address_with_bit_32_and_branch(case: str):
    code, taken = programs.LINK_CASES[case]
    machine = run_hlasm_machine(programs.program(code))

    assert programs.link_view(machine) == HlasmMachine(
        ABENDED,
        programs.PRESET_CC,
        {
            programs.PATH_REGISTER: programs.path(taken),
            programs.LINK_REGISTER: programs.AMODE_31_LINK,
        },
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.MODE_CASES))
def test_set_mode_and_test_mode_stay_in_amode_31(case: str):
    code, taken, cc, mode_register = programs.MODE_CASES[case]
    machine = run_hlasm_machine(programs.program(code))

    assert machine.restricted_to(programs.MODE_VIEW) == HlasmMachine(
        ABENDED,
        cc,
        {
            programs.PATH_REGISTER: programs.path(taken),
            programs.MODE_REGISTER: mode_register,
        },
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CALLER_RETURNS))
def test_mode_setting_branch_to_the_return_address_returns_in_any_mode(case: str):
    assert run_hlasm(
        programs.return_program(programs.CALLER_RETURNS[case])
    ) == HlasmRun(return_code=programs.RETURN_CODE, abend="", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.MODE_SWITCH_CASES))
def test_leaving_amode_31_is_an_operation_exception(case: str):
    code, *_ = programs.MODE_SWITCH_CASES[case]
    machine = run_hlasm_machine(programs.program(code))

    assert machine.restricted_to(programs.MODE_VIEW) == HlasmMachine(
        OPERATION_EXCEPTION,
        programs.PRESET_CC,
        {programs.PATH_REGISTER: programs.FILL, programs.MODE_REGISTER: programs.FILL},
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.xfail(
    reason="AMODE 24 and 64 are not modelled; leaving AMODE 31 abends S0C1 — red-dragon-6uyp.75",
    strict=True,
)
@pytest.mark.parametrize("case", list(programs.MODE_SWITCH_CASES))
def test_mode_switches_enter_amode_24_and_64(case: str):
    code, taken, cc, mode_register = programs.MODE_SWITCH_CASES[case]
    machine = run_hlasm_machine(programs.program(code))

    assert machine.restricted_to(programs.MODE_VIEW) == HlasmMachine(
        ABENDED,
        cc,
        {
            programs.PATH_REGISTER: programs.path(taken),
            programs.MODE_REGISTER: mode_register,
        },
    )
