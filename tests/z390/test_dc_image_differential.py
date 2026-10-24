# pyright: standard
"""DC constants hold the same images in RedDragon and in z390, except floating-point forms z390 misassembles, pinned here as z390 assembles them (red-dragon-6uyp.74): it keeps the sign of an unextended HFP zero, ignores scale digits, applies EE2 as E-2, sets HFP (MIN) one characteristic too high and DFP (MIN) to (DMIN), truncates fractions cut by a length modifier, overflows 3.4028235E38 to infinity, drops a zero's quantum and wraps a DFP overflow. RedDragon's images for them are PAST_Z390 in tests/integration/hlasm/dc_image_programs.py."""

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


Z390_FLOATING_POINT = (
    "         DC    E'-0',ES2'1'\n"
    "         DC    EE2'.46415',EH'(MIN)'\n"
    "         DC    EL5'0.1',XL3'0'\n"
    "         DC    DL3'0.1',XL5'0'\n"
    "         DC    LL10'0.1',XL6'0'\n"
    "         DC    LS3'1'\n"
    "         DC    EB'3.4028235E38',ED'(MIN)'\n"
    "         DC    ED'0.000',ED'-0'\n"
    "         DC    DD'(MIN)'\n"
    "         DC    LD'1.5E6200'\n"
)
Z390_FLOATING_POINT_IMAGE = (
    "80000000"
    "43100000"
    "3F1302F7"
    "01100000"
    "4019999A"
    "00000000"
    "40199900"
    "00000000"
    "40199999"
    "99999999"
    "32990000"
    "00000000"
    "44100000"
    "00000000"
    "36000000"
    "00000000"
    "7F800000"
    "00000001"
    "22500000"
    "A2500000"
    "00000000"
    "00000001"
    "0015C000"
    "00000000"
    "00000000"
    "00000015"
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_z390_misassembles_floating_point_constants(z390: Z390Runner, tmp_path: Path):
    expected = programs.registers(Z390_FLOATING_POINT_IMAGE)
    source = programs.image_program(Z390_FLOATING_POINT, len(expected))

    assert z390.run_machine(source, tmp_path).restricted_to(expected) == HlasmMachine(
        ABENDED, 0, expected
    )
