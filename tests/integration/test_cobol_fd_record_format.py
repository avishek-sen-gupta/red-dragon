"""Integration: each FD's RECORDING MODE and RECORD clause reach CobolASG.file_descriptions."""

from __future__ import annotations

import os

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_parser import ProLeapCobolParser
from cobol_asg.cobol_statements import (
    FileDescription,
    NoRecordClause,
    RecordContains,
    RecordContainsRange,
    RecordVarying,
)
from cobol_asg.file_enums import RecordingMode
from cobol_asg.subprocess_runner import RealSubprocessRunner
from interpreter.cobol.features import CobolFeature
from tests.covers import FeatureStatus, covers
from tests.integration.cobol_helpers import to_fixed


@covers(CobolFeature.SECTION_FILE, status=FeatureStatus.PARTIAL)
def test_each_fd_carries_its_recording_mode_and_record_clause():
    source = to_fixed(
        [
            "IDENTIFICATION DIVISION.",
            "PROGRAM-ID. FDFORMS.",
            "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.",
            "FILE-CONTROL.",
            "    SELECT FIXED-FILE ASSIGN TO FIXDD.",
            "    SELECT SIZED-FILE ASSIGN TO SIZEDD.",
            "    SELECT RANGE-FILE ASSIGN TO RANGEDD.",
            "    SELECT VARY-FILE ASSIGN TO VARYDD.",
            "    SELECT BARE-FILE ASSIGN TO BAREDD.",
            "DATA DIVISION.",
            "FILE SECTION.",
            "FD  FIXED-FILE RECORDING MODE IS F.",
            "01  FIXED-REC PIC X(80).",
            "FD  SIZED-FILE RECORD CONTAINS 80 CHARACTERS.",
            "01  SIZED-REC PIC X(80).",
            "FD  RANGE-FILE RECORD CONTAINS 20 TO 120 CHARACTERS.",
            "01  RANGE-REC PIC X(120).",
            "FD  VARY-FILE RECORDING MODE V",
            "    RECORD IS VARYING IN SIZE FROM 10 TO 300",
            "    DEPENDING ON WS-LEN.",
            "01  VARY-REC PIC X(300).",
            "FD  BARE-FILE RECORD IS VARYING.",
            "01  BARE-REC PIC X(50).",
            "WORKING-STORAGE SECTION.",
            "01  WS-LEN PIC 9(4) COMP.",
            "PROCEDURE DIVISION.",
            "    STOP RUN.",
        ]
    )
    bridge_jar = os.environ["PROLEAP_BRIDGE_JAR"]
    asg = (
        ProLeapCobolParser(RealSubprocessRunner(), bridge_jar)
        .parse(source.encode("utf-8"))
        .first_program
    )
    expected = [
        FileDescription("FIXED-FILE", RecordingMode.F, NoRecordClause()),
        FileDescription("SIZED-FILE", RecordingMode.NOT_CODED, RecordContains(80)),
        FileDescription(
            "RANGE-FILE", RecordingMode.NOT_CODED, RecordContainsRange(20, 120)
        ),
        FileDescription("VARY-FILE", RecordingMode.V, RecordVarying(10, 300, "WS-LEN")),
        FileDescription("BARE-FILE", RecordingMode.NOT_CODED, RecordVarying(0, 0, "")),
    ]
    assert (
        asg.file_descriptions,
        CobolASG.from_dict(asg.to_dict()).file_descriptions,
    ) == (expected, expected)
