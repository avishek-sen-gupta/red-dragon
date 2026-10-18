# pyright: standard
"""A bridge program object's own entries apart from the programs it contains."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

CONTAINED_PROGRAMS = "programs"
UNNAMED_PROGRAM = "MAIN"


def program_alone(written: Mapping) -> dict:
    """The program object without its contained programs."""
    return {key: value for key, value in written.items() if key != CONTAINED_PROGRAMS}


def contained_programs(written: Mapping) -> Sequence[dict]:
    """The program objects directly contained in this one, in source order."""
    return written.get(CONTAINED_PROGRAMS, [])


def written_program_id(written: Mapping) -> str:
    """The PROGRAM-ID the bridge wrote for this program object, "" when none."""
    return written.get("program_id", "")


def written_program_name(written: Mapping) -> str:
    """The name a bridge program object's program goes by in the run unit."""
    return (written_program_id(written) or UNNAMED_PROGRAM).upper()
