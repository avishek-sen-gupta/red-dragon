# pyright: standard
"""The job-step PARM image: a halfword length and the text in EBCDIC through the machine's table, padded to 100 bytes; text longer than 100 characters, or with a character the table has no code for, is refused."""

import pytest

from interpreter.hlasm_run_inputs.job_parm_builtins import job_parm_builtins
from interpreter.hlasm_run_inputs.parm_not_encodable import ParmNotEncodable
from interpreter.hlasm_run_inputs.parm_too_long import ParmTooLong
from interpreter.hlasm_run_inputs.run_input_names import JOB_PARM_BUILTIN
from interpreter.run import initial_vm_state
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parm_image_and_refusals():
    image = job_parm_builtins("Aé")[JOB_PARM_BUILTIN]([], initial_vm_state()).value

    with pytest.raises(ParmTooLong) as long:
        job_parm_builtins("X" * 101)
    with pytest.raises(ParmNotEncodable) as unencodable:
        job_parm_builtins("A€")

    assert image == [0, 2, 0xC1, 0x51, *[0] * 98]
    assert [str(long.value), str(unencodable.value)] == [
        "PARM of 101 characters exceeds 100",
        "PARM character '€' has no EBCDIC code",
    ]
