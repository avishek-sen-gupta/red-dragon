"""Integration: COBOL COPY copybook inlining end-to-end via the ProLeap bridge."""

from __future__ import annotations

import pytest

from interpreter.address import Address
from interpreter.cobol.features import CobolFeature
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run_linked
from interpreter.var_name import VarName
from interpreter.vm.vm_types import Pointer
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,
    decode_zoned_unsigned as _decode_zoned_unsigned,
    to_fixed as _to_fixed,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR for run()/compile_directory-based
    tests (fails loudly via bridge_jar if it's unset)."""


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_copy_inlined_field_executes(tmp_path):
    """A field declared in a copybook is inlined and usable in PROCEDURE DIVISION."""
    (tmp_path / "VALBOOK.cpy").write_text(
        _to_fixed(["01 WS-FROM-COPY PIC 9(4) VALUE 0."])
    )
    (tmp_path / "MAIN.cbl").write_text(
        _to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "COPY VALBOOK.",
                "PROCEDURE DIVISION.",
                "    MOVE 4242 TO WS-FROM-COPY.",
                "    STOP RUN.",
            ]
        )
    )

    linked = compile_directory(tmp_path, Language.COBOL)
    vm = run_linked(
        linked,
        entry_point=EntryPoint.function(
            lambda ref: str(ref.label).endswith("func_main_0")
            and "init_params" not in str(ref.label)
        ),
        max_steps=500,
    )

    ptr = None
    for frame in reversed(vm.call_stack):
        if VarName("__prog_MAIN") in frame.local_vars:
            ptr = frame.local_vars[VarName("__prog_MAIN")].value
            break
    assert ptr is not None and isinstance(ptr, Pointer)
    region = vm.region_get(
        Address(vm.heap_get(ptr.base).fields[FieldName("ws_handle")].value)
    )
    assert region is not None
    assert _decode_zoned_unsigned(region, 0, 4) == 4242


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_copy_of_library_inlined(tmp_path):
    """The `COPY name OF library` form is inlined and usable in PROCEDURE DIVISION."""
    (tmp_path / "LIBBOOK.cpy").write_text(_to_fixed(["01 WS-L PIC 9(4) VALUE 0."]))
    (tmp_path / "MAIN.cbl").write_text(
        _to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "COPY LIBBOOK OF MYLIB.",
                "PROCEDURE DIVISION.",
                "    MOVE 7777 TO WS-L.",
                "    STOP RUN.",
            ]
        )
    )

    linked = compile_directory(tmp_path, Language.COBOL)
    vm = run_linked(
        linked,
        entry_point=EntryPoint.function(
            lambda ref: str(ref.label).endswith("func_main_0")
            and "init_params" not in str(ref.label)
        ),
        max_steps=500,
    )

    ptr = None
    for frame in reversed(vm.call_stack):
        if VarName("__prog_MAIN") in frame.local_vars:
            ptr = frame.local_vars[VarName("__prog_MAIN")].value
            break
    assert ptr is not None and isinstance(ptr, Pointer)
    region = vm.region_get(
        Address(vm.heap_get(ptr.base).fields[FieldName("ws_handle")].value)
    )
    assert region is not None
    assert _decode_zoned_unsigned(region, 0, 4) == 7777


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_missing_copybook_raises_clean_error(tmp_path):
    """An unresolvable COPY surfaces a clean error naming the copybook."""
    from interpreter.cobol.subprocess_runner import CobolParseError

    (tmp_path / "MAIN.cbl").write_text(
        _to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "COPY NOSUCHBOOK.",
                "PROCEDURE DIVISION.",
                "    STOP RUN.",
            ]
        )
    )

    with pytest.raises(CobolParseError) as excinfo:
        compile_directory(tmp_path, Language.COBOL)
    assert "NOSUCHBOOK" in str(excinfo.value)


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_multiple_copybooks_inlined(tmp_path):
    """Two separate copybooks both inline; fields from each are usable."""
    (tmp_path / "BOOKA.cpy").write_text(_to_fixed(["01 WS-A PIC 9(4) VALUE 0."]))
    (tmp_path / "BOOKB.cpy").write_text(_to_fixed(["01 WS-B PIC 9(4) VALUE 0."]))
    (tmp_path / "MAIN.cbl").write_text(
        _to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "COPY BOOKA.",
                "COPY BOOKB.",
                "PROCEDURE DIVISION.",
                "    MOVE 11 TO WS-A.",
                "    MOVE 22 TO WS-B.",
                "    STOP RUN.",
            ]
        )
    )

    linked = compile_directory(tmp_path, Language.COBOL)
    vm = run_linked(
        linked,
        entry_point=EntryPoint.function(
            lambda ref: str(ref.label).endswith("func_main_0")
            and "init_params" not in str(ref.label)
        ),
        max_steps=500,
    )
    ptr = None
    for frame in reversed(vm.call_stack):
        if VarName("__prog_MAIN") in frame.local_vars:
            ptr = frame.local_vars[VarName("__prog_MAIN")].value
            break
    assert ptr is not None and isinstance(ptr, Pointer)
    region = vm.region_get(
        Address(vm.heap_get(ptr.base).fields[FieldName("ws_handle")].value)
    )
    assert region is not None
    assert _decode_zoned_unsigned(region, 0, 4) == 11
    assert _decode_zoned_unsigned(region, 4, 4) == 22


