"""Tests for interpreter.llm_client."""

from __future__ import annotations

import pytest

from interpreter.llm_client import (
    ClaudeLLMClient,
    OpenAILLMClient,
    get_llm_client,
    LLMClient,
)


class FakeAnthropicResponse:
    """Mimics anthropic message response structure."""

    def __init__(self, text: str):
        self.content = [type("Block", (), {"text": text})()]


class FakeAnthropicClient:
    """Fake anthropic.Anthropic() for testing."""

    def __init__(self):
        self.messages = self
        self.last_call = {}

    def create(self, **kwargs):
        self.last_call = kwargs
        return FakeAnthropicResponse("fake claude response")


class FakeOpenAIResponse:
    """Mimics openai chat completion response structure."""

    def __init__(self, text: str):
        self.choices = [
            type("Choice", (), {"message": type("Msg", (), {"content": text})()})()
        ]


class FakeOpenAIClient:
    """Fake openai.OpenAI() for testing."""

    def __init__(self):
        self.chat = type("Chat", (), {"completions": self})()
        self.last_call = {}

    def create(self, **kwargs):
        self.last_call = kwargs
        return FakeOpenAIResponse("fake openai response")


class TestClaudeLLMClient:
    def test_complete_with_injected_client(self):
        fake = FakeAnthropicClient()
        client = ClaudeLLMClient(client=fake)
        result = client.complete("sys prompt", "user msg", max_tokens=512)

        assert result == "fake claude response"
        assert fake.last_call["model"] == "claude-sonnet-4-20250514"
        assert fake.last_call["system"] == "sys prompt"
        assert fake.last_call["max_tokens"] == 512
        assert fake.last_call["messages"] == [{"role": "user", "content": "user msg"}]

    def test_custom_model(self):
        fake = FakeAnthropicClient()
        client = ClaudeLLMClient(model="claude-haiku-35", client=fake)
        client.complete("s", "u")
        assert fake.last_call["model"] == "claude-haiku-35"


class TestOpenAILLMClient:
    def test_complete_with_injected_client(self):
        fake = FakeOpenAIClient()
        client = OpenAILLMClient(client=fake)
        result = client.complete("sys prompt", "user msg", max_tokens=256)

        assert result == "fake openai response"
        assert fake.last_call["model"] == "gpt-4o"
        assert fake.last_call["max_tokens"] == 256
        assert fake.last_call["response_format"] == {"type": "json_object"}
        messages = fake.last_call["messages"]
        assert messages[0] == {"role": "system", "content": "sys prompt"}
        assert messages[1] == {"role": "user", "content": "user msg"}

    def test_custom_model(self):
        fake = FakeOpenAIClient()
        client = OpenAILLMClient(model="gpt-3.5-turbo", client=fake)
        client.complete("s", "u")
        assert fake.last_call["model"] == "gpt-3.5-turbo"


class TestGetLLMClient:
    def test_claude_default(self):
        fake = FakeAnthropicClient()
        client = get_llm_client(provider="claude", client=fake)
        assert isinstance(client, ClaudeLLMClient)

    def test_openai_default(self):
        fake = FakeOpenAIClient()
        client = get_llm_client(provider="openai", client=fake)
        assert isinstance(client, OpenAILLMClient)

    def test_claude_with_model(self):
        fake = FakeAnthropicClient()
        client = get_llm_client(provider="claude", model="custom-model", client=fake)
        assert isinstance(client, ClaudeLLMClient)
        client.complete("s", "u")
        assert fake.last_call["model"] == "custom-model"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm_client(provider="gemini")
