"""Unit tests for CICS shared runtime types."""

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.types import CicsContext, DispatchKind, DispatchResult


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cics_context_creation():
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    assert ctx.transid == "CC00"
    assert ctx.eibaid == "\x7d"
    assert len(ctx.commarea) == 0


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dispatch_result_return():
    r = DispatchResult(kind=DispatchKind.RETURN)
    assert r.kind == DispatchKind.RETURN
    assert r.transid is None
    assert r.commarea is None
    assert r.program is None
    assert r.abcode is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dispatch_result_return_transid():
    r = DispatchResult(
        kind=DispatchKind.RETURN_TRANSID,
        transid="CC01",
        commarea=b"\x00" * 16,
    )
    assert r.kind == DispatchKind.RETURN_TRANSID
    assert r.transid == "CC01"
    assert len(r.commarea) == 16


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dispatch_result_xctl():
    r = DispatchResult(kind=DispatchKind.XCTL, program="COCRDUPC", commarea=b"")
    assert r.kind == DispatchKind.XCTL
    assert r.program == "COCRDUPC"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dispatch_result_abend():
    r = DispatchResult(kind=DispatchKind.ABEND, abcode="CICS")
    assert r.kind == DispatchKind.ABEND
    assert r.abcode == "CICS"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dispatch_kind_static_field():
    r = DispatchResult(kind=DispatchKind.RETURN_TRANSID, transid="X", commarea=b"")
    assert r.kind == DispatchKind.RETURN_TRANSID
    assert r.kind != DispatchKind.RETURN
