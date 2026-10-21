# pyright: standard
"""Logical add and subtract programs leave the same declared registers and CC in RedDragon and in z390, bar z390's known CC errors."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm import logical_add_subtract_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")

Z390_CC = {
    "ALGRK": 1,
    "SLGRK": 1,
    "ALHSIK": 1,
    "ALGHSIK": 0,
    "ALSI": 3,
    "ALGSI": 1,
}

MATCHING = [mnemonic for mnemonic in programs.CASES if mnemonic not in Z390_CC]


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("mnemonic", MATCHING)
def test_mnemonic_matches(z390: Z390Runner, tmp_path: Path, mnemonic: str):
    body, results, cc = programs.CASES[mnemonic]
    source = storage.based_program(body, storage.ABEND)

    expected = HlasmMachine(ABENDED, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("mnemonic", list(Z390_CC))
def test_mnemonic_sets_the_principles_of_operation_cc_where_z390_does_not(
    z390: Z390Runner, tmp_path: Path, mnemonic: str
):
    body, results, cc = programs.CASES[mnemonic]
    source = storage.based_program(body, storage.ABEND)

    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (
        HlasmMachine(ABENDED, cc, results),
        HlasmMachine(ABENDED, Z390_CC[mnemonic], results),
    )
