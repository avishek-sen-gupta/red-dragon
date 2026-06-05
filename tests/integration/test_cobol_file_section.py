"""Integration: a COBOL FILE SECTION parses through the ProLeap bridge and its FD
record fields land in CobolASG.file_fields and SectionedLayout.file.

LAYOUT ONLY — no runtime wiring (READ/WRITE do not yet populate the FD record), so
this asserts the layout plumbing and is tagged INFRASTRUCTURE, NOT
@covers(SECTION_FILE). SECTION_FILE coverage waits for the READ/WRITE wiring slice
(red-dragon-4q25.32)."""

from __future__ import annotations

import pytest

from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from tests.covers import covers, NotLanguageFeature
from tests.integration.cobol_helpers import JAR_PATH, JAR_AVAILABLE, to_fixed

pytestmark = pytest.mark.skipif(
    not JAR_AVAILABLE, reason="ProLeap bridge JAR not available"
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_file_section_fields_in_sectioned_layout():
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. FILEPROG.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            "    SELECT CUST-FILE ASSIGN TO CUSTDAT.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD  CUST-FILE.",
            "01  CUSTOMER-RECORD.",
            "    05  CUST-ID    PIC 9(5).",
            "    05  CUST-NAME  PIC X(20).",
            "WORKING-STORAGE SECTION.",
            '01  WS-EOF PIC X VALUE "N".',
            "PROCEDURE DIVISION.",
            "    STOP RUN.",
        ]
    )
    parser = ProLeapCobolParser(RealSubprocessRunner(), JAR_PATH)
    asg = parser.parse(source.encode("utf-8"))

    # FD record fields reached the ASG
    assert [f.name for f in asg.file_fields] == ["CUSTOMER-RECORD"]

    # ...and the SectionedLayout exposes them in its `file` layout
    layout = build_sectioned_layout(asg)
    assert layout.file.lookup_as_storage("CUST-ID") is not None
    assert layout.file.lookup_as_storage("CUST-NAME") is not None
    # WORKING-STORAGE still works and FILE fields didn't leak into it
    assert layout.working_storage.lookup_as_storage("WS-EOF") is not None
    assert layout.working_storage.lookup_as_storage("CUST-ID") is None
