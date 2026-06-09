"""Unit tests for run_cics() and the CICS dispatcher loop."""

import inspect
import queue
from unittest.mock import MagicMock

from tests.covers import covers, NotLanguageFeature
from interpreter.run import run_linked
from interpreter.cics.types import CicsContext, DispatchKind, DispatchResult
from interpreter.cics.dispatcher import (
    _run_dispatcher_with_runner,
    _advance_routing,
    CicsRegion,
    InputEvent,
    parse_csd,
)
import interpreter.cics.dispatcher as dispatcher_mod


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


# ─────────────────────────────────────────────────────────────────────────────
# _advance_routing — the single copy of the "which program/transid next" rule.
# ─────────────────────────────────────────────────────────────────────────────


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_advance_routing_return_transid_maps_via_csd():
    """RETURN TRANSID resolves the next program via the transid→program map and
    returns (stripped transid, that program, commarea)."""
    prog2 = object()
    program_cache = {"PROG1": object(), "PROG2": prog2}
    transid_to_program = {"CC00": "PROG1", "CC01": "PROG2"}
    result = DispatchResult(
        kind=DispatchKind.RETURN_TRANSID, transid="CC01", commarea=b"AB"
    )
    out = _advance_routing(result, "CC00", program_cache, transid_to_program)
    assert out == ("CC01", prog2, b"AB")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_advance_routing_return_transid_strips_and_defaults_commarea():
    """transid is stripped of trailing pad and a None commarea becomes b''."""
    prog2 = object()
    program_cache = {"PROG2": prog2}
    transid_to_program = {"CC01": "PROG2"}
    result = DispatchResult(
        kind=DispatchKind.RETURN_TRANSID, transid="CC01    ", commarea=None
    )
    out = _advance_routing(result, "CC00", program_cache, transid_to_program)
    assert out == ("CC01", prog2, b"")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_advance_routing_return_transid_unknown_abends_trni():
    """An unknown RETURN TRANSID target abends TRNI (terminal)."""
    result = DispatchResult(kind=DispatchKind.RETURN_TRANSID, transid="ZZZZ")
    out = _advance_routing(result, "CC00", {}, {"CC00": "PROG1"})
    assert isinstance(out, DispatchResult)
    assert out.kind == DispatchKind.ABEND
    assert out.abcode == "TRNI"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_advance_routing_xctl_carries_transid():
    """XCTL switches program but the transid CARRIES (same task)."""
    prog2 = object()
    program_cache = {"PROG1": object(), "COMEN01C": prog2}
    result = DispatchResult(kind=DispatchKind.XCTL, program="COMEN01C", commarea=b"X")
    out = _advance_routing(result, "CC00", program_cache, {})
    assert out == ("CC00", prog2, b"X")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_advance_routing_xctl_unknown_abends_pgmi():
    """An XCTL to an unknown program abends PGMI (terminal)."""
    result = DispatchResult(kind=DispatchKind.XCTL, program="NOPE")
    out = _advance_routing(result, "CC00", {}, {})
    assert isinstance(out, DispatchResult)
    assert out.kind == DispatchKind.ABEND
    assert out.abcode == "PGMI"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_advance_routing_return_is_terminal():
    """A plain RETURN (or any other kind) is returned unchanged (terminal)."""
    result = DispatchResult(kind=DispatchKind.RETURN)
    out = _advance_routing(result, "CC00", {}, {})
    assert out is result


# ─────────────────────────────────────────────────────────────────────────────
# CicsRegion — turn-by-turn dispatch API. Driven here with a monkeypatched
# run_cics returning scripted DispatchResults so we test the routing/advance
# state machine in isolation.
# ─────────────────────────────────────────────────────────────────────────────


