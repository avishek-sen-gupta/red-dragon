from __future__ import annotations

import dataclasses
from unittest import mock

import pytest

from interpreter.frontend import make_cobol_parser
from interpreter.run import EntryPoint, initial_vm_state, run_linked
from cobol_asg.frontend_extension import NullDialectParser
from interpreter.project.coprocessor_compile import CoprocessorSpec, compile_program


def test_default_source_prepass_is_identity():
    spec = CoprocessorSpec(name="noop", make_strategy=lambda: object())
    assert spec.source_prepass("       IDENTIFICATION DIVISION.") == (
        "       IDENTIFICATION DIVISION."
    )


def test_defaults_are_non_execution_owning_with_null_dialect_parser():
    spec = CoprocessorSpec(name="noop", make_strategy=lambda: object())
    assert spec.owns_execution is False
    assert isinstance(spec.dialect_parser, NullDialectParser)
    assert spec.dialect_parser.applies({"type": "ANYTHING"}) is False
    assert spec.source_search_dirs() == ()


def test_spec_is_frozen():
    spec = CoprocessorSpec(name="noop", make_strategy=lambda: object())
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.name = "renamed"


_TRIVIAL_PROGRAM = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TRIVIAL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-FIELD PIC X(10).
       PROCEDURE DIVISION.
           MOVE 'HELLO' TO WS-FIELD.
           STOP RUN.
"""


class _FakeStrategy:
    """A minimal RedDragonExtensionLoweringStrategy that handles nothing —
    proves compile_program's plumbing without needing real CICS/SQL lowering."""

    def handles(self, stmt) -> bool:
        return False

    def preprocess_program_dict(self, data: dict) -> dict:
        return data

    def on_procedure_entry(self, ctx, materialised) -> None:
        pass

    def lower(self, ctx, stmt, materialised) -> None:
        pass


def test_every_specs_prepass_runs_before_any_make_strategy():
    call_order = []

    def prepass_a(source: str) -> str:
        call_order.append("prepass_a")
        return source

    def prepass_b(source: str) -> str:
        call_order.append("prepass_b")
        return source

    def make_strategy_a():
        call_order.append("make_strategy_a")
        return _FakeStrategy()

    def make_strategy_b():
        call_order.append("make_strategy_b")
        return _FakeStrategy()

    specs = [
        CoprocessorSpec(
            name="a", make_strategy=make_strategy_a, source_prepass=prepass_a
        ),
        CoprocessorSpec(
            name="b", make_strategy=make_strategy_b, source_prepass=prepass_b
        ),
    ]
    parser = make_cobol_parser()

    compile_program(_TRIVIAL_PROGRAM, parser, specs)

    assert call_order == [
        "prepass_a",
        "prepass_b",
        "make_strategy_a",
        "make_strategy_b",
    ]


# A caller that names its callee by DATA-NAME, not by literal: the program name
# is WS-CALLEE's runtime contents, so cobol_asg.cobol_imports -- whose CALL_STMT
# terminal matches quoted literals only -- extracts no CALL edge for it, and no
# source_search_dirs search path can ever discover the callee. Linking it is
# exactly what linked_subprogram_sources is for (red-dragon-t3kl).
_DATA_NAME_CALLER = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DNCALLER.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-CALLEE PIC X(8) VALUE 'DNCALLEE'.
       PROCEDURE DIVISION.
           CALL WS-CALLEE.
           GOBACK.
"""

_DATA_NAME_CALLEE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DNCALLEE.
       PROCEDURE DIVISION.
           DISPLAY 'IN DNCALLEE'.
           GOBACK.
"""


def test_a_spec_links_a_subprogram_no_static_call_scan_can_discover():
    """A CALL by data-name resolves to the contributed subprogram at run time.

    Without the contribution the CALL raises UnresolvedProgramError: the callee
    is named by WS-CALLEE's contents, so nothing static discovers it and it is
    never linked into the run unit.
    """
    spec = CoprocessorSpec(
        name="supplies-a-callee",
        make_strategy=_FakeStrategy,
        linked_subprogram_sources=lambda: {"DNCALLEE": _DATA_NAME_CALLEE},
    )

    _, linked = compile_program(_DATA_NAME_CALLER, make_cobol_parser(), [spec])

    assert any(
        "dncallee" in str(getattr(instr, "label", "")).lower()
        for instr in linked.merged_ir
        if hasattr(instr, "label")
    ), "the contributed callee's IR must be linked into the run unit"

    assert (
        run_linked(
            linked,
            entry_point=EntryPoint.top_level(),
            max_steps=10_000,
            initial_vm=initial_vm_state(),
        )
        is not None
    )


def test_specs_contributions_merge_and_a_default_spec_contributes_nothing():
    quiet = CoprocessorSpec(name="quiet", make_strategy=_FakeStrategy)
    assert quiet.linked_subprogram_sources() == {}

    first = CoprocessorSpec(
        name="first",
        make_strategy=_FakeStrategy,
        linked_subprogram_sources=lambda: {"ONE": b"one"},
    )
    second = CoprocessorSpec(
        name="second",
        make_strategy=_FakeStrategy,
        linked_subprogram_sources=lambda: {"TWO": b"two"},
    )
    captured: dict = {}

    def capture(_source, **kwargs):
        captured.update(kwargs)
        raise _Captured

    with pytest.raises(_Captured):
        with mock.patch(
            "interpreter.project.coprocessor_compile.compile_cobol", capture
        ):
            compile_program(
                _TRIVIAL_PROGRAM, make_cobol_parser(), [quiet, first, second]
            )

    assert captured["extra_subprogram_sources"] == {"ONE": b"one", "TWO": b"two"}


class _Captured(Exception):
    """Ends compile_program once the forwarded arguments have been captured."""
