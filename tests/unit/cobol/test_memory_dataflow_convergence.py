"""A truncated solve must be distinguishable from a complete one.

``DATAFLOW_MAX_ITERATIONS`` counts worklist POPS, not sweeps, so programs from
roughly 650 lines up exhaust it. ``solve_reaching_definitions`` then logs a
warning and returns whatever it has — a result with edges MISSING, which is
the precise failure this analysis exists to eliminate. Before this signal
existed, ``analyze_memory_dataflow`` passed nothing to the caller, so a
truncated graph and a complete one were indistinguishable at the API.

Filed as red-dragon-aso9. Raising the cap is that issue's business; these
tests only insist the truncation is VISIBLE.
"""

from __future__ import annotations

import pytest

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter import constants
from interpreter.cfg import build_cfg
from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.memory_dataflow import (
    MemoryDataflowResult,
    analyze_memory_dataflow,
)
from interpreter.cobol.memory_effects import CollectingRecorder
from interpreter.dataflow import (
    solve_reaching_definitions,
    solve_reaching_definitions_checked,
)
from tests.covers import NotLanguageFeature, covers

_SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-SRC       PIC X(3).
       01  WS-MID       PIC X(3).
       01  WS-DST       PIC X(3).
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-SRC TO WS-MID.
           PERFORM COPY-PARA.
           MOVE WS-MID TO WS-DST.
           STOP RUN.
       COPY-PARA.
           MOVE WS-SRC TO WS-DST.
"""


def _analyze() -> MemoryDataflowResult:
    recorder = CollectingRecorder()
    ir = CobolFrontend(make_cobol_parser(), recorder=recorder).lower(_SRC)
    assert recorder.effects, "the lowering recorded no memory effects at all"
    return analyze_memory_dataflow(build_cfg(ir), recorder.effects)


@pytest.fixture(scope="module")
def probe_cfg_and_effects():
    recorder = CollectingRecorder()
    ir = CobolFrontend(make_cobol_parser(), recorder=recorder).lower(_SRC)
    return build_cfg(ir), recorder.effects


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_complete_solve_reports_convergence():
    result = _analyze()
    assert result.converged is True
    assert result.to_json()["converged"] is True


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_truncated_solve_is_reported_not_silently_returned(monkeypatch):
    """The whole point: the caller can tell, without reading a log."""
    monkeypatch.setattr(constants, "DATAFLOW_MAX_ITERATIONS", 1)
    result = _analyze()
    assert result.converged is False, (
        "the solver was capped at one worklist pop, so the graph is missing "
        "edges — the result must say so"
    )
    assert result.to_json()["converged"] is False


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_checked_solver_agrees_with_the_unchecked_one(probe_cfg_and_effects):
    """``solve_reaching_definitions`` is shared by all 16 frontends.

    Its signature is unchanged and it now delegates, so this asserts the
    delegation is behaviour-preserving: same facts, plus a flag.
    """
    cfg, _effects = probe_cfg_and_effects
    plain = solve_reaching_definitions(cfg)
    checked, converged = solve_reaching_definitions_checked(cfg)

    assert converged is True
    assert set(plain) == set(checked)
    for label in plain:
        assert plain[label].reach_in == checked[label].reach_in
        assert plain[label].reach_out == checked[label].reach_out
