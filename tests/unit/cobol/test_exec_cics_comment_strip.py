"""Unit tests for *> comment stripping in ExecCicsStatement.from_dict (red-dragon-kn0n)."""

from __future__ import annotations
from interpreter.cobol.cobol_statements import (
    CicsOperand,
    ExecCicsStatement,
    _cics_text_parser,
)
from tests.covers import NotLanguageFeature, covers


class TestExecCicsCommentStrip:
    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_inline_comment_stripped_before_parser(self):
        """*> inline comment is stripped from exec_cics_text before parsing."""
        received: list[str] = []

        def capturing_parser(text: str) -> tuple[str, dict[str, CicsOperand | None]]:
            received.append(text)
            return ("RETURN", {})

        token = _cics_text_parser.set(capturing_parser)
        try:
            ExecCicsStatement.from_dict(
                {"exec_cics_text": "RETURN TRANSID (WS-TRANID) *> some comment"}
            )
        finally:
            _cics_text_parser.reset(token)

        assert received == ["RETURN TRANSID (WS-TRANID)"]

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_text_without_comment_unchanged(self):
        """exec_cics_text without *> reaches the parser unchanged."""
        received: list[str] = []

        def capturing_parser(text: str) -> tuple[str, dict[str, CicsOperand | None]]:
            received.append(text)
            return ("SEND", {"MAP": None})

        token = _cics_text_parser.set(capturing_parser)
        try:
            ExecCicsStatement.from_dict({"exec_cics_text": "SEND MAP ('TRNADD')"})
        finally:
            _cics_text_parser.reset(token)

        assert received == ["SEND MAP ('TRNADD')"]

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_multiline_comment_stripped(self):
        """*> comment on its own line is stripped; remaining lines are joined."""
        received: list[str] = []

        def capturing_parser(text: str) -> tuple[str, dict[str, CicsOperand | None]]:
            received.append(text)
            return ("RETURN", {})

        token = _cics_text_parser.set(capturing_parser)
        try:
            ExecCicsStatement.from_dict(
                {
                    "exec_cics_text": "RETURN TRANSID (WS-TRANID)\n*> LENGTH(LENGTH OF X)\nCOMMARE (Y)"
                }
            )
        finally:
            _cics_text_parser.reset(token)

        assert "*>" not in received[0]

    @covers(NotLanguageFeature.INFRASTRUCTURE)
    def test_cotrn02c_pattern_no_valueerror(self):
        """Reproduces the exact COTRN02C exec_cics_text that raised ValueError (kn0n)."""

        def parser(text: str) -> tuple[str, dict[str, CicsOperand | None]]:
            return ("RETURN", {})

        token = _cics_text_parser.set(parser)
        try:
            # This exact text from COTRN02C used to raise ValueError
            ExecCicsStatement.from_dict(
                {
                    "exec_cics_text": (
                        "RETURN TRANSID (WS-TRANID) COMMAREA (CARDDEMO-COMMAREA)"
                        " *>  LENGTH(LENGTH OF CARDDEMO-COMMAREA)"
                    )
                }
            )
        finally:
            _cics_text_parser.reset(token)
        # No exception = pass
