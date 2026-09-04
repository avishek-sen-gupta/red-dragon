"""Memory dataflow end-to-end on real COBOL source: parse → lower → CFG → analyze.

This module deliberately departs from the project's usual rule that an
integration test exercises the VM through ``run()``. The memory dataflow
analysis is a STATIC pass: it never executes a single instruction, so there is
no VM state to assert on. "Integration" here means the whole real pipeline —
ProLeap parse, COBOL lowering with a ``CollectingRecorder`` attached,
``build_cfg``, then ``analyze_memory_dataflow`` — driven from COBOL source
text rather than hand-built IR. The convention was not forgotten; it does not
apply.

Every fixture obeys the neighbour rule: each field under test has declared
neighbours on BOTH sides, and the tests assert the neighbours' extents and the
ABSENCE of edges to them. A single-field fixture cannot catch a width bug — an
extent one byte too long is invisible in isolation and immediately visible
against a neighbour. That failure class shipped four bugs in this codebase
(red-dragon-ilb6, r9s9, qhtv, bqds).

Two known limitations shape what is asserted here, and neither is a bug to
chase:

* ``edge_locations``/``via`` renders ``<unknown>`` for every edge because the
  COBOL frontend never populates ``InstructionBase.source_location``
  (red-dragon-bmx3). No test here asserts a source line.
* The field graph is flow-insensitive — one node per field — so a killed
  definition's inputs still appear downstream. ``build_def_use_chains`` is the
  flow-sensitive layer when that matters.

Parsing COBOL is slow, so every program is parsed exactly once by a
module-scoped fixture and shared across the tests that interrogate it.
"""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cfg import build_cfg
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.field_extent import FieldExtent
from interpreter.cobol.memory_dataflow import (
    MemoryDataflowResult,
    analyze_memory_dataflow,
    build_def_use_chains,
)
from interpreter.cobol.memory_effects import CollectingRecorder, NullRecorder
from interpreter.dataflow import DefUseLink
from tests.covers import NotLanguageFeature, covers

