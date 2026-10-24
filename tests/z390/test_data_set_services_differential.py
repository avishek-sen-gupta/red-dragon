# pyright: standard
"""OPEN, GET, PUT and CLOSE in RedDragon, with our macros, and in z390, with its own, over the same input data set: z390 finds a DDNAME's file through the environment variable of that name. The DCB layouts differ, so the programs compare registers and the output data set, not DCB fields. z390 does not write the record a locate-mode PUT left in its buffer when CLOSE is issued; IBM does, and so do we."""

from pathlib import Path

import pytest

from interpreter.hlasm_run_inputs.dd_definition import DdDefinition
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import data_set_service_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
FIXED_RECORD = 80
Z390_DROPS_THE_LAST_LOCATE_PUT = programs.FIXED_INPUT[: 2 * FIXED_RECORD]
CASES = {
    "fixed_move": (programs.COPY_MOVE, programs.FIXED_INPUT, {2: 3, 7: 0, 8: 0}),
    "fixed_locate": (programs.COPY_LOCATE, programs.FIXED_INPUT, {2: 3}),
    "variable_move": (
        programs.COPY_VARIABLE,
        programs.VARIABLE_INPUT,
        {4: programs.FIRST_DESCRIPTOR},
    ),
}
Z390_OUTPUT = {"fixed_locate": Z390_DROPS_THE_LAST_LOCATE_PUT}


def _copied(tmp_path: Path, given: bytes) -> tuple[Path, Path]:
    tmp_path.mkdir()
    (tmp_path / "in.dat").write_bytes(given)
    return tmp_path / "in.dat", tmp_path / "out.dat"


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(CASES))
def test_a_copy_matches_z390(z390: Z390Runner, tmp_path: Path, case: str):
    source, given, expected = CASES[case]
    ours_in, ours_out = _copied(tmp_path / "ours", given)
    theirs_in, theirs_out = _copied(tmp_path / "theirs", given)

    ours = run_hlasm_machine(
        source,
        dds={"INDD": DdDefinition(ours_in), "OUTDD": DdDefinition(ours_out)},
    )
    theirs = z390.run_machine(
        source, tmp_path / "theirs", {"INDD": str(theirs_in), "OUTDD": str(theirs_out)}
    )

    assert (
        (
            ours.run,
            {r: ours.gprs[r] & 0xFFFFFFFF for r in expected},
            ours_out.read_bytes(),
        ),
        (
            theirs.run,
            {r: theirs.gprs[r] & 0xFFFFFFFF for r in expected},
            theirs_out.read_bytes(),
        ),
    ) == (
        (ABENDED, expected, given),
        (ABENDED, expected, Z390_OUTPUT.get(case, given)),
    )
