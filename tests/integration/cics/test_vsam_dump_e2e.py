"""Gated e2e: a real CardDemo REWRITE, then decode the backing .dat via the dump CLI.

Proves the whole copybook-driven dump pipeline end to end. Drives the SAME real
CardDemo account-update REWRITE the durable harness exercises
(``test_carddemo_signon_real._drive_rewrite``) but through a ``FileBackend`` that
write-throughs every mutation to ``<store>/ACCTDAT.dat`` as a fixed-length flat
image. Then loads the real ACCOUNT copybook (``CVACT01Y.cpy``) into a DataLayout,
reads the backing flat file, decodes each record via the dump module, finds the
rewritten account (ACCT-ID 00000000011) and asserts ACCT-ACTIVE-STATUS == "N".

Gated exactly like ``test_vsam_persistence.py`` (skipped unless CARDDEMO_HOME +
bms-tools + the ProLeap JAR are present). Run explicitly:

    BMS_TOOLS_HOME=~/code/bms-tools \\
        CARDDEMO_HOME=/path/to/aws-mainframe-carddemo/app \\
        poetry run python -m pytest \\
        tests/integration/cics/test_vsam_dump_e2e.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

# Reuse the persistence test's gate (CARDDEMO_HOME + bms-tools + ProLeap JAR).
from tests.integration.cics.test_vsam_persistence import (  # noqa: F401
    pytestmark,  # the skipif gate
)
from tests.integration.cics.test_carddemo_signon_real import (
    _ACCT_ID,
    _NEW_ACCT_STATUS,
    _drive_rewrite,
)
from tests.integration.cobol_helpers import JAR_PATH
from interpreter.cics.vsam.backend import FileBackend
from interpreter.cics.vsam.dump import decode_record, load_record_layout
from interpreter.cics.vsam.format import read_flat_file
from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dump_decodes_rewritten_acctdat_status_n(tmp_path):
    """Decode the REWRITE off disk via the copybook-driven dump module.

    ACCT-ID is ``PIC 9(11)`` so the dump decodes it to the integer 11; match by
    numeric value (the seeded/rewritten key from the durable harness) rather than
    the zero-padded string. ACCT-ACTIVE-STATUS is ``PIC X(01)`` and must decode to
    "N" — the value the REWRITE flow set (Y -> N).
    """
    backing = tmp_path / "store"
    _drive_rewrite(tmp_path, backend=FileBackend(backing))

    # Locate the real CardDemo ACCOUNT copybook (the one ACCTDAT records use).
    carddemo = Path(os.environ["CARDDEMO_HOME"])
    copybook = next(carddemo.rglob("CVACT01Y.cpy"))
    # The ProLeap bridge JAR (the gate's JAR_AVAILABLE keys off this same path,
    # defaulting to the in-tree build when PROLEAP_BRIDGE_JAR is unset).
    layout = load_record_layout(copybook, None, JAR_PATH, [])
    records = read_flat_file(backing / "ACCTDAT.dat", layout.total_bytes)
    assert records, "ACCTDAT.dat backing file is empty or missing after REWRITE"

    decoded = [decode_record(layout, r) for r in records]

    want_id = int(_ACCT_ID)
    target = [d for d in decoded if int(d["ACCT-ID"]) == want_id]
    assert target, (
        f"rewritten account {_ACCT_ID!r} not found in dumped records "
        f"({len(decoded)} records decoded off disk)"
    )
    assert target[0]["ACCT-ACTIVE-STATUS"] == _NEW_ACCT_STATUS, (
        f"REWRITE not reflected in dumped record: ACCT-ACTIVE-STATUS is "
        f"{target[0]['ACCT-ACTIVE-STATUS']!r}, expected {_NEW_ACCT_STATUS!r}"
    )
