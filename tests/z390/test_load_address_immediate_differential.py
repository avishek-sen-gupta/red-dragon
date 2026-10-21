# pyright: standard
"""Load address and immediate programs leave the same declared registers and CC in RedDragon and in z390."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import load_address_immediate_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")

FAMILIES = {
    "addresses": (programs.ADDRESSES, programs.ADDRESSES_RESULTS),
    "loaded immediates": (
        programs.LOADED_IMMEDIATES,
        programs.LOADED_IMMEDIATES_RESULTS,
    ),
    "inserted immediates": (
        programs.INSERTED_IMMEDIATES,
        programs.INSERTED_IMMEDIATES_RESULTS,
    ),
}

INDEXED_FAMILIES = {
    "indexed": (programs.INDEXED, programs.INDEXED_RESULTS),
    "logical indexed": (programs.LOGICAL_INDEXED, programs.LOGICAL_INDEXED_RESULTS),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("family", list(FAMILIES))
def test_family_matches(z390: Z390Runner, tmp_path: Path, family: str):
    body, results = FAMILIES[family]
    source = storage.based_program(body, storage.ABEND)

    expected = HlasmMachine(ABENDED, programs.CC_TWO, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_load_address_extended_beyond_storage_completes_here_but_not_in_z390(
    z390: Z390Runner, tmp_path: Path
):
    source = storage.based_program(programs.BEYOND_STORAGE, storage.ABEND)
    results = programs.BEYOND_STORAGE_RESULTS

    assert run_hlasm_machine(source).restricted_to(results) == HlasmMachine(
        ABENDED, 0, results
    )
    assert z390.run_machine(source, tmp_path).run == HlasmRun(
        return_code=0, abend="S0C5", stdout=""
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("family", list(INDEXED_FAMILIES))
def test_indexed_address_runs_here_from_the_principles_of_operation_but_not_in_z390(
    z390: Z390Runner, tmp_path: Path, family: str
):
    body, results = INDEXED_FAMILIES[family]
    source = storage.based_program(body, storage.ABEND)

    assert run_hlasm_machine(source).restricted_to(results) == HlasmMachine(
        ABENDED, programs.CC_TWO, results
    )
    assert z390.run_machine(source, tmp_path).run == HlasmRun(
        return_code=0, abend="S0C1", stdout=""
    )
