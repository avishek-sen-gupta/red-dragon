"""GATED demo: a real CardDemo REWRITE / WRITE persists to the VSAM flat file.

This is the final task of VSAM file persistence. The persistence machinery is
built (``VsamEngine(config, backend=FileBackend(backing_dir))`` write-throughs
every mutation to ``<backing_dir>/<NAME>.dat`` as a raw fixed-length flat image).
These two tests prove it end to end by driving the SAME real CardDemo flows the
durable harness already exercises (``test_carddemo_signon_real.py``) — only with
a ``FileBackend`` — then reading the backing flat file off disk with
``read_flat_file`` and asserting the mutation landed there.

The driving is NOT re-derived here: the shared region/engine setup and the
turn-by-turn drivers (``_drive_rewrite`` / ``_drive_transaction_add``) are reused
from ``test_carddemo_signon_real.py`` (each now takes an optional ``backend``).

Gated exactly like the durable test (skipped unless CARDDEMO_HOME + bms-tools +
the ProLeap JAR are present). Run explicitly:

    BMS_TOOLS_HOME=~/code/bms-tools \\
        CARDDEMO_HOME=/path/to/aws-mainframe-carddemo/app \\
        poetry run python -m pytest \\
        tests/integration/cics/test_vsam_persistence.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.cics.vsam.backend import FileBackend
from interpreter.cics.vsam.format import read_flat_file
from tests.covers import covers, NotLanguageFeature
from tests.integration.cics.test_carddemo_signon_real import (
    _ACCT_ID,
    _CARDDEMO_HOME,
    _NEW_ACCT_STATUS,
    _NEW_GROUP_ID,
    _NEW_CREDIT_LIMIT,
    _NEW_CASH_LIMIT,
    _NEW_CURR_BAL,
    _NEW_CYC_CREDIT,
    _NEW_CYC_DEBIT,
    _NEW_OPEN_YEAR,
    _NEW_OPEN_MON,
    _NEW_OPEN_DAY,
    _NEW_EXP_YEAR,
    _NEW_EXP_MON,
    _NEW_EXP_DAY,
    _NEW_REISSUE_YEAR,
    _NEW_REISSUE_MON,
    _NEW_REISSUE_DAY,
    _EXPECTED_NEW_TRAN_ID,
    _ADD_TYPE_CD,
    _ADD_CAT_CD,
    _ADD_SOURCE,
    _ADD_DESC,
    _TRAN_RECLN,
    _drive_rewrite,
    _drive_transaction_add,
    _usrsec_engine,
)
from tests.integration.cobol_helpers import JAR_PATH

# Mandatory locally, skipped in CI — via the shared carddemo_e2e marker
# (see tests/integration/cics/conftest.py).
pytestmark = pytest.mark.carddemo_e2e

# ACCTDAT record layout (CVACT01Y, RECLN 300): ACCT-ID 9(11)@0 (key),
# ACCT-ACTIVE-STATUS X(1)@11. Matches _acct_record() in the durable harness.
_ACCTDAT_RECLN = 300
_ACCT_ID_OFFSET = 0
_ACCT_ID_LEN = 11
_ACCT_STATUS_OFFSET = 11


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_account_update_rewrite_persists_to_flat_file(tmp_path):
    """Real CardDemo account-update REWRITE (status 'Y'->'N') write-throughs to
    the ACCTDAT backing flat file on disk.

    Drives the SAME flow as ``test_real_carddemo_account_update_rewrite`` but
    builds the shared VsamEngine with ``FileBackend(tmp_path/'store')``. After the
    REWRITE, reads ``store/ACCTDAT.dat`` as fixed-length records, finds the record
    whose ACCT-ID (offset 0, 11 bytes) == '00000000011', and asserts its
    ACCT-ACTIVE-STATUS byte (offset 11) is now 'N' — proving the mutation is
    durable on disk, not just in the in-memory engine.
    """
    store = tmp_path / "store"
    _drive_rewrite(tmp_path, backend=FileBackend(store))

    records = read_flat_file(store / "ACCTDAT.dat", _ACCTDAT_RECLN)
    assert records, "ACCTDAT.dat backing file is empty or missing after REWRITE"

    want_key = _ACCT_ID.encode("cp037")
    match = next(
        (
            r
            for r in records
            if r[_ACCT_ID_OFFSET : _ACCT_ID_OFFSET + _ACCT_ID_LEN] == want_key
        ),
        None,
    )
    assert match is not None, (
        f"account {_ACCT_ID!r} not found in ACCTDAT.dat backing file "
        f"({len(records)} records on disk)"
    )
    status_byte = match[_ACCT_STATUS_OFFSET : _ACCT_STATUS_OFFSET + 1]
    assert status_byte == _NEW_ACCT_STATUS.encode("cp037"), (
        f"REWRITE not persisted to flat file: ACCT-ACTIVE-STATUS on disk is "
        f"{status_byte!r}, expected {_NEW_ACCT_STATUS.encode('cp037')!r}"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_transaction_add_write_persists_to_flat_file(tmp_path):
    """Real CardDemo transaction-ADD WRITE (a brand-new TRANSACT record) write-
    throughs to the TRANSACT backing flat file on disk.

    Drives the SAME flow as ``test_real_carddemo_transaction_add_write`` but
    builds the shared VsamEngine with ``FileBackend(tmp_path/'store')``. After the
    EXEC CICS WRITE, reads ``store/TRANSACT.dat`` as fixed-length records, finds
    the record whose TRAN-ID (offset 0, 16 bytes) == the generated next id, and
    asserts the seeded fields (type/cat/source/desc) the add flow set are present
    on disk — proving the created record is durable, not just in memory.
    """
    store = tmp_path / "store"
    rB, viewB, _ = _drive_transaction_add(tmp_path, backend=FileBackend(store))

    records = read_flat_file(store / "TRANSACT.dat", _TRAN_RECLN)
    assert records, (
        f"TRANSACT.dat backing file empty/missing after WRITE; "
        f"screen err={viewB.get('ERRMSG')!r}"
    )

    want_key = _EXPECTED_NEW_TRAN_ID.encode("cp037")
    match = next((r for r in records if r[0:16] == want_key), None)
    assert match is not None, (
        f"newly-written transaction {_EXPECTED_NEW_TRAN_ID!r} not found in "
        f"TRANSACT.dat backing file ({len(records)} records on disk); "
        f"screen err={viewB.get('ERRMSG')!r}"
    )
    # The fields the add flow set, read back off disk (CVTRA05Y layout):
    # TRAN-ID X(16)@0, TRAN-TYPE-CD X(2)@16, TRAN-CAT-CD 9(4)@18,
    # TRAN-SOURCE X(10)@22, TRAN-DESC X(100)@32.
    assert match[0:16].decode("cp037") == _EXPECTED_NEW_TRAN_ID
    assert match[16:18].decode("cp037") == _ADD_TYPE_CD
    assert match[18:22].decode("cp037") == _ADD_CAT_CD
    assert match[22:32].decode("cp037").rstrip() == _ADD_SOURCE
    assert match[32:132].decode("cp037").rstrip() == _ADD_DESC


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_account_update_dump_before_after(tmp_path):
    """Dump ACCTDAT before and after the account-update REWRITE.

    Reads the seeded ACCOUNT-RECORD, prints a human-readable block dump, drives
    the update flow (status 'Y'->'N'), then prints the block dump of the same
    record read back from the FileBackend-persisted flat file.
    """
    from interpreter.cics.vsam.dump import load_record_layout, render_block

    assert _CARDDEMO_HOME, "CARDDEMO_HOME must be set for this test"
    app = Path(_CARDDEMO_HOME)
    layout = load_record_layout(
        app / "cpy" / "CVACT01Y.cpy",
        "ACCOUNT-RECORD",
        JAR_PATH,
        [app / "cpy"],
    )

    acct_key = _ACCT_ID.encode("cp037")

    engine_before = _usrsec_engine()
    record_before, _ = engine_before.read("ACCTDAT", acct_key, 11)
    assert record_before is not None, "seeded ACCTDAT record not found before update"

    print("\n=== ACCTDAT before update ===")
    print(render_block(layout, [record_before]))

    engine_after = _drive_rewrite(
        tmp_path,
        # Account group
        AADDGRP=_NEW_GROUP_ID,
        # Numeric fields (display format accepted by NUMVAL-C)
        ACRDLIM=_NEW_CREDIT_LIMIT,
        ACSHLIM=_NEW_CASH_LIMIT,
        ACURBAL=_NEW_CURR_BAL,
        ACRCYCR=_NEW_CYC_CREDIT,
        ACRCYDB=_NEW_CYC_DEBIT,
        # Dates: COACTUPC receives YEAR/MON/DAY as separate BMS fields and
        # STRINGs them as "YYYY-MM-DD" into the X(10) date slot.
        OPNYEAR=_NEW_OPEN_YEAR,
        OPNMON=_NEW_OPEN_MON,
        OPNDAY=_NEW_OPEN_DAY,
        EXPYEAR=_NEW_EXP_YEAR,
        EXPMON=_NEW_EXP_MON,
        EXPDAY=_NEW_EXP_DAY,
        RISYEAR=_NEW_REISSUE_YEAR,
        RISMON=_NEW_REISSUE_MON,
        RISDAY=_NEW_REISSUE_DAY,
    )
    record_after, _ = engine_after.read("ACCTDAT", acct_key, 11)
    assert record_after is not None, "ACCTDAT record missing from engine after update"

    print("\n=== ACCTDAT after update ===")
    print(render_block(layout, [record_after]))

    # CVACT01Y offsets (confirmed from layout):
    # @11  ACCT-ACTIVE-STATUS X(1)
    # @48  ACCT-OPEN-DATE X(10)
    # @58  ACCT-EXPIRAION-DATE X(10)
    # @68  ACCT-REISSUE-DATE X(10)
    # @102 ACCT-ADDR-ZIP X(10)  — not screen-editable; COACTUPC carries from old record
    # @112 ACCT-GROUP-ID X(10)

    status_after = record_after[_ACCT_STATUS_OFFSET : _ACCT_STATUS_OFFSET + 1].decode(
        "cp037"
    )
    assert status_after == _NEW_ACCT_STATUS

    open_date_after = record_after[48:58].decode("cp037")
    assert (
        open_date_after == f"{_NEW_OPEN_YEAR}-{_NEW_OPEN_MON}-{_NEW_OPEN_DAY}"
    ), f"ACCT-OPEN-DATE not updated: got {open_date_after!r}"

    exp_date_after = record_after[58:68].decode("cp037")
    assert (
        exp_date_after == f"{_NEW_EXP_YEAR}-{_NEW_EXP_MON}-{_NEW_EXP_DAY}"
    ), f"ACCT-EXPIRAION-DATE not updated: got {exp_date_after!r}"

    reissue_date_after = record_after[68:78].decode("cp037")
    assert reissue_date_after == (
        f"{_NEW_REISSUE_YEAR}-{_NEW_REISSUE_MON}-{_NEW_REISSUE_DAY}"
    ), f"ACCT-REISSUE-DATE not updated: got {reissue_date_after!r}"

    addr_zip_after = record_after[102:112].decode("cp037").rstrip()
    assert (
        addr_zip_after == "12345"
    ), f"ACCT-ADDR-ZIP should be carried from seeded record, got {addr_zip_after!r}"

    group_id_after = record_after[112:122].decode("cp037").rstrip()
    assert (
        group_id_after == _NEW_GROUP_ID
    ), f"ACCT-GROUP-ID not updated: expected {_NEW_GROUP_ID!r}, got {group_id_after!r}"
