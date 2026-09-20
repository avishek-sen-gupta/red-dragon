"""CALL identifier — the callee named by a data item's runtime contents.

Cobol.g4:1241 is ``callStatement : CALL (identifier | literal) ...``, so the
callee is either a literal program name or an *identifier* whose contents at
runtime name the program. The identifier arm covers a plain (optionally
qualified) data name, a subscripted table element, and a reference-modified
slice — ``CALL WS-PROG(1:8)`` is the common real idiom, because a program name
is 8 characters and the holding field is usually wider.

Every test here runs a two-module directory: MAIN calls HELPER, HELPER writes 77
into the LINKAGE item and GOBACKs so the BY REFERENCE copy-back runs. A callee
that never ran leaves WS-TICKET at its VALUE 0 — which is exactly how this bug
presented (red-dragon-jgra): a silent no-op, neither dispatching nor raising.
"""

import os

import pytest

from interpreter.address import Address
from interpreter.cobol.features import CobolFeature
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.handlers.calls import UnresolvedProgramError
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.run import initial_vm_state, run_linked
from interpreter.var_name import VarName
from interpreter.vm.vm_types import Pointer
from tests.covers import covers
from tests.integration.cobol_helpers import bridge_jar  # noqa: F401
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned as _decode_zoned_unsigned,
)

HELPER_SRC = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. HELPER.\n"
    "       DATA DIVISION.\n"
    "       LINKAGE SECTION.\n"
    "       01 LK-TICKET PIC 9(4).\n"
    "       PROCEDURE DIVISION USING LK-TICKET.\n"
    "           MOVE 77 TO LK-TICKET.\n"
    "           GOBACK.\n"
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Fails loudly when PROLEAP_BRIDGE_JAR is unset."""
    os.environ["PROLEAP_BRIDGE_JAR"] = str(bridge_jar)


def _main_src(working_storage: str, body: str) -> str:
    return (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. MAIN.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-TICKET PIC 9(4) VALUE 0.\n"
        f"{working_storage}"
        "       PROCEDURE DIVISION.\n"
        f"{body}"
        "           STOP RUN.\n"
    )


def _run(tmp_path, main_src: str):
    (tmp_path / "HELPER.cbl").write_text(HELPER_SRC)
    (tmp_path / "MAIN.cbl").write_text(main_src)
    linked = compile_directory(tmp_path, Language.COBOL)
    return run_linked(
        linked,
        entry_point=EntryPoint.function(
            lambda ref: str(ref.label).endswith("func_main_0")
            and "init_params" not in str(ref.label)
        ),
        max_steps=3000,
        initial_vm=initial_vm_state(),
    )


def _ticket(vm) -> int:
    """MAIN's WS-TICKET, located via MAIN's program singleton.

    Region ordering is unstable once CALL USING allocates a params region, so
    the WS region is reached through ``__prog_MAIN``'s ws_handle rather than by
    index.
    """
    main_ptr = None
    for frame in reversed(vm.call_stack):
        if VarName("__prog_MAIN") in frame.local_vars:
            main_ptr = frame.local_vars[VarName("__prog_MAIN")].value
            break
    assert main_ptr is not None, "__prog_MAIN singleton not found"
    assert isinstance(main_ptr, Pointer)
    ws = vm.region_get(
        Address(vm.heap_get(main_ptr.base).fields[FieldName("ws_handle")].value)
    )
    assert ws is not None
    return _decode_zoned_unsigned(ws, 0, 4)


@covers(CobolFeature.CALL, CobolFeature.CALL_USING)
def test_call_literal_dispatches(tmp_path):
    """The working baseline: CALL 'HELPER' runs HELPER and its write comes back."""
    vm = _run(
        tmp_path,
        _main_src("", "           CALL 'HELPER' USING BY REFERENCE WS-TICKET.\n"),
    )
    assert _ticket(vm) == 77


@covers(CobolFeature.CALL_BY_IDENTIFIER)
def test_call_qualified_data_name_dispatches(tmp_path):
    """CALL WS-PROG dispatches to whatever WS-PROG holds at runtime."""
    vm = _run(
        tmp_path,
        _main_src(
            "       01 WS-PROG PIC X(6) VALUE 'HELPER'.\n",
            "           CALL WS-PROG USING BY REFERENCE WS-TICKET.\n",
        ),
    )
    assert _ticket(vm) == 77


@covers(CobolFeature.CALL_BY_IDENTIFIER)
def test_call_data_name_trailing_spaces_are_trimmed(tmp_path):
    """A name held in a wider PIC X field is space-padded; padding is not part of it."""
    vm = _run(
        tmp_path,
        _main_src(
            "       01 WS-PROG PIC X(10) VALUE 'HELPER'.\n",
            "           CALL WS-PROG USING BY REFERENCE WS-TICKET.\n",
        ),
    )
    assert _ticket(vm) == 77


@covers(CobolFeature.CALL_BY_IDENTIFIER, CobolFeature.REFERENCE_MODIFICATION)
def test_call_reference_modified_slice_dispatches(tmp_path):
    """CALL WS-PROG(1:6) calls the slice, not the whole field.

    WS-PROG's tail holds a different name; a fix that ignored the ref-mod would
    resolve the whole field and call nothing (or the wrong thing).
    """
    vm = _run(
        tmp_path,
        _main_src(
            "       01 WS-PROG PIC X(12) VALUE 'HELPERNOSUCH'.\n",
            "           CALL WS-PROG(1:6) USING BY REFERENCE WS-TICKET.\n",
        ),
    )
    assert _ticket(vm) == 77


@covers(CobolFeature.CALL_BY_IDENTIFIER, CobolFeature.OCCURS_FIXED)
def test_call_subscripted_table_element_dispatches(tmp_path):
    """CALL WS-PE(I) calls the element the subscript names.

    Element 1 holds a name that does not exist, so dropping the subscript would
    not merely call the wrong program — it would fail to resolve at all.
    """
    vm = _run(
        tmp_path,
        _main_src(
            "       01 WS-PROGS.\n"
            "           05 WS-PE PIC X(6) OCCURS 2 TIMES.\n"
            "       01 I PIC 9(4) COMP VALUE 2.\n",
            "           MOVE 'NOSUCH' TO WS-PE(1)\n"
            "           MOVE 'HELPER' TO WS-PE(2)\n"
            "           CALL WS-PE(I) USING BY REFERENCE WS-TICKET.\n",
        ),
    )
    assert _ticket(vm) == 77


@covers(CobolFeature.CALL_BY_IDENTIFIER)
def test_call_unresolvable_runtime_name_raises(tmp_path):
    """A runtime-resolved name that names no linked program must be loud.

    This is the whole point of red-dragon-jgra: CardDemo's
    ``CALL LIT-DSNTIAC`` silently did nothing, so every Db2 error message came
    out as garbage. Failing to find DSNTIAC is a correct and diagnosable
    outcome; silence is not.
    """
    with pytest.raises(UnresolvedProgramError) as excinfo:
        _run(
            tmp_path,
            _main_src(
                "       01 LIT-DSNTIAC PIC X(8) VALUE 'DSNTIAC'.\n",
                "           CALL LIT-DSNTIAC USING BY REFERENCE WS-TICKET.\n",
            ),
        )
    assert "DSNTIAC" in str(excinfo.value)
