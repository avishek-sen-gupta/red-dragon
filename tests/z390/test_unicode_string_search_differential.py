# pyright: standard
"""SRST programs leave the same registers and CC in RedDragon and in z390; z390 does not execute the Unicode conversions or SRSTU (it abends S0C1), so a representative case per mnemonic checks RedDragon against the Principles of Operation expectation and pins z390's operation exception."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import unicode_string_search_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import HIGH_FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")
OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")

SEARCH_STRING_CASES: Mapping[str, tuple[programs.Case, HlasmRun]] = {
    **{
        name: (case, ABENDED)
        for name, case in programs.SEARCHES.items()
        if name.startswith("SRST ")
    },
    "SRST GR0 bits 32-55": (
        programs.SPECIFICATION_EXCEPTIONS["SRST GR0 bits 32-55"],
        SPECIFICATION,
    ),
}


def _unexecuted(target_length: int, source_length: int) -> HlasmMachine:
    return HlasmMachine(
        OPERATION,
        programs.INITIAL_CC,
        {3: HIGH_FILL | target_length, 5: HIGH_FILL | source_length},
    )


Z390_MACHINE: Mapping[str, HlasmMachine] = {
    "CU12 exhausted": _unexecuted(16, 10),
    "CUTFU exhausted": _unexecuted(16, 10),
    "CU14 exhausted": _unexecuted(16, 10),
    "CU21 exhausted": _unexecuted(16, 10),
    "CUUTF exhausted": _unexecuted(16, 10),
    "CU24 exhausted": _unexecuted(16, 10),
    "CU41 exhausted": _unexecuted(16, 16),
    "CU42 exhausted": _unexecuted(16, 16),
    "SRSTU found": HlasmMachine(OPERATION, programs.INITIAL_CC, {0: 0x42}),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(SEARCH_STRING_CASES))
def test_search_string_matches(z390: Z390Runner, tmp_path: Path, case: str):
    (body, results, cc), run = SEARCH_STRING_CASES[case]
    source = programs.unicode_program(body)

    expected = HlasmMachine(run, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_MACHINE))
def test_unicode_string_search_follows_the_principles_of_operation_where_z390_does_not(
    z390: Z390Runner, tmp_path: Path, case: str
):
    body, results, cc = programs.CASES[case]
    source = programs.unicode_program(body)
    z390_machine = Z390_MACHINE[case]

    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(z390_machine.gprs),
    ) == (HlasmMachine(ABENDED, cc, results), z390_machine)
