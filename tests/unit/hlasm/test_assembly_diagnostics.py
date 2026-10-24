# pyright: standard
"""An assembly's warnings and MNOTEs, and its DC constants' warnings, become unit diagnostics."""

from pathlib import Path

from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.dc_statement import DcStatement
from hlasm_asg.program.diagnostic import Diagnostic
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.length_unit import LengthUnit
from hlasm_asg.program.literal_pool import LiteralPool
from hlasm_asg.program.macro_origin import MacroOrigin
from hlasm_asg.program.mnote_comment import MnoteComment
from hlasm_asg.program.mnote_level import MnoteLevel
from hlasm_asg.program.no_mnote import NoMnote
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.related_location import RelatedLocation
from hlasm_asg.program.section import Section
from hlasm_asg.program.section_kind import SectionKind
from hlasm_asg.program.severity import Severity
from hlasm_asg.program.string_nominal import StringNominal
from interpreter.hlasm.assembly_diagnostics import assembly_diagnostics
from interpreter.project.coded_diagnostic import CodedDiagnostic
from interpreter.project.comment_mnote import CommentMnote
from interpreter.project.constant_diagnostic import ConstantDiagnostic
from interpreter.project.diagnostic_place import DiagnosticPlace
from interpreter.project.diagnostic_severity import DiagnosticSeverity
from interpreter.project.severity_mnote import SeverityMnote
from interpreter.project.unit_diagnostic import UnitDiagnostic
from tests.covers import NotLanguageFeature, covers

FIXTURES = Path(__file__).parent / "fixtures"
MEMBER = "file:///lib/GREET.mac"
SOURCE = "__main__.asm"
OPEN_CODE = OpenCodeOrigin(kind="OPEN_CODE", file=SOURCE, line=9)
GENERATED = MacroOrigin(kind="MACRO", file=SOURCE, line=12, macro="GEN", depth=1)


HELLO_SECTIONS = (Section(name="HELLO", kind=SectionKind.CSECT, length=64),)


def _program(
    *,
    diagnostics: tuple[Diagnostic, ...] = (),
    sections: tuple[Section, ...] = HELLO_SECTIONS,
    statements: tuple[DcStatement, ...] = (),
    literals: tuple[LiteralPool, ...] = (),
) -> HlasmProgram:
    hello = HlasmProgram.model_validate_json(
        (FIXTURES / "hello_program.json").read_text()
    )
    return hello.model_copy(
        update={
            "diagnostics": diagnostics,
            "sections": sections,
            "statements": statements,
            "literals": literals,
        }
    )


def _item(type_: str, extension: str, value: str, duplication: int = 1) -> DcItem:
    return DcItem(
        type=type_,
        extension=extension,
        duplication=duplication,
        length=4,
        length_unit=LengthUnit.BYTE,
        explicit_length=False,
        scale=0,
        exponent=0,
        offset=0,
        bit_offset=0,
        nominal=StringNominal(kind="STRING", value=value),
    )


def _bit_item(value: str) -> DcItem:
    return _item("E", "B", value).model_copy(
        update={"length": 32, "length_unit": LengthUnit.BIT}
    )


def _dc(
    section: str, origin: OpenCodeOrigin | MacroOrigin, *items: DcItem
) -> DcStatement:
    return DcStatement(
        kind="DC",
        section=section,
        offset=0,
        label="",
        mnemonic="DC",
        items=items,
        origin=origin,
    )


def _warning(line: int, message: str) -> UnitDiagnostic:
    return UnitDiagnostic(
        DiagnosticSeverity.WARNING,
        ConstantDiagnostic(),
        message,
        DiagnosticPlace(SOURCE, line),
    )


def _diagnostic(
    code: str,
    severity: Severity,
    message: str,
    file: str,
    line: int,
    mnote: MnoteLevel | MnoteComment | NoMnote,
    related: tuple[RelatedLocation, ...] = (),
) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity=severity,
        message=message,
        file=file,
        line=line,
        related=related,
        mnote=mnote,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bridge_diagnostics_keep_kind_text_and_call_stack_with_members_named():
    program = _program(
        diagnostics=(
            _diagnostic(
                "MNOTE",
                Severity.WARNING,
                "CAREFUL",
                MEMBER,
                3,
                MnoteLevel(kind="LEVEL", level=4),
                (
                    RelatedLocation(file="file:///lib/OUTER", line=2),
                    RelatedLocation(file=SOURCE, line=9),
                ),
            ),
            _diagnostic(
                "MNOTE",
                Severity.HINT,
                "NOTED",
                SOURCE,
                4,
                MnoteLevel(kind="LEVEL", level=0),
            ),
            _diagnostic(
                "MNOTE", Severity.HINT, "ASIDE", SOURCE, 5, MnoteComment(kind="COMMENT")
            ),
            _diagnostic(
                "A300",
                Severity.WARNING,
                "Apostrophes missing",
                "hlasm://0/AINSERT_1.hlasm",
                1,
                NoMnote(kind="NONE"),
            ),
        )
    )

    assert assembly_diagnostics(program) == (
        UnitDiagnostic(
            DiagnosticSeverity.WARNING,
            SeverityMnote(4),
            "CAREFUL",
            DiagnosticPlace("GREET", 3),
            (DiagnosticPlace("OUTER", 2), DiagnosticPlace(SOURCE, 9)),
        ),
        UnitDiagnostic(
            DiagnosticSeverity.INFO,
            SeverityMnote(0),
            "NOTED",
            DiagnosticPlace(SOURCE, 4),
        ),
        UnitDiagnostic(
            DiagnosticSeverity.INFO, CommentMnote(), "ASIDE", DiagnosticPlace(SOURCE, 5)
        ),
        UnitDiagnostic(
            DiagnosticSeverity.WARNING,
            CodedDiagnostic("A300"),
            "Apostrophes missing",
            DiagnosticPlace("hlasm://0/AINSERT_1.hlasm", 1),
        ),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dc_warnings_come_once_per_value_from_every_section_with_line_and_macro():
    program = _program(
        sections=(
            *HELLO_SECTIONS,
            Section(name="MAP", kind=SectionKind.DSECT, length=4),
        ),
        statements=(
            _dc("HELLO", OPEN_CODE, _item("E", "B", "1E39", duplication=3)),
            _dc(
                "HELLO",
                GENERATED,
                _item("E", "B", "1E39,1E39"),
                _item("E", "", "1"),
                _bit_item("1E-50"),
            ),
            _dc(
                "MAP",
                OpenCodeOrigin(kind="OPEN_CODE", file=SOURCE, line=20),
                _item("E", "B", "1E39"),
                _item("D", "B", "1E400", duplication=0),
            ),
        ),
        literals=(
            LiteralPool(
                section="HELLO",
                offset=48,
                item=_item("E", "D", "1.2345678"),
                origin=OpenCodeOrigin(kind="OPEN_CODE", file=SOURCE, line=14),
            ),
        ),
    )

    assert assembly_diagnostics(program) == (
        _warning(9, "EB'1E39' overflow"),
        _warning(12, "EB'1E39' overflow in macro GEN"),
        _warning(12, "EB'1E39' overflow in macro GEN"),
        _warning(12, "EB'1E-50' underflow in macro GEN"),
        _warning(20, "EB'1E39' overflow"),
        _warning(20, "DB'1E400' overflow"),
        _warning(14, "ED'1.2345678' inexact"),
    )
