# pyright: standard
"""Boolean programs leave the same declared registers and CC in RedDragon and in z390, bar z390's known field-CC, XI and OC errors."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import boolean_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")

Z390_MACHINE: Mapping[str, tuple[int, Mapping[int, int]]] = {
    "NIHF": (0, programs.CASES["NIHF"][1]),
    "NILF": (1, programs.CASES["NILF"][1]),
    "XIHF": (1, programs.CASES["XIHF"][1]),
    "OIHF": (0, programs.CASES["OIHF"][1]),
    "OILF": (0, programs.CASES["OILF"][1]),
    "XILF": (0, programs.CASES["XILF"][1]),
    "NIHH": (1, programs.CASES["NIHH"][1]),
    "NILL": (1, programs.CASES["NILL"][1]),
    "OILH": (1, programs.CASES["OILH"][1]),
    "XI": (1, programs.CASES["XI"][1]),
    "OC": (1, {7: 0x5A5A0000_00000000}),
}

MATCHING = [mnemonic for mnemonic in programs.CASES if mnemonic not in Z390_MACHINE]


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
@pytest.mark.parametrize("mnemonic", list(Z390_MACHINE))
def test_mnemonic_follows_the_principles_of_operation_where_z390_does_not(
    z390: Z390Runner, tmp_path: Path, mnemonic: str
):
    body, results, cc = programs.CASES[mnemonic]
    source = storage.based_program(body, storage.ABEND)
    z390_cc, z390_results = Z390_MACHINE[mnemonic]

    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (
        HlasmMachine(ABENDED, cc, results),
        HlasmMachine(ABENDED, z390_cc, z390_results),
    )
