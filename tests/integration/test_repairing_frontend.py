"""Integration tests for AST repair pipeline.

Uses real tree-sitter parsing with FakeLLMClient to verify the full
repair → re-parse → deterministic lowering pipeline.
"""

from __future__ import annotations

from interpreter.ast_repair.repair_config import RepairConfig
from interpreter.ast_repair.repairing_frontend_decorator import (
    RepairingFrontendDecorator,
)
from interpreter.constants import Language
from interpreter.frontends import get_deterministic_frontend
from interpreter.ir import Opcode
from interpreter.llm_client import LLMClient
from interpreter.parser import TreeSitterParserFactory


class FakeLLMClient(LLMClient):
    """Returns a canned response and records calls."""

    def __init__(self, response: str = ""):
        self._response = response
        self.calls: list[dict] = []

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_message": user_message,
                "max_tokens": max_tokens,
            }
        )
        return self._response


class TestRepairPipelinePython:
    """Full pipeline: broken Python → LLM repair → deterministic lowering."""

    def test_broken_python_repaired_produces_clean_ir(self):
        inner = get_deterministic_frontend(Language.PYTHON)
        # The broken source: missing closing paren in def
        broken = b"def foo(:\n  return 1\n"
        # The LLM returns just the repaired error fragment (line 0)
        llm = FakeLLMClient("def foo():")
        decorator = RepairingFrontendDecorator(
            inner, llm, TreeSitterParserFactory(), Language.PYTHON
        )

        ir = decorator.lower(broken)

        assert len(ir) > 0
        # Should have entry label
        assert ir[0].opcode == Opcode.LABEL
        assert ir[0].label == "entry"
        # Should NOT have any SYMBOLIC "unsupported:ERROR" — the repair fixed it
        symbolic_errors = [
            inst
            for inst in ir
            if inst.opcode == Opcode.SYMBOLIC
            and any("unsupported:ERROR" in str(op) for op in inst.operands)
        ]
        assert symbolic_errors == [], f"Unexpected ERROR symbolics: {symbolic_errors}"
        assert len(llm.calls) == 1

    def test_valid_python_no_llm_calls(self):
        inner = get_deterministic_frontend(Language.PYTHON)
        llm = FakeLLMClient("should not be called")
        decorator = RepairingFrontendDecorator(
            inner, llm, TreeSitterParserFactory(), Language.PYTHON
        )

        valid_source = b"def foo():\n  return 1\n"
        ir = decorator.lower(valid_source)

        assert len(ir) > 0
        assert len(llm.calls) == 0


class TestRepairPipelineJavaScript:
    """Full pipeline: broken JavaScript → LLM repair → deterministic lowering."""

    def test_broken_js_repaired_produces_clean_ir(self):
        inner = get_deterministic_frontend(Language.JAVASCRIPT)
        # Missing closing brace
        broken = b"function foo() {\n  return 1;\n"
        # The LLM repairs the fragment by adding the closing brace
        llm = FakeLLMClient("function foo() {\n  return 1;\n}")
        decorator = RepairingFrontendDecorator(
            inner, llm, TreeSitterParserFactory(), Language.JAVASCRIPT
        )

        ir = decorator.lower(broken)

        assert len(ir) > 0
        assert ir[0].opcode == Opcode.LABEL
        symbolic_errors = [
            inst
            for inst in ir
            if inst.opcode == Opcode.SYMBOLIC
            and any("unsupported:ERROR" in str(op) for op in inst.operands)
        ]
        assert symbolic_errors == [], f"Unexpected ERROR symbolics: {symbolic_errors}"


class TestRepairFallback:
    """When repair fails, the original source is passed through."""

    def test_unrepairable_falls_back_gracefully(self):
        inner = get_deterministic_frontend(Language.PYTHON)
        broken = b"def foo(:\n  return 1\n"
        # LLM always returns garbage
        llm = FakeLLMClient("completely invalid {{{{")
        decorator = RepairingFrontendDecorator(
            inner,
            llm,
            TreeSitterParserFactory(),
            Language.PYTHON,
            config=RepairConfig(max_retries=2),
        )

        ir = decorator.lower(broken)

        # Should still produce IR (with SYMBOLIC fallbacks), not crash
        assert len(ir) > 0
        assert ir[0].opcode == Opcode.LABEL
        assert len(llm.calls) == 2
