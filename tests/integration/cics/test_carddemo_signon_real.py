"""MANUAL regression test: the REAL CardDemo programs run end to end (five turns).

This is intentionally skipped during normal/CI test runs. It compiles and executes
the actual (unmodified) programs from a local CardDemo checkout, which is an
external dependency not present in the repo or CI. It exists to lock in the
end-to-end milestone and to re-verify it on demand.

Run it explicitly:

    CARDDEMO_HOME=/path/to/aws-mainframe-carddemo/app \\
        poetry run python -m pytest \\
        tests/integration/cics/test_carddemo_signon_real.py -v

Five-turn flow across three programs, all sharing one CicsLoweringStrategy (one
VsamEngine seeded with USRSEC + the three account-view datasets, plus the
bms-tools-generated BMS maps; gated on BMS_TOOLS_HOME), driven through ``run_cics``:

  Turn 1 (COSGN00C): RECEIVE MAP -> UPPER-CASE -> READ USRSEC -> XCTL COMEN01C.
  Turn 2 (COMEN01C): first display renders the user menu COMEN1A -> RETURN CM00.
  Turn 3 (COMEN01C): ENTER option '01' -> option-table lookup -> XCTL COACTVWC.
  Turn 4 (COACTVWC): first display renders the account-view map CACTVWA -> RETURN.
  Turn 5 (COACTVWC): ENTER account id -> 9000-READ-ACCT's three chained VSAM reads
      (CXACAIX alt-index key@offset-25 -> ACCTDAT key@0 -> CUSTDAT key@0) ->
      re-render CACTVWA with the read-through account/customer fields.

Turns 1-4 are ``test_real_carddemo_signon_menu_and_option_select``; turn 5 is
``test_real_carddemo_account_view_three_reads``. Both pass: the full
account-view flow runs end to end (the entered account id echoes back and the
read-through account status + customer first/last names render from the three
chained VSAM reads).
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
from interpreter.cics.vsam.engine import VsamEngine
from interpreter.cics.vsam.fct import FctConfig, DatasetConfig
from interpreter.cics.bms.generate import generate_symbolic_copybooks
from interpreter.cobol.features import CobolFeature
from tests.covers import covers
from tests.integration.cics.bms_tools_helpers import (
    BMS_TOOLS_AVAILABLE,
    BMS_COPYBOOK_GEN_SRC,
    HLASM_EXPORT_BIN,
)
from tests.integration.cobol_helpers import JAR_AVAILABLE, JAR_PATH

# CARDDEMO_HOME is unset in normal/CI runs, so this whole module is skipped by
# default. Set it (to the CardDemo `app` directory) to run the test explicitly.
_CARDDEMO_HOME = os.environ.get("CARDDEMO_HOME")

pytestmark = pytest.mark.skipif(
    not _CARDDEMO_HOME or not JAR_AVAILABLE or not BMS_TOOLS_AVAILABLE,
    reason="manual: set CARDDEMO_HOME + BMS_TOOLS_HOME (built hlasm_export) + ProLeap JAR",
)

_CICS_COPYBOOKS = Path(__file__).parents[3] / "interpreter" / "cics" / "copybooks"


def _ebcdic(s: str, n: int) -> bytes:
    return s.ljust(n)[:n].encode("cp037")


# Concrete keys used by the turn-5 account-view read-through. The xref record's
# CUST-ID@16 must equal the CUSTDAT key, and the xref ACCT-ID@25 + the ACCTDAT
# key must equal the account id entered on the screen.
_ACCT_ID = "00000000011"  # 11-digit account id (matches WS-CARD-RID-ACCT-ID-X)
_CUST_ID = "000000001"  # 9-digit customer id (matches WS-CARD-RID-CUST-ID-X)
_ACCT_STATUS = "Y"  # ACCT-ACTIVE-STATUS X(01) -> ACSTTUSO
_CUST_FIRST = "JOHN"  # CUST-FIRST-NAME X(25) -> ACSFNAMO
_CUST_LAST = "DOE"  # CUST-LAST-NAME  X(25) -> ACSLNAMO


def _num(s: str, n: int) -> bytes:
    """Zoned-decimal style numeric field: right-justified zero-filled, cp037."""
    return s.zfill(n)[:n].encode("cp037")


def _xref_record() -> bytes:
    """CVACT03Y CARD-XREF-RECORD (RECLN 50): card-num X(16)@0, cust-id 9(9)@16,
    acct-id 9(11)@25, filler X(14)@36. ACCT-ID is the alt-index key (offset 25)."""
    return (
        _ebcdic("CARD0000000000011", 16)[:16]  # XREF-CARD-NUM X(16)
        + _num(_CUST_ID, 9)  # XREF-CUST-ID 9(9) @16
        + _num(_ACCT_ID, 11)  # XREF-ACCT-ID 9(11) @25  <- key
        + _ebcdic("", 14)  # FILLER X(14)
    )


def _acct_record() -> bytes:
    """CVACT01Y ACCOUNT-RECORD (RECLN 300): ACCT-ID 9(11)@0 (key), status X(1),
    then signed packed-as-display numerics. We seed the key + status (the field
    we assert) and leave the numeric balances as zeros (rendered, not asserted)."""
    rec = (
        _num(_ACCT_ID, 11)  # ACCT-ID 9(11) @0  <- key
        + _ebcdic(_ACCT_STATUS, 1)  # ACCT-ACTIVE-STATUS X(1)
        + _num("0", 12)  # ACCT-CURR-BAL S9(10)V99
        + _num("0", 12)  # ACCT-CREDIT-LIMIT
        + _num("0", 12)  # ACCT-CASH-CREDIT-LIMIT
        + _ebcdic("2020-01-01", 10)  # ACCT-OPEN-DATE
        + _ebcdic("2025-01-01", 10)  # ACCT-EXPIRAION-DATE
        + _ebcdic("2022-01-01", 10)  # ACCT-REISSUE-DATE
        + _num("0", 12)  # ACCT-CURR-CYC-CREDIT
        + _num("0", 12)  # ACCT-CURR-CYC-DEBIT
        + _ebcdic("12345", 10)  # ACCT-ADDR-ZIP
        + _ebcdic("GRP1", 10)  # ACCT-GROUP-ID
    )
    return rec.ljust(300, b"\x00")[:300]


def _cust_record() -> bytes:
    """CVCUS01Y CUSTOMER-RECORD (RECLN 500): CUST-ID 9(9)@0 (key), first X(25),
    middle X(25), last X(25), ... We seed the key + first/last names (asserted)."""
    rec = (
        _num(_CUST_ID, 9)  # CUST-ID 9(9) @0  <- key
        + _ebcdic(_CUST_FIRST, 25)  # CUST-FIRST-NAME
        + _ebcdic("Q", 25)  # CUST-MIDDLE-NAME
        + _ebcdic(_CUST_LAST, 25)  # CUST-LAST-NAME
        + _ebcdic("1 MAIN ST", 50)  # CUST-ADDR-LINE-1
        + _ebcdic("", 50)  # CUST-ADDR-LINE-2
        + _ebcdic("ANYTOWN", 50)  # CUST-ADDR-LINE-3
        + _ebcdic("CA", 2)  # CUST-ADDR-STATE-CD
        + _ebcdic("USA", 3)  # CUST-ADDR-COUNTRY-CD
        + _ebcdic("90001", 10)  # CUST-ADDR-ZIP
        + _ebcdic("5551234567", 15)  # CUST-PHONE-NUM-1
        + _ebcdic("5559876543", 15)  # CUST-PHONE-NUM-2
        + _num("123456789", 9)  # CUST-SSN 9(9)
        + _ebcdic("GID12345", 20)  # CUST-GOVT-ISSUED-ID
        + _ebcdic("1980-01-01", 10)  # CUST-DOB-YYYY-MM-DD
        + _ebcdic("", 10)  # CUST-EFT-ACCOUNT-ID
        + _ebcdic("Y", 1)  # CUST-PRI-CARD-HOLDER-IND
        + _num("750", 3)  # CUST-FICO-CREDIT-SCORE 9(3)
    )
    return rec.ljust(500, b"\x00")[:500]


def _usrsec_engine() -> VsamEngine:
    """In-memory engine seeded with FOUR datasets used across all five turns:

      * USRSEC  — sign-on user (turn 1), key@0, 80-byte CSUSR01Y record.
      * CXACAIX — CARD-XREF alternate-index path (turn 5, 9200-GETCARDXREF):
                  key = 11-digit ACCT-ID at record OFFSET 25 (CVACT03Y).
      * ACCTDAT — account master (turn 5, 9300-GETACCTDATA): key 11-digit @0.
      * CUSTDAT — customer master (turn 5, 9400-GETCUSTDATA): key 9-digit @0.

    The xref record's CUST-ID@16 == the CUSTDAT key, so the chained reads
    (acct-id -> cust-id -> customer) resolve end to end.
    """
    # CSUSR01Y record: id(8) fname(20) lname(20) pwd(8) type(1) filler(23) = 80.
    usrsec_rec = (
        _ebcdic("USER0001", 8)
        + _ebcdic("First", 20)
        + _ebcdic("Last", 20)
        + _ebcdic("PASS0001", 8)
        + _ebcdic("U", 1)  # regular user -> XCTL COMEN01C
        + _ebcdic("", 23)
    )
    td = Path(tempfile.mkdtemp())
    usrsec_path = td / "usrsec.txt"
    usrsec_path.write_bytes(usrsec_rec)
    xref_path = td / "cxacaix.txt"
    xref_path.write_bytes(_xref_record())
    acct_path = td / "acctdat.txt"
    acct_path.write_bytes(_acct_record())
    cust_path = td / "custdat.txt"
    cust_path.write_bytes(_cust_record())

    engine = VsamEngine(
        FctConfig(
            datasets={
                "USRSEC": DatasetConfig(path=usrsec_path, record_length=80),
                # Alt-index path: key is the 11-digit ACCT-ID at offset 25.
                "CXACAIX": DatasetConfig(
                    path=xref_path,
                    record_length=50,
                    key_offset=25,
                    key_length=11,
                ),
                "ACCTDAT": DatasetConfig(
                    path=acct_path, record_length=300, key_length=11
                ),
                "CUSTDAT": DatasetConfig(
                    path=cust_path, record_length=500, key_length=9
                ),
            }
        )
    )
    engine.load_all()
    return engine


def _drive_through_turn4(tmp_path):
    """Compile the three CardDemo programs and drive turns 1-4, asserting each.

    Turn 1 (COSGN00C): valid credentials -> RECEIVE MAP -> UPPER-CASE ->
        READ USRSEC -> password check -> XCTL COMEN01C.
    Turn 2 (COMEN01C, first display): SET reenter -> SEND MAP COMEN1A (the user
        menu) -> RETURN TRANSID CM00.
    Turn 3 (COMEN01C, ENTER + option '01'): RECEIVE MAP -> parse option ->
        option-table lookup -> XCTL COACTVWC (menu option 1's program).
    Turn 4 (COACTVWC, first display): entered via the menu XCTL -> 1000-SEND-MAP
        renders the account-view map CACTVWA -> RETURN TRANSID CAVW.

    All three programs share one CicsLoweringStrategy (one VsamEngine seeded with
    USRSEC + the three account-view datasets, plus BMS maps). Driven via the
    single-execution run_cics entry (no unbounded dispatcher loop).

    Returns the live drive context so a caller can continue into turn 5:
    ``(acct_program, r4, screen_q, input_q, context_holder, result_holder)``.
    """
    from interpreter.cobol.cobol_parser import ProLeapCobolParser
    from interpreter.cobol.subprocess_runner import RealSubprocessRunner

    app = Path(_CARDDEMO_HOME)
    signon_path = app / "cbl" / "COSGN00C.cbl"
    menu_path = app / "cbl" / "COMEN01C.cbl"
    acct_path = app / "cbl" / "COACTVWC.cbl"
    assert signon_path.is_file(), f"COSGN00C not found: {signon_path}"
    assert menu_path.is_file(), f"COMEN01C not found: {menu_path}"
    assert acct_path.is_file(), f"COACTVWC not found: {acct_path}"

    # INVARIANT: the symbolic map copybooks the programs COPY (COSGN00, COMEN01)
    # must be GENERATED by the bms-tools pipeline, not the shipped cpy-bms/*.CPY.
    # The .bms stems (COSGN00.bms, COMEN01.bms) match the COPY member names, so
    # generate_symbolic_copybooks writes COSGN00.cpy / COMEN01.cpy directly — no
    # name mapping needed.
    sym_dir = tmp_path / "sym"
    generate_symbolic_copybooks(
        bms_dir=app / "bms",
        out_dir=sym_dir,
        hlasm_export_bin=HLASM_EXPORT_BIN,
        bms_copybook_gen_src=BMS_COPYBOOK_GEN_SRC,
    )

    # PRECEDENCE: ProLeapCobolParser passes each dir as a separate -copybook-dir
    # to the bridge in list order; the bridge resolves COPY NAME by first match.
    # sym_dir is placed FIRST so the generated map copybooks win over the shipped
    # cpy-bms/*.CPY (which share the same basename). This honors the invariant.
    # (Assumption: bridge search order == arg order, first-match-wins. The test
    # skips locally when the bms-tools binary is unbuilt, so this could not be
    # empirically confirmed here.)
    parser = ProLeapCobolParser(
        RealSubprocessRunner(),
        JAR_PATH,
        copybook_dirs=[sym_dir, app / "cpy", app / "cpy-bms", _CICS_COPYBOOKS],
    )

    screen_q: queue.Queue = queue.Queue()
    input_q: queue.Queue = queue.Queue()
    context_holder = [None]
    result_holder: list = [None]
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=_usrsec_engine(),
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(
        apply_cics_prepass(signon_path.read_text()).encode(), parser, strategy
    )
    menu = compile_cics_program(
        apply_cics_prepass(menu_path.read_text()).encode(), parser, strategy
    )
    acct = compile_cics_program(
        apply_cics_prepass(acct_path.read_text()).encode(), parser, strategy
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

    # --- Turn 3: ENTER on the menu with option '01' -> XCTL to its program ---
    # The reenter flag set on turn 2 (SET CDEMO-PGM-REENTER TO TRUE) carries in
    # r2.commarea, so COMEN01C now takes PROCESS-ENTER-KEY instead of redisplaying.
    while not screen_q.empty():
        screen_q.get_nowait()
    input_q.put(InputEvent(eibaid="\x7d", fields={"OPTION": "01"}))
    r3 = run_cics(
        menu,
        CicsContext(
            transid="CM00",
            commarea=(r2.commarea or b"").ljust(300, b"\x00"),
            eibaid="\x7d",
        ),
        screen_q,
        input_q,
        context_holder=context_holder,
        result_holder=result_holder,
        max_steps=600_000,
    )
    assert r3.kind == DispatchKind.XCTL, (
        f"menu option select did not XCTL (kind={r3.kind}); the menu likely "
        f"redisplayed instead of processing the option (reenter gate / option parse)"
    )
    # Menu option 1 maps to COACTVWC in the option table (COMEN02Y); the
    # subscripted XCTL PROGRAM(CDEMO-MENU-OPT-PGMNAME(WS-OPTION)) resolves it.
    assert (
        r3.program or ""
    ).strip() == "COACTVWC", (
        f"menu option 1 XCTL'd to {r3.program!r}, expected COACTVWC"
    )

    # --- Turn 4: COACTVWC first display (XCTL'd in from the menu) ---
    # Entered via the menu XCTL (CDEMO-PGM-ENTER), COACTVWC gathers selection
    # criteria: PERFORM 1000-SEND-MAP renders the account-view map CACTVWA (asking
    # for an account id) then RETURN TRANSID CAVW. No VSAM read on this turn.
    # CACTVWA uses extended attributes (DFHMDI DSATTS/MAPATTS) — the generated
    # symbolic map must carry the <field>C/P/H/V subfields the program moves into.
    while not screen_q.empty():
        screen_q.get_nowait()
    r4 = run_cics(
        acct,
        CicsContext(
            transid="CAVW",
            commarea=(r3.commarea or b"").ljust(400, b"\x00"),
            eibaid="\x7d",
        ),
        screen_q,
        input_q,
        context_holder=context_holder,
        result_holder=result_holder,
        max_steps=800_000,
    )
    screens = []
    while not screen_q.empty():
        screens.append(screen_q.get_nowait())
    assert any(
        s.get("map") == "CACTVWA" for s in screens
    ), f"COACTVWC did not render CACTVWA; screens={[s.get('map') for s in screens]}"
    acct_screen = next(s for s in screens if s.get("map") == "CACTVWA")
    assert acct_screen["fields"].get("TRNNAME") == "CAVW"
    assert acct_screen["fields"].get("PGMNAME") == "COACTVWC"
    # COACTVWC parks for the account-id entry (pseudo-conversational).
    assert r4.kind == DispatchKind.RETURN_TRANSID
    assert (r4.transid or "").strip() == "CAVW"

    return acct, r4, screen_q, input_q, context_holder, result_holder


@covers(CobolFeature.EXEC_CICS, CobolFeature.INTRINSIC_FUNCTION)
def test_real_carddemo_signon_menu_and_option_select(tmp_path):
    """Four-turn flow through unmodified CardDemo source (sign-on -> menu ->
    option select -> COACTVWC first display). See ``_drive_through_turn4``."""
    _drive_through_turn4(tmp_path)


@covers(CobolFeature.EXEC_CICS, CobolFeature.INTRINSIC_FUNCTION)
def test_real_carddemo_account_view_three_reads(tmp_path):
    """Turn 5: account-id entry into COACTVWC -> 9000-READ-ACCT's three chained
    VSAM reads -> account-view render.

    Continues the four-turn flow. ENTER with ACCTSID=00000000011. 9000-READ-ACCT:
      1) READ CXACAIX RIDFLD=ACCT-ID(11) -> xref record; key sits at OFFSET 25
         (CVACT03Y) so this exercises the new VSAM key-offset support. Yields CUST-ID.
      2) READ ACCTDAT RIDFLD=ACCT-ID(11) -> account master (key @0).
      3) READ CUSTDAT RIDFLD=CUST-ID(9)  -> customer master (key @0).
    1200-SETUP-SCREEN-VARS then moves the read-through values (gated by the
    FOUND-ACCT-IN-MASTER / FOUND-CUST-IN-MASTER level-88 flags) into CACTVWAO and
    1000-SEND-MAP re-renders CACTVWA. This completes the account-view flow: the
    entered account id echoes back, the account status renders 'Y', and the
    customer first/last names render from the chained reads.
    """
    acct, r4, screen_q, input_q, context_holder, result_holder = _drive_through_turn4(
        tmp_path
    )

    # --- Turn 5: account-id entry -> 9000-READ-ACCT (3 chained VSAM reads) ---
    while not screen_q.empty():
        screen_q.get_nowait()
    input_q.put(InputEvent(eibaid="\x7d", fields={"ACCTSID": _ACCT_ID}))
    r5 = run_cics(
        acct,
        CicsContext(
            transid="CAVW",
            commarea=(r4.commarea or b"").ljust(400, b"\x00"),
            eibaid="\x7d",
        ),
        screen_q,
        input_q,
        context_holder=context_holder,
        result_holder=result_holder,
        max_steps=1_000_000,
    )
    screens = []
    while not screen_q.empty():
        screens.append(screen_q.get_nowait())
    assert any(
        s.get("map") == "CACTVWA" for s in screens
    ), f"turn 5 did not render CACTVWA; screens={[s.get('map') for s in screens]}"
    view = next(s for s in screens if s.get("map") == "CACTVWA")["fields"]
    # The entered account id echoes back (MOVE CC-ACCT-ID TO ACCTSIDO).
    assert (
        view.get("ACCTSID") == _ACCT_ID
    ), f"account id did not echo: ACCTSID={view.get('ACCTSID')!r}"
    # Read-through field #1 (proves xref@25 -> ACCTDAT@0 chain): account status
    # MOVE ACCT-ACTIVE-STATUS TO ACSTTUSO. FOUND-ACCT-IN-MASTER gated this MOVE.
    assert (
        view.get("ACSTTUS") == _ACCT_STATUS
    ), f"account status not rendered (acct read failed?): ACSTTUS={view.get('ACSTTUS')!r}"
    # Read-through field #2 (proves CUSTDAT@0 chain via xref CUST-ID@16): the
    # customer first/last names. FOUND-CUST-IN-MASTER gated these MOVEs.
    assert view.get("ACSFNAM") == _CUST_FIRST, (
        f"customer first name not rendered (cust read failed?): "
        f"ACSFNAM={view.get('ACSFNAM')!r}"
    )
    assert (
        view.get("ACSLNAM") == _CUST_LAST
    ), f"customer last name not rendered: ACSLNAM={view.get('ACSLNAM')!r}"
    # COACTVWC parks again pseudo-conversationally after rendering the view.
    assert r5.kind == DispatchKind.RETURN_TRANSID
    assert (r5.transid or "").strip() == "CAVW"
