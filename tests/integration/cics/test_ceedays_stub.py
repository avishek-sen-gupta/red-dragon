"""Integration (JAR-gated): the CEEDAYS LE-service stub validates dates.

CSUTLDTC.cbl CALLs the IBM Language Environment service CEEDAYS to validate a
date; there is no COBOL source for CEEDAYS, so we supply a stub
(``interpreter.cics.le_stubs.CEEDAYS_STUB_SOURCE``). These tests drive a tiny
COBOL caller that mirrors CSUTLDTC's CALL shape (a Vstring date + a feedback
token) and assert the feedback severity: 0 for a valid Gregorian date, nonzero
for an invalid one. The stub is linked like any other CALLed subprogram via the
project linker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.cobol.features import CobolFeature
from interpreter.cics.le_stubs import CEEDAYS_STUB_SOURCE
from interpreter.project.compiler import compile_directory
from interpreter.run import run_linked, EntryPoint
from interpreter.var_name import VarName
from interpreter.field_name import FieldName
from interpreter.address import Address
from tests.covers import covers
from tests.integration.cobol_helpers import JAR_AVAILABLE

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)


# Caller mirrors CSUTLDTC's CALL: a Vstring date (S9(4) BINARY length + 10-char
# text) and a feedback token. After the CALL it copies the severity halfword
# into a plain PIC 9(4) field WS-SEV (exactly as CSUTLDTC does), so the test can
# read back '0000' for valid / nonzero for invalid from the WS region.
def _caller_src(date_text: str) -> str:
    return f"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DRIVER.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SEV          PIC 9(4) VALUE 9999.
       01 WS-DATE-VS.
          05 WS-DATE-LEN   PIC S9(4) BINARY VALUE 10.
          05 WS-DATE-TXT   PIC X(256).
       01 WS-FMT-VS.
          05 WS-FMT-LEN    PIC S9(4) BINARY VALUE 10.
          05 WS-FMT-TXT    PIC X(256).
       01 WS-LILIAN        PIC S9(9) BINARY VALUE 0.
       01 WS-FEEDBACK.
          05 WS-FB-SEV     PIC S9(4) BINARY VALUE 0.
          05 WS-FB-MSG     PIC S9(4) BINARY VALUE 0.
          05 FILLER        PIC X(8).
       PROCEDURE DIVISION.
           MOVE '{date_text}' TO WS-DATE-TXT.
           MOVE 'YYYY-MM-DD' TO WS-FMT-TXT.
           CALL 'CEEDAYS' USING WS-DATE-VS WS-FMT-VS
                                WS-LILIAN WS-FEEDBACK.
           MOVE WS-FB-SEV TO WS-SEV.
           STOP RUN.
"""


def _run_and_read_sev(tmp_path: Path, date_text: str) -> int:
    """Compile DRIVER + the CEEDAYS stub, run, and return WS-SEV (the severity)."""
    (tmp_path / "DRIVER.cbl").write_text(_caller_src(date_text))
    (tmp_path / "CEEDAYS.cbl").write_text(CEEDAYS_STUB_SOURCE)

    linked = compile_directory(tmp_path, Language.COBOL)
    vm = run_linked(
        linked,
        EntryPoint.function(
            lambda r: str(r.label).endswith("func_driver_0")
            and "init_params" not in str(r.label)
        ),
        max_steps=200_000,
    )

    # Read WS-SEV (offset 0, 4 zoned-decimal bytes) from DRIVER's WS region.
    for frame in reversed(vm.call_stack):
        if VarName("__prog_DRIVER") in frame.local_vars:
            ptr = frame.local_vars[VarName("__prog_DRIVER")].value
            base = getattr(ptr, "base", ptr)
            ws_handle = vm.heap_get(base).fields[FieldName("ws_handle")].value
            region = vm.region_get(Address(ws_handle))
            assert region is not None, "DRIVER WS region missing"
            return int(region[0:4].decode("cp037"))
    raise AssertionError("DRIVER singleton not found in VM state")


@covers(CobolFeature.CALL_USING, CobolFeature.INTRINSIC_FUNCTION)
def test_ceedays_valid_date_severity_zero(tmp_path):
    """A valid Gregorian date (2024-01-15) yields feedback severity 0."""
    assert _run_and_read_sev(tmp_path, "2024-01-15") == 0


@covers(CobolFeature.CALL_USING, CobolFeature.INTRINSIC_FUNCTION)
def test_ceedays_leap_day_valid(tmp_path):
    """2024-02-29 is valid (2024 is a leap year) → severity 0."""
    assert _run_and_read_sev(tmp_path, "2024-02-29") == 0


@covers(CobolFeature.CALL_USING, CobolFeature.INTRINSIC_FUNCTION)
def test_ceedays_invalid_month_severity_nonzero(tmp_path):
    """Month 13 is invalid → nonzero severity (drives the caller's error path)."""
    assert _run_and_read_sev(tmp_path, "2024-13-15") != 0


@covers(CobolFeature.CALL_USING, CobolFeature.INTRINSIC_FUNCTION)
def test_ceedays_non_leap_day_invalid(tmp_path):
    """2023-02-29 is invalid (2023 is not a leap year) → nonzero severity."""
    assert _run_and_read_sev(tmp_path, "2023-02-29") != 0


@covers(CobolFeature.CALL_USING, CobolFeature.INTRINSIC_FUNCTION)
def test_ceedays_non_numeric_date_invalid(tmp_path):
    """A non-numeric date component → nonzero severity."""
    assert _run_and_read_sev(tmp_path, "20XX-01-15") != 0
