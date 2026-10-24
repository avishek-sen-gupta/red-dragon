# pyright: standard
"""SAVE, RETURN and YREGS from our maclib: instructions only, run in the VM."""

from functools import partial

import pytest

from hlasm_asg.hlasm_parse_error import HlasmParseError
from hlasm_asg.program.mnote_level import MnoteLevel
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
@pytest.mark.parametrize("case", [*programs.SUB_CASES, *programs.VM_ONLY_CASES])
def test_save_and_return_restore_the_registers_they_cover(case: str):
    body, expected = {**programs.SUB_CASES, **programs.VM_ONLY_CASES}[case]

    ran = run_hlasm_machine(programs.caller(body))

    assert (ran.run, programs.machine_view(ran.gprs)) == (ABENDED, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("label", list(programs.IDENTIFIERS))
def test_the_identifier_follows_a_branch_at_entry_and_names_the_label_or_csect(
    label: str,
):
    name = programs.IDENTIFIERS[label]
    ran, stored = run_hlasm_storage(
        programs.standard(label),
        "MAIN",
        (programs.ID_START, programs.ID_START + 1 + len(name)),
    )

    assert (ran.run, stored) == (
        HlasmRun(7, "", ""),
        bytes([len(name)]) + name.encode("cp037"),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_nested_subroutine_chains_through_its_own_save_area():
    start, _ = programs.NESTED_SPAN
    ran, stored = run_hlasm_storage(programs.NESTED, "MAIN", programs.NESTED_SPAN)
    word = partial(_word, stored, start=start)
    base = word(programs.BASE_WORD)
    keep = word(programs.KEEP_WORD)
    caller_area = word(programs.SA_BACK_CHAIN_WORD)

    assert (
        ran.run,
        ran.gprs[13] & LOW_WORD,
        [
            word(o)
            for o in (
                programs.SA_BACK_CHAIN_WORD,
                programs.SA_FORWARD_CHAIN_WORD,
                programs.SAVED_R14_WORD,
                programs.SAVED_R2_WORD,
                programs.SAVED_R3_WORD,
                programs.ISA_BACK_CHAIN_WORD,
            )
        ],
    ) == (
        HlasmRun(3, "", ""),
        caller_area,
        [
            caller_area,
            base + programs.ISA_FROM_BASE,
            AMODE_31 | keep,
            base + programs.SA_FROM_BASE,
            33,
            base + programs.SA_FROM_BASE,
        ],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bad_operands_refuse_the_assembly_with_severity_8():
    with pytest.raises(HlasmParseError) as refused:
        run_hlasm(programs.BAD_OPERANDS)

    assert [
        (d.message, d.related[0].line, d.mnote) for d in refused.value.diagnostics
    ] == [
        (m, line, MnoteLevel(kind="LEVEL", level=8))
        for m, line in programs.BAD_OPERAND_REFUSALS
    ]
