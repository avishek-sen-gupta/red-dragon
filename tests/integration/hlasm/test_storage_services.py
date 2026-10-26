# pyright: standard
"""GETMAIN, FREEMAIN, STORAGE, TIME and STIMER from our maclib, run in the VM: aligned areas, released only as obtained, and the time and date from the run's TOD clock."""

import pytest

from hlasm_asg.hlasm_parse_error import HlasmParseError
from hlasm_asg.program.mnote_level import MnoteLevel
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import storage_service_programs as programs
from tests.integration.hlasm.hlasm_helpers import (
    run_hlasm,
    run_hlasm_allocations,
    run_hlasm_machine,
)
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
ALL_PAIR_CASES = {**programs.PAIR_CASES, **programs.VM_ONLY_PAIR_CASES}


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(ALL_PAIR_CASES))
def test_two_obtained_areas_are_aligned_distinct_usable_and_released(case: str):
    source, expected = ALL_PAIR_CASES[case]

    ran = run_hlasm_machine(source)

    assert (ran.run, programs.pair_view(ran.gprs)) == (ABENDED, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_last_byte_of_a_page_aligned_area_is_written_and_read_back():
    ran = run_hlasm_machine(programs.LAST_BYTE)

    assert (ran.run, ran.gprs[3], ran.gprs[4]) == (ABENDED, 0x5A, 0)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.BAD_RELEASES))
def test_a_release_not_matching_an_obtained_area_abends_and_leaves_the_table(case: str):
    source, code, entries = programs.BAD_RELEASES[case]

    assert run_hlasm_allocations(source) == (
        HlasmRun(return_code=0, abend=code, stdout=""),
        entries,
        0,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_time_returns_the_fixed_clock_as_decimal_and_binary_time_and_packed_date():
    ran = run_hlasm_machine(programs.TIME)

    assert (ran.run, programs.time_view(ran.gprs)) == (
        ABENDED,
        programs.FIXED_TIME_REGISTERS,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bad_operands_refuse_the_assembly_with_severity_8():
    with pytest.raises(HlasmParseError) as refused:
        run_hlasm(programs.BAD_OPERANDS)

    assert [
        (d.message, d.related[-1].line, d.mnote) for d in refused.value.diagnostics
    ] == [
        (m, line, MnoteLevel(kind="LEVEL", level=8))
        for m, line in programs.BAD_OPERAND_REFUSALS
    ]
