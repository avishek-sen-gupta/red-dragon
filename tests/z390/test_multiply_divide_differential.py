# pyright: standard
"""Multiply and divide programs leave the same declared registers and CC in RedDragon and in z390, bar z390's missing quotient-overflow divide exceptions."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm import multiply_divide_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
FIXED_POINT_DIVIDE = HlasmRun(return_code=0, abend="S0C9", stdout="")

Z390_MACHINE: Mapping[str, HlasmMachine] = {
    "DR quotient beyond a signed word": HlasmMachine(
        ABENDED, programs.CC_KEPT, {2: storage.HIGH_FILL, 3: storage.HIGH_FILL}
    ),
    "DL quotient beyond an unsigned word": HlasmMachine(
        ABENDED, programs.CC_KEPT, {2: storage.HIGH_FILL, 3: storage.HIGH_FILL}
    ),
    "DSGR minimum by minus one": HlasmMachine(
        ABENDED, programs.CC_KEPT, {4: 0, 5: 0x80000000_00000000}
    ),
}

MATCHING_EXCEPTIONS = [
    case for case in programs.DIVIDE_EXCEPTIONS if case not in Z390_MACHINE
]


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("mnemonic", list(programs.CASES))
def test_mnemonic_matches(z390: Z390Runner, tmp_path: Path, mnemonic: str):
    body, results, cc = programs.CASES[mnemonic]
    source = storage.based_program(body, storage.ABEND)

    expected = HlasmMachine(ABENDED, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", MATCHING_EXCEPTIONS)
def test_divide_exception_matches(z390: Z390Runner, tmp_path: Path, case: str):
    body, results, cc = programs.DIVIDE_EXCEPTIONS[case]
    source = storage.based_program(body, storage.ABEND)

    expected = HlasmMachine(FIXED_POINT_DIVIDE, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_MACHINE))
def test_quotient_overflow_abends_here_but_z390_keeps_the_truncated_quotient(
    z390: Z390Runner, tmp_path: Path, case: str
):
    body, results, cc = programs.DIVIDE_EXCEPTIONS[case]
    source = storage.based_program(body, storage.ABEND)

    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (HlasmMachine(FIXED_POINT_DIVIDE, cc, results), Z390_MACHINE[case])
