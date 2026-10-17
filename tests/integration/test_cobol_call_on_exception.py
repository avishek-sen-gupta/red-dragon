"""End-to-end: CALL ... ON EXCEPTION runs when the called program is not in the
run unit; without the phrase the run's unresolved-call strategy decides."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.features import CobolFeature
from interpreter.handlers.calls import UnresolvedProgramError
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.source_file import SourceFile
from interpreter.run import EntryPoint, initial_vm_state, run_linked
from interpreter.vm.builtins import core_builtins
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    to_fixed,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")

_SUBPROGRAM = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. SUBP.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
    '    DISPLAY "IN SUBP".',
    "    GOBACK.",
]


def _main(calls: Sequence[str]) -> list[str]:
    return [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. MAINP.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-W PIC X(9) VALUE SPACES.",
        "PROCEDURE DIVISION.",
        "MAIN-PARA.",
        *calls,
        '    DISPLAY "END".',
        "    STOP RUN.",
    ]


def _run_strict(main: Sequence[str], subprograms: Mapping[str, Sequence[str]]) -> None:
    linked = compile_cobol(
        to_fixed(list(main)).encode(),
        parser=make_cobol_parser(),
        programs=tuple(
            SourceFile(Path(f"{name}.cbl"), to_fixed(list(lines)).encode())
            for name, lines in subprograms.items()
        ),
    )
    entry = linked.entry_func_label
    run_linked(
        linked,
        entry_point=EntryPoint.function(lambda ref: ref.label == entry),
        max_steps=50_000,
        builtins=core_builtins(),
        initial_vm=initial_vm_state(),
        permit_unresolved_call_targets=False,
    )


@covers(CobolFeature.CALL)
def test_on_exception_runs_only_when_the_program_cannot_be_made_available(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """IBM Enterprise COBOL LR, CALL, ON EXCEPTION and NOT ON EXCEPTION
    phrases; ON OVERFLOW has the same effect as ON EXCEPTION."""
    _run_strict(
        _main(
            [
                '    CALL "NOSUCHPG" ON EXCEPTION MOVE "EXCEPTION" TO WS-W',
                '        NOT ON EXCEPTION MOVE "CALLED" TO WS-W END-CALL.',
                "    DISPLAY WS-W.",
                '    CALL "NOSUCHPG" ON OVERFLOW MOVE "OVERFLOW" TO WS-W END-CALL.',
                "    DISPLAY WS-W.",
                '    CALL "SUBP" ON EXCEPTION MOVE "EXCEPTION" TO WS-W',
                '        NOT ON EXCEPTION MOVE "CALLED" TO WS-W END-CALL.',
                "    DISPLAY WS-W.",
                '    CALL "SUBP" NOT ON EXCEPTION MOVE "AGAIN" TO WS-W END-CALL.',
                "    DISPLAY WS-W.",
            ]
        ),
        {"SUBP": _SUBPROGRAM},
    )
    assert capsys.readouterr().out == (
        "EXCEPTION\nOVERFLOW \nIN SUBP\nCALLED   \nIN SUBP\nAGAIN    \nEND\n"
    )


@covers(CobolFeature.CALL)
def test_without_on_exception_the_strict_strategy_raises() -> None:
    with pytest.raises(UnresolvedProgramError):
        _run_strict(_main(['    CALL "NOSUCHPG".']), {})
