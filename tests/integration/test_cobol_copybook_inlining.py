"""Integration: COBOL COPY copybook inlining end-to-end via the ProLeap bridge."""

from __future__ import annotations

import pytest

from interpreter.address import Address
from interpreter.cobol.features import CobolFeature
from interpreter.field_name import FieldName
from interpreter.project.entry_point import EntryPoint
from interpreter.project.types import LinkedProgram
from interpreter.run import initial_vm_state, run_linked
from interpreter.var_name import VarName
from interpreter.vm.builtins import core_builtins
from interpreter.vm.vm_types import Pointer
from tests.covers import covers
from tests.integration.cobol_helpers import (
    bridge_jar,  # noqa: F401
    compile_programs_in,
)
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned as _decode_zoned_unsigned,
)
from tests.integration.cobol_helpers import (
    to_fixed as _to_fixed,
)


@pytest.fixture(autouse=True)
def _require_bridge_jar(bridge_jar):
    """Enforce the required PROLEAP_BRIDGE_JAR for run()/compile_cobol-based
    tests (fails loudly via bridge_jar if it's unset)."""


def _working_storage(linked: LinkedProgram, program: str) -> bytearray:
    """Run ``program`` to its end and return its WORKING-STORAGE region."""
    vm = run_linked(
        linked,
        entry_point=EntryPoint.function(
            lambda ref: str(ref.label).endswith(f"func_{program.lower()}_0")
            and "init_params" not in str(ref.label)
        ),
        max_steps=500,
        initial_vm=initial_vm_state(),
        builtins=core_builtins(),
    )
    program_var = VarName(f"__prog_{program}")
    pointer = next(
        frame.local_vars[program_var].value
        for frame in reversed(vm.call_stack)
        if program_var in frame.local_vars
    )
    assert isinstance(pointer, Pointer)
    handle = vm.heap_get(pointer.base).fields[FieldName("ws_handle")].value
    match vm.region_get(Address(str(handle))):
        case bytearray() as region:
            return region
        case _:
            raise AssertionError(f"{program} has no WORKING-STORAGE region")


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

    linked = compile_programs_in(tmp_path, "MAIN")
    region = _working_storage(linked, "MAIN")
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

    linked = compile_programs_in(tmp_path, "MAIN")
    region = _working_storage(linked, "MAIN")
    assert _decode_zoned_unsigned(region, 0, 4) == 7777


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_missing_copybook_raises_clean_error(tmp_path):
    """An unresolvable COPY surfaces a clean error naming the copybook. The AST
    cache parses every program before lowering and reports a failure as
    AstParseError, naming the program and the underlying parser error."""
    from cobol_asg.ast_store import AstParseError

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

    with pytest.raises(AstParseError) as excinfo:
        compile_programs_in(tmp_path, "MAIN")
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

    linked = compile_programs_in(tmp_path, "MAIN")
    region = _working_storage(linked, "MAIN")
    assert _decode_zoned_unsigned(region, 0, 4) == 11
    assert _decode_zoned_unsigned(region, 4, 4) == 22


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_copybook_with_a_high_byte_in_a_comment_is_inlined(tmp_path):
    """A copybook is 8-bit text, not UTF-8, and its comments do not have to decode.

    Real layout members carry box-drawing and currency bytes in their comment
    banners -- one production corpus has 110 members with bytes >= 0x80, none of
    which is valid UTF-8. ``decode_source`` already settles the policy for a
    program's own source (latin-1, byte-identity), but a copybook is read on the
    Java side by ProLeap, and ProLeap read it as strict UTF-8. The high byte
    raised ``MalformedInputException``, ProLeap caught the ``IOException`` and
    logged it through a logger with no provider bound, and the COPY expanded to
    nothing. The parse then succeeded with the whole record silently absent, and
    the first symptom was ``Field 'X' not found in any DATA DIVISION section``
    pointing at a copybook that is on the search path and complete -- a wrong
    error naming the wrong culprit.
    """
    copybook = _to_fixed(
        [
            "* BANNER \xa6 WITH A HIGH BYTE",
            "01 WS-HIGH PIC 9(4) VALUE 0.",
        ]
    )
    (tmp_path / "HIBOOK.cpy").write_bytes(copybook.encode("latin-1"))
    (tmp_path / "MAIN.cbl").write_text(
        _to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. MAIN.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "COPY HIBOOK.",
                "PROCEDURE DIVISION.",
                "    MOVE 1234 TO WS-HIGH.",
                "    STOP RUN.",
            ]
        )
    )

    linked = compile_programs_in(tmp_path, "MAIN")
    region = _working_storage(linked, "MAIN")
    assert _decode_zoned_unsigned(region, 0, 4) == 1234


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

    linked = compile_programs_in(tmp_path, "MAINPROG")
    region = _working_storage(linked, "MAINPROG")
    # SR-VALUE at offset 0: 7 (set by MAINPROG) + 10 (added by CALLEE via LINKAGE)
    # propagated back through the BY REFERENCE params region.
    sr_value = _decode_zoned_unsigned(region, 0, 4)
    assert (
        sr_value == 17
    ), f"SR-VALUE: expected 17 (7 + 10 via shared copybook), got {sr_value}"


@covers(CobolFeature.MULTI_FILE_IMPORTS)
def test_copy_of_a_mapped_library_copies_that_librarys_text(tmp_path):
    """COPY BOOK OF LIBA and COPY BOOK IN LIBB copy the BOOK of each library; an
    unqualified COPY BOOK copies the one in the copybook directories."""
    from cobol_asg.cobol_parser import make_cobol_parser
    from cobol_asg.copybook_library import CopybookLibrary
    from interpreter.project.cobol_compile import compile_cobol

    books = {"liba": "WS-A PIC 9(4) VALUE 1111", "libb": "WS-B PIC 9(4) VALUE 2222"}
    for directory, field in {**books, "syslib": "WS-S PIC 9(4) VALUE 3333"}.items():
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "BOOK.cpy").write_text(_to_fixed([f"01 {field}."]))
    main = _to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. MAIN.",
            "DATA DIVISION.",
            "WORKING-STORAGE SECTION.",
            "COPY BOOK OF LIBA.",
            "COPY BOOK IN",
            "    LIBB.",
            "COPY BOOK.",
            "PROCEDURE DIVISION.",
            "    STOP RUN.",
        ]
    )
    syslib = [tmp_path / "syslib"]
    linked = compile_cobol(
        main.encode(),
        parser=make_cobol_parser(
            copybook_dirs=syslib,
            copybook_libraries=(
                CopybookLibrary("LIBA", tmp_path / "liba"),
                CopybookLibrary("LIBB", tmp_path / "libb"),
            ),
        ),
        copybook_dirs=syslib,
    )
    region = _working_storage(linked, "MAIN")
    assert [_decode_zoned_unsigned(region, offset, 4) for offset in (0, 4, 8)] == [
        1111,
        2222,
        3333,
    ]
