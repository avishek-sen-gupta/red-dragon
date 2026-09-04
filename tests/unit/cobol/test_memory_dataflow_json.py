"""JSON projection of the field graph, for graph visualisation.

``analyze_probe`` here is not shared with ``test_memory_dataflow.py`` via a
conftest fixture -- that module defines its fixture locally, and this file
mirrors just enough of it (skeleton, frontend, ``analyze_memory_dataflow``)
to drive the same probe source through the real frontend, per the task
brief's instruction to reuse probe fixtures rather than hand-build results.
"""

from __future__ import annotations

import json

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cfg import build_cfg
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.memory_dataflow import (
    MemoryDataflowResult,
    analyze_memory_dataflow,
)
from interpreter.cobol.memory_effects import CollectingRecorder
from tests.covers import NotLanguageFeature, covers

_SKELETON = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-SRC       PIC X(3).
       01  WS-DST       PIC X(3).
       PROCEDURE DIVISION.
       MAIN-PARA.
%s
           STOP RUN.
"""


def _analyze(statements: str) -> MemoryDataflowResult:
    recorder = CollectingRecorder()
    frontend = CobolFrontend(make_cobol_parser(), recorder=recorder)
    ir = frontend.lower((_SKELETON % statements).encode("utf-8"))
    assert recorder.effects, "the lowering recorded no memory effects at all"
    cfg = build_cfg(ir)
    return analyze_memory_dataflow(cfg, recorder.effects)


@pytest.fixture(scope="module")
def analyze_probe():
    """Splice statements into the fixed skeleton and analyse the result."""
    return _analyze


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_edges_point_along_data_flow(analyze_probe):
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
    """)
    doc = result.to_json()
    assert {"from": "WS-SRC", "to": "WS-DST"} in [
        {"from": e["from"], "to": e["to"]} for e in doc["edges"]
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_nodes_list_every_field_mentioned(analyze_probe):
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
    """)
    doc = result.to_json()
    assert {"WS-SRC", "WS-DST"} <= set(doc["nodes"])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_output_is_json_serialisable(analyze_probe):
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
    """)
    json.dumps(result.to_json())  # must not raise


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_edges_carry_via_source_locations(analyze_probe):
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
    """)
    edge = next(e for e in result.to_json()["edges"] if e["to"] == "WS-DST")
    assert edge["via"], "an edge must say which statements produced it"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_via_is_sorted_and_deduplicated_across_multiple_statements(analyze_probe):
    """Two MOVEs feed the same edge -> via must not depend on set order.

    ``reach_in`` (interpreter/dataflow.py) is a ``set[Definition]`` whose
    iteration order is subject to hash randomisation across processes, so a
    ``via`` list built without sorting would be nondeterministic between
    runs -- exactly the phantom-diff hazard a visualiser must not see.

    NOTE: the COBOL frontend currently records ``NO_SOURCE_LOCATION`` (which
    stringifies to ``"<unknown>"``) on every ``WriteRegion``/``LoadRegion``
    it emits, so both MOVEs below contribute the identical location string.
    That is a pre-existing gap in the frontend's location threading, out of
    scope for this additive task -- but it still exercises de-duplication
    directly: two contributing statements must collapse to ONE ``via``
    entry, not two copies of the same string. Sortedness is asserted
    generally (``via == sorted(via)``), which holds vacuously for a
    single-element list; a genuine multi-*distinct*-location regression test
    needs the underlying location-threading gap fixed first.
    """
    result = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
           MOVE WS-SRC TO WS-DST.
    """)
    edge = next(e for e in result.to_json()["edges"] if e["to"] == "WS-DST")
    via = edge["via"]
    assert via == ["<unknown>"], (
        "two statements contributing the identical location string must "
        "collapse to one de-duplicated via entry"
    )
    assert via == sorted(via), "via must be sorted, not incidentally ordered"
    assert len(via) == len(set(via)), "via must be de-duplicated"
