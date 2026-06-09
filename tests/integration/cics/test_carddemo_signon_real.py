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
from interpreter.cics.types import DispatchKind
from interpreter.cics.dispatcher import InputEvent, CicsRegion
from interpreter.cics.bootstrap import compile_cics_program
from interpreter.cics.le_stubs import le_service_stub_sources
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
        + _ebcdic("0000000099", 10)  # CUST-EFT-ACCOUNT-ID (numeric, required by 1245)
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
    USRSEC + the three account-view datasets, plus BMS maps). Driven through a
    ``CicsRegion`` one turn at a time: routing (which program/transid runs next)
    is DEDUCED from each DispatchResult, not hardcoded per turn.

    Returns the live drive context so a caller can continue into turn 5:
    ``(acct_program, region, r4, screen_q, input_q, context_holder,
    result_holder)``.
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

    # The CSD/region configuration: which program backs each transid. This is the
    # static config the system is set up with (NOT per-turn hardcoding). The
    # region deduces the next (program, transid) from each DispatchResult.
    program_cache = {
        "COSGN00C": signon,
        "COMEN01C": menu,
        "COACTVWC": acct,
    }
    transid_to_program = {"CC00": "COSGN00C", "CM00": "COMEN01C", "CAVW": "COACTVWC"}
    # COMEN01C/COACTVWC index a commarea (CARDDEMO-COMMAREA) larger than the 100
    # bytes sign-on starts with; pad to 400 so EIBCALEN covers the menu/view
    # CDEMO-* fields the programs read. This is a genuine EIBCALEN minimum, set
    # once at the region level rather than re-padded per turn.
    region = CicsRegion(
        program_cache,
        transid_to_program,
        screen_q,
        input_q,
        context_holder=context_holder,
        result_holder=result_holder,
        max_steps=1_000_000,
        min_commarea_len=400,
    )

    # --- Turn 1: sign-on ENTER turn -> XCTL COMEN01C ---
    r1 = region.start(
        "CC00",
        commarea=b"\x00" * 100,
        input_event=InputEvent(
            eibaid="\x7d", fields={"USERID": "USER0001", "PASSWD": "PASS0001"}
        ),
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
    # After the XCTL, the transid CARRIES (same task): COMEN01C runs under CC00.
    assert region.transid == "CC00"

    # --- Turn 2: the menu program's first display renders the menu map ---
    # XCTL'd in from sign-on (same task) -> no fresh terminal input.
    while not screen_q.empty():  # drain any sign-on screen output
        screen_q.get_nowait()
    r2 = region.step()

    screens = []
    while not screen_q.empty():
        screens.append(screen_q.get_nowait())

    assert any(
        s.get("map") == "COMEN1A" for s in screens
    ), f"menu program did not render COMEN1A; screens={[s.get('map') for s in screens]}"
    menu_screen = next(s for s in screens if s.get("map") == "COMEN1A")
    # The menu header reflects the running transid/program (proves real execution).
    # TRNNAME comes from COMEN01C's own LIT-THISTRANID literal ("CM00"), NOT the
    # carried EIBTRNID (which is still CC00 from the XCTL) — so this still holds.
    assert menu_screen["fields"].get("TRNNAME") == "CM00"
    assert menu_screen["fields"].get("PGMNAME") == "COMEN01C"
    # COMEN01C parks for the next terminal action (pseudo-conversational).
    assert r2.kind == DispatchKind.RETURN_TRANSID

    # --- Turn 3: ENTER on the menu with option '01' -> XCTL to its program ---
    # The reenter flag set on turn 2 (SET CDEMO-PGM-REENTER TO TRUE) carries in
    # the commarea, so COMEN01C now takes PROCESS-ENTER-KEY instead of redisplaying.
    # Following a RETURN TRANSID -> a fresh terminal input (the menu selection).
    while not screen_q.empty():
        screen_q.get_nowait()
    r3 = region.step(input_event=InputEvent(eibaid="\x7d", fields={"OPTION": "01"}))
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
    # for an account id) then RETURN TRANSID CAVW. No VSAM read on this turn. XCTL'd
    # in -> no fresh terminal input.
    # CACTVWA uses extended attributes (DFHMDI DSATTS/MAPATTS) — the generated
    # symbolic map must carry the <field>C/P/H/V subfields the program moves into.
    while not screen_q.empty():
        screen_q.get_nowait()
    r4 = region.step()
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

    return acct, region, r4, screen_q, input_q, context_holder, result_holder


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
    acct, region, r4, screen_q, input_q, context_holder, result_holder = (
        _drive_through_turn4(tmp_path)
    )

    # --- Turn 5: account-id entry -> 9000-READ-ACCT (3 chained VSAM reads) ---
    # Following COACTVWC's RETURN TRANSID CAVW -> a fresh terminal input (the
    # account id). The region re-dispatches COACTVWC (CAVW -> COACTVWC via map).
    while not screen_q.empty():
        screen_q.get_nowait()
    r5 = region.step(
        input_event=InputEvent(eibaid="\x7d", fields={"ACCTSID": _ACCT_ID})
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


# ─────────────────────────────────────────────────────────────────────────────
# Account UPDATE flow (menu option '02' -> COACTUPC), with READ-for-UPDATE +
# REWRITE writeback. Mirrors the account-VIEW driver but routes through the
# update program. The update flow is pseudo-conversational across several turns:
#   Turn A: XCTL COACTUPC -> first display renders CACTUPA (asks for acct id).
#   Turn B: enter acct id -> 9000-READ-ACCT (3 chained reads) -> shows details.
#   Turn C: submit full (valid) field set with ONE change + ENTER -> validation
#           passes -> ACUP-CHANGES-OK-NOT-CONFIRMED -> redisplay asking confirm.
#   Turn D: PF05 confirm -> 9600-WRITE-PROCESSING -> READ UPDATE + REWRITE.
# ─────────────────────────────────────────────────────────────────────────────

_NEW_ACCT_STATUS = "N"  # change account status Y -> N (the modified field)
_DFHENTER = "\x7d"
_DFHPF5 = "\xf5"  # PF05 = confirm-and-save


def _compile_update_programs(tmp_path):
    """Compile COSGN00C + COMEN01C + COACTUPC sharing one strategy/engine.

    Returns ``(signon, menu, acctupd, screen_q, input_q, context_holder,
    result_holder, engine)``. The engine is returned so the test can read the
    stored ACCTDAT/CUSTDAT records back after the REWRITE.
    """
    from interpreter.cobol.cobol_parser import ProLeapCobolParser
    from interpreter.cobol.subprocess_runner import RealSubprocessRunner

    app = Path(_CARDDEMO_HOME)
    signon_path = app / "cbl" / "COSGN00C.cbl"
    menu_path = app / "cbl" / "COMEN01C.cbl"
    acctupd_path = app / "cbl" / "COACTUPC.cbl"
    assert acctupd_path.is_file(), f"COACTUPC not found: {acctupd_path}"

    sym_dir = tmp_path / "sym"
    generate_symbolic_copybooks(
        bms_dir=app / "bms",
        out_dir=sym_dir,
        hlasm_export_bin=HLASM_EXPORT_BIN,
        bms_copybook_gen_src=BMS_COPYBOOK_GEN_SRC,
    )
    parser = ProLeapCobolParser(
        RealSubprocessRunner(),
        JAR_PATH,
        copybook_dirs=[sym_dir, app / "cpy", app / "cpy-bms", _CICS_COPYBOOKS],
    )

    screen_q: queue.Queue = queue.Queue()
    input_q: queue.Queue = queue.Queue()
    context_holder = [None]
    result_holder: list = [None]
    engine = _usrsec_engine()
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=engine,
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(
        apply_cics_prepass(signon_path.read_text()).encode(), parser, strategy
    )
    menu = compile_cics_program(
        apply_cics_prepass(menu_path.read_text()).encode(), parser, strategy
    )
    acctupd = compile_cics_program(
        apply_cics_prepass(acctupd_path.read_text()).encode(), parser, strategy
    )
    return (
        signon,
        menu,
        acctupd,
        screen_q,
        input_q,
        context_holder,
        result_holder,
        engine,
    )


def _drive_to_coactupc(tmp_path):
    """Sign-on -> menu -> option '02' -> XCTL COACTUPC -> first display (CACTUPA).

    Returns ``(acctupd, r_first, screen_q, input_q, context_holder,
    result_holder, engine)`` parked pseudo-conversationally on CAUP.
    """
    (
        signon,
        menu,
        acctupd,
        screen_q,
        input_q,
        context_holder,
        result_holder,
        engine,
    ) = _compile_update_programs(tmp_path)

    # Region config: this run routes the menu's option '02' to COACTUPC.
    program_cache = {
        "COSGN00C": signon,
        "COMEN01C": menu,
        "COACTUPC": acctupd,
    }
    transid_to_program = {"CC00": "COSGN00C", "CM00": "COMEN01C", "CAUP": "COACTUPC"}
    region = CicsRegion(
        program_cache,
        transid_to_program,
        screen_q,
        input_q,
        context_holder=context_holder,
        result_holder=result_holder,
        max_steps=2_000_000,
        min_commarea_len=400,  # menu/update programs index a 400-byte commarea
    )

    # Turn 1: sign-on -> XCTL COMEN01C (transid carries; no input after XCTL)
    r1 = region.start(
        "CC00",
        commarea=b"\x00" * 100,
        input_event=InputEvent(
            eibaid=_DFHENTER, fields={"USERID": "USER0001", "PASSWD": "PASS0001"}
        ),
    )
    assert r1.kind == DispatchKind.XCTL and (r1.program or "").strip() == "COMEN01C"

    # Turn 2: menu first display (XCTL'd in -> no fresh input)
    while not screen_q.empty():
        screen_q.get_nowait()
    r2 = region.step()
    assert r2.kind == DispatchKind.RETURN_TRANSID

    # Turn 3: menu ENTER option '02' -> XCTL COACTUPC (fresh input after RETURN)
    while not screen_q.empty():
        screen_q.get_nowait()
    r3 = region.step(input_event=InputEvent(eibaid=_DFHENTER, fields={"OPTION": "02"}))
    assert (
        r3.kind == DispatchKind.XCTL
    ), f"menu option '02' did not XCTL (kind={r3.kind}); expected COACTUPC"
    assert (
        r3.program or ""
    ).strip() == "COACTUPC", (
        f"menu option '02' XCTL'd to {r3.program!r}, expected COACTUPC"
    )

    # Turn A: COACTUPC first display renders CACTUPA, asks for acct id (XCTL'd in).
    while not screen_q.empty():
        screen_q.get_nowait()
    r4 = region.step()
    screens = []
    while not screen_q.empty():
        screens.append(screen_q.get_nowait())
    assert any(
        s.get("map") == "CACTUPA" for s in screens
    ), f"COACTUPC did not render CACTUPA; screens={[s.get('map') for s in screens]}"
    first = next(s for s in screens if s.get("map") == "CACTUPA")
    assert first["fields"].get("TRNNAME") == "CAUP"
    assert first["fields"].get("PGMNAME") == "COACTUPC"
    assert r4.kind == DispatchKind.RETURN_TRANSID
    assert (r4.transid or "").strip() == "CAUP"
    return acctupd, region, r4, screen_q, input_q, context_holder, result_holder, engine


@covers(CobolFeature.EXEC_CICS, CobolFeature.INTRINSIC_FUNCTION)
def test_real_carddemo_account_update_first_display(tmp_path):
    """Account-update Turn A: menu option '02' -> XCTL COACTUPC -> CACTUPA."""
    _drive_to_coactupc(tmp_path)


def _drive_update_to_details(tmp_path):
    """Continue past Turn A: enter the seeded acct id (Turn B) -> 9000-READ-ACCT
    (3 chained VSAM reads) -> details rendered for edit.

    Returns ``(acctupd, r_details, screen_q, input_q, context_holder,
    result_holder, engine)`` parked on CAUP showing the fetched account.
    """
    acctupd, region, r4, screen_q, input_q, context_holder, result_holder, engine = (
        _drive_to_coactupc(tmp_path)
    )

    # Turn B: enter acct id -> ACUP-DETAILS-NOT-FETCHED path reads + shows detail.
    # Following the Turn-A RETURN TRANSID CAUP -> a fresh terminal input.
    while not screen_q.empty():
        screen_q.get_nowait()
    rB = region.step(
        input_event=InputEvent(eibaid=_DFHENTER, fields={"ACCTSID": _ACCT_ID})
    )
    screens = []
    while not screen_q.empty():
        screens.append(screen_q.get_nowait())
    assert any(
        s.get("map") == "CACTUPA" for s in screens
    ), f"Turn B did not render CACTUPA; screens={[s.get('map') for s in screens]}"
    view = next(s for s in screens if s.get("map") == "CACTUPA")["fields"]
    return (
        acctupd,
        region,
        rB,
        view,
        screen_q,
        input_q,
        context_holder,
        result_holder,
        engine,
    )


@covers(CobolFeature.EXEC_CICS, CobolFeature.INTRINSIC_FUNCTION)
def test_real_carddemo_account_update_reads_and_shows_details(tmp_path):
    """Account-update Turn B: enter acct id -> 9000-READ-ACCT (CXACAIX@25 ->
    ACCTDAT@0 -> CUSTDAT@0) -> details render for edit (status + names echo)."""
    (
        acctupd,
        region,
        rB,
        view,
        screen_q,
        input_q,
        context_holder,
        result_holder,
        engine,
    ) = _drive_update_to_details(tmp_path)
    # The entered account id echoes back.
    assert (
        view.get("ACCTSID") == _ACCT_ID
    ), f"acct id not echoed: {view.get('ACCTSID')!r}"
    # Read-through account status + customer names (proves the 3 chained reads).
    assert view.get("ACSTTUS") == _ACCT_STATUS, f"status: {view.get('ACSTTUS')!r}"
    assert view.get("ACSFNAM") == _CUST_FIRST, f"first name: {view.get('ACSFNAM')!r}"
    assert view.get("ACSLNAM") == _CUST_LAST, f"last name: {view.get('ACSLNAM')!r}"
    assert rB.kind == DispatchKind.RETURN_TRANSID
    assert (rB.transid or "").strip() == "CAUP"


def _resubmit_fields(view: dict, *, status: str) -> dict[str, str]:
    """Build the Turn-C field set: echo back every displayed (valid) value, with
    the account status changed. Phone is left blank (optional → valid) to avoid
    the area-code lookup. Customer id is read but not editable."""
    keys = [
        "ACSTNUM",
        "ACTSSN1",
        "ACTSSN2",
        "ACTSSN3",
        "DOBYEAR",
        "DOBMON",
        "DOBDAY",
        "ACSTFCO",
        "ACSFNAM",
        "ACSMNAM",
        "ACSLNAM",
        "ACSADL1",
        "ACSADL2",
        "ACSCITY",
        "ACSSTTE",
        "ACSZIPC",
        "ACSCTRY",
        "ACSGOVT",
        "ACSEFTC",
        "ACSPFLG",
        "OPNYEAR",
        "OPNMON",
        "OPNDAY",
        "EXPYEAR",
        "EXPMON",
        "EXPDAY",
        "RISYEAR",
        "RISMON",
        "RISDAY",
        "ACRDLIM",
        "ACSHLIM",
        "ACURBAL",
        "ACRCYCR",
        "ACRCYDB",
        "AADDGRP",
    ]
    fields = {k: view.get(k, "") for k in keys if view.get(k, "")}
    fields["ACCTSID"] = _ACCT_ID
    fields["ACSTTUS"] = status  # the modified field
    return fields


@covers(CobolFeature.EXEC_CICS, CobolFeature.INTRINSIC_FUNCTION)
def test_real_carddemo_account_update_rewrite(tmp_path):
    """Account-update Turns C + D: edit a field, confirm with PF05, and verify
    the REWRITE persisted to the VsamEngine.

    Turn C: resubmit the fetched (valid) field set with ACCT-ACTIVE-STATUS
        changed Y -> N + ENTER. 1200-EDIT-MAP-INPUTS validates all fields ->
        ACUP-CHANGES-OK-NOT-CONFIRMED -> redisplay asking for PF05 confirm.
    Turn D: PF05 -> ACUP-CHANGES-OK-NOT-CONFIRMED AND CCARD-AID-PFK05 ->
        9600-WRITE-PROCESSING -> READ ... UPDATE (lock) + REWRITE on ACCTDAT and
        CUSTDAT. Assert the engine's stored ACCTDAT record now has status 'N'.
    """
    (
        acctupd,
        region,
        rB,
        view,
        screen_q,
        input_q,
        context_holder,
        result_holder,
        engine,
    ) = _drive_update_to_details(tmp_path)

    # --- Turn C: submit the change (status Y->N) + ENTER ---
    # Following Turn B's RETURN TRANSID CAUP -> a fresh terminal input.
    while not screen_q.empty():
        screen_q.get_nowait()
    rC = region.step(
        input_event=InputEvent(
            eibaid=_DFHENTER, fields=_resubmit_fields(view, status=_NEW_ACCT_STATUS)
        )
    )
    screensC = []
    while not screen_q.empty():
        screensC.append(screen_q.get_nowait())
    viewC = next((s["fields"] for s in screensC if s.get("map") == "CACTUPA"), {})
    # Turn C should ask for confirmation (no validation error). The info/error
    # message tells us if validation rejected the input.
    assert rC.kind == DispatchKind.RETURN_TRANSID, (
        f"Turn C did not park (kind={rC.kind}); info={viewC.get('INFOMSG')!r} "
        f"err={viewC.get('ERRMSG')!r}"
    )

    # --- Turn D: PF05 confirm -> 9600-WRITE-PROCESSING (READ UPDATE + REWRITE) ---
    # Following Turn C's RETURN TRANSID CAUP -> a fresh terminal input (PF05).
    # COACTUPC re-RECEIVEs and re-validates the map on the confirm turn too
    # (1000-PROCESS-INPUTS runs before 2000-DECIDE-ACTION), so a real 3270 resends
    # the full screen buffer. Resend the same modified field set with PF05 — sending
    # only ACCTSID would blank ACUP-NEW-ACTIVE-STATUS and lose the change.
    while not screen_q.empty():
        screen_q.get_nowait()
    rD = region.step(
        input_event=InputEvent(
            eibaid=_DFHPF5, fields=_resubmit_fields(view, status=_NEW_ACCT_STATUS)
        )
    )
    # Verify the REWRITE persisted: read ACCTDAT back from the engine and check
    # the active-status byte (offset 11, X(1)) is now 'N'.
    record, resp = engine.read("ACCTDAT", _ACCT_ID.encode("cp037"), 11)
    assert record is not None, f"ACCTDAT record vanished after REWRITE (resp={resp})"
    status_byte = record[11:12].decode("cp037")
    assert status_byte == _NEW_ACCT_STATUS, (
        f"REWRITE did not persist status change: stored {status_byte!r}, "
        f"expected {_NEW_ACCT_STATUS!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Transaction ADD (create) flow: menu option '08' -> COTRN02C, with the
# STARTBR + READPREV TRAN-ID generation and EXEC CICS WRITE create.
#
# COTRN02C is option 8 in COMEN02Y (the regular-user main menu; "Admin Only" is
# commented out and the usertype byte is 'U'), so a regular USRSEC user reaches
# it via sign-on -> COMEN01C -> option '08' -> XCTL COTRN02C (transid CT02). It
# is pseudo-conversational:
#   Turn A: XCTL COTRN02C -> first display renders COTRN2A (asks for the new
#           transaction's fields).
#   Turn B: enter account id + all required fields + CONFIRM='Y' + ENTER ->
#           PROCESS-ENTER-KEY -> VALIDATE-INPUT-KEY-FIELDS reads CXACAIX (acct
#           -> card num), VALIDATE-INPUT-DATA-FIELDS passes, CONFIRM='Y' ->
#           ADD-TRANSACTION: MOVE HIGH-VALUES TO TRAN-ID; STARTBR + READPREV +
#           ENDBR on TRANSACT to find the highest existing id; ADD 1; build
#           TRAN-RECORD; WRITE-TRANSACT-FILE -> EXEC CICS WRITE on TRANSACT.
# The new record is read back from the engine by its generated key.
# ─────────────────────────────────────────────────────────────────────────────

# CVTRA05Y TRAN-RECORD field layout (RECLN 350): TRAN-ID X(16)@0 (the key),
# TRAN-TYPE-CD X(2)@16, TRAN-CAT-CD 9(4)@18, TRAN-SOURCE X(10)@22,
# TRAN-DESC X(100)@32, TRAN-AMT S9(9)V99@132 (11 display bytes), ...
_TRAN_RECLN = 350
_TRAN_KEYLEN = 16
# One pre-existing transaction so STARTBR(HIGH-VALUES)+READPREV finds a "last"
# id; ADD-TRANSACTION then generates the next one (id 1 -> id 2).
_SEED_TRAN_ID = "0000000000000001"
_EXPECTED_NEW_TRAN_ID = "0000000000000002"
# Field values entered on the add screen (per COTRN2A map / CVTRA05Y).
_ADD_TYPE_CD = "01"  # TTYPCD  -> TRAN-TYPE-CD  X(2)
_ADD_CAT_CD = "0005"  # TCATCD  -> TRAN-CAT-CD   9(4)
_ADD_SOURCE = "POS"  # TRNSRC  -> TRAN-SOURCE   X(10)
_ADD_DESC = "GROCERIES"  # TDESC   -> TRAN-DESC     X(100)
_ADD_AMT = "+00000123.45"  # TRNAMT (PIC X(12), -99999999.99 form)
_ADD_MID = "000000789"  # MID     -> TRAN-MERCHANT-ID 9(9)
_ADD_MNAME = "ACME STORE"  # MNAME   -> TRAN-MERCHANT-NAME
_ADD_MCITY = "ANYTOWN"  # MCITY   -> TRAN-MERCHANT-CITY
_ADD_MZIP = "90001"  # MZIP    -> TRAN-MERCHANT-ZIP
_ADD_ORIG_DT = "2024-01-15"  # TORIGDT -> TRAN-ORIG-TS
_ADD_PROC_DT = "2024-01-16"  # TPROCDT -> TRAN-PROC-TS


def _transact_seed_record() -> bytes:
    """CVTRA05Y TRAN-RECORD with TRAN-ID '0000000000000001' (key @0), the rest
    zero/space-filled. Seeds one record so READPREV can find the highest id."""
    rec = _ebcdic(_SEED_TRAN_ID, _TRAN_KEYLEN)
    return rec.ljust(_TRAN_RECLN, b"\x00")[:_TRAN_RECLN]


def _add_engine() -> VsamEngine:
    """Engine seeded with USRSEC (sign-on), CXACAIX (acct->card xref the add
    flow validates the account against) and TRANSACT (browse for last id +
    target of the WRITE). Reuses the USRSEC + xref records from the view flow."""
    usrsec_rec = (
        _ebcdic("USER0001", 8)
        + _ebcdic("First", 20)
        + _ebcdic("Last", 20)
        + _ebcdic("PASS0001", 8)
        + _ebcdic("U", 1)  # regular user -> XCTL COMEN01C
        + _ebcdic("", 23)
    )
    td = Path(tempfile.mkdtemp())
    (td / "usrsec.txt").write_bytes(usrsec_rec)
    (td / "cxacaix.txt").write_bytes(_xref_record())
    (td / "transact.txt").write_bytes(_transact_seed_record())

    engine = VsamEngine(
        FctConfig(
            datasets={
                "USRSEC": DatasetConfig(path=td / "usrsec.txt", record_length=80),
                "CXACAIX": DatasetConfig(
                    path=td / "cxacaix.txt",
                    record_length=50,
                    key_offset=25,
                    key_length=11,
                ),
                "TRANSACT": DatasetConfig(
                    path=td / "transact.txt",
                    record_length=_TRAN_RECLN,
                    key_length=_TRAN_KEYLEN,
                ),
            }
        )
    )
    engine.load_all()
    return engine


def _drive_to_cotrn02c(tmp_path):
    """Sign-on -> menu -> option '08' -> XCTL COTRN02C -> first display (COTRN2A).

    Returns ``(region, screen_q, input_q, engine)`` parked pseudo-conversationally
    on CT02 showing the empty transaction-add screen.
    """
    from interpreter.cobol.cobol_parser import ProLeapCobolParser
    from interpreter.cobol.subprocess_runner import RealSubprocessRunner

    app = Path(_CARDDEMO_HOME)
    signon_path = app / "cbl" / "COSGN00C.cbl"
    menu_path = app / "cbl" / "COMEN01C.cbl"
    tranadd_path = app / "cbl" / "COTRN02C.cbl"
    assert tranadd_path.is_file(), f"COTRN02C not found: {tranadd_path}"

    sym_dir = tmp_path / "sym"
    generate_symbolic_copybooks(
        bms_dir=app / "bms",
        out_dir=sym_dir,
        hlasm_export_bin=HLASM_EXPORT_BIN,
        bms_copybook_gen_src=BMS_COPYBOOK_GEN_SRC,
    )
    parser = ProLeapCobolParser(
        RealSubprocessRunner(),
        JAR_PATH,
        copybook_dirs=[sym_dir, app / "cpy", app / "cpy-bms", _CICS_COPYBOOKS],
    )

    screen_q: queue.Queue = queue.Queue()
    input_q: queue.Queue = queue.Queue()
    context_holder = [None]
    result_holder: list = [None]
    engine = _add_engine()
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        result_holder=result_holder,
        vsam_engine=engine,
        screen_queue=screen_q,
        input_queue=input_q,
    )

    signon = compile_cics_program(
        apply_cics_prepass(signon_path.read_text()).encode(), parser, strategy
    )
    menu = compile_cics_program(
        apply_cics_prepass(menu_path.read_text()).encode(), parser, strategy
    )
    # COTRN02C CALLs 'CSUTLDTC' to validate the Orig/Proc dates; CSUTLDTC in turn
    # CALLs the LE service "CEEDAYS" (no COBOL source). Link CSUTLDTC (resolved
    # from the CardDemo cbl/ dir) plus the CEEDAYS LE-service stub so the date
    # validation completes and the ADD-TRANSACTION WRITE path runs.
    tranadd = compile_cics_program(
        apply_cics_prepass(tranadd_path.read_text()).encode(),
        parser,
        strategy,
        program_source_dir=app / "cbl",
        extra_subprogram_sources=le_service_stub_sources(),
    )

    program_cache = {
        "COSGN00C": signon,
        "COMEN01C": menu,
        "COTRN02C": tranadd,
    }
    transid_to_program = {"CC00": "COSGN00C", "CM00": "COMEN01C", "CT02": "COTRN02C"}
    region = CicsRegion(
        program_cache,
        transid_to_program,
        screen_q,
        input_q,
        context_holder=context_holder,
        result_holder=result_holder,
        max_steps=2_000_000,
        min_commarea_len=400,
    )

    # Turn 1: sign-on -> XCTL COMEN01C (transid carries; no input after XCTL)
    r1 = region.start(
        "CC00",
        commarea=b"\x00" * 100,
        input_event=InputEvent(
            eibaid=_DFHENTER, fields={"USERID": "USER0001", "PASSWD": "PASS0001"}
        ),
    )
    assert r1.kind == DispatchKind.XCTL and (r1.program or "").strip() == "COMEN01C"

    # Turn 2: menu first display (XCTL'd in -> no fresh input)
    while not screen_q.empty():
        screen_q.get_nowait()
    r2 = region.step()
    assert r2.kind == DispatchKind.RETURN_TRANSID

    # Turn 3: menu ENTER option '08' -> XCTL COTRN02C (fresh input after RETURN)
    while not screen_q.empty():
        screen_q.get_nowait()
    r3 = region.step(input_event=InputEvent(eibaid=_DFHENTER, fields={"OPTION": "08"}))
    assert (
        r3.kind == DispatchKind.XCTL
    ), f"menu option '08' did not XCTL (kind={r3.kind}); expected COTRN02C"
    assert (
        r3.program or ""
    ).strip() == "COTRN02C", (
        f"menu option '08' XCTL'd to {r3.program!r}, expected COTRN02C"
    )

    # Turn A: COTRN02C first display renders COTRN2A (XCTL'd in -> no fresh input).
    while not screen_q.empty():
        screen_q.get_nowait()
    rA = region.step()
    screens = []
    while not screen_q.empty():
        screens.append(screen_q.get_nowait())
    assert any(
        s.get("map") == "COTRN2A" for s in screens
    ), f"COTRN02C did not render COTRN2A; screens={[s.get('map') for s in screens]}"
    first = next(s for s in screens if s.get("map") == "COTRN2A")
    assert first["fields"].get("TRNNAME") == "CT02"
    assert first["fields"].get("PGMNAME") == "COTRN02C"
    assert rA.kind == DispatchKind.RETURN_TRANSID
    assert (rA.transid or "").strip() == "CT02"
    return region, screen_q, input_q, engine


@covers(CobolFeature.EXEC_CICS, CobolFeature.INTRINSIC_FUNCTION)
def test_real_carddemo_transaction_add_first_display(tmp_path):
    """Transaction-add Turn A: menu option '08' -> XCTL COTRN02C -> COTRN2A."""
    _drive_to_cotrn02c(tmp_path)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Cross-program COBOL CALL linking (red-dragon-1bp2) is now wired through the "
        "CICS bootstrap: compile_cics_program(program_source_dir=app/'cbl', "
        "extra_subprogram_sources=le_service_stub_sources()) links CSUTLDTC and a "
        "CEEDAYS LE-service stub into COTRN02C via the project linker. NEW BLOCKER: "
        "CSUTLDTC.cbl itself fails to lower — its WS-DATE-TO-TEST / WS-DATE-FORMAT "
        "use a variable-length group: 02 Vstring-text > 03 Vstring-char PIC X OCCURS "
        "0 TO 256 DEPENDING ON Vstring-length (CSUTLDTC.cbl:25-39). build_sectioned_"
        "layout materialises the GROUP but not its OCCURS-DEPENDING-ON subordinate "
        "fields (Vstring-length / Vstring-text), so the very first paragraph statement "
        "MOVE LENGTH OF LS-DATE TO VSTRING-LENGTH OF WS-DATE-TO-TEST (CSUTLDTC.cbl:105) "
        "raises KeyError: \"Field 'VSTRING-LENGTH' not found in any DATA DIVISION "
        'section" during lowering. Everything ELSE is proven: region subprogram '
        "linking (test_region_subprogram_link.py) and the CEEDAYS date-validation stub "
        "(test_ceedays_stub.py) are green; MOVE into the RETURN-CODE special register "
        "no longer crashes. Next gap: support OCCURS ... DEPENDING ON variable-length "
        "subordinate fields in the COBOL data-division layout (build_sectioned_layout)."
    ),
)
@covers(CobolFeature.EXEC_CICS, CobolFeature.INTRINSIC_FUNCTION)
def test_real_carddemo_transaction_add_write(tmp_path):
    """Transaction-add Turn B: enter a full new transaction + CONFIRM='Y' ->
    ADD-TRANSACTION (STARTBR/READPREV/ENDBR id-generation + EXEC CICS WRITE) ->
    verify the new TRANSACT record persisted to the VsamEngine.

    The account id is validated against CXACAIX (acct -> card num) by
    VALIDATE-INPUT-KEY-FIELDS; the id-generation browses the seeded TRANSACT
    record (id ...0001) for the highest key and writes the next (id ...0002).
    The created record's key + selected fields are read back and asserted.

    Currently xfail(strict): the date-validation CALL 'CSUTLDTC' is unlinked
    (red-dragon-1bp2). The assertions below are the intended end state and will
    pass once cross-program COBOL CALL linking lands.
    """
    region, screen_q, input_q, engine = _drive_to_cotrn02c(tmp_path)

    # --- Turn B: submit the new transaction with CONFIRM='Y' + ENTER ---
    # Following Turn A's RETURN TRANSID CT02 -> a fresh terminal input.
    while not screen_q.empty():
        screen_q.get_nowait()
    rB = region.step(
        input_event=InputEvent(
            eibaid=_DFHENTER,
            fields={
                "ACTIDIN": _ACCT_ID,  # account id -> CXACAIX lookup -> card num
                "TTYPCD": _ADD_TYPE_CD,
                "TCATCD": _ADD_CAT_CD,
                "TRNSRC": _ADD_SOURCE,
                "TDESC": _ADD_DESC,
                "TRNAMT": _ADD_AMT,
                "TORIGDT": _ADD_ORIG_DT,
                "TPROCDT": _ADD_PROC_DT,
                "MID": _ADD_MID,
                "MNAME": _ADD_MNAME,
                "MCITY": _ADD_MCITY,
                "MZIP": _ADD_MZIP,
                "CONFIRM": "Y",
            },
        )
    )
    screensB = []
    while not screen_q.empty():
        screensB.append(screen_q.get_nowait())
    viewB = next((s["fields"] for s in screensB if s.get("map") == "COTRN2A"), {})

    # The created record must exist in TRANSACT under the generated key.
    record, resp = engine.read(
        "TRANSACT", _EXPECTED_NEW_TRAN_ID.encode("cp037"), _TRAN_KEYLEN
    )
    assert record is not None, (
        f"new TRANSACT record not written (resp={resp}); "
        f"screen err={viewB.get('ERRMSG')!r}"
    )
    # TRAN-ID X(16)@0 — the generated next id.
    assert (
        record[0:16].decode("cp037") == _EXPECTED_NEW_TRAN_ID
    ), f"TRAN-ID wrong: {record[0:16].decode('cp037')!r}"
    # TRAN-TYPE-CD X(2)@16, TRAN-CAT-CD 9(4)@18, TRAN-SOURCE X(10)@22.
    assert record[16:18].decode("cp037") == _ADD_TYPE_CD
    assert record[18:22].decode("cp037") == _ADD_CAT_CD
    assert record[22:32].decode("cp037").rstrip() == _ADD_SOURCE
    # TRAN-DESC X(100)@32.
    assert record[32:132].decode("cp037").rstrip() == _ADD_DESC
    # TRAN-CARD-NUM X(16)@262 came from the CXACAIX xref (XREF-CARD-NUM).
    # Offsets: TRAN-ID 16, TYPE 2, CAT 4, SOURCE 10, DESC 100, AMT 11,
    # MERCH-ID 9, MERCH-NAME 50, MERCH-CITY 50, MERCH-ZIP 10 => card num @262.
    # XREF-CARD-NUM seeded as 'CARD000000000001' (16 bytes).
    assert record[262:278].decode("cp037").rstrip() == "CARD000000000001"
    # COTRN02C parks pseudo-conversationally after the successful WRITE.
    assert rB.kind == DispatchKind.RETURN_TRANSID
    assert (rB.transid or "").strip() == "CT02"
