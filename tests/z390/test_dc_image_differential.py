# pyright: standard
"""DC constants hold the same images in RedDragon and in z390."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import dc_image_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("family", list(programs.FAMILIES))
def test_family_matches(z390: Z390Runner, tmp_path: Path, family: str):
    constants, image = programs.FAMILIES[family]
    expected = programs.registers(image)
    source = programs.image_program(constants, len(expected))

    assert (
        run_hlasm_machine(source).restricted_to(expected),
        z390.run_machine(source, tmp_path).restricted_to(expected),
    ) == (HlasmMachine(ABENDED, 0, expected), HlasmMachine(ABENDED, 0, expected))
