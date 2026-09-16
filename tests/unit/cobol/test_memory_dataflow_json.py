"""JSON projection of the field graph, for graph visualisation.

``analyze_probe`` here is not shared with ``test_memory_dataflow.py`` via a
conftest fixture -- that module defines its fixture locally, and this file
mirrors just enough of it (skeleton, frontend, ``analyze_memory_dataflow``)
to drive the same probe source through the real frontend, per the task
brief's instruction to reuse probe fixtures rather than hand-build results.
"""

from __future__ import annotations

import json
import re

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
    """``via`` lists one location per contributing statement, sorted, deduped.

    Two MOVE statements on different lines now produce two genuinely
    DISTINCT locations (MOVE lowering threads ``stmt.span`` as of
    ``lower_arithmetic.py``'s span-threading), so ``via`` must contain both,
    in sorted order -- ``reach_in`` (interpreter/dataflow.py) is a
    ``set[Definition]`` whose iteration order is subject to hash
    randomisation across processes, so an unsorted ``via`` would be
    nondeterministic between runs, exactly the phantom-diff hazard a
    visualiser must not see.

    De-duplication is exercised separately, by a construction that still
    produces two contributions sharing ONE identical location string: a
    SINGLE ``MOVE WS-SRC TO WS-DST WS-DST.`` statement names its target
    field twice, so ``lower_move`` emits two ``WriteRegion`` instructions
    for ``WS-DST`` -- one per target occurrence -- both carrying the same
    statement's span. Those must still collapse into ONE ``via`` entry,
    not two copies of the same string.
    """
    # -- Two statements -> two distinct locations, sorted. --
    distinct = analyze_probe("""
           MOVE WS-SRC TO WS-DST.
           MOVE WS-SRC TO WS-DST.
    """)
    edge = next(e for e in distinct.to_json()["edges"] if e["to"] == "WS-DST")
    via = edge["via"]
    assert len(via) == 2, f"two distinct MOVEs must produce two via entries: {via}"
    assert via == sorted(via), "via must be sorted, not incidentally ordered"
    assert len(via) == len(set(via)), "via must be de-duplicated"
    assert all(
        v != "<unknown>" for v in via
    ), f"MOVE now threads real source spans, expected no <unknown>: {via}"
    # Line numbers are pinned by the fixed skeleton + probe text below (the
    # first MOVE lands on line 10, the second on line 11); columns are left
    # unpinned since they are an implementation detail of tree-sitter's node
    # boundaries, not something this test should hardcode.
    assert re.match(r"^10:\d+-10:\d+$", via[0]), via
    assert re.match(r"^11:\d+-11:\d+$", via[1]), via

    # -- One statement, same target named twice -> one shared location,
    # still collapsed to a single via entry. --
    duplicate_target = analyze_probe("""
           MOVE WS-SRC TO WS-DST WS-DST.
    """)
    dup_edge = next(
        e for e in duplicate_target.to_json()["edges"] if e["to"] == "WS-DST"
    )
    dup_via = dup_edge["via"]
    assert len(dup_via) == 1, (
        "one MOVE statement writing the same target twice must still "
        f"collapse to a single via entry: {dup_via}"
    )
    assert dup_via[0] != "<unknown>"
    assert re.match(r"^10:\d+-10:\d+$", dup_via[0]), dup_via
