# pyright: standard
"""DCB, DCBD, OPEN, CLOSE, GET and PUT from our maclib, run in the VM over the run's DD definitions and the file provider."""

from pathlib import Path

import pytest

from hlasm_asg.hlasm_parse_error import HlasmParseError
from hlasm_asg.program.mnote_level import MnoteLevel
from interpreter.hlasm_run_inputs.dd_definition import DdDefinition
from interpreter.hlasm_run_inputs.record_format import RecordFormat
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
AMODE_31_BIT = 0x80000000


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
def test_bad_dcb_and_open_operands_refuse_the_assembly_with_severity_8():
    with pytest.raises(HlasmParseError) as refused:
        run_hlasm(programs.BAD_DCBS)

    assert [
        (d.message, d.related[-1].line, d.mnote) for d in refused.value.diagnostics
    ] == [
        (m, line, MnoteLevel(kind="LEVEL", level=8))
        for m, line in programs.BAD_DCB_REFUSALS
    ]


def _dds(tmp_path: Path, given: bytes) -> dict[str, DdDefinition]:
    (tmp_path / "in.dat").write_bytes(given)
    return {
        "INDD": DdDefinition(tmp_path / "in.dat"),
        "OUTDD": DdDefinition(tmp_path / "out.dat"),
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_move_mode_copies_fixed_records_and_ends_at_eodad(tmp_path: Path):
    ran = run_hlasm_machine(
        programs.COPY_MOVE, dds=_dds(tmp_path, programs.FIXED_INPUT)
    )

    assert (
        ran.run,
        {r: ran.gprs[r] for r in programs.COPY_MOVE_REGISTERS},
        ran.gprs[6],
        (tmp_path / "out.dat").read_bytes(),
    ) == (
        ABENDED,
        programs.COPY_MOVE_REGISTERS,
        ran.gprs[5] | AMODE_31_BIT,
        programs.FIXED_INPUT,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_locate_mode_get_and_put_copy_through_their_buffers(tmp_path: Path):
    ran = run_hlasm_machine(
        programs.COPY_LOCATE, dds=_dds(tmp_path, programs.FIXED_INPUT)
    )

    assert (ran.run, ran.gprs[2], (tmp_path / "out.dat").read_bytes()) == (
        ABENDED,
        3,
        programs.FIXED_INPUT,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_variable_records_carry_their_rdw_through_get_and_put(tmp_path: Path):
    ran = run_hlasm_machine(
        programs.COPY_VARIABLE, dds=_dds(tmp_path, programs.VARIABLE_INPUT)
    )

    assert (ran.run, ran.gprs[4], (tmp_path / "out.dat").read_bytes()) == (
        ABENDED,
        programs.FIRST_DESCRIPTOR,
        programs.VARIABLE_INPUT,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize(
    ("source", "abend"),
    [
        (programs.NO_EODAD, "S337"),
        (programs.EODAD_ZERO, "S337"),
        (programs.NOT_OPENED, "S0C1"),
        (programs.PUT_BEFORE_OPEN, "S0C1"),
        (programs.NO_LRECL, "S013"),
        (programs.VARIABLE_PUT_OVER_LRECL, "S002"),
    ],
    ids=[
        "end_of_data_without_eodad",
        "end_of_data_with_eodad_zero",
        "get_before_open",
        "put_before_open",
        "open_without_lrecl",
        "variable_put_over_lrecl",
    ],
)
def test_data_set_misuse_abends(tmp_path: Path, source: str, abend: str):
    ran = run_hlasm_machine(
        source, dds=_dds(tmp_path, programs.fixed_records("ONLY RECORD"))
    )

    assert ran.run == HlasmRun(return_code=0, abend=abend, stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_open_fills_empty_dcb_fields_from_the_dd_and_fails_a_dd_or_mode_it_lacks(
    tmp_path: Path,
):
    (tmp_path / "in.dat").write_bytes(programs.FIXED_INPUT)
    (tmp_path / "ex.dat").write_bytes(programs.fixed_records("FIRST RECORD"))
    dds = {
        "INDD": DdDefinition(tmp_path / "in.dat", RecordFormat.FB, 80, 800),
        "EXDD": DdDefinition(tmp_path / "ex.dat"),
    }

    ran = run_hlasm_machine(programs.OPEN_FROM_DDS, dds=dds)

    assert (
        ran.run,
        {r: ran.gprs[r] for r in programs.OPEN_FROM_DDS_REGISTERS},
        (tmp_path / "ex.dat").read_bytes(),
        Path("nodd.dat").exists(),
    ) == (ABENDED, programs.OPEN_FROM_DDS_REGISTERS, programs.EXTENDED, False)
