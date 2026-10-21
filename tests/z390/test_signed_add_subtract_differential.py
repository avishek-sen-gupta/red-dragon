# pyright: standard
"""Signed add and subtract programs leave the same declared registers and CC in RedDragon and in z390."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm import signed_add_subtract_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")


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
