# pyright: standard
"""What raised a unit diagnostic: an assembler message code, an MNOTE with a severity or as a comment, or a constant."""

from interpreter.project.coded_diagnostic import CodedDiagnostic
from interpreter.project.comment_mnote import CommentMnote
from interpreter.project.constant_diagnostic import ConstantDiagnostic
from interpreter.project.severity_mnote import SeverityMnote

type DiagnosticKind = CodedDiagnostic | SeverityMnote | CommentMnote | ConstantDiagnostic
