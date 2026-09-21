"""Integration tests for the COBOL RETURN-CODE special register (red-dragon-o8uq).

RETURN-CODE is a compiler special register, not a DATA DIVISION field. It lives
in its own dedicated region (isolated from WORKING-STORAGE and the FD/file region)
so a ``MOVE n TO RETURN-CODE`` cannot disturb any other field's layout. After a run
its value is readable from the returned VMState via ``read_return_code``.
"""

from __future__ import annotations

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.return_code_readback import read_return_code
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import (
    decode_zoned_unsigned,
    return_code_of,
    run_cobol,
    run_cobol_programs,
    ws_region,
)


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


# ── Copy-on-return across a CALL (red-dragon-ltq6) ────────────────
#
# RETURN-CODE is not one shared cell: each program has its own, and on return the
# callee's value is copied into the caller's, exactly as z/OS does it through
# register 15. The tests below pin that, in both the directions it constrains --
# a value must travel UP out of a callee, and must NOT travel DOWN into one.

_SETS_TWELVE = [
    "IDENTIFICATION DIVISION.",
    "PROGRAM-ID. RCCALLEE.",
    "PROCEDURE DIVISION.",
    "    MOVE 12 TO RETURN-CODE.",
    "    GOBACK.",
]


@covers(CobolFeature.CALL)
def test_callee_return_code_reaches_its_caller():
    """The idiom this exists for: CALL, then read RETURN-CODE to see how it went."""
    caller = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RCCALLER.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-RC PIC S9(4) VALUE 0.",
        "PROCEDURE DIVISION.",
        "    CALL 'RCCALLEE'.",
        "    MOVE RETURN-CODE TO WS-RC.",
        "    GOBACK.",
    ]

    vm = run_cobol_programs(caller, {"RCCALLEE": _SETS_TWELVE})

    assert return_code_of(vm, "RCCALLER") == 12
    assert decode_zoned_unsigned(ws_region(vm, "RCCALLER"), 0, 4) == 12


@covers(CobolFeature.CALL)
def test_return_code_propagates_through_a_nested_call_chain():
    """A -> B -> C: C's code reaches A, carried up one CALL at a time."""
    prog_c = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RCDEEP.",
        "PROCEDURE DIVISION.",
        "    MOVE 7 TO RETURN-CODE.",
        "    GOBACK.",
    ]
    prog_b = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RCMID.",
        "PROCEDURE DIVISION.",
        "    CALL 'RCDEEP'.",
        "    GOBACK.",
    ]
    prog_a = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RCTOP.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-RC PIC S9(4) VALUE 0.",
        "PROCEDURE DIVISION.",
        "    CALL 'RCMID'.",
        "    MOVE RETURN-CODE TO WS-RC.",
        "    GOBACK.",
    ]

    vm = run_cobol_programs(prog_a, {"RCMID": prog_b, "RCDEEP": prog_c})

    # RCMID never mentions RETURN-CODE; it carries RCDEEP's value purely by
    # returning, which is what makes the propagation transitive.
    assert return_code_of(vm, "RCTOP") == 7
    assert decode_zoned_unsigned(ws_region(vm, "RCTOP"), 0, 4) == 7


@covers(CobolFeature.CALL)
def test_callee_that_never_sets_return_code_overwrites_the_caller_value():
    """A no-op callee copies up its OWN register -- zero -- over the caller's.

    This is the case IBM warns about ("do not inadvertently reset RETURN-CODE in
    a called subprogram"), and it is what separates copy-on-return from a single
    shared cell: under a shared cell the caller's 5 would survive.
    """
    quiet_callee = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RCQUIET.",
        "PROCEDURE DIVISION.",
        "    GOBACK.",
    ]
    caller = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RCSETTER.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-RC PIC S9(4) VALUE 9.",
        "PROCEDURE DIVISION.",
        "    MOVE 5 TO RETURN-CODE.",
        "    CALL 'RCQUIET'.",
        "    MOVE RETURN-CODE TO WS-RC.",
        "    GOBACK.",
    ]

    vm = run_cobol_programs(caller, {"RCQUIET": quiet_callee})

    assert return_code_of(vm, "RCSETTER") == 0
    assert decode_zoned_unsigned(ws_region(vm, "RCSETTER"), 0, 4) == 0


