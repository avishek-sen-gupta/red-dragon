"""Field-level dependency graph over COBOL memory.

These tests drive REAL COBOL source through the whole frontend (parse →
lower → CFG) with a ``CollectingRecorder`` attached, then ask
``analyze_memory_dataflow`` which field feeds which. Nothing here hand-builds
a ``FieldExtent`` or a CFG: the point of the analysis is that byte-range
aliasing is derived from the lowering, so a probe that bypassed the lowering
would prove nothing.

Two groups of tests live here and they mean opposite things:

* the behavioural tests assert edges that MUST exist — a missing one is a
  silently dropped dependency, the exact failure this work exists to prevent;
* the characterization tests assert edges that are known to be SPURIOUS.
  They are over-approximations we have deliberately accepted, written down so
  their scope is visible and tracked. Do not "fix" them.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cfg import build_cfg
from interpreter.cobol.cobol_frontend import CobolFrontend
from cobol_memory.field_extent import FieldExtent
from interpreter.cobol.memory_dataflow import (
    MemoryAccess,
    MemoryDataflowResult,
    analyze_memory_dataflow,
    build_def_use_chains,
    rewrite_cfg,
)
from interpreter.cobol.memory_effects import CollectingRecorder
from interpreter.dataflow import DefUseLink
from tests.covers import NotLanguageFeature, covers

# WS-BASE / WS-ALIAS overlap by REDEFINES. WS-REC and WS-REC2 are two
# unrelated 01 records: nothing in any probe writes one from the other, so an
# edge between their children can only come from the analysis mushing them
# together.
_SKELETON = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-SRC       PIC X(3).
       01  WS-DST       PIC X(3).
       01  WS-OTHER     PIC X(3).
       01  WS-IDX       PIC 9(4).
       01  WS-REC.
           05  WS-NAME  PIC X(3).
           05  WS-TAIL  PIC X(2).
       01  WS-REC2.
           05  WS-P     PIC X(3).
           05  WS-Q     PIC X(2).
       01  WS-BASE      PIC X(6).
       01  WS-ALIAS REDEFINES WS-BASE.
           05  WS-A1    PIC X(3).
           05  WS-A2    PIC X(3).
       01  WS-TAB.
           05  WS-QTY   OCCURS 10 TIMES PIC X(3).
       PROCEDURE DIVISION.
       MAIN-PARA.
%s
           STOP RUN.
"""

_PARAGRAPH_PROBE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-AMT        PIC X(3).
       01  WS-FEE        PIC X(3).
       01  WS-WORK       PIC X(3).
       01  WS-FIRST-OUT  PIC X(3).
       01  WS-SECOND-OUT PIC X(3).
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM 1000-CALC.
           PERFORM 9000-FORMAT-FIRST.
           PERFORM 2000-FEES.
           PERFORM 9000-FORMAT-SECOND.
           STOP RUN.
       1000-CALC.
           MOVE WS-AMT TO WS-WORK.
       2000-FEES.
           MOVE WS-FEE TO WS-WORK.
       9000-FORMAT-FIRST.
           MOVE WS-WORK TO WS-FIRST-OUT.
       9000-FORMAT-SECOND.
           MOVE WS-WORK TO WS-SECOND-OUT.
