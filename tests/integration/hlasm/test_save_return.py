# pyright: standard
"""SAVE, RETURN and YREGS from our maclib: instructions only, run in the VM."""

from functools import partial

import pytest

from hlasm_asg.hlasm_parse_error import HlasmParseError
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import save_return_programs as programs
from tests.integration.hlasm.hlasm_helpers import (
    run_hlasm,
    run_hlasm_machine,
    run_hlasm_storage,
)
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
WORD = 4
LOW_WORD = 0xFFFFFFFF
AMODE_31 = 0x80000000


def _word(stored: bytes, offset: int, start: int) -> int:
    return int.from_bytes(stored[offset - start : offset - start + WORD], "big")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.SUB_CASES))
def test_save_and_return_restore_the_registers_they_cover(case: str):
    body, expected = programs.SUB_CASES[case]

    ran = run_hlasm_machine(programs.caller(body))

    assert (ran.run, programs.machine_view(ran.gprs)) == (ABENDED, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_standard_entry_and_exit_with_an_identifier_and_the_returned_code():
    ran, stored = run_hlasm_storage(programs.STANDARD, "MAIN", (0, 100))

    assert (ran.run, stored[84:89]) == (
        HlasmRun(7, "", ""),
        b"\x04" + "MAIN".encode("cp037"),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_nested_subroutine_chains_through_its_own_save_area():
    start, _ = programs.NESTED_SPAN
    ran, stored = run_hlasm_storage(programs.NESTED, "MAIN", programs.NESTED_SPAN)
    word = partial(_word, stored, start=start)
    base = word(152)
    caller_area = word(8)

    assert (
        ran.run,
        ran.gprs[13] & LOW_WORD,
        [word(o) for o in (8, 12, 16, 32, 36, 80, 148)],
    ) == (
        HlasmRun(3, "", ""),
        caller_area,
        [
            caller_area,
            base + 76,
            AMODE_31 | word(148),
            base + 4,
            33,
            base + 4,
            word(148),
        ],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bad_operands_refuse_the_assembly_with_severity_8():
    with pytest.raises(HlasmParseError) as refused:
        run_hlasm(programs.BAD_OPERANDS)

    assert [
        (d.message, d.related[0].line, d.mnote.level) for d in refused.value.diagnostics
    ] == [(m, line, 8) for m, line in programs.BAD_OPERAND_REFUSALS]
