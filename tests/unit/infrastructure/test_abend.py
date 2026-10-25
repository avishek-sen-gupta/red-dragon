# pyright: standard
"""Abend types render as z/OS prints them."""

from infrastructure.zos.abend.system_abend import SystemAbend
from infrastructure.zos.abend.user_abend import UserAbend


def test_abends_render_as_zos_prints_them() -> None:
    assert SystemAbend(0x0C7).rendered() == "S0C7"
    assert SystemAbend(0x806).rendered() == "S806"
    assert UserAbend(1).rendered() == "U0001"
    assert UserAbend(4038).rendered() == "U4038"
