"""A READ whose outcome the provider cannot compute leaves a symbolic I-O status,
in the IR and in the FILE STATUS field."""

from __future__ import annotations

import pytest

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.io_provider import NullIOProvider
from interpreter.run import run
from interpreter.var_name import VarName
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.integration.cobol_helpers import (  # noqa: F401
    bridge_jar,
    to_fixed,
    ws_address,
)

pytestmark = pytest.mark.usefixtures("bridge_jar")

_LINES = (
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. FSNULL.",
    "ENVIRONMENT DIVISION.",
    "INPUT-OUTPUT SECTION.",
    "FILE-CONTROL.",
    "    SELECT F ASSIGN TO FDD FILE STATUS IS FS-F.",
    "DATA DIVISION.",
    "FILE SECTION.",
    "FD  F.",
    "01  F-REC PIC X(4).",
    "WORKING-STORAGE SECTION.",
    "01  FS-F PIC XX.",
    "PROCEDURE DIVISION.",
    "MAIN-PARA.",
    "    OPEN INPUT F.",
    "    READ F.",
    "    STOP RUN.",
)

_LOOKUP = (
    "__list_get(['00', '02', '10', '23', '22', '35', '39', '44', '37', '47', '48'],"
    " __cobol_io_outcome(…))"
)
_FIELD_IMAGE = (
    f"__list_slice(__list_concat(__string_to_bytes(__cobol_to_text({_LOOKUP}),"
    " 'ebcdic'), [64, 64]), 0, 2)"
)


@covers(CobolFeature.READ)
def test_symbolic_read_leaves_a_symbolic_status() -> None:
    vm = run(
        to_fixed(list(_LINES)),
        language="cobol",
        io_provider=NullIOProvider(),
        max_steps=200_000,
    )
    statuses = vm.call_stack[0].local_vars
    assert (
        statuses[VarName("io_status_0")].value,
        statuses[VarName("io_status_11")].value,
        vm.load(ws_address(vm, "FSNULL"), 2),
    ) == (
        "00",
        SymbolicValue(name="sym_6", type_hint=_LOOKUP, constraints=[_LOOKUP]),
        SymbolicValue(
            name="sym_14", type_hint=_FIELD_IMAGE, constraints=[_FIELD_IMAGE]
        ),
    )
