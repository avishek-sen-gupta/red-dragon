# pyright: standard
"""A program that calls the linked CEE3ABD stub ends with the user abend it recorded."""

from __future__ import annotations

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from infrastructure.zos.abend.user_abend import UserAbend
from interpreter.cobol.cee3abd_abend import LE_STUBS, user_abend
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.source_file import SourceFile
from interpreter.run import EntryPoint, initial_vm_state, run_linked
from interpreter.vm.builtins import core_builtins
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import to_fixed

_CALLER = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. CALLER.",
    "DATA DIVISION.",
    "WORKING-STORAGE SECTION.",
    "01 WS-CODE PIC S9(9) BINARY VALUE {code}.",
    "01 WS-CLEANUP PIC S9(9) BINARY VALUE 0.",
    "PROCEDURE DIVISION.",
    "    {call}",
    "    GOBACK.",
]
_CALL = "CALL 'CEE3ABD' USING WS-CODE WS-CLEANUP."
_NO_CALL = "CONTINUE."


def _abends(code: int, call: str) -> tuple[UserAbend, ...]:
    source = to_fixed([line.format(code=code, call=call) for line in _CALLER])
    linked = compile_cobol(
        source.encode(),
        parser=make_cobol_parser(),
        programs=(
            SourceFile(
                LE_STUBS / "CEE3ABD.cbl", (LE_STUBS / "CEE3ABD.cbl").read_bytes()
            ),
        ),
    )
    vm = run_linked(
        linked,
        entry_point=EntryPoint.function(lambda f: str(f.name) == "func_caller_0"),
        max_steps=500_000,
        initial_vm=initial_vm_state(),
        builtins=core_builtins(),
    )
    return user_abend(vm)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize(
    ("code", "call", "expected"),
    [
        (1234, _CALL, (UserAbend(1234),)),
        (0, _CALL, (UserAbend(0),)),
        (1234, _NO_CALL, ()),
    ],
)
def test_a_program_that_calls_cee3abd_ends_with_that_user_abend(
    code: int, call: str, expected: tuple[UserAbend, ...]
):
    assert _abends(code, call) == expected