"""


@dataclass
class _Analysed:
    """Both layers of the answer: the flow-sensitive chains and the graphs."""

    result: MemoryDataflowResult
    chains: list[DefUseLink]


def _analyze(source: str) -> _Analysed:
    recorder = CollectingRecorder()
    frontend = CobolFrontend(make_cobol_parser(), recorder=recorder)
    ir = frontend.lower(source.encode("utf-8"))
    assert recorder.effects, "the lowering recorded no memory effects at all"
    cfg = build_cfg(ir)
    return _Analysed(
        result=analyze_memory_dataflow(cfg, recorder.effects),
        chains=build_def_use_chains(cfg, recorder.effects),
    )


_CACHE: dict[str, _Analysed] = {}


def _probe(statements: str) -> _Analysed:
    if statements not in _CACHE:
        _CACHE[statements] = _analyze(_SKELETON % statements)
    return _CACHE[statements]


@pytest.fixture(scope="module")
def analyze_probe():
    """Splice statements into the fixed skeleton and analyse the result."""

    def run(statements: str) -> MemoryDataflowResult:
        return _probe(statements).result

    return run


@pytest.fixture(scope="module")
def probe_chains():
    """The same probe, answered at the flow-sensitive def-use level."""

    def run(statements: str) -> list[DefUseLink]:
        return _probe(statements).chains

    return run


@pytest.fixture(scope="module")
def paragraph_probe() -> _Analysed:
    return _analyze(_PARAGRAPH_PROBE)


# ── Edges that must exist ──────────────────────────────────────────


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_value_flows_between_fields(analyze_probe):
    """MOVE WS-SRC TO WS-DST makes WS-DST depend on WS-SRC."""
    result = analyze_probe("           MOVE WS-SRC TO WS-DST.")
    assert "WS-SRC" in result.field_graph["WS-DST"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_group_write_reaches_every_child(analyze_probe):
    """MOVE to a group must define all children by range subsumption.

    Nothing writes WS-NAME by name. The only way WS-DST can depend on WS-SRC
    is if the write of the GROUP WS-REC is recognised as a definition of the
    child WS-NAME that the second statement reads.
    """
    result = analyze_probe(
        "           MOVE WS-SRC TO WS-REC.\n           MOVE WS-NAME TO WS-DST."
    )
    assert "WS-SRC" in result.field_graph["WS-DST"]


_CROSS_BLOCK_GROUP = (
    "           MOVE WS-SRC TO WS-REC.\n"
    "           IF WS-IDX = 1\n"
    "               MOVE WS-NAME TO WS-DST\n"
    "           END-IF."
)

_CROSS_BLOCK_REDEFINES = (
    "           MOVE WS-SRC TO WS-BASE.\n"
    "           IF WS-IDX = 1\n"
    "               MOVE WS-A1 TO WS-DST\n"
    "           END-IF."
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_rewritten_cfg_keeps_every_control_flow_edge():
    """The rewrite is a per-instruction substitution and must not touch the CFG.

    Re-deriving the graph with ``build_cfg`` over a flattened block list loses
    every edge: ``build_cfg`` strips the ``Label_`` from each block's
    instruction list, so a re-flattened stream has no labels at all, every
    block is renamed ``__block_N``, and the ``if target in cfg.blocks`` guard
    on edge wiring never fires. ``reach_in`` is then empty everywhere and the
    analysis silently degenerates to intra-block. Asserted structurally, not
    just through its symptoms, because the symptoms are invisible.
    """
    recorder = CollectingRecorder()
    frontend = CobolFrontend(make_cobol_parser(), recorder=recorder)
    original = build_cfg(frontend.lower((_SKELETON % _CROSS_BLOCK_GROUP).encode()))
    rewritten = rewrite_cfg(original, recorder.effects)

    assert list(rewritten.blocks) == list(original.blocks)
    assert rewritten.entry == original.entry
    original_edges = sum(len(b.successors) for b in original.blocks.values())
    assert original_edges > 0, "the probe produced no control flow to preserve"

    substituted = 0
    for label, block in original.blocks.items():
        new_block = rewritten.blocks[label]
        # Every original edge is still there. The rewrite may ADD edges (the
        # PERFORM returns build_cfg cannot wire), so this is containment, not
        # equality — and the added edges have their own test.
        assert set(block.successors) <= set(new_block.successors)
        assert set(block.predecessors) <= set(new_block.predecessors)
        assert len(new_block.instructions) == len(block.instructions)
        for old_inst, new_inst in zip(block.instructions, new_block.instructions):
            if isinstance(new_inst, MemoryAccess):
                substituted += 1
                assert new_inst.origin is old_inst
            else:
                # Not merely the same shape: the identical object. Anything
                # without a recorded effect must pass through untouched.
                assert new_inst is old_inst
    assert substituted > 0, "no region access was substituted; the probe is inert"


_PERFORM_FLOW_PROBE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-A  PIC X(3).
       01  WS-B  PIC X(3).
       01  WS-C  PIC X(3).
       01  WS-D  PIC X(3).
       01  WS-E  PIC X(3).
       01  WS-F  PIC X(3).
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-A TO WS-B.
           PERFORM 1000-SUB.
           MOVE WS-B TO WS-C.
           MOVE WS-E TO WS-F.
           STOP RUN.
       1000-SUB.
           MOVE WS-D TO WS-E.
"""


@pytest.fixture(scope="module")
def perform_flow_probe() -> _Analysed:
    return _analyze(_PERFORM_FLOW_PROBE)


