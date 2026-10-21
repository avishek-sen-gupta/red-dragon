# pyright: standard
"""The real che4z bridge, run through HlasmBridgeParser."""

from __future__ import annotations

from pathlib import Path

import pytest

from hlasm_asg.hlasm_bridge_parser import make_hlasm_parser
from hlasm_asg.hlasm_parse_error import HlasmParseError
from hlasm_asg.program.diagnostic import Diagnostic
from hlasm_asg.program.macro_origin import MacroOrigin
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.severity import Severity
from tests.covers import NotLanguageFeature, covers

MACRO_SOURCE = b"HELLO    CSECT\n         MYM\n         BR    14\n         END\n"
MACRO_LIBRARY = b"         MACRO\n         MYM\n         LA    3,1\n         MEND\n"


SOURCE_NAME = "src/hello.asm"


@pytest.fixture
def syslib(tmp_path: Path) -> Path:
    directory = tmp_path / "lib"
    directory.mkdir()
    (directory / "MYM").write_bytes(MACRO_LIBRARY)
    return directory


class TestBridgeParser:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_bridge_parses_hello_and_keeps_macro_origin(
        self, tmp_path: Path, syslib: Path
    ):
        parser = make_hlasm_parser([syslib])

        out = parser.parse_to_file(MACRO_SOURCE, SOURCE_NAME, tmp_path / "program.json")
        program = parser.read(out)

        macro_origin, open_origin = [s.origin for s in program.statements]
        assert macro_origin == MacroOrigin(
            kind="MACRO", file=SOURCE_NAME, line=2, macro="MYM", depth=1
        )
        assert open_origin == OpenCodeOrigin(kind="OPEN_CODE", file=SOURCE_NAME, line=3)
        assert [section.name for section in program.sections] == ["HELLO"]

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_bridge_refuses_assembly_errors(self, tmp_path: Path):
        parser = make_hlasm_parser()

        with pytest.raises(HlasmParseError, match="M120 line 1") as refused:
            parser.parse_to_file(
                b"         LA    99,0\n", SOURCE_NAME, tmp_path / "program.json"
            )

        (diagnostic,) = refused.value.diagnostics
        assert diagnostic == Diagnostic(
            code="M120",
            severity=Severity.ERROR,
            message="Error at LA instruction: register operand absolute value must be between 0 and 15",
            file=SOURCE_NAME,
            line=1,
        )
        assert not (tmp_path / "program.json").exists()