# ── The program under analysis ─────────────────────────────────────
#
# A small but complete payroll-shaped program. Every layout construct the
# analysis claims to handle appears once, and every field under test is
# bracketed by neighbours:
#
#   WS-EMP-REC     group; WS-EMP-NAME is bracketed by WS-EMP-LEAD/-TAIL.
#   WS-PACKED      redefined by WS-UNPACKED. WS-P-NUM is bracketed by
#                  WS-P-LEAD/-TAIL, and the redefining WS-U-HI/-LO are
#                  bracketed by WS-U-LEAD/-TAIL over the very same bytes.
#   WS-TABLE       OCCURS; the cells are bracketed by WS-TAB-HDR/-FTR.
#   WS-AUDIT-REC   the unrelated record. Nothing in the program moves a value
#                  between it and anything above, so an edge either way is
#                  mush.
_LAYOUT_PROGRAM = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-IN-NAME    PIC X(10).
       01  WS-IN-NUM     PIC X(6).
       01  WS-IN-EDGE    PIC X(2).
       01  WS-IN-CELL    PIC X(3).
       01  WS-IN-HDR     PIC X(2).
       01  WS-IN-AUDIT   PIC X(3).
       01  WS-EMP-REC.
           05  WS-EMP-LEAD   PIC X(2).
           05  WS-EMP-NAME   PIC X(6).
           05  WS-EMP-TAIL   PIC X(2).
       01  WS-PACKED.
           05  WS-P-LEAD     PIC X(2).
           05  WS-P-NUM      PIC X(6).
           05  WS-P-TAIL     PIC X(2).
       01  WS-UNPACKED REDEFINES WS-PACKED.
           05  WS-U-LEAD     PIC X(2).
           05  WS-U-HI       PIC X(3).
           05  WS-U-LO       PIC X(3).
           05  WS-U-TAIL     PIC X(2).
       01  WS-TABLE.
           05  WS-TAB-HDR    PIC X(2).
           05  WS-CELL       OCCURS 4 TIMES PIC X(3).
           05  WS-TAB-FTR    PIC X(2).
       01  WS-AUDIT-REC.
           05  WS-AUD-ID     PIC X(3).
           05  WS-AUD-FLAG   PIC X(1).
       01  WS-OUT-LEAD   PIC X(2).
       01  WS-OUT-NAME   PIC X(6).
       01  WS-OUT-TAIL   PIC X(2).
       01  WS-OUT-EDGE   PIC X(2).
       01  WS-OUT-HI     PIC X(3).
       01  WS-OUT-LO     PIC X(3).
       01  WS-OUT-PTAIL  PIC X(2).
       01  WS-OUT-UTAIL  PIC X(2).
       01  WS-OUT-HDR    PIC X(2).
       01  WS-OUT-TABLE  PIC X(16).
       01  WS-OUT-FTR    PIC X(2).
       01  WS-OUT-AUDIT  PIC X(3).
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM 1000-LOAD-EMPLOYEE.
           PERFORM 2000-PACK-NUMBER.
           PERFORM 3000-FILL-TABLE.
           PERFORM 4000-WRITE-AUDIT.
           STOP RUN.
       1000-LOAD-EMPLOYEE.
           MOVE WS-IN-NAME TO WS-EMP-REC.
           MOVE WS-EMP-LEAD TO WS-OUT-LEAD.
           MOVE WS-EMP-NAME TO WS-OUT-NAME.
           MOVE WS-EMP-TAIL TO WS-OUT-TAIL.
       2000-PACK-NUMBER.
           MOVE WS-IN-NUM TO WS-P-NUM.
           MOVE WS-IN-EDGE TO WS-U-LEAD.
           MOVE WS-U-HI TO WS-OUT-HI.
           MOVE WS-U-LO TO WS-OUT-LO.
           MOVE WS-P-LEAD TO WS-OUT-EDGE.
           MOVE WS-P-TAIL TO WS-OUT-PTAIL.
           MOVE WS-U-TAIL TO WS-OUT-UTAIL.
       3000-FILL-TABLE.
           MOVE WS-IN-HDR TO WS-TAB-HDR.
           MOVE WS-IN-CELL TO WS-CELL(2).
           MOVE WS-TABLE TO WS-OUT-TABLE.
           MOVE WS-TAB-HDR TO WS-OUT-HDR.
           MOVE WS-TAB-FTR TO WS-OUT-FTR.
       4000-WRITE-AUDIT.
           MOVE WS-IN-AUDIT TO WS-AUD-ID.
           MOVE WS-AUD-ID TO WS-OUT-AUDIT.
"""

# A value written BEFORE a PERFORM must reach a read AFTER it, and a value
# written INSIDE the performed paragraph must reach the return point. Until
# recently ``build_cfg`` severed the driver at every PERFORM (each
# ``perform_return_N`` block had zero predecessors) and both flows were
# silently dropped. WS-GUARD-LO/-HI bracket WS-CARRIED and are never touched
# by any statement, so they must not appear anywhere in the graph.
_PERFORM_PROGRAM = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PERFPROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-SEEDED       PIC X(3).
       01  WS-GUARD-LO     PIC X(3).
       01  WS-CARRIED      PIC X(3).
       01  WS-GUARD-HI     PIC X(3).
       01  WS-INNER-SRC    PIC X(3).
       01  WS-INNER-OUT    PIC X(3).
       01  WS-AFTER-CARRY  PIC X(3).
       01  WS-AFTER-INNER  PIC X(3).
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-SEEDED TO WS-CARRIED.
           PERFORM 1000-INNER.
           MOVE WS-CARRIED TO WS-AFTER-CARRY.
           MOVE WS-INNER-OUT TO WS-AFTER-INNER.
           STOP RUN.
       1000-INNER.
           MOVE WS-INNER-SRC TO WS-INNER-OUT.
"""


