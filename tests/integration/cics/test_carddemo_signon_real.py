"""MANUAL regression test: the REAL CardDemo sign-on program reaches the menu.

This is intentionally skipped during normal/CI test runs. It compiles and executes
the actual (unmodified) sign-on program from a local CardDemo checkout, which is an
external dependency not present in the repo or CI. It exists to lock in the
end-to-end milestone and to re-verify it on demand.

Run it explicitly:

    CARDDEMO_HOME=/path/to/aws-mainframe-carddemo/app \\
        poetry run python -m pytest \\
        tests/integration/cics/test_carddemo_signon_real.py -v

It drives the real sign-on (transid CC00) through ``run_cics`` for the ENTER turn:

  RECEIVE MAP -> FUNCTION UPPER-CASE(USERIDI OF COSGN0AI) -> MOVE (multi-target)
  -> READ DATASET(WS-USRSEC-FILE) -> password check -> XCTL COMEN01C

with an in-memory USRSEC dataset seeded with one user and tiny stub XCTL targets.
Asserts the dispatcher result is an XCTL to the menu program.
"""

from __future__ import annotations

import os
import queue
import tempfile
from pathlib import Path

import pytest

from interpreter.cics.preprocessor import apply_cics_prepass
from interpreter.cics.strategy import CicsLoweringStrategy
from interpreter.cics.types import CicsContext, DispatchKind
from interpreter.cics.dispatcher import run_cics, InputEvent
from interpreter.cics.bootstrap import compile_cics_program
from interpreter.cics.bms.loader import BmsLoader, BmsMap, BmsField
from interpreter.cics.vsam.engine import VsamEngine
from interpreter.cics.vsam.fct import FctConfig, DatasetConfig
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cobol_helpers import JAR_AVAILABLE, JAR_PATH

# CARDDEMO_HOME is unset in normal/CI runs, so this whole module is skipped by
# default. Set it (to the CardDemo `app` directory) to run the test explicitly.
_CARDDEMO_HOME = os.environ.get("CARDDEMO_HOME")

pytestmark = pytest.mark.skipif(
    not _CARDDEMO_HOME or not JAR_AVAILABLE,
    reason="manual: set CARDDEMO_HOME=<carddemo app dir> (and have the ProLeap JAR) to run",
)

_CICS_COPYBOOKS = Path(__file__).parents[3] / "interpreter" / "cics" / "copybooks"


def _ebcdic(s: str, n: int) -> bytes:
    return s.ljust(n)[:n].encode("cp037")


def _usrsec_engine() -> VsamEngine:
    """In-memory USRSEC keyed by user id; one regular user USER0001/PASS0001."""
    # CSUSR01Y record: id(8) fname(20) lname(20) pwd(8) type(1) filler(23) = 80.
    rec = (
        _ebcdic("USER0001", 8)
        + _ebcdic("First", 20)
        + _ebcdic("Last", 20)
        + _ebcdic("PASS0001", 8)
        + _ebcdic("U", 1)  # regular user -> XCTL COMEN01C
        + _ebcdic("", 23)
    )
    td = tempfile.mkdtemp()
    path = Path(td) / "usrsec.txt"
    path.write_bytes(rec)
    engine = VsamEngine(
        FctConfig(datasets={"USRSEC": DatasetConfig(path=path, record_length=80)})
    )
    engine.load_all()
    return engine


def _map_loader() -> BmsLoader:
    loader = BmsLoader(maps_dir=None)
    loader.register_stub(
        "COSGN0A",
        BmsMap(
            name="COSGN0A",
            fields={
                "USERID": BmsField(offset=0, length=8),
                "PASSWD": BmsField(offset=8, length=8),
                "ERRMSG": BmsField(offset=16, length=78),
            },
        ),
    )
    loader.register_stub(
        "COMEN1A",
        BmsMap(
            name="COMEN1A",
            fields={
                b: BmsField(offset=0, length=8)
                for b in (
                    "TITLE01",
                    "TITLE02",
                    "TRNNAME",
                    "PGMNAME",
                    "CURDATE",
                    "ERRMSG",
                )
            },
        ),
    )
    return loader


