"""Tests for get_frontend() factory with frontend_type parameter."""

from __future__ import annotations

import pytest

from interpreter import constants
from interpreter.frontend import PythonFrontend, get_frontend
from interpreter.llm_client import LLMClient
from interpreter.llm_frontend import LLMFrontend


class FakeLLMClient(LLMClient):
    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        return "[]"


class TestGetFrontend:
    def test_deterministic_python(self):
        frontend = get_frontend("python")
        assert isinstance(frontend, PythonFrontend)

    def test_deterministic_explicit(self):
        frontend = get_frontend(
            "python", frontend_type=constants.FRONTEND_DETERMINISTIC
        )
        assert isinstance(frontend, PythonFrontend)

    def test_deterministic_unsupported_language_raises(self):
        with pytest.raises(ValueError, match="Unsupported language"):
            get_frontend("javascript", frontend_type=constants.FRONTEND_DETERMINISTIC)

    def test_llm_frontend_with_injected_client(self):
        fake = FakeLLMClient()
        frontend = get_frontend(
            "python",
            frontend_type=constants.FRONTEND_LLM,
            llm_client=fake,
        )
        assert isinstance(frontend, LLMFrontend)

    def test_llm_frontend_any_language(self):
        fake = FakeLLMClient()
        frontend = get_frontend(
            "javascript",
            frontend_type=constants.FRONTEND_LLM,
            llm_client=fake,
        )
        assert isinstance(frontend, LLMFrontend)

    def test_unknown_frontend_type_raises(self):
        with pytest.raises(ValueError, match="Unknown frontend type"):
            get_frontend("python", frontend_type="magic")