@dataclass
class _Analysed:
    """All three layers: the graphs, the flow-sensitive chains, and the raw
    extents the lowering declared.

    The chains are not a luxury. A field-graph edge can be produced by
    transitive closure over field-level nodes without any real flow behind it,
    so for anything that is really a claim about CONTROL flow the graph is not
    evidence — see ``test_a_value_written_before_a_perform_reaches_a_read``.
    """

    result: MemoryDataflowResult
    chains: list[DefUseLink]
    extents: dict[str, set[FieldExtent]]


def _analyze(source: str) -> _Analysed:
    recorder = CollectingRecorder()
    frontend = CobolFrontend(make_cobol_parser(), recorder=recorder)
    ir = frontend.lower(source.encode("utf-8"))
    assert recorder.effects, "the lowering recorded no memory effects at all"

    extents: dict[str, set[FieldExtent]] = {}
    for effect in recorder.effects.values():
        extents.setdefault(effect.extent.field_name, set()).add(effect.extent)

    cfg = build_cfg(ir)
    return _Analysed(
        result=analyze_memory_dataflow(cfg, recorder.effects),
        chains=build_def_use_chains(cfg, recorder.effects),
        extents=extents,
    )


@pytest.fixture(scope="module", autouse=True)
def require_bridge_jar() -> str:
    """The ProLeap bridge JAR is mandatory. A missing env var must fail loudly
    (KeyError) rather than skip: a silently skipped analysis test proves
    nothing. Mirrors ``tests.integration.cobol_helpers.bridge_jar``, redeclared
    at module scope because the parsed programs are module-scoped too."""
    return os.environ["PROLEAP_BRIDGE_JAR"]


@pytest.fixture(scope="module")
def layout() -> _Analysed:
    """``_LAYOUT_PROGRAM``, parsed and analysed once for the whole module."""
    return _analyze(_LAYOUT_PROGRAM)


@pytest.fixture(scope="module")
def perform() -> _Analysed:
    """``_PERFORM_PROGRAM``, parsed and analysed once for the whole module."""
    return _analyze(_PERFORM_PROGRAM)


def _only(analysed: _Analysed, field_name: str) -> FieldExtent:
    """The single extent the lowering declared for ``field_name``.

    More than one means the field was accessed at two different byte ranges,
    which for every field here would itself be the bug.
    """
    found = analysed.extents.get(field_name, set())
    assert (
        len(found) == 1
    ), f"{field_name}: expected one extent, got {sorted(map(str, found))}"
    return next(iter(found))


def _deps(analysed: _Analysed, field_name: str) -> set[str]:
    """What ``field_name`` depends on, as the report renders it.

    Indexed, never ``.get(..., set())``: a missing key is a dropped dependency
    and must fail rather than quietly satisfy a negative assertion.
    """
    return analysed.result.field_graph[field_name]