@covers(CobolFeature.EXEC_CICS, CobolFeature.INTRINSIC_FUNCTION)
def test_real_carddemo_signon_then_menu_renders():
    """Real two-program flow:

    Turn 1 (COSGN00C): valid credentials -> RECEIVE MAP -> UPPER-CASE ->
        READ USRSEC -> password check -> XCTL COMEN01C.
    Turn 2 (COMEN01C): first display -> SEND MAP COMEN1A (the user menu) ->
        RETURN TRANSID CM00.

    Each program is the real, unmodified CardDemo source; they share one
    CicsLoweringStrategy (and its USRSEC engine + BMS maps). Driven via the
    single-execution run_cics entry (no unbounded dispatcher loop).
    """
    from interpreter.cobol.cobol_parser import ProLeapCobolParser
    from interpreter.cobol.subprocess_runner import RealSubprocessRunner

    app = Path(_CARDDEMO_HOME)
    signon_path = app / "cbl" / "COSGN00C.cbl"
    menu_path = app / "cbl" / "COMEN01C.cbl"
    assert signon_path.is_file(), f"COSGN00C not found: {signon_path}"
    assert menu_path.is_file(), f"COMEN01C not found: {menu_path}"

    parser = ProLeapCobolParser(
        RealSubprocessRunner(),
        JAR_PATH,
        copybook_dirs=[app / "cpy", app / "cpy-bms", _CICS_COPYBOOKS],
    )

    screen_q: queue.Queue = queue.Queue()
    input_q: queue.Queue = queue.Queue()
    context_holder = [None]
    result_holder: list = [None]
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=_usrsec_engine(),
        bms_loader=_map_loader(),
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(
        apply_cics_prepass(signon_path.read_text()).encode(), parser, strategy
    )
    menu = compile_cics_program(
        apply_cics_prepass(menu_path.read_text()).encode(), parser, strategy
    )

    # --- Turn 1: sign-on ENTER turn -> XCTL COMEN01C ---
    input_q.put(
        InputEvent(eibaid="\x7d", fields={"USERID": "USER0001", "PASSWD": "PASS0001"})
    )
    r1 = run_cics(
        signon,
        CicsContext(transid="CC00", commarea=b"\x00" * 100, eibaid="\x7d"),
        screen_q,
        input_q,
        context_holder=context_holder,
        result_holder=result_holder,
        max_steps=200_000,
    )
    assert r1.kind == DispatchKind.XCTL, (
        f"sign-on did not XCTL (kind={r1.kind}); it likely re-sent the sign-on "
        f"screen with an error instead of advancing to the menu"
    )
    assert (
        r1.program or ""
    ).strip() == "COMEN01C", (
        f"sign-on XCTL'd to {r1.program!r}, expected COMEN01C (the user menu)"
    )

    # --- Turn 2: the menu program's first display renders the menu map ---
    while not screen_q.empty():  # drain any sign-on screen output
        screen_q.get_nowait()
    menu_commarea = (r1.commarea or b"").ljust(300, b"\x00")
    r2 = run_cics(
        menu,
        CicsContext(transid="CM00", commarea=menu_commarea, eibaid="\x7d"),
        screen_q,
        input_q,
        context_holder=context_holder,
        result_holder=result_holder,
        max_steps=400_000,
    )

    screens = []
    while not screen_q.empty():
        screens.append(screen_q.get_nowait())

    assert any(
        s.get("map") == "COMEN1A" for s in screens
    ), f"menu program did not render COMEN1A; screens={[s.get('map') for s in screens]}"
    menu_screen = next(s for s in screens if s.get("map") == "COMEN1A")
    # The menu header reflects the running transid/program (proves real execution).
    assert menu_screen["fields"].get("TRNNAME") == "CM00"
    assert menu_screen["fields"].get("PGMNAME") == "COMEN01C"
    # COMEN01C parks for the next terminal action (pseudo-conversational).
    assert r2.kind == DispatchKind.RETURN_TRANSID