@covers(CobolFeature.CALL)
def test_caller_sees_the_callee_last_write_not_its_first():
    """The value is read at the callee's exit, not latched at its first write."""
    twice_setting_callee = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RCTWICE.",
        "PROCEDURE DIVISION.",
        "    MOVE 4 TO RETURN-CODE.",
        "    MOVE 9 TO RETURN-CODE.",
        "    GOBACK.",
    ]
    caller = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RCLAST.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-RC PIC S9(4) VALUE 0.",
        "PROCEDURE DIVISION.",
        "    CALL 'RCTWICE'.",
        "    MOVE RETURN-CODE TO WS-RC.",
        "    GOBACK.",
    ]

    vm = run_cobol_programs(caller, {"RCTWICE": twice_setting_callee})

    assert decode_zoned_unsigned(ws_region(vm, "RCLAST"), 0, 4) == 9


@covers(CobolFeature.CALL)
def test_a_program_keeps_its_own_return_code_between_invocations():
    """A subprogram is left in its last-used state, RETURN-CODE included.

    Its register is allocated once, with WORKING-STORAGE, rather than freshly on
    every entry -- so the second call sees the 4 the first call left.
    """
    remembering_callee = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RCMEMO.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "01 WS-CALLS PIC 9 VALUE 0.",
        "01 WS-SEEN  PIC S9(4) VALUE 9.",
        "PROCEDURE DIVISION.",
        "    ADD 1 TO WS-CALLS.",
        "    IF WS-CALLS = 1",
        "        PERFORM 100-SET",
        "    ELSE",
        "        PERFORM 200-PEEK",
        "    END-IF.",
        "    GOBACK.",
        "100-SET.",
        "    MOVE 4 TO RETURN-CODE.",
        "200-PEEK.",
        "    MOVE RETURN-CODE TO WS-SEEN.",
    ]
    driver = [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. RCDRIVER.",
        "PROCEDURE DIVISION.",
        "    CALL 'RCMEMO'.",
        "    CALL 'RCMEMO'.",
        "    GOBACK.",
    ]

    vm = run_cobol_programs(driver, {"RCMEMO": remembering_callee})

    memo_ws = ws_region(vm, "RCMEMO")
    assert decode_zoned_unsigned(memo_ws, 0, 1) == 2, "WORKING-STORAGE must persist too"
    assert decode_zoned_unsigned(memo_ws, 1, 4) == 4


@covers(CobolFeature.CALL)
def test_call_seeds_its_result_register_from_the_caller_return_code():
    """A callee that returns nothing must leave the caller's RETURN-CODE alone.

    A VOID return is deliberately not written into the caller's result register
    (run.py skips it), which is how a CICS task-ending RETURN avoids propagating
    a code. But an unwritten register resolves to the literal string "%n", and the
    copy-up would store that into RETURN-CODE as garbage. The lowering therefore
    seeds the call's result register with the caller's own RETURN-CODE first, so
    "nothing came back" and "my own value" are the same bytes.
    """
    from cobol_asg.cobol_parser import make_cobol_parser
    from interpreter.cobol.cobol_frontend import CobolFrontend
    from tests.integration.cobol_helpers import to_fixed

    ir = CobolFrontend(make_cobol_parser()).lower(
        to_fixed(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. RCSEED.",
                "PROCEDURE DIVISION.",
                "    CALL 'SOMEPROG'.",
                "    GOBACK.",
            ]
        ).encode()
    )

    call = next(i for i in ir if i.opcode.name == "CALL_WITH_MEMORY")
    preceding = ir[: ir.index(call)]
    seed = next(
        i
        for i in reversed(preceding)
        if i.opcode.name == "LOAD_REGION" and i.result_reg == call.result_reg
    )
    assert (
        seed is not None
    ), "the register CALL_WITH_MEMORY writes must be loaded from RETURN-CODE first"
