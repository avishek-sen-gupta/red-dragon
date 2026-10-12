from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Mapping

import pytest

from cobol_asg.frontend_extension import NullDialectParser
from interpreter.frontend import make_cobol_parser
from interpreter.project.coprocessor_compile import CoprocessorSpec, compile_program
from interpreter.project.types import LinkedProgram

_ORDER = logging.getLogger(__name__)


class _FakeStrategy:
    """A minimal RedDragonExtensionLoweringStrategy that handles nothing —
    proves compile_program's plumbing without needing real CICS/SQL lowering."""

    def handles(self, stmt) -> bool:
        return False

    def preprocess_program_dict(self, data: Mapping[str, str]) -> dict[str, str]:
        return dict(data)

    def on_procedure_entry(self, ctx, materialised) -> None:
        pass

    def lower(self, ctx, stmt, materialised) -> None:
        pass


def test_default_source_prepass_is_identity():
    spec = CoprocessorSpec(name="noop", make_strategy=_FakeStrategy)
    assert spec.source_prepass("       IDENTIFICATION DIVISION.") == (
        "       IDENTIFICATION DIVISION."
    )


def test_defaults_are_non_execution_owning_with_null_dialect_parser():
    spec = CoprocessorSpec(name="noop", make_strategy=_FakeStrategy)
    assert spec.owns_execution is False
    assert isinstance(spec.dialect_parser, NullDialectParser)
    assert spec.dialect_parser.applies({"type": "ANYTHING"}) is False
    assert spec.source_search_dirs() == ()


def test_spec_is_frozen():
    spec = CoprocessorSpec(name="noop", make_strategy=_FakeStrategy)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(spec, "name", "renamed")


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


def _logging_transform(name: str) -> Callable[[str], str]:
    def transform(source: str) -> str:
        _ORDER.info("prepass_%s", name)
        return source

    return transform


def _logging_factory(name: str) -> Callable[[], _FakeStrategy]:
    def make() -> _FakeStrategy:
        _ORDER.info("make_strategy_%s", name)
        return _FakeStrategy()

    return make


def test_every_specs_prepass_runs_before_any_make_strategy(caplog):
    specs = [
        CoprocessorSpec(name, _logging_factory(name), _logging_transform(name))
        for name in ("a", "b")
    ]

    with caplog.at_level(logging.INFO, logger=__name__):
        compile_program(_TRIVIAL_PROGRAM, make_cobol_parser(), specs)

    assert [r.message for r in caplog.records if r.name == __name__] == [
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


def _linked_stems(linked: LinkedProgram) -> list[str]:
    return sorted(path.stem for path in linked.modules)


def _callee(program_id: str) -> bytes:
    return _DATA_NAME_CALLEE.replace(b"DNCALLEE", program_id.encode())


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

    assert _linked_stems(linked) == ["DNCALLEE", "__main__", "__start_up__"]


def test_the_caller_links_a_subprogram_no_static_call_scan_can_discover():
    """A caller with no coprocessor links a data-name callee itself, as a link
    list names the members of a load module."""
    _, linked = compile_program(
        _DATA_NAME_CALLER,
        make_cobol_parser(),
        [],
        linked_subprogram_sources={"DNCALLEE": _DATA_NAME_CALLEE},
    )

    assert _linked_stems(linked) == ["DNCALLEE", "__main__", "__start_up__"]


def test_specs_contributions_merge_and_a_default_spec_contributes_nothing():
    quiet = CoprocessorSpec(name="quiet", make_strategy=_FakeStrategy)
    first = CoprocessorSpec(
        name="first",
        make_strategy=_FakeStrategy,
        linked_subprogram_sources=lambda: {"PGMONE": _callee("PGMONE")},
    )
    second = CoprocessorSpec(
        name="second",
        make_strategy=_FakeStrategy,
        linked_subprogram_sources=lambda: {"PGMTWO": _callee("PGMTWO")},
    )

    _, linked = compile_program(
        _TRIVIAL_PROGRAM,
        make_cobol_parser(),
        [quiet, first, second],
        linked_subprogram_sources={"PGMZERO": _callee("PGMZERO")},
    )

    assert quiet.linked_subprogram_sources() == {}
    assert _linked_stems(linked) == [
        "PGMONE",
        "PGMTWO",
        "PGMZERO",
        "__main__",
        "__start_up__",
    ]
