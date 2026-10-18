# pyright: standard
"""A COBOL source file's programs, as the bridge serialises them.

A source holds one or more programs: written one after another (batch
compilation), or contained one in another and ended by END PROGRAM (nested
programs; IBM Enterprise COBOL LR, "Nested programs"). The bridge emits
``{"programs": [...]}``, the top-level programs in source order, each carrying the
programs it directly contains under the same key.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from cobol_asg.addressing_mode import AddressingMode
from cobol_asg.asg_types import CobolASG
from cobol_asg.contained_programs import (
    CONTAINED_PROGRAMS,
    contained_programs,
    program_alone,
)
from cobol_asg.lp32 import LP32_MODE

_IDENTITY: Callable[[dict], dict] = lambda d: d  # noqa: E731


def programs_in_preorder(written: Mapping) -> tuple[dict, ...]:
    """Every program object of a bridge compilation unit, each without the
    programs it contains: source order, a program before those it contains."""
    return tuple(
        program for top in written[CONTAINED_PROGRAMS] for program in _preorder(top)
    )


def _preorder(written: Mapping) -> tuple[dict, ...]:
    return (
        program_alone(written),
        *(
            program
            for inner in contained_programs(written)
            for program in _preorder(inner)
        ),
    )


def _preprocessed(written: Mapping, preprocessor: Callable[[dict], dict]) -> dict:
    """The program object with ``preprocessor`` applied to it alone, then to each
    program it contains, in pre-order."""
    return preprocessor(program_alone(written)) | {
        CONTAINED_PROGRAMS: [
            _preprocessed(inner, preprocessor) for inner in contained_programs(written)
        ]
    }


@dataclass(frozen=True)
class CobolCompilationUnit:
    """The top-level programs of one source file, in source order."""

    programs: tuple[CobolASG, ...]

    @classmethod
    def from_dict(
        cls,
        written: Mapping,
        addressing_mode: AddressingMode = LP32_MODE,
        preprocessor: Callable[[dict], dict] = _IDENTITY,
    ) -> CobolCompilationUnit:
        return cls(
            tuple(
                CobolASG.from_dict(_preprocessed(top, preprocessor), addressing_mode)
                for top in written[CONTAINED_PROGRAMS]
            )
        )

    @property
    def first_program(self) -> CobolASG:
        """The first top-level program: the one a single-program consumer means."""
        return self.programs[0]
