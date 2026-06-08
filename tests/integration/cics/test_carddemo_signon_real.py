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


def _signon_map_loader() -> BmsLoader:
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
    return loader


@covers(CobolFeature.EXEC_CICS, CobolFeature.INTRINSIC_FUNCTION)
def test_real_carddemo_signon_reaches_menu_xctl():
    """Real COSGN00C: valid credentials -> READ USRSEC -> XCTL to COMEN01C."""
    from interpreter.cobol.cobol_parser import ProLeapCobolParser
    from interpreter.cobol.subprocess_runner import RealSubprocessRunner

    app = Path(_CARDDEMO_HOME)
    source_path = app / "cbl" / "COSGN00C.cbl"
    assert (
        source_path.is_file()
    ), f"COSGN00C not found under CARDDEMO_HOME: {source_path}"

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
        bms_loader=_signon_map_loader(),
        screen_queue=screen_q,
        input_queue=input_q,
    )

    src = apply_cics_prepass(source_path.read_text()).encode()
    program = compile_cics_program(src, parser, strategy)

    # ENTER turn: non-empty COMMAREA => EIBCALEN>0 => PROCESS-ENTER-KEY path.
    input_q.put(
        InputEvent(eibaid="\x7d", fields={"USERID": "USER0001", "PASSWD": "PASS0001"})
    )
    ctx = CicsContext(transid="CC00", commarea=b"\x00" * 100, eibaid="\x7d")

    result = run_cics(
        program,
        ctx,
        screen_q,
        input_q,
        context_holder=context_holder,
        result_holder=result_holder,
        max_steps=200_000,
    )

    assert result.kind == DispatchKind.XCTL, (
        f"sign-on did not XCTL (kind={result.kind}); the sign-on screen likely "
        f"re-sent with an error message instead of advancing to the menu"
    )
    assert (
        result.program or ""
    ).strip() == "COMEN01C", (
        f"sign-on XCTL'd to {result.program!r}, expected COMEN01C (the user menu)"
    )
