"""Integration tests for the COBOL RETURN-CODE special register (red-dragon-o8uq).

RETURN-CODE is a compiler special register, not a DATA DIVISION field. It lives
in its own dedicated region (isolated from WORKING-STORAGE and the FD/file region)
so a ``MOVE n TO RETURN-CODE`` cannot disturb any other field's layout. After a run
its value is readable from the returned VMState via ``read_return_code``.
"""

from __future__ import annotations

from interpreter.cobol.return_code_readback import read_return_code
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import decode_zoned_unsigned, run_cobol


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_move_to_return_code_is_stored_and_readable():
    """MOVE 8 TO RETURN-CODE stores 8 and is read back from the VMState."""
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. RCTEST.",
            "PROCEDURE DIVISION.",
            "    MOVE 8 TO RETURN-CODE.",
            "    GOBACK.",
        ]
    )

    assert read_return_code(vm) == 8


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_return_code_does_not_corrupt_working_storage():
    """A WS field and RETURN-CODE coexist: WS uncorrupted AND RETURN-CODE correct."""
    vm = run_cobol(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. RCISO.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "01 WS-NUM PIC 9(4) VALUE 1234.",
            "PROCEDURE DIVISION.",
            "    MOVE 12 TO RETURN-CODE.",
            "    GOBACK.",
        ]
    )

    # WS region is the first region (allocated in the program init block).
    ws_region = vm.region_get(list(vm.region_keys())[0])
    assert decode_zoned_unsigned(ws_region, 0, 4) == 1234
    assert read_return_code(vm) == 12