# ── Layout: the extents themselves, against their neighbours ───────


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_group_children_tile_their_parent_without_overlap(layout):
    """WS-EMP-NAME sits between two neighbours and must not steal a byte.

    Asserted as adjacency rather than absolute offsets: the byte at which
    WORKING-STORAGE places WS-EMP-REC is not what is under test, but a child
    that starts one byte early or runs one byte long is.
    """
    lead, name, tail = (
        _only(layout, "WS-EMP-LEAD"),
        _only(layout, "WS-EMP-NAME"),
        _only(layout, "WS-EMP-TAIL"),
    )
    assert (lead.length, name.length, tail.length) == (2, 6, 2)
    assert lead.end == name.start, "WS-EMP-NAME does not start where WS-EMP-LEAD ends"
    assert name.end == tail.start, "WS-EMP-NAME does not end where WS-EMP-TAIL starts"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_redefines_lays_its_children_over_the_same_bytes(layout):
    """The two views must cover byte-for-byte the same range.

    WS-U-HI + WS-U-LO together must occupy exactly WS-P-NUM's six bytes, and
    the bracketing WS-U-LEAD/-TAIL must land exactly on WS-P-LEAD/-TAIL. If
    the redefining view were offset or mis-sized by even one byte, the aliasing
    edges below would still appear — just between the wrong fields.
    """
    p_lead, p_num, p_tail = (
        _only(layout, "WS-P-LEAD"),
        _only(layout, "WS-P-NUM"),
        _only(layout, "WS-P-TAIL"),
    )
    u_lead, u_hi, u_lo, u_tail = (
        _only(layout, "WS-U-LEAD"),
        _only(layout, "WS-U-HI"),
        _only(layout, "WS-U-LO"),
        _only(layout, "WS-U-TAIL"),
    )
    assert (p_lead.start, p_lead.length) == (u_lead.start, u_lead.length)
    assert (p_tail.start, p_tail.length) == (u_tail.start, u_tail.length)
    assert p_lead.end == p_num.start == u_hi.start
    assert u_hi.length == u_lo.length == 3
    assert u_hi.end == u_lo.start
    assert u_lo.end == p_num.end == p_tail.start


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_occurs_element_lands_between_the_table_header_and_footer(layout):
    """WS-CELL(2) is the second of four 3-byte cells sitting between a 2-byte
    header and a 2-byte footer. Both neighbours are asserted, so a cell whose
    stride or origin is wrong cannot hide."""
    header, cell, footer = (
        _only(layout, "WS-TAB-HDR"),
        _only(layout, "WS-CELL"),
        _only(layout, "WS-TAB-FTR"),
    )
    assert cell.length == 3
    assert cell.start == header.end + 3, "WS-CELL(2) is not the second cell"
    assert footer.start == header.end + 4 * 3, "the footer does not follow four cells"
    assert footer.length == 2


# ── Layout: the edges those extents produce ────────────────────────


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_redefines_creates_an_alias_edge(layout):
    """WS-IN-NUM is moved into WS-P-NUM; WS-U-HI and WS-U-LO are read.

    Neither name appears in the other's declaration and no statement mentions
    both, so name-equality analysis reports nothing at all here. This is the
    case that justifies the whole byte-range model.

    The neighbours are the point of the second half: WS-U-LEAD sits over
    WS-P-LEAD and WS-U-TAIL over WS-P-TAIL, both disjoint from WS-P-NUM, so
    the value must NOT be observable through them. An extent two bytes too
    wide in either direction turns one of those into a passing edge.
    """
    assert "WS-IN-NUM" in _deps(layout, "WS-OUT-HI")
    assert "WS-IN-NUM" in _deps(layout, "WS-OUT-LO")

    assert "WS-IN-NUM" not in _deps(layout, "WS-OUT-EDGE"), "leaked into WS-P-LEAD"
    assert "WS-IN-NUM" not in _deps(layout, "WS-OUT-PTAIL"), "leaked into WS-P-TAIL"
    assert "WS-IN-NUM" not in _deps(layout, "WS-OUT-UTAIL"), "leaked into WS-U-TAIL"

    # And the reverse width check: the value written to the redefining
    # WS-U-LEAD reaches WS-P-LEAD (they are the same two bytes) but must not
    # reach WS-U-HI or WS-U-LO.
    assert "WS-IN-EDGE" in _deps(layout, "WS-OUT-EDGE"), "the alias edge itself"
    assert "WS-IN-EDGE" not in _deps(layout, "WS-OUT-HI")
    assert "WS-IN-EDGE" not in _deps(layout, "WS-OUT-LO")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_group_move_propagates_to_every_child(layout):
    """MOVE WS-IN-NAME TO WS-EMP-REC defines all three children at once.

    No statement names any child as a target, so every one of these edges
    exists only because the group's write range subsumes the child's read
    range. All three are asserted, not just the middle one: a rule that fired
    for WS-EMP-NAME alone would be a per-construct special case, and the
    bracketing children are what proves it is not.
    """
    assert "WS-IN-NAME" in _deps(layout, "WS-OUT-LEAD")
    assert "WS-IN-NAME" in _deps(layout, "WS-OUT-NAME")
    assert "WS-IN-NAME" in _deps(layout, "WS-OUT-TAIL")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_occurs_element_write_reaches_a_read_of_the_table(layout):
    """WS-CELL(2) is written, then the whole WS-TABLE is read.

    The element's three bytes lie inside the table's sixteen, so the read of
    the table sees the element's definition. The header, written separately,
    must come through too — and neither must reach the footer's own reader,
    which no statement ever writes.
    """
    table_deps = _deps(layout, "WS-OUT-TABLE")
    assert "WS-IN-CELL" in table_deps, "the OCCURS element write"
    assert "WS-IN-HDR" in table_deps, "the header write, inside the same table"

    # WS-TAB-FTR is read but never written, and lies beyond the last cell.
    assert "WS-IN-CELL" not in _deps(layout, "WS-OUT-FTR")
    assert "WS-IN-HDR" not in _deps(layout, "WS-OUT-FTR")
    # The header's reader must not pick up the cell four bytes further on.
    assert "WS-IN-CELL" not in _deps(layout, "WS-OUT-HDR")
    assert "WS-IN-HDR" in _deps(layout, "WS-OUT-HDR")


