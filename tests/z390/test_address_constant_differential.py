# pyright: standard
"""Each address constant that names * holds its own address, in RedDragon and in z390."""

from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import HlasmRun, run_hlasm
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

SLOTS_AND_VALUES = (
    (0, 0),
    (4, 4),
    (8, 8),
    (12, 12),
    (16, 16),
    (20, 22),
    (24, 24),
    (28, 30),
)


def _check(index: int, slot: int, value: int) -> str:
    return (
        f"         L     2,V+{slot}\n"
        f"         LA    3,V+{value}\n"
        "         CR    2,3\n"
        f"         BE    OK{index}\n"
        f"         AHI   15,{1 << index}\n"
        f"OK{index}      DS    0H\n"
    )


SOURCE = (
    "T        CSECT\n"
    "         BASR  12,0\n"
    "         USING *,12\n"
    "         SR    15,15\n"
    + "".join(
        _check(i, slot, value) for i, (slot, value) in enumerate(SLOTS_AND_VALUES)
    )
    + "         BR    14\n"
    "V        DC    2A(*),A(*,*),2A(*,*+2)\n"
    "         END   T\n"
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_star_in_duplicated_and_multi_value_constants_matches(
    z390: Z390Runner, tmp_path: Path
):
    expected = HlasmRun(return_code=0, abend="", stdout="")

    assert (run_hlasm(SOURCE), z390.run(SOURCE, tmp_path)) == (expected, expected)
