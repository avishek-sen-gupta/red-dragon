from __future__ import annotations

import json
from pathlib import Path

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import SubprocessRunner
from interpreter.instructions import InstructionBase
from tests.covers import NotLanguageFeature, covers

_MINIMAL_ASG = {
    "program_id": "PROG",
    "data_fields": [],
    "sections": [],
    "paragraphs": [{"name": "MAIN", "statements": [{"type": "STOP_RUN"}]}],
}


class _FakeRunner(SubprocessRunner):
    def __init__(self, output: str) -> None:
        self._output = output

    def run(self, command, input_data=""):
        return self._output


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_returns_instructions():
    parser = ProLeapCobolParser(_FakeRunner(json.dumps(_MINIMAL_ASG)), "fake.jar")
    frontend = CobolFrontend(parser)
    ir = frontend.lower_from_ast_dict(dict(_MINIMAL_ASG))
    assert isinstance(ir, list)
    assert len(ir) > 0
    assert all(isinstance(inst, InstructionBase) for inst in ir)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_matches_lower():
    """lower_from_ast_dict with the same dict must produce equivalent IR to lower()."""
    parser = ProLeapCobolParser(_FakeRunner(json.dumps(_MINIMAL_ASG)), "fake.jar")

    frontend1 = CobolFrontend(parser)
    ir_from_source = frontend1.lower(b"ignored - fake runner ignores it")

    frontend2 = CobolFrontend(parser)
    ir_from_dict = frontend2.lower_from_ast_dict(dict(_MINIMAL_ASG))

    assert len(ir_from_source) == len(ir_from_dict)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_applies_preprocessor():
    calls: list[dict] = []

    class _SpyStrategy:
        def handles(self, stmt) -> bool:
            return False

        def preprocess_program_dict(self, data: dict) -> dict:
            calls.append(data)
            return data

        def on_procedure_entry(self, ctx, materialised) -> None:
            pass

        def lower(self, ctx, stmt, materialised) -> None:
            pass

    parser = ProLeapCobolParser(_FakeRunner(json.dumps(_MINIMAL_ASG)), "fake.jar")
    frontend = CobolFrontend(parser, extension_strategies=[_SpyStrategy()])
    frontend.lower_from_ast_dict(dict(_MINIMAL_ASG))
    assert len(calls) == 1
