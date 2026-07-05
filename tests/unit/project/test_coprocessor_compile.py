from __future__ import annotations

import dataclasses

import pytest

from interpreter.frontend import make_cobol_parser
from interpreter.frontend_extension import NullDialectParser
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
    assert spec.extra_program_source_dirs() == ()


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
