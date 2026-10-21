# pyright: standard
"""Load and store programs leave the same declared registers and CC in RedDragon and in z390."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import load_store_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm, run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")

FAMILIES = {
    "storage loads, 32-bit": (
        programs.STORAGE_LOADS_32,
        programs.STORAGE_LOADS_32_RESULTS,
    ),
    "partial inserts": (programs.PARTIAL_INSERTS, programs.PARTIAL_INSERTS_RESULTS),
    "storage loads, 64-bit": (
        programs.STORAGE_LOADS_64,
        programs.STORAGE_LOADS_64_RESULTS,
    ),
    "more storage loads, 64-bit": (
        programs.MORE_LOADS_64,
        programs.MORE_LOADS_64_RESULTS,
    ),
    "guarded loads": (programs.GUARDED_LOADS, programs.GUARDED_LOADS_RESULTS),
    "register loads": (programs.REGISTER_LOADS, programs.REGISTER_LOADS_RESULTS),
    "more register loads": (
        programs.MORE_REGISTER_LOADS,
        programs.MORE_REGISTER_LOADS_RESULTS,
    ),
    "relative loads": (programs.RELATIVE_LOADS, programs.RELATIVE_LOADS_RESULTS),
    "stores": (programs.STORES, programs.STORES_RESULTS),
    "more stores": (programs.MORE_STORES, programs.MORE_STORES_RESULTS),
    "relative stores": (programs.RELATIVE_STORES, programs.RELATIVE_STORES_RESULTS),
    "load multiple wrapping": (
        programs.LOAD_MULTIPLE_WRAPPING,
        programs.LOAD_MULTIPLE_WRAPPING_RESULTS,
    ),
    "multiples": (programs.MULTIPLES, programs.MULTIPLES_RESULTS),
    "store under mask": (programs.STORE_MASKED, programs.STORE_MASKED_RESULTS),
}


def _both(
    z390: Z390Runner, source: str, tmp: Path, registers: Mapping[int, int]
) -> tuple[HlasmMachine, HlasmMachine]:
    return (
        run_hlasm_machine(source).restricted_to(registers),
        z390.run_machine(source, tmp).restricted_to(registers),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("family", list(FAMILIES))
def test_family_matches(z390: Z390Runner, tmp_path: Path, family: str):
    body, results = FAMILIES[family]
    source = programs.based_program(body, programs.ABEND)

    expected = HlasmMachine(ABENDED, 0, results)
    assert _both(z390, source, tmp_path, results) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", range(len(programs.INSERT_MASKED_CASES)))
def test_insert_under_mask_cc_matches(z390: Z390Runner, tmp_path: Path, case: int):
    body, value, cc = programs.INSERT_MASKED_CASES[case]
    source = programs.based_program(body, programs.ABEND)

    expected = HlasmMachine(ABENDED, cc, {2: value})
    assert _both(z390, source, tmp_path, {2: value}) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_misaligned_relative_load_abends_here_but_not_in_z390(
    z390: Z390Runner, tmp_path: Path
):
    source = programs.based_program("         LRL   2,NEG+2\n", programs.ABEND)

    assert run_hlasm(source) == HlasmRun(return_code=0, abend="S0C6", stdout="")
    assert z390.run_machine(source, tmp_path).restricted_to((2,)) == HlasmMachine(
        ABENDED, 0, {2: programs.HIGH_FILL | 0x00017FFF}
    )