# ── The anti-mush check ────────────────────────────────────────────

_AUDIT_FIELDS = {"WS-AUDIT-REC", "WS-AUD-ID", "WS-AUD-FLAG", "WS-IN-AUDIT"}

_EVERYTHING_ELSE = {
    "WS-IN-NAME",
    "WS-IN-NUM",
    "WS-IN-EDGE",
    "WS-IN-CELL",
    "WS-IN-HDR",
    "WS-EMP-REC",
    "WS-EMP-LEAD",
    "WS-EMP-NAME",
    "WS-EMP-TAIL",
    "WS-PACKED",
    "WS-P-LEAD",
    "WS-P-NUM",
    "WS-P-TAIL",
    "WS-UNPACKED",
    "WS-U-LEAD",
    "WS-U-HI",
    "WS-U-LO",
    "WS-U-TAIL",
    "WS-TABLE",
    "WS-TAB-HDR",
    "WS-CELL",
    "WS-TAB-FTR",
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_unrelated_records_stay_disconnected(layout):
    """The anti-mush check, and the single test that makes this an impact
    analysis rather than a claim that everything affects everything.

    WS-AUDIT-REC is a live 01 record in a program full of aliasing: it is
    written, read and reported, in a paragraph performed from the same driver
    as every other. But no statement ever moves a value between it and the
    employee, packed or table records, so not one name from those may appear
    among its dependencies, nor its names among theirs.

    Asserted as exact equality on both sides. ``not in`` against a
    ``.get(..., set())`` would be satisfied by an EMPTY graph, and a test that
    passes when the analysis produces nothing is not an anti-mush test.
    """
    assert _deps(layout, "WS-AUD-ID") == {"WS-IN-AUDIT"}
    assert _deps(layout, "WS-OUT-AUDIT") == {"WS-IN-AUDIT", "WS-AUD-ID"}

    for target in ("WS-AUD-ID", "WS-OUT-AUDIT"):
        assert not (
            _deps(layout, target) & _EVERYTHING_ELSE
        ), f"{target} picked up dependencies on records it shares no bytes with"

    # And nothing on the other side of the program depends on the audit record.
    for target in ("WS-OUT-NAME", "WS-OUT-HI", "WS-OUT-TABLE", "WS-OUT-EDGE"):
        assert not (
            _deps(layout, target) & _AUDIT_FIELDS
        ), f"{target} picked up a dependency on the unrelated audit record"


# ── Values crossing a PERFORM ──────────────────────────────────────


def _defs_reaching_a_read_after_a_perform(analysed: _Analysed, name: str) -> set[str]:
    """Blocks whose definition of ``name`` reaches a read sited at a PERFORM
    return point. Empty means the driver is severed at the PERFORM."""
    return {
        str(link.definition.block_label)
        for link in analysed.chains
        if isinstance(link.use.variable, FieldExtent)
        and link.use.variable.field_name == name
        and str(link.use.block_label).startswith("perform_return")
        and isinstance(link.definition.variable, FieldExtent)
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_value_written_before_a_perform_reaches_a_read_after_it(perform):
    """WS-CARRIED is written before PERFORM 1000-INNER and read after it.

    Nothing in the paragraph touches WS-CARRIED, so the definition has to
    survive the call. Until recently ``build_cfg`` left every
    ``perform_return_N`` block with zero predecessors, and it did not.

    Asserted on the DEF-USE CHAINS, not on the field graph, and that choice is
    load-bearing. Measured against a deliberately severed CFG, the field-graph
    edge ``WS-AFTER-CARRY <- WS-SEEDED`` survives unchanged: the write of
    WS-AFTER-CARRY traces its value register straight to the read of
    WS-CARRIED, and transitive closure supplies WS-SEEDED from a definition
    made in a different block that never reached it. The graph assertion would
    therefore pass on the broken CFG — it asserts the right answer via the
    wrong mechanism. The chains go to zero, so they are the real check.
    """
    assert _defs_reaching_a_read_after_a_perform(perform, "WS-CARRIED") == {
        "para_MAIN-PARA"
    }
    # The reader-visible outcome, kept as a second-order check only.
    assert "WS-SEEDED" in _deps(perform, "WS-AFTER-CARRY")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_value_written_inside_a_performed_paragraph_reaches_the_return(perform):
    """WS-INNER-OUT is written ONLY inside 1000-INNER and read only after the
    PERFORM returns, so the definition has to travel out of the paragraph and
    back to the call site.

    The definition's block label is what is asserted: naming
    ``para_1000-INNER`` pins that the value came out of the performed
    paragraph rather than from anywhere in the driver.
    """
    assert _defs_reaching_a_read_after_a_perform(perform, "WS-INNER-OUT") == {
        "para_1000-INNER"
    }
    assert "WS-INNER-SRC" in _deps(perform, "WS-AFTER-INNER")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_untouched_neighbours_of_a_carried_field_stay_out_of_the_graph(perform):
    """WS-GUARD-LO and WS-GUARD-HI bracket WS-CARRIED and are never mentioned
    by any statement. If a write to WS-CARRIED were three bytes too wide in
    either direction it would still not be *read* — so the check is that the
    guards appear nowhere at all, as neither node nor dependency."""
    graph = perform.result.field_graph
    everything = set(graph) | {dep for deps in graph.values() for dep in deps}
    assert everything, "the perform probe produced an empty graph"
    assert not ({"WS-GUARD-LO", "WS-GUARD-HI"} & everything)


# ── Off by default ─────────────────────────────────────────────────


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_analysis_is_off_by_default():
    """Lowering without a ``CollectingRecorder`` records nothing and changes
    nothing.

    Three separate claims, because "off by default" can fail three ways:

    1. the default really is a ``NullRecorder`` (checked on the constructor
       signature, not on a private attribute);
    2. a ``NullRecorder`` driven through a full lowering accumulates NO state
       — ``vars()`` stays empty, so it is genuinely dropping effects rather
       than recording into an object that is later discarded;
    3. the emitted IR is identical with and without recording, so attaching
       the recorder cannot change program behaviour.
    """
    default = inspect.signature(CobolFrontend.__init__).parameters["recorder"].default
    assert isinstance(default, NullRecorder)

    source = _LAYOUT_PROGRAM.encode("utf-8")

    silent = NullRecorder()
    silent_ir = CobolFrontend(make_cobol_parser(), recorder=silent).lower(source)
    assert vars(silent) == {}, "the NullRecorder accumulated state"

    recording = CollectingRecorder()
    recorded_ir = CobolFrontend(make_cobol_parser(), recorder=recording).lower(source)
    assert recording.effects, "the recording lowering is inert; the comparison is void"

    assert [i.opcode for i in silent_ir] == [i.opcode for i in recorded_ir]

    # And the analysis over an empty sidecar is empty rather than an error:
    # running it against a lowering that recorded nothing is a caller mistake
    # the caller can see.
    empty = analyze_memory_dataflow(build_cfg(silent_ir), {})
    assert empty.field_graph == {}
    assert empty.extent_graph == {}
    assert empty.to_json() == {"nodes": [], "edges": []}
