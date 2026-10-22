# pyright: standard
"""CP and TP programs leave the same CC and abend in RedDragon and in z390."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import packed_compare_test_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.ALL_CASES))
def test_packed_compare_and_test_match(z390: Z390Runner, tmp_path: Path, case: str):
    (body, cc), run = programs.ALL_CASES[case]
    source = programs.compare_test_program(body)

    expected = HlasmMachine(run, cc, {})
    assert (
        run_hlasm_machine(source).restricted_to(()),
        z390.run_machine(source, tmp_path).restricted_to(()),
    ) == (expected, expected)
