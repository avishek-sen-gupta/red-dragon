"""Unit and linked-program files round-trip; a bad file names itself."""

import json

import pytest

from interpreter.cfg import build_cfg
from interpreter.frontend import make_cobol_parser
from interpreter.ir import CodeLabel
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.coded_diagnostic import CodedDiagnostic
from interpreter.project.comment_mnote import CommentMnote
from interpreter.project.constant_diagnostic import ConstantDiagnostic
from interpreter.project.dc_warning_kind import DcWarningKind
from interpreter.project.diagnostic_place import DiagnosticPlace
from interpreter.project.diagnostic_severity import DiagnosticSeverity
from interpreter.project.in_macro import InMacro
from interpreter.project.in_open_code import InOpenCode
from interpreter.project.ir_codec import IrCodec
from interpreter.project.linked_codec import LinkedCodec
from interpreter.project.severity_mnote import SeverityMnote
from interpreter.project.unit_codec import UnitCodec
from interpreter.project.unit_diagnostic import UnitDiagnostic
from interpreter.project.unit_format_error import UnitFormatError
from tests.covers import NotLanguageFeature, covers

_SOURCE = (
    b"       IDENTIFICATION DIVISION.\n"
    b"       PROGRAM-ID. CALLER.\n"
    b"       DATA DIVISION.\n"
    b"       WORKING-STORAGE SECTION.\n"
    b"       01 WS-N PIC 9(4) VALUE 5.\n"
    b"       PROCEDURE DIVISION.\n"
    b"           ADD 1 TO WS-N.\n"
    b"           GOBACK.\n"
)


def _linked():
    return compile_cobol(_SOURCE, parser=make_cobol_parser())


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_unit_round_trips_through_its_file(tmp_path):
    module = next(iter(_linked().modules.values()))
    unit = module.__class__(
        **{
            **vars(module),
            "entry_label": CodeLabel("func_caller_0"),
            "diagnostics": (
                UnitDiagnostic(
                    DiagnosticSeverity.WARNING,
                    SeverityMnote(4, "CAREFUL"),
                    DiagnosticPlace("GREET", 3),
                    (DiagnosticPlace("CALLER", 9),),
                ),
                UnitDiagnostic(
                    DiagnosticSeverity.INFO,
                    CommentMnote("ASIDE"),
                    DiagnosticPlace("GREET", 4),
                ),
                UnitDiagnostic(
                    DiagnosticSeverity.WARNING,
                    CodedDiagnostic("A300", "Apostrophes missing"),
                    DiagnosticPlace("CALLER", 2),
                ),
                UnitDiagnostic(
                    DiagnosticSeverity.WARNING,
                    ConstantDiagnostic(
                        "EB'1E39'", DcWarningKind.OVERFLOW, InOpenCode()
                    ),
                    DiagnosticPlace("CALLER", 5),
                ),
                UnitDiagnostic(
                    DiagnosticSeverity.WARNING,
                    ConstantDiagnostic(
                        "EB'1E-50'", DcWarningKind.UNDERFLOW, InMacro("GEN")
                    ),
                    DiagnosticPlace("CALLER", 6),
                ),
            ),
        }
    )
    codec = UnitCodec(IrCodec())
    codec.write(unit, tmp_path / "caller.unit.json")
    assert codec.read(tmp_path / "caller.unit.json") == unit


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linked_program_round_trips_and_rebuilds_its_cfg(tmp_path):
    linked = _linked()
    codec = LinkedCodec(IrCodec())
    codec.write(linked, tmp_path / "caller.linked.json")
    read = codec.read(tmp_path / "caller.linked.json")
    assert (read, read.merged_cfg) == (linked, build_cfg(list(linked.merged_ir)))


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("text", ['{"format": 99, "unit": null}', '{"format": 1, "un'])
def test_a_file_that_does_not_decode_names_itself(tmp_path, text):
    bad = tmp_path / "bad.unit.json"
    bad.write_text(text)
    with pytest.raises(UnitFormatError, match=r"bad\.unit\.json"):
        UnitCodec(IrCodec()).read(bad)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linked_file_of_format_5_is_refused_naming_itself(tmp_path):
    path = tmp_path / "old.linked.json"
    LinkedCodec(IrCodec()).write(_linked(), path)
    path.write_text(
        json.dumps({**json.loads(path.read_text()), "format": 5}), encoding="utf-8"
    )
    with pytest.raises(UnitFormatError) as refused:
        LinkedCodec(IrCodec()).read(path)
    assert str(refused.value) == f"{path}: not a linked-program file of format 6"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_unit_file_of_format_5_is_refused_naming_itself(tmp_path):
    path = tmp_path / "old.unit.json"
    UnitCodec(IrCodec()).write(next(iter(_linked().modules.values())), path)
    path.write_text(
        json.dumps({**json.loads(path.read_text()), "format": 5}), encoding="utf-8"
    )
    with pytest.raises(UnitFormatError) as refused:
        UnitCodec(IrCodec()).read(path)
    assert str(refused.value) == f"{path}: not a unit file of format 6"
