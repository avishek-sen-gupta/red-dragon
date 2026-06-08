"""
Integration test: CICS pseudo-conversational sign-on -> main menu flow.

Exercises the REAL dispatcher loop (_run_dispatcher_with_runner) and the REAL
screen builtins (SEND MAP / RECEIVE MAP), which read/write the symbolic map
group's leaf fields from the program's WORKING-STORAGE layout (vm.data_layout).
Only the COBOL program execution is stubbed via a stateful run_fn, so no ProLeap
JAR is required; each turn supplies a small fake VM carrying the map region and
layout the real lowering would have produced.

Flow:
  Turn 1: CC00 / COSGN00C -- SEND MAP COSGN0A, RECEIVE MAP (credentials),
          XCTL to COMEN01C.
  Turn 2: CC00 / COMEN01C -- SEND MAP COMEN0A, RETURN (terminate).
"""

import queue

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.types import CicsContext, DispatchKind, DispatchResult
from interpreter.cics.builtins.screen import (
    make_send_map_builtin,
    make_receive_map_builtin,
)
from interpreter.cics.dispatcher import _run_dispatcher_with_runner, InputEvent
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import UNKNOWN


class _FakeVM:
    """Minimal VM standing in for the symbolic map group in WORKING-STORAGE.

    Holds the map region bytes and a name->{offset,length} layout, mirroring
    what compile_cics_program would have built for the program's WS records.
    """

    def __init__(self, region: bytearray, layout: dict, addr: int = 1):
        self._region = region
        self.data_layout = layout
        self._addr = addr

    def region_get(self, addr):
        return self._region if addr == self._addr else None

    def region_set(self, addr, data):
        if addr == self._addr:
            self._region[: len(data)] = data


def _tv(v):
    return typed(v, UNKNOWN)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_sign_on_to_main_menu_flow(monkeypatch):
    screen_q: queue.Queue = queue.Queue()
    input_q: queue.Queue = queue.Queue()

    # The screen builtins locate the WS region via _get_ws_region_addr; pin it.
    monkeypatch.setattr(
        "interpreter.cics.builtins.system._get_ws_region_addr", lambda _vm: 1
    )

    send_map = make_send_map_builtin(screen_q)
    # short timeout so a missing input fails fast rather than hanging the suite
    receive_map = make_receive_map_builtin(input_q, timeout=5.0)

    # Sign-on map COSGN0A: symbolic output leaves USERIDO / PASSWDO and the
    # matching input leaves USERIDI / PASSWDI (REDEFINES, same offsets).
    sgn_layout = {
        "USERIDO": {"offset": 0, "length": 8},
        "PASSWDO": {"offset": 8, "length": 8},
        "USERIDI": {"offset": 0, "length": 8},
        "PASSWDI": {"offset": 8, "length": 8},
        "EIBAID": {"offset": 16, "length": 1},
    }
    sgn_region = bytearray(b"\x40" * 17)
    # The program MOVEd a userid prompt into the output field before SEND.
    sgn_region[0:8] = "USER0001".encode("cp037")
    sgn_vm = _FakeVM(sgn_region, sgn_layout)

    # Menu map COMEN0A: one output leaf OPTIONO.
    men_layout = {"OPTIONO": {"offset": 0, "length": 2}}
    men_region = bytearray(b"\x40" * 2)
    men_vm = _FakeVM(men_region, men_layout)

    # Distinct stub program objects so run_fn can tell which one it's running.
    prog_sign_on = object()
    prog_menu = object()
    program_cache = {"COSGN00C": prog_sign_on, "COMEN01C": prog_menu}
    transid_to_program = {"CC00": "COSGN00C"}

    # Pre-load the credentials the sign-on RECEIVE MAP will consume.
    input_q.put(
        InputEvent(eibaid="\x7d", fields={"USERID": "ALICE", "PASSWD": "SECRET"})
    )

    def run_fn(program, context, sq, iq):
        if program is prog_sign_on:
            # SEND MAP('COSGN0A') FROM(COSGN0AO): base names USERID/PASSWD are
            # the leaves of the output group with the trailing 'O' stripped.
            send_map([_tv("COSGN0A"), _tv(["USERID", "PASSWD"])], sgn_vm)
            # RECEIVE MAP('COSGN0A') INTO(COSGN0AI): credentials land in the
            # input leaves USERIDI / PASSWDI of the WS region.
            receive_map([_tv("COSGN0A"), _tv(["USERID", "PASSWD"])], sgn_vm)
            # Pass the populated map region forward in the COMMAREA, XCTL to menu.
            return DispatchResult(
                kind=DispatchKind.XCTL, program="COMEN01C", commarea=bytes(sgn_region)
            )
        else:
            send_map([_tv("COMEN0A"), _tv(["OPTION"])], men_vm)
            return DispatchResult(kind=DispatchKind.RETURN)

    initial_context = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    result = _run_dispatcher_with_runner(
        run_fn, program_cache, transid_to_program, initial_context, screen_q, input_q
    )

    # Loop terminated on the menu program's RETURN.
    assert result.kind == DispatchKind.RETURN

    # Two screens were sent, in order: sign-on then menu.
    screens = []
    while not screen_q.empty():
        screens.append(screen_q.get_nowait())
    assert [s["map"] for s in screens] == ["COSGN0A", "COMEN0A"]

    # The sign-on screen exposed the symbolic output field value from WS.
    assert screens[0]["fields"]["USERID"] == "USER0001"

    # Credentials flowed through RECEIVE MAP into the input leaves of the WS
    # region (EBCDIC cp037); USERID occupies bytes 0:8.
    assert sgn_region[0:8].decode("cp037").rstrip() == "ALICE"
    assert sgn_region[8:16].decode("cp037").rstrip() == "SECRET"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_return_transid_blocks_on_input_then_resumes():
    """RETURN TRANSID parks the transaction until the next terminal InputEvent."""
    screen_q: queue.Queue = queue.Queue()
    input_q: queue.Queue = queue.Queue()

    prog_a = object()
    prog_b = object()
    program_cache = {"PROGA": prog_a, "PROGB": prog_b}
    transid_to_program = {"AA00": "PROGA", "BB00": "PROGB"}

    calls = []

    def run_fn(program, context, sq, iq):
        calls.append(context.transid)
        if program is prog_a:
            return DispatchResult(
                kind=DispatchKind.RETURN_TRANSID, transid="BB00", commarea=b"X"
            )
        return DispatchResult(kind=DispatchKind.RETURN)

    # The next-turn input that unblocks RETURN TRANSID.
    input_q.put(InputEvent(eibaid="\x7d", fields={}))

    initial_context = CicsContext(transid="AA00", commarea=b"", eibaid="\x7d")
    result = _run_dispatcher_with_runner(
        run_fn, program_cache, transid_to_program, initial_context, screen_q, input_q
    )

    assert result.kind == DispatchKind.RETURN
    assert calls == ["AA00", "BB00"]
