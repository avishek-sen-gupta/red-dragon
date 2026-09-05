"""RegionId — which of the (at most six) section buffers a field lives in."""

from __future__ import annotations

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from cobol_memory.region_id import RegionId
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    build_sectioned_layout,
)
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers

_PROBE_SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A.
           05  WS-A1  PIC X(10).
           05  WS-A2  PIC 9(5).
       01  WS-B      PIC X(4).
       PROCEDURE DIVISION.
           MOVE 'HI' TO WS-A1.
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_region_ids_are_the_six_section_buffers():
    assert {r.value for r in RegionId} == {
        "working_storage",
        "linkage",
        "local_storage",
        "file",
        "special_registers",
        "indexes",
    }


@pytest.fixture
def cobol_frontend_probe() -> MaterialisedSectionedLayout:
    parser = make_cobol_parser()
    asg = parser.parse(_PROBE_SRC)
    sectioned = build_sectioned_layout(asg)
    return MaterialisedSectionedLayout(
        working_storage=(sectioned.working_storage, Register("%ws")),
        linkage=(sectioned.linkage, Register("%lk")),
        local_storage=(sectioned.local_storage, Register("%ls")),
        file=(sectioned.file, Register("%file")),
        indexes=(sectioned.indexes, Register("%ix")),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_resolve_reports_the_owning_region(cobol_frontend_probe):
    """WORKING-STORAGE fields resolve to the WORKING_STORAGE region."""
    materialised = cobol_frontend_probe
    _fl, _reg, region = materialised.resolve_with_region("WS-A1")
    assert region is RegionId.WORKING_STORAGE
