# pyright: standard
"""Shift and rotate programs leave the same declared registers and CC in RedDragon and in z390, bar z390's known SLL, RISBGN and shift-logical-high errors."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm import shift_rotate_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_assembly_failed import Z390AssemblyFailed
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")

OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")

Z390_MACHINE: Mapping[str, HlasmMachine] = {
    "SLL amount 33 from a base register": HlasmMachine(
        ABENDED, programs.CC_KEPT, {2: storage.HIGH_FILL | 0x00000002}
    ),
    "RISBGN": HlasmMachine(OPERATION, programs.CC_KEPT, {5: storage.FILL}),
    "RISBGNZ": HlasmMachine(OPERATION, programs.CC_KEPT, {5: storage.FILL}),
}

Z390_UNASSEMBLED = list(programs.HIGH_WORD_SHIFTS)

MATCHING = [
    mnemonic
    for mnemonic in programs.CASES
    if mnemonic not in Z390_MACHINE and mnemonic not in Z390_UNASSEMBLED
]


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

    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (HlasmMachine(ABENDED, cc, results), Z390_MACHINE[mnemonic])


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("mnemonic", Z390_UNASSEMBLED)
def test_shift_logical_high_runs_from_the_principles_of_operation_but_z390_refuses_it(
    z390: Z390Runner, tmp_path: Path, mnemonic: str
):
    body, results, cc = programs.CASES[mnemonic]
    source = storage.based_program(body, storage.ABEND)

    assert run_hlasm_machine(source).restricted_to(results) == HlasmMachine(
        ABENDED, cc, results
    )
    with pytest.raises(Z390AssemblyFailed, match="AZ390E error  50"):
        z390.run_machine(source, tmp_path)
