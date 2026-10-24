# pyright: standard
"""An assembly's diagnostics below error level: che4z's warnings and MNOTEs, and the warnings of every DC constant, DSECTs included; encoding each one also refuses its errors."""

from collections.abc import Mapping
from itertools import chain
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

from hlasm_asg.program.dc_item import DcItem
from hlasm_asg.program.dc_statement import DcStatement
from hlasm_asg.program.diagnostic import Diagnostic
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.macro_origin import MacroOrigin
from hlasm_asg.program.mnote_comment import MnoteComment
from hlasm_asg.program.mnote_level import MnoteLevel
from hlasm_asg.program.no_mnote import NoMnote
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.origin import Origin
from hlasm_asg.program.severity import Severity
from interpreter.hlasm.bit_length_image import BitLengthImage
from interpreter.hlasm.constant_image import ConstantImage
from interpreter.hlasm.dc_encoding import encode_dc
from interpreter.hlasm.dc_warning import DcWarning
from interpreter.project.coded_diagnostic import CodedDiagnostic
from interpreter.project.comment_mnote import CommentMnote
from interpreter.project.constant_diagnostic import ConstantDiagnostic
from interpreter.project.constant_source import ConstantSource
from interpreter.project.diagnostic_kind import DiagnosticKind
from interpreter.project.diagnostic_place import DiagnosticPlace
from interpreter.project.diagnostic_severity import DiagnosticSeverity
from interpreter.project.in_macro import InMacro
from interpreter.project.in_open_code import InOpenCode
from interpreter.project.severity_mnote import SeverityMnote
from interpreter.project.unit_diagnostic import UnitDiagnostic

_LIBRARY_SCHEME = "file"
_SEVERITIES: Mapping[Severity, DiagnosticSeverity] = {
    Severity.WARNING: DiagnosticSeverity.WARNING,
    Severity.INFO: DiagnosticSeverity.INFO,
    Severity.HINT: DiagnosticSeverity.INFO,
    Severity.UNSPECIFIED: DiagnosticSeverity.INFO,
}


def _named(file: str) -> str:
    uri = urlparse(file)
    if uri.scheme != _LIBRARY_SCHEME:
        return file
    return PurePosixPath(unquote(uri.path)).stem


def _place(file: str, line: int) -> DiagnosticPlace:
    return DiagnosticPlace(_named(file), line)


def _mnote_kind(mnote: MnoteLevel | MnoteComment, text: str) -> DiagnosticKind:
    match mnote:
        case MnoteLevel(level=level):
            return SeverityMnote(level, text)
        case MnoteComment():
            return CommentMnote(text)


def _kind(diagnostic: Diagnostic) -> DiagnosticKind:
    match diagnostic.mnote:
        case NoMnote():
            return CodedDiagnostic(diagnostic.code, diagnostic.message)
        case mnote:
            return _mnote_kind(mnote, diagnostic.message)


def _bridge(diagnostic: Diagnostic) -> UnitDiagnostic:
    return UnitDiagnostic(
        _SEVERITIES[diagnostic.severity],
        _kind(diagnostic),
        _place(diagnostic.file, diagnostic.line),
        tuple(_place(frame.file, frame.line) for frame in diagnostic.related),
    )


def _one_copy_warnings(item: DcItem, origin: Origin) -> tuple[DcWarning, ...]:
    match encode_dc(item.model_copy(update={"duplication": 1}), origin):
        case BitLengthImage(warnings=warnings):
            return warnings
        case pieces:
            return tuple(
                chain.from_iterable(
                    piece.warnings
                    for piece in pieces
                    if isinstance(piece, ConstantImage)
                )
            )


def _source(origin: Origin) -> ConstantSource:
    match origin:
        case MacroOrigin(macro=macro):
            return InMacro(macro)
        case OpenCodeOrigin():
            return InOpenCode()


def _constant(warning: DcWarning, origin: Origin) -> UnitDiagnostic:
    return UnitDiagnostic(
        DiagnosticSeverity.WARNING,
        ConstantDiagnostic(warning.constant, warning.kind, _source(origin)),
        _place(origin.file, origin.line),
    )


def _constants(program: HlasmProgram) -> tuple[tuple[DcItem, Origin], ...]:
    statements = (
        (item, s.origin)
        for s in program.statements
        if isinstance(s, DcStatement)
        for item in s.items
    )
    literals = ((literal.item, literal.origin) for literal in program.literals)
    return (*statements, *literals)


def assembly_diagnostics(program: HlasmProgram) -> tuple[UnitDiagnostic, ...]:
    constants = (
        _constant(warning, origin)
        for item, origin in _constants(program)
        for warning in _one_copy_warnings(item, origin)
    )
    return (*map(_bridge, program.diagnostics), *constants)
