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

import os

import pytest

from interpreter.cics.vsam.backend import FileBackend
from interpreter.cics.vsam.format import read_flat_file
from tests.covers import covers, NotLanguageFeature
from tests.integration.cics.bms_tools_helpers import BMS_TOOLS_AVAILABLE
from tests.integration.cobol_helpers import JAR_AVAILABLE
from tests.integration.cics.test_carddemo_signon_real import (
    _ACCT_ID,
    _NEW_ACCT_STATUS,
    _EXPECTED_NEW_TRAN_ID,
    _ADD_TYPE_CD,
    _ADD_CAT_CD,
    _ADD_SOURCE,
    _ADD_DESC,
    _TRAN_RECLN,
    _drive_rewrite,
    _drive_transaction_add,
)

_CARDDEMO_HOME = os.environ.get("CARDDEMO_HOME")

pytestmark = pytest.mark.skipif(
    not _CARDDEMO_HOME or not JAR_AVAILABLE or not BMS_TOOLS_AVAILABLE,
    reason="manual: set CARDDEMO_HOME + BMS_TOOLS_HOME (built hlasm_export) + ProLeap JAR",
)

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
