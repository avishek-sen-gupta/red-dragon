"""Unit tests for run_cics() and the CICS dispatcher loop."""

import inspect
import queue
from unittest.mock import MagicMock

from tests.covers import covers, NotLanguageFeature
from interpreter.run import run_linked
from interpreter.cics.types import CicsContext, DispatchKind, DispatchResult
from interpreter.cics.dispatcher import (
    _run_dispatcher_with_runner,
    InputEvent,
    parse_csd,
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_run_linked_accepts_initial_vm():
    sig = inspect.signature(run_linked)
    assert "initial_vm" in sig.parameters


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dispatcher_return_stops_loop():
    calls = []

    def mock_run(program, ctx, sq, iq):
        calls.append(ctx.transid)
        return DispatchResult(kind=DispatchKind.RETURN)

    program_cache = {"PROG1": MagicMock()}
    transid_to_program = {"CC00": "PROG1"}
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    sq, iq = queue.Queue(), queue.Queue()

    result = _run_dispatcher_with_runner(
        mock_run, program_cache, transid_to_program, ctx, sq, iq
    )
    assert result.kind == DispatchKind.RETURN
    assert len(calls) == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dispatcher_xctl_switches_program():
    call_count = [0]

    def mock_run(program, ctx, sq, iq):
        call_count[0] += 1
        if call_count[0] == 1:
            return DispatchResult(kind=DispatchKind.XCTL, program="PROG2", commarea=b"")
        return DispatchResult(kind=DispatchKind.RETURN)

    program_cache = {"PROG1": MagicMock(), "PROG2": MagicMock()}
    transid_to_program = {"CC00": "PROG1"}
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    sq, iq = queue.Queue(), queue.Queue()

    result = _run_dispatcher_with_runner(
        mock_run, program_cache, transid_to_program, ctx, sq, iq
    )
    assert call_count[0] == 2
    assert result.kind == DispatchKind.RETURN


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dispatcher_return_transid_blocks_then_resumes():
    call_count = [0]

    def mock_run(program, ctx, sq, iq):
        call_count[0] += 1
        if call_count[0] == 1:
            return DispatchResult(
                kind=DispatchKind.RETURN_TRANSID, transid="CC01", commarea=b""
            )
        return DispatchResult(kind=DispatchKind.RETURN)

    program_cache = {"PROG1": MagicMock(), "PROG2": MagicMock()}
    transid_to_program = {"CC00": "PROG1", "CC01": "PROG2"}
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    sq, iq = queue.Queue(), queue.Queue()
    iq.put(InputEvent(eibaid="\x7d", fields={}))

    result = _run_dispatcher_with_runner(
        mock_run, program_cache, transid_to_program, ctx, sq, iq
    )
    assert call_count[0] == 2
    assert result.kind == DispatchKind.RETURN


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dispatcher_resume_propagates_event_eibaid_to_context():
    """On RETURN TRANSID resume, the input event's attention key flows into the
    next turn's CicsContext (which init_eib then writes to EIBAID)."""
    seen_eibaids: list[str] = []

    def mock_run(program, ctx, sq, iq):
        seen_eibaids.append(ctx.eibaid)
        if len(seen_eibaids) == 1:
            return DispatchResult(
                kind=DispatchKind.RETURN_TRANSID, transid="CC01", commarea=b""
            )
        return DispatchResult(kind=DispatchKind.RETURN)

    program_cache = {"PROG1": MagicMock(), "PROG2": MagicMock()}
    transid_to_program = {"CC00": "PROG1", "CC01": "PROG2"}
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    sq, iq = queue.Queue(), queue.Queue()
    # The resumed turn's terminal input carries PF3.
    iq.put(InputEvent(eibaid="\xf3", fields={}))

    _run_dispatcher_with_runner(
        mock_run, program_cache, transid_to_program, ctx, sq, iq
    )
    assert seen_eibaids[0] == "\x7d"  # first turn: initial context aid
    assert seen_eibaids[1] == "\xf3"  # resumed turn: event's aid propagated


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_csd(tmp_path):
    csd = tmp_path / "carddemo.csd"
    csd.write_text(
        "DEFINE TRANSACTION(CC00) PROGRAM(COSGN00C)\n"
        "DEFINE TRANSACTION(CC01) PROGRAM(COMEN01C)\n"
    )
    mapping = parse_csd(csd)
    assert mapping["CC00"] == "COSGN00C"
    assert mapping["CC01"] == "COMEN01C"
