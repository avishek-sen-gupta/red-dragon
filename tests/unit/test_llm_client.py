"""Tests for interpreter.llm_client."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from interpreter.llm.llm_client import (
    LiteLLMClient,
    LLMClient,
    get_llm_client,
    _resolve_model,
)


def _fake_completion_fn(**kwargs):
    """Fake litellm.completion() that records calls and returns a canned response."""
    _fake_completion_fn.last_call = kwargs
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="fake response"))]
    )


class TestLiteLLMClient:
    def test_complete_delegates_to_completion_fn(self):
        _fake_completion_fn.last_call = {}
        client = LiteLLMClient(
            model="claude-sonnet-4-20250514", completion_fn=_fake_completion_fn
        )
        result = client.complete("sys prompt", "user msg", max_tokens=512)

        assert result == "fake response"
        call = _fake_completion_fn.last_call
        assert call["model"] == "claude-sonnet-4-20250514"
        assert call["max_tokens"] == 512
        assert call["messages"] == [
            {"role": "system", "content": "sys prompt"},
            {"role": "user", "content": "user msg"},
        ]
        assert "api_base" not in call

    def test_api_base_passed_when_set(self):
        _fake_completion_fn.last_call = {}
        client = LiteLLMClient(
            model="ollama/qwen2.5-coder:7b-instruct",
            api_base="http://localhost:11434",
            completion_fn=_fake_completion_fn,
        )
        client.complete("s", "u")
        assert _fake_completion_fn.last_call["api_base"] == "http://localhost:11434"

    def test_is_llm_client_subclass(self):
        client = LiteLLMClient(model="test", completion_fn=_fake_completion_fn)
        assert isinstance(client, LLMClient)


class TestResolveModel:
    def test_claude_default(self):
        model, base = _resolve_model("claude", "", "")
        assert model == "claude-sonnet-4-20250514"
        assert base == ""

    def test_claude_custom_model(self):
        model, base = _resolve_model("claude", "claude-haiku-35", "")
        assert model == "claude-haiku-35"
        assert base == ""

    def test_openai_default(self):
        model, base = _resolve_model("openai", "", "")
        assert model == "gpt-4o"
        assert base == ""

    def test_ollama_default(self):
        model, base = _resolve_model("ollama", "", "")
        assert model == "ollama/qwen2.5-coder:7b-instruct"
        assert base == "http://localhost:11434"

    def test_ollama_custom_model(self):
        model, base = _resolve_model("ollama", "llama3", "")
        assert model == "ollama/llama3"

    def test_huggingface_registry_lookup(self):
        model, base = _resolve_model("huggingface", "qwen2.5-coder-32b", "")
        assert "huggingface/" in model
        assert "huggingface.cloud" in base

    def test_huggingface_explicit_url(self):
        model, base = _resolve_model(
            "huggingface", "my-model", "https://my-endpoint.com"
        )
        assert model == "huggingface/my-model"
        assert base == "https://my-endpoint.com"

    def test_huggingface_no_url_no_registry_raises(self):
        with pytest.raises(ValueError, match="No base_url provided"):
            _resolve_model("huggingface", "unknown-model", "")

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            _resolve_model("gemini", "", "")


class TestGetLLMClient:
    def test_returns_litellm_client(self):
        client = get_llm_client(provider="claude", completion_fn=_fake_completion_fn)
        assert isinstance(client, LiteLLMClient)

    def test_claude_model_resolution(self):
        _fake_completion_fn.last_call = {}
        client = get_llm_client(provider="claude", completion_fn=_fake_completion_fn)
        client.complete("s", "u")
        assert _fake_completion_fn.last_call["model"] == "claude-sonnet-4-20250514"

    def test_openai_model_resolution(self):
        _fake_completion_fn.last_call = {}
        client = get_llm_client(provider="openai", completion_fn=_fake_completion_fn)
        client.complete("s", "u")
        assert _fake_completion_fn.last_call["model"] == "gpt-4o"

    def test_custom_model_override(self):
        _fake_completion_fn.last_call = {}
        client = get_llm_client(
            provider="claude", model="custom-model", completion_fn=_fake_completion_fn
        )
        client.complete("s", "u")
        assert _fake_completion_fn.last_call["model"] == "custom-model"

    def test_ollama_prefixes_model(self):
        _fake_completion_fn.last_call = {}
        client = get_llm_client(provider="ollama", completion_fn=_fake_completion_fn)
        client.complete("s", "u")
        assert (
            _fake_completion_fn.last_call["model"] == "ollama/qwen2.5-coder:7b-instruct"
        )

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm_client(provider="gemini")
