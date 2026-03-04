"""Tests for interpreter.ast_repair.repairing_frontend_decorator."""

from __future__ import annotations

from interpreter.ast_repair.repair_config import RepairConfig
from interpreter.ast_repair.repairing_frontend_decorator import (
    RepairingFrontendDecorator,
)
from interpreter.constants import Language
from interpreter.frontend import Frontend
from interpreter.ir import IRInstruction, Opcode
from interpreter.llm_client import LLMClient
from interpreter.parser import TreeSitterParserFactory

# ── Test doubles ─────────────────────────────────────────────────


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


class FakeRetryLLMClient(LLMClient):
    """Returns different responses on successive calls."""

    def __init__(self, responses: list[str]):
        self._responses = responses
        self._call_index = 0
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
        response = self._responses[min(self._call_index, len(self._responses) - 1)]
        self._call_index += 1
        return response


class RecordingFrontend(Frontend):
    """Records calls to lower() and returns canned IR."""

    def __init__(self, instructions: list[IRInstruction]):
        self._instructions = instructions
        self.lower_calls: list[bytes] = []

    def lower(self, source: bytes) -> list[IRInstruction]:
        self.lower_calls.append(source)
        return self._instructions


ENTRY_IR = [IRInstruction(opcode=Opcode.LABEL, label="entry")]
VALID_PYTHON = b"x = 1\nprint(x)\n"
BROKEN_PYTHON = b"def foo(:\n  return 1\n"
FIXED_PYTHON = b"def foo():\n  return 1\n"


# ── Tests ────────────────────────────────────────────────────────


class TestNoErrorPassthrough:
    def test_valid_source_delegates_directly(self):
        inner = RecordingFrontend(ENTRY_IR)
        llm = FakeLLMClient("should not be called")
        decorator = RepairingFrontendDecorator(
            inner, llm, TreeSitterParserFactory(), Language.PYTHON
        )

        result = decorator.lower(VALID_PYTHON)

        assert result == ENTRY_IR
        assert len(inner.lower_calls) == 1
        assert inner.lower_calls[0] == VALID_PYTHON
        assert len(llm.calls) == 0


class TestSuccessfulRepair:
    def test_repair_fixes_syntax_on_first_attempt(self):
        inner = RecordingFrontend(ENTRY_IR)
        # The error span covers only line 0: "def foo(:"
        # The LLM should return just the repaired fragment for that span
        llm = FakeLLMClient("def foo():")
        decorator = RepairingFrontendDecorator(
            inner, llm, TreeSitterParserFactory(), Language.PYTHON
        )

        result = decorator.lower(BROKEN_PYTHON)

        assert result == ENTRY_IR
        assert len(llm.calls) == 1
        # Inner frontend should receive the repaired source, not the broken one
        assert inner.lower_calls[0] != BROKEN_PYTHON


class TestRetrySucceeds:
    def test_retry_succeeds_on_second_attempt(self):
        inner = RecordingFrontend(ENTRY_IR)
        # First response is still broken (only the error span fragment), second is fixed
        llm = FakeRetryLLMClient(["def foo(:", "def foo():"])
        decorator = RepairingFrontendDecorator(
            inner,
            llm,
            TreeSitterParserFactory(),
            Language.PYTHON,
            config=RepairConfig(max_retries=3),
        )

        result = decorator.lower(BROKEN_PYTHON)

        assert result == ENTRY_IR
        assert len(llm.calls) == 2


class TestAllRetriesFail:
    def test_falls_back_to_original_source(self):
        inner = RecordingFrontend(ENTRY_IR)
        # LLM always returns garbage
        llm = FakeLLMClient("still broken def foo(:")
        decorator = RepairingFrontendDecorator(
            inner,
            llm,
            TreeSitterParserFactory(),
            Language.PYTHON,
            config=RepairConfig(max_retries=2),
        )

        result = decorator.lower(BROKEN_PYTHON)

        assert result == ENTRY_IR
        # Falls back to original source
        assert inner.lower_calls[0] == BROKEN_PYTHON


class TestMaxRetriesRespected:
    def test_exact_retry_count(self):
        inner = RecordingFrontend(ENTRY_IR)
        llm = FakeLLMClient("def foo(:")  # always broken
        config = RepairConfig(max_retries=4)
        decorator = RepairingFrontendDecorator(
            inner, llm, TreeSitterParserFactory(), Language.PYTHON, config=config
        )

        decorator.lower(BROKEN_PYTHON)

        assert len(llm.calls) == 4


class TestDataLayoutDelegation:
    def test_data_layout_delegates_to_inner(self):
        inner = RecordingFrontend(ENTRY_IR)
        llm = FakeLLMClient()
        decorator = RepairingFrontendDecorator(
            inner, llm, TreeSitterParserFactory(), Language.PYTHON
        )
        assert decorator.data_layout == inner.data_layout


class TestLastLoweredSource:
    def test_no_error_records_original_source(self):
        inner = RecordingFrontend(ENTRY_IR)
        llm = FakeLLMClient()
        decorator = RepairingFrontendDecorator(
            inner, llm, TreeSitterParserFactory(), Language.PYTHON
        )

        decorator.lower(VALID_PYTHON)

        assert decorator.last_lowered_source == VALID_PYTHON

    def test_successful_repair_records_repaired_source(self):
        inner = RecordingFrontend(ENTRY_IR)
        llm = FakeLLMClient("def foo():")
        decorator = RepairingFrontendDecorator(
            inner, llm, TreeSitterParserFactory(), Language.PYTHON
        )

        decorator.lower(BROKEN_PYTHON)

        assert decorator.last_lowered_source != BROKEN_PYTHON
        assert b"def foo():" in decorator.last_lowered_source

    def test_failed_repair_records_original_source(self):
        inner = RecordingFrontend(ENTRY_IR)
        llm = FakeLLMClient("still broken def foo(:")
        decorator = RepairingFrontendDecorator(
            inner,
            llm,
            TreeSitterParserFactory(),
            Language.PYTHON,
            config=RepairConfig(max_retries=1),
        )

        decorator.lower(BROKEN_PYTHON)

        assert decorator.last_lowered_source == BROKEN_PYTHON

    def test_empty_before_first_call(self):
        inner = RecordingFrontend(ENTRY_IR)
        llm = FakeLLMClient()
        decorator = RepairingFrontendDecorator(
            inner, llm, TreeSitterParserFactory(), Language.PYTHON
        )

        assert decorator.last_lowered_source == b""