def _region(program_cache, transid_to_program):
    return CicsRegion(
        program_cache,
        transid_to_program,
        queue.Queue(),
        queue.Queue(),
        context_holder=[None],
        result_holder=[None],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_region_start_dispatches_entry_program(monkeypatch):
    seen = []

    def fake_run(program, ctx, sq, iq, **kw):
        seen.append((program, ctx.transid, ctx.eibaid))
        return DispatchResult(kind=DispatchKind.RETURN)

    monkeypatch.setattr(dispatcher_mod, "run_cics", fake_run)
    p1 = object()
    region = _region({"PROG1": p1}, {"CC00": "PROG1"})
    r = region.start("CC00", input_event=InputEvent(eibaid="\x7d", fields={}))
    assert seen == [(p1, "CC00", "\x7d")]
    assert r.kind == DispatchKind.RETURN
    assert region.done is True


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_region_xctl_carries_transid_and_runs_next_program_with_no_input(
    monkeypatch,
):
    """After an XCTL, step() runs the XCTL'd program under the SAME transid with
    no new terminal input (same task)."""
    signon, menu = object(), object()
    seen = []
    scripted = [
        DispatchResult(kind=DispatchKind.XCTL, program="COMEN01C", commarea=b"C1"),
        DispatchResult(
            kind=DispatchKind.RETURN_TRANSID, transid="CM00", commarea=b"C2"
        ),
    ]

    def fake_run(program, ctx, sq, iq, **kw):
        seen.append((program, ctx.transid, ctx.commarea, ctx.eibaid))
        return scripted[len(seen) - 1]

    monkeypatch.setattr(dispatcher_mod, "run_cics", fake_run)
    region = _region(
        {"COSGN00C": signon, "COMEN01C": menu}, {"CC00": "COSGN00C", "CM00": "COMEN01C"}
    )
    r1 = region.start("CC00", commarea=b"INIT", input_event=InputEvent(eibaid="\x7d"))
    assert r1.kind == DispatchKind.XCTL
    assert region.transid == "CC00"  # transid carries on XCTL
    assert region.done is False

    r2 = region.step()  # no input_event after XCTL
    # menu ran under transid CC00 (carried), commarea from the XCTL, eibaid carried.
    assert seen[1] == (menu, "CC00", b"C1", "\x7d")
    assert r2.kind == DispatchKind.RETURN_TRANSID


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_region_return_transid_then_step_with_fresh_input(monkeypatch):
    """After RETURN TRANSID, the next program comes from the CSD map, the transid
    is the returned one, and a fresh terminal input is supplied to step()."""
    menu, acct = object(), object()
    seen = []
    scripted = [
        DispatchResult(kind=DispatchKind.RETURN_TRANSID, transid="CM00", commarea=b"M"),
        DispatchResult(kind=DispatchKind.RETURN),
    ]

    def fake_run(program, ctx, sq, iq, **kw):
        seen.append((program, ctx.transid, ctx.commarea, ctx.eibaid))
        return scripted[len(seen) - 1]

    monkeypatch.setattr(dispatcher_mod, "run_cics", fake_run)
    region = _region(
        {"COMEN01C": menu, "COACTVWC": acct},
        {"CM00": "COMEN01C", "CAVW": "COACTVWC"},
    )
    # Pretend the first program already RETURN TRANSID'd to CM00 -> but to test the
    # RETURN_TRANSID branch we start on CM00 (menu) which returns RETURN_TRANSID CM00.
    r1 = region.start("CM00", input_event=InputEvent(eibaid="\x7d"))
    assert r1.kind == DispatchKind.RETURN_TRANSID
    assert region.transid == "CM00"
    assert region.done is False
    # The CSD map says CM00 -> COMEN01C, so the next program is the menu again.
    r2 = region.step(input_event=InputEvent(eibaid="\xf3", fields={"OPTION": "01"}))
    assert seen[1][0] is menu  # CM00 -> COMEN01C via map
    assert seen[1][1] == "CM00"
    assert seen[1][2] == b"M"  # commarea carried from the RETURN TRANSID
    assert seen[1][3] == "\xf3"  # fresh input event's aid
    assert r2.kind == DispatchKind.RETURN


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_region_input_event_is_put_on_queue_for_receive_map(monkeypatch):
    """When an input_event is supplied, it is put on the input_queue so the
    program's RECEIVE MAP can consume it."""
    drained = []

    def fake_run(program, ctx, sq, iq, **kw):
        drained.append(iq.get_nowait())
        return DispatchResult(kind=DispatchKind.RETURN)

    monkeypatch.setattr(dispatcher_mod, "run_cics", fake_run)
    region = _region({"PROG1": object()}, {"CC00": "PROG1"})
    ev = InputEvent(eibaid="\x7d", fields={"USERID": "U"})
    region.start("CC00", input_event=ev)
    assert drained == [ev]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_region_step_raises_when_done(monkeypatch):
    def fake_run(program, ctx, sq, iq, **kw):
        return DispatchResult(kind=DispatchKind.RETURN)

    monkeypatch.setattr(dispatcher_mod, "run_cics", fake_run)
    region = _region({"PROG1": object()}, {"CC00": "PROG1"})
    region.start("CC00", input_event=InputEvent())
    assert region.done is True
    try:
        region.step()
        assert False, "step() after terminal should raise"
    except RuntimeError:
        pass


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