def _defs_reaching_reads_after_a_perform(chains, field_name: str) -> set[str]:
    """Blocks defining ``field_name`` for reads sited at a PERFORM return."""
    return {
        str(link.definition.block_label)
        for link in chains
        if isinstance(link.use.variable, FieldExtent)
        and link.use.variable.field_name == field_name
        and str(link.use.block_label).startswith("perform_return")
        and isinstance(link.definition.variable, FieldExtent)
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_perform_return_block_is_reachable(perform_flow_probe):
    """A PERFORM's return point must have a predecessor.

    ``build_cfg`` cannot wire it: a paragraph ends in RESUME_CONTINUATION
    whose target is dynamic, so it gets a fall-through edge and nothing else,
    and every ``perform_return_N`` block is left with ZERO predecessors. The
    driver paragraph is then severed at each PERFORM — no definition made
    before one reaches anything after it, and the block holding everything
    after the LAST perform (including STOP RUN) is unreachable outright.

    ``rewrite_cfg`` reconnects them by matching each RESUME_CONTINUATION's
    name against the SET_CONTINUATIONs that bind it.
    """
    recorder = CollectingRecorder()
    frontend = CobolFrontend(make_cobol_parser(), recorder=recorder)
    original = build_cfg(frontend.lower(_PERFORM_FLOW_PROBE.encode()))
    rewritten = rewrite_cfg(original, recorder.effects)

    returns = [
        label for label in rewritten.blocks if str(label).startswith("perform_return")
    ]
    assert returns, "the probe contains no PERFORM; this test would be vacuous"
    orphans = [
        str(label) for label in returns if not rewritten.blocks[label].predecessors
    ]
    assert orphans == [], f"PERFORM return points left unreachable: {orphans}"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_definition_before_a_perform_reaches_a_read_after_it(perform_flow_probe):
    """WS-B is written before the PERFORM and read after it. Nothing in
    1000-SUB touches WS-B, so the definition must survive across the call."""
    assert _defs_reaching_reads_after_a_perform(perform_flow_probe.chains, "WS-B") == {
        "para_MAIN-PARA"
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_definition_inside_a_performed_paragraph_reaches_the_return_point(
    perform_flow_probe,
):
    """WS-E is written only inside 1000-SUB and read only after the PERFORM,
    so the edge exists only if the return point is wired to the paragraph."""
    assert _defs_reaching_reads_after_a_perform(perform_flow_probe.chains, "WS-E") == {
        "para_1000-SUB"
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_values_cross_a_perform_in_the_field_graph(perform_flow_probe):
    """The same two flows, as a reader of the report would see them."""
    assert "WS-A" in perform_flow_probe.result.field_graph["WS-C"]
    assert "WS-D" in perform_flow_probe.result.field_graph["WS-F"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_group_write_reaches_a_child_read_in_another_block(analyze_probe):
    """The aliasing case that only works if reach_in survives the rewrite.

    Nothing writes WS-NAME by name, and the read sits inside an IF, so the
    definition of the group must cross a block boundary to reach it. With the
    control-flow edges lost this edge simply disappears — no error, no
    warning, just a missing dependency in the report.
    """
    deps = analyze_probe(_CROSS_BLOCK_GROUP).field_graph["WS-DST"]
    assert "WS-SRC" in deps, "the group definition did not cross the block boundary"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_redefines_overlap_survives_a_block_boundary(analyze_probe):
    """The same check where the overlap comes from REDEFINES rather than
    containment: WS-A1 and WS-BASE share bytes and share no declaration."""
    deps = analyze_probe(_CROSS_BLOCK_REDEFINES).field_graph["WS-DST"]
    assert "WS-SRC" in deps, "the redefines alias did not cross the block boundary"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_child_write_reaches_a_later_group_read(analyze_probe):
    """The containment relation must work in the other direction too."""
    result = analyze_probe(
        "           MOVE WS-SRC TO WS-NAME.\n           MOVE WS-REC TO WS-DST."
    )
    assert "WS-SRC" in result.field_graph["WS-DST"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_redefines_overlap_creates_an_edge(analyze_probe):
    """WS-A1 redefines the first three bytes of WS-BASE, so writing WS-BASE
    defines WS-A1 without either name appearing in the other's declaration."""
    result = analyze_probe(
        "           MOVE WS-SRC TO WS-BASE.\n           MOVE WS-A1 TO WS-DST."
    )
    assert "WS-SRC" in result.field_graph["WS-DST"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_partial_write_does_not_shadow_the_definition_it_overlaps(analyze_probe):
    """Both definitions of WS-REC's bytes must reach the group read.

    The shared ``extract_def_use_chains`` shadows by dict identity: the read
    of WS-REC finds an exact key from statement 1, links only that, and never
    looks at statement 2's write of the child. WS-OTHER's edge would be gone.
    Handled by the memory analysis' own chain extraction, which keeps local
    definitions as a list and removes only what a new write ``must_cover``s.
    """
    result = analyze_probe(
        "           MOVE WS-SRC TO WS-REC.\n"
        "           MOVE WS-OTHER TO WS-NAME.\n"
        "           MOVE WS-REC TO WS-DST."
    )
    deps = result.field_graph["WS-DST"]
    assert "WS-OTHER" in deps, "the partial write of the child was shadowed away"
    assert "WS-SRC" in deps, "the group write it only partly overwrote"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_partial_local_write_still_admits_the_incoming_definition(analyze_probe):
    """The cross-block half of the same rule.

    Inside the IF, the only local definition is the three-byte WS-NAME. It
    may_alias the read of WS-REC but cannot must_cover it, so the definition
    arriving from the predecessor block must still be matched — a partial
    write shadows only what it covers.
    """
    result = analyze_probe(
        "           MOVE WS-SRC TO WS-REC.\n"
        "           IF WS-IDX = 1\n"
        "               MOVE WS-OTHER TO WS-NAME\n"
        "               MOVE WS-REC TO WS-DST\n"
        "           END-IF."
    )
    deps = result.field_graph["WS-DST"]
    assert "WS-OTHER" in deps, "the local partial write"
    assert "WS-SRC" in deps, "the incoming definition it did not cover"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_edges_carry_the_source_locations_that_produced_them(analyze_probe):
    result = analyze_probe("           MOVE WS-SRC TO WS-DST.")
    assert result.edge_locations[("WS-SRC", "WS-DST")]


# ── Edges that must NOT exist (the anti-mush checks) ───────────────


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_disjoint_records_do_not_create_edges(analyze_probe):
    """WS-OTHER neither overlaps nor feeds WS-DST, so no edge."""
    result = analyze_probe("           MOVE WS-SRC TO WS-DST.")
    assert "WS-OTHER" not in result.field_graph.get("WS-DST", set())


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_two_unrelated_records_stay_unconnected(analyze_probe):
    """The real anti-mush check: two live records with no data path between
    them. Both are written in the same program, from the same source field —
    that shared source is the only thing they may have in common. If a child
    of one shows up as a dependency of a child of the other, the graph is
    over-connected and the whole report is worthless."""
    result = analyze_probe(
        "           MOVE WS-SRC TO WS-NAME.\n           MOVE WS-SRC TO WS-P."
    )
    # Hard equality, not `not in`: `.get(..., set())` would let an EMPTY graph
    # satisfy every negative assertion, and a test that passes when the
    # analysis produces nothing is not an anti-mush test.
    assert result.field_graph["WS-NAME"] == {"WS-SRC"}
    assert result.field_graph["WS-P"] == {"WS-SRC"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_field_never_touched_by_the_program_has_no_edges(analyze_probe):
    result = analyze_probe("           MOVE WS-SRC TO WS-DST.")
    assert "WS-Q" not in result.field_graph.get("WS-DST", set())


# ── Accepted imprecision, asserted so its scope stays visible ──────


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_computed_subscript_write_does_not_kill(analyze_probe):
    """A clamped write may-overlaps but cannot must-cover, so the earlier
    definition survives alongside it. Over-approximating by design: the read
    of WS-QTY(1) could see either value, and the graph says so."""
    result = analyze_probe(
        "           MOVE WS-SRC TO WS-QTY(1).\n"
        "           MOVE WS-OTHER TO WS-QTY(WS-IDX).\n"
        "           MOVE WS-QTY(1) TO WS-DST."
    )
    deps = result.field_graph["WS-DST"]
    assert "WS-SRC" in deps, "surviving exact definition"
    assert "WS-OTHER" in deps, "clamped write cannot kill, so it also reaches"


_TWO_WRITES = (
    "           MOVE WS-SRC TO WS-DST.\n"
    "           MOVE WS-OTHER TO WS-DST.\n"
    "           MOVE WS-DST TO WS-NAME."
)


def _defs_reaching_reads_of(chains, field_name: str) -> list[DefUseLink]:
    return [
        link
        for link in chains
        if isinstance(link.use.variable, FieldExtent)
        and link.use.variable.field_name == field_name
        and isinstance(link.definition.variable, FieldExtent)
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_exact_write_kills_the_definition_before_it(probe_chains):
    """The other half of the clamped rule, without which it is vacuous.

    WS-DST is written twice with EXACT extents, so the second must_covers the
    first and the first must NOT survive to the read. Asserted on the def-use
    chains rather than the graph because that is the flow-sensitive layer:
    the graph has one node per extent, so both writes land on the same node
    (see the next test).
    """
    reads = _defs_reaching_reads_of(probe_chains(_TWO_WRITES), "WS-DST")
    assert reads, "the read of WS-DST matched no definition at all"
    indices = {link.definition.instruction_index for link in reads}
    assert (
        len(indices) == 1
    ), f"the killed first write still reaches the read: {sorted(indices)}"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_field_graph_is_flow_insensitive_about_rewrites(analyze_probe):
    """KNOWN IMPRECISION: the graph has one node per field, so the killed
    definition's own inputs still hang off that node and reappear downstream.

    WS-SRC is dead by the time WS-DST is read, and the def-use chains above
    prove the analysis knows it — but ``dict[str, set[str]]`` cannot express
    "WS-DST at this point", so the edge survives projection. This is the same
    property the register-level ``dependency_graph`` has. Upgrade path is
    per-definition nodes; asserted here so the cost is visible.
    """
    deps = analyze_probe(_TWO_WRITES).field_graph["WS-NAME"]
    assert "WS-OTHER" in deps, "the live definition"
    assert "WS-SRC" in deps, "the dead one, retained by field-level collapse"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_perform_call_sites_are_merged_context_insensitively(paragraph_probe):
    """KNOWN IMPRECISION (spec 7.4), now genuinely what the code does.

    9000-FORMAT-FIRST is performed from one site and 9000-FORMAT-SECOND from
    another, but each paragraph has ONE CFG entry that every PERFORM of it
    branches to, and one RESUME_CONTINUATION that returns to every site that
    bound it. Contexts are therefore merged: both writers of WS-WORK reach the
    read inside 9000-FORMAT-FIRST, even though only 1000-CALC has run by then.

    That merge is sound — it over-approximates — and it is the deliberate
    scope decision. The upgrade path is per-paragraph summaries (call-site
    indexed reaching definitions).

    Asserted at the def-use layer, where the CFG's contribution is visible.
    An earlier version of this test asserted the same OUTPUT via a false
    mechanism: with PERFORM returns unmodelled the paragraph was severed and
    exactly one definition reached, so the edge came from field-node collapse
    instead. Both writers reaching is what "context-insensitive" means.
    """
    reaching = {
        str(link.definition.block_label)
        for link in paragraph_probe.chains
        if isinstance(link.use.variable, FieldExtent)
        and link.use.variable.field_name == "WS-WORK"
        and str(link.use.block_label) == "para_9000-FORMAT-FIRST"
        and isinstance(link.definition.variable, FieldExtent)
    }
    assert reaching == {"para_1000-CALC", "para_2000-FEES"}, (
        "both PERFORM contexts must reach the merged paragraph entry; "
        f"got {sorted(reaching)}"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_merged_context_shows_up_as_a_field_edge(paragraph_probe):
    """The same imprecision as a reader of the report sees it.

    WS-FIRST-OUT is formatted before 2000-FEES runs, so it cannot really
    depend on WS-FEE; the merged paragraph context says it does. Accepted, and
    asserted so its scope stays tracked.

    WS-AMT is now a REAL edge carried by real flow. Before PERFORM returns
    were wired it survived only by field-node collapse — the correct edge was
    being produced by an imprecision, which is why that is no longer the
    documented mechanism.
    """
    deps = paragraph_probe.result.field_graph["WS-FIRST-OUT"]
    assert "WS-AMT" in deps, "the real edge, now carried by real flow"
    assert "WS-FEE" in deps, "the accepted spurious edge from context merging"
