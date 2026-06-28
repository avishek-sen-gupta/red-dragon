from __future__ import annotations

import json

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import make_cobol_parser
from interpreter.instructions import InstructionBase
from tests.covers import NotLanguageFeature, covers

_MINIMAL_ASG = {
    "program_id": "PROG",
    "data_fields": [],
    "sections": [],
    "paragraphs": [{"name": "MAIN", "statements": [{"type": "STOP_RUN"}]}],
}

_MINIMAL_SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROG.
       PROCEDURE DIVISION.
           GOBACK.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_returns_instructions():
    frontend = CobolFrontend(make_cobol_parser())
    ir = frontend.lower_from_ast_dict(dict(_MINIMAL_ASG))
    assert isinstance(ir, list)
    assert len(ir) > 0
    assert all(isinstance(inst, InstructionBase) for inst in ir)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_matches_lower(tmp_path):
    """lower_from_ast_dict with the real bridge dict must produce equivalent IR to lower()."""
    parser = make_cobol_parser()
    ast_path = tmp_path / "prog.ast.json"
    parser.parse_to_file(_MINIMAL_SRC, ast_path)
    data = json.loads(ast_path.read_text())

    frontend1 = CobolFrontend(make_cobol_parser())
    ir_from_dict = frontend1.lower_from_ast_dict(data)

    frontend2 = CobolFrontend(make_cobol_parser())
    ir_from_source = frontend2.lower(_MINIMAL_SRC)

    assert len(ir_from_source) == len(ir_from_dict)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_from_ast_dict_applies_preprocessor():
    calls: list[dict] = []

    class _SpyStrategy:
        def handles(self, stmt) -> bool:  # noqa: ARG002
            return False

        def preprocess_program_dict(self, data: dict) -> dict:
            calls.append(data)
            return data

        def on_procedure_entry(self, ctx, materialised) -> None:  # noqa: ARG002
            pass

        def lower(self, ctx, stmt, materialised) -> None:  # noqa: ARG002
            pass

    frontend = CobolFrontend(make_cobol_parser(), extension_strategies=[_SpyStrategy()])
    frontend.lower_from_ast_dict(dict(_MINIMAL_ASG))
    assert len(calls) == 1
