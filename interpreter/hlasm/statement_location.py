# pyright: standard
"""A statement's line in the open-code source; macro-generated statements take the call's line."""

from hlasm_asg.program.origin import Origin
from interpreter.ir import SourceLocation


def statement_location(origin: Origin) -> SourceLocation:
    return SourceLocation(
        start_line=origin.line, start_col=0, end_line=origin.line, end_col=0
    )
