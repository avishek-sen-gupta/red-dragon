# pyright: standard
"""DCB, DCBD, OPEN, CLOSE, GET and PUT from our maclib, run in the VM over the run's DD definitions and the file provider."""

import pytest

from hlasm_asg.hlasm_parse_error import HlasmParseError
from hlasm_asg.program.mnote_level import MnoteLevel
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import data_set_service_programs as programs
from tests.integration.hlasm.hlasm_helpers import (
    run_hlasm,
    run_hlasm_machine,
    run_hlasm_storage,
)
from tests.integration.hlasm.hlasm_run import HlasmRun

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
DCB_BYTES = 96


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_dcb_macro_lays_out_its_operands_at_ibm_offsets():
    at = programs.DCB_IMAGE_AT
    ran, image = run_hlasm_storage(programs.DCB_IMAGE, "T", (at, at + DCB_BYTES))

    assert (ran.run, image) == (
        ABENDED,
        programs.dcb_image(ran.gprs[2] & 0xFFFFFF, ran.gprs[3] & 0xFFFFFF),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dcbd_names_each_field_and_flag_of_a_dcb():
    ran = run_hlasm_machine(programs.DCBD_FIELDS)

    assert (
        ran.run,
        {r: ran.gprs[r] & 0xFFFFFFFF for r in programs.DCBD_REGISTERS},
    ) == (ABENDED, programs.DCBD_REGISTERS)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bad_dcb_operands_refuse_the_assembly_with_severity_8():
    with pytest.raises(HlasmParseError) as refused:
        run_hlasm(programs.BAD_DCBS)

    assert [
        (d.message, d.related[-1].line, d.mnote) for d in refused.value.diagnostics
    ] == [
        (m, line, MnoteLevel(kind="LEVEL", level=8))
        for m, line in programs.BAD_DCB_REFUSALS
    ]
