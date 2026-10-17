"""End-to-end: switch-status conditions read the run's switch settings; SET changes them."""

from __future__ import annotations

from pathlib import Path

import pytest

from cobol_asg.switch_status import SwitchStatus
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.run import run
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    to_fixed,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")


def _flag(condition: str, flag: str) -> list[str]:
    return [f"    IF {condition}", f'        MOVE "Y" TO {flag}', "    END-IF."]


@covers(CobolFeature.IMPLEMENTOR_SWITCH)
def test_switch_conditions_follow_the_supplied_settings_and_set(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    flags = [f"F{n}" for n in range(1, 9)]
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. SWITCHES.",
            "ENVIRONMENT DIVISION.",
            "CONFIGURATION SECTION.",
            "SPECIAL-NAMES.",
            "    SWITCH-1 IS SW-1",
            "        ON STATUS IS ON-SWITCH-1",
            "        OFF STATUS IS OFF-SWITCH-1",
            "    SWITCH-2 IS SW-2",
            "        OFF IS OFF-SWITCH-2",
            "        ON IS ON-SWITCH-2.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            *(f'01 {flag} PIC X VALUE "N".' for flag in flags),
            "PROCEDURE DIVISION.",
            "MAIN-PARA.",
            *_flag("ON-SWITCH-1", "F1"),
            *_flag("OFF-SWITCH-1", "F2"),
            *_flag("ON-SWITCH-2", "F3"),
            *_flag("NOT OFF-SWITCH-2", "F4"),
            "    SET SW-1 TO OFF SW-2 TO ON.",
            *_flag("OFF-SWITCH-1", "F5"),
            *_flag("ON-SWITCH-1", "F6"),
            *_flag("ON-SWITCH-2", "F7"),
            *_flag("NOT OFF-SWITCH-2", "F8"),
            f"    DISPLAY {' '.join(flags)}.",
            "    STOP RUN.",
        ]
    )
    run(
        source=source,
        language="cobol",
        max_steps=5000,
        io_provider=RealFileIOProvider(
            base_dir=tmp_path, switches={"SWITCH-1": SwitchStatus.ON}
        ),
    )
    assert capsys.readouterr().out == "YNNNYNYY\n"
