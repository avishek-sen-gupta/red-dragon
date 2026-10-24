# pyright: standard
"""What raised a unit diagnostic: an assembler message code, an MNOTE with a severity or as a comment, a constant, or an EXTRN the binder could not resolve."""

from interpreter.project.coded_diagnostic import CodedDiagnostic
from interpreter.project.comment_mnote import CommentMnote
from interpreter.project.constant_diagnostic import ConstantDiagnostic
from interpreter.project.severity_mnote import SeverityMnote
from interpreter.project.unresolved_external import UnresolvedExternal

type DiagnosticKind = (
    CodedDiagnostic
    | SeverityMnote
    | CommentMnote
    | ConstantDiagnostic
    | UnresolvedExternal
)
