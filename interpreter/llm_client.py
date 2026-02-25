"""Shared LLM client infrastructure — used by both frontend and backend."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract base for LLM API clients."""

    @abstractmethod
    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        """Send a prompt to the LLM and return the raw text response."""
        ...


class ClaudeLLMClient(LLMClient):
    """Wraps anthropic.Anthropic() with lazy import and DI."""

    _LAZY_IMPORT = object()

    def __init__(
        self, model: str = "claude-sonnet-4-20250514", client: Any = _LAZY_IMPORT
    ):
        if client is ClaudeLLMClient._LAZY_IMPORT:
            import anthropic

            self._client = anthropic.Anthropic()
        else:
            self._client = client
        self._model = model

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        logger.debug(
            "ClaudeLLMClient.complete: model=%s, max_tokens=%d", self._model, max_tokens
        )
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text


class OpenAILLMClient(LLMClient):
    """Wraps openai.OpenAI() with lazy import and DI."""

    _LAZY_IMPORT = object()

    def __init__(self, model: str = "gpt-4o", client: Any = _LAZY_IMPORT):
        if client is OpenAILLMClient._LAZY_IMPORT:
            import openai

            self._client = openai.OpenAI()
        else:
            self._client = client
        self._model = model

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        logger.debug(
            "OpenAILLMClient.complete: model=%s, max_tokens=%d", self._model, max_tokens
        )
        response = self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


def get_llm_client(
    provider: str = "claude",
    model: str = "",
    client: Any = None,
) -> LLMClient:
    """Factory for LLM clients.

    Args:
        provider: "claude" or "openai"
        model: Model name override (empty string = use default)
        client: Pre-built API client for DI/testing
    """
    if provider == "claude":
        kwargs: dict[str, Any] = {}
        if model:
            kwargs["model"] = model
        if client is not None:
            kwargs["client"] = client
        return ClaudeLLMClient(**kwargs)

    if provider == "openai":
        kwargs = {}
        if model:
            kwargs["model"] = model
        if client is not None:
            kwargs["client"] = client
        return OpenAILLMClient(**kwargs)

    raise ValueError(f"Unknown LLM provider: {provider}")
