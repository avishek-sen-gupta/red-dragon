# pyright: standard
"""Edit programs leave the same declared registers, CC and abend in RedDragon and in z390."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import edit_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.ALL_CASES))
def test_edit_matches(z390: Z390Runner, tmp_path: Path, case: str):
    (body, results, cc), run = programs.ALL_CASES[case]
    source = programs.edit_program(body)

    expected = HlasmMachine(run, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)
