"""Which USE declarative an I-O condition on a file selects.

Within a program, "a USE statement specifying File-1 takes precedence over any USE
statements specifying an INPUT, OUTPUT, I-O, or EXTEND phrase". When the program that
holds the statement has none that qualifies, the next is "a qualifying declarative
with the GLOBAL attribute in the next inclusive directly containing source element.
This step is repeated with the next higher directly containing source element until
a declarative is selected or the outermost source element is reached." A file-named
USE GLOBAL of a containing program qualifies when it names the same file connector.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cobol_asg.asg_types import CobolASG, CobolSection
from interpreter.cobol.global_names import file_owner
from interpreter.cobol.program_object import program_name

_NAMED_FILE = "FILE"


@dataclass(frozen=True)
class UseProcedure:
    """A declarative section of ``program``, limited to files open in ``mode``, or,
    when ``mode`` is empty, selected for the file it names whatever its mode."""

    program: str
    section: str
    mode: str


NO_USE = UseProcedure("", "", "")


def use_procedures(asg: CobolASG, file_name: str) -> tuple[UseProcedure, ...]:
    """The declaratives an I-O condition on ``file_name`` in ``asg`` can select, in
    order of precedence, up to and including the first one selected whatever the
    file's mode."""
    connector = program_name(file_owner(asg, file_name))
    ranked = (
        *_qualifying(asg, asg.declaratives, file_name, True),
        *(
            use
            for outer in asg.enclosing
            for use in _qualifying(
                outer,
                [s for s in outer.declaratives if s.use and s.use.is_global],
                file_name,
                program_name(file_owner(outer, file_name)) == connector,
            )
        ),
    )
    unconditional = next(
        (n for n, use in enumerate(ranked) if not use.mode), len(ranked) - 1
    )
    return ranked[: unconditional + 1]


def _qualifying(
    asg: CobolASG,
    sections: Sequence[CobolSection],
    file_name: str,
    same_connector: bool,
) -> tuple[UseProcedure, ...]:
    """The file-named declaratives first, then those for an open mode."""
    program = program_name(asg)
    return (
        *(
            UseProcedure(program, s.name, "")
            for s in sections
            if same_connector
            and s.use
            and s.use.target == _NAMED_FILE
            and file_name.upper() in s.use.files
        ),
        *(
            UseProcedure(program, s.name, s.use.target)
            for s in sections
            if s.use and s.use.target != _NAMED_FILE
        ),
    )
