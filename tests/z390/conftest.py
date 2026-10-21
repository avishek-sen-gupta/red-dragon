# pyright: standard
"""The z390 runner the differential tests compare RedDragon against."""

import os
from pathlib import Path

import pytest

from hlasm_asg.real_subprocess_runner import RealSubprocessRunner
from tests.z390.z390_runner import Z390Runner

Z390_HOME = "Z390_HOME"


@pytest.fixture
def z390() -> Z390Runner:
    home = os.environ.get(Z390_HOME, "")
    if not home:
        pytest.fail(
            f"{Z390_HOME} is not set: point it at a built z390 checkout to run -m z390"
        )
    return Z390Runner(Path(home), RealSubprocessRunner())