@covers(
    CobolFeature.MULTI_FILE_IMPORTS,
    CobolFeature.CALL_USING,
    CobolFeature.SECTION_LINKAGE,
)
def test_copy_shared_record_across_call(tmp_path):
    """Most-general case: a shared copybook record is COPYed into the caller's
    WORKING-STORAGE and the callee's LINKAGE SECTION, passed BY REFERENCE,
    mutated by the callee, and returned via GOBACK.

    Mirrors the real CardDemo pattern where one copybook defines the interface
    record shared between a calling program and its subprogram. Exercises COPY
    inlining (in both WS and LINKAGE), CALL USING BY REFERENCE copy-in/copy-back,
    and GOBACK return — all in one program.

    SHARED-REC.SR-VALUE starts at 7 in MAINPROG; CALLEE adds 10 via its LINKAGE
    view and GOBACKs; copy-back propagates 17 back to MAINPROG's WS.
    """
    (tmp_path / "SHARED.cpy").write_text(
        _to_fixed(
            [
                "01 SHARED-REC.",
                "   05 SR-VALUE PIC 9(4).",
            ]
        )
    )
    (tmp_path / "MAINPROG.cbl").write_text(
        _to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MAINPROG.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "COPY SHARED.",
                "PROCEDURE DIVISION.",
                "    MOVE 7 TO SR-VALUE.",
                "    CALL 'CALLEE' USING BY REFERENCE SR-VALUE.",
                "    STOP RUN.",
            ]
        )
    )
    (tmp_path / "CALLEE.cbl").write_text(
        _to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. CALLEE.",
                "DATA DIVISION.",
                "LINKAGE SECTION.",
                "COPY SHARED.",
                "PROCEDURE DIVISION.",
                "    ADD 10 TO SR-VALUE.",
                "    GOBACK.",
            ]
        )
    )

    linked = compile_directory(tmp_path, Language.COBOL)
    vm = run_linked(
        linked,
        entry_point=EntryPoint.function(
            lambda ref: str(ref.label).endswith("func_mainprog_0")
            and "init_params" not in str(ref.label)
        ),
        max_steps=500,
    )

    ptr = None
    for frame in reversed(vm.call_stack):
        if VarName("__prog_MAINPROG") in frame.local_vars:
            ptr = frame.local_vars[VarName("__prog_MAINPROG")].value
            break
    assert ptr is not None and isinstance(ptr, Pointer)
    region = vm.region_get(
        Address(vm.heap_get(ptr.base).fields[FieldName("ws_handle")].value)
    )
    assert region is not None
    # SR-VALUE at offset 0: 7 (set by MAINPROG) + 10 (added by CALLEE via LINKAGE)
    # propagated back through the BY REFERENCE params region.
    sr_value = _decode_zoned_unsigned(region, 0, 4)
    assert (
        sr_value == 17
    ), f"SR-VALUE: expected 17 (7 + 10 via shared copybook), got {sr_value}"
