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


class OllamaLLMClient(LLMClient):
    """Wraps Ollama's OpenAI-compatible API at localhost:11434."""

    _LAZY_IMPORT = object()

    def __init__(
        self,
        model: str = "qwen2.5-coder:7b-instruct",
        client: Any = _LAZY_IMPORT,
        base_url: str = "http://localhost:11434/v1",
    ):
        if client is OllamaLLMClient._LAZY_IMPORT:
            import openai

            self._client = openai.OpenAI(base_url=base_url, api_key="ollama")
        else:
            self._client = client
        self._model = model

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        logger.info(
            "OllamaLLMClient.complete: model=%s, max_tokens=%d",
            self._model,
            max_tokens,
        )
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


class HuggingFaceLLMClient(LLMClient):
    """Wraps a HuggingFace Inference Endpoint (OpenAI-compatible)."""

    _LAZY_IMPORT = object()

    def __init__(
        self,
        base_url: str,
        model: str = "",
        client: Any = _LAZY_IMPORT,
        api_key_env: str = "HUGGING_FACE_API_TOKEN",
    ):
        if client is HuggingFaceLLMClient._LAZY_IMPORT:
            import os

            import openai

            api_key = os.environ.get(api_key_env, "")
            if not api_key:
                raise ValueError(
                    f"Environment variable {api_key_env} is not set. "
                    "Set it to your HuggingFace API token."
                )
            self._client = openai.OpenAI(
                base_url=f"{base_url.rstrip('/')}/v1", api_key=api_key
            )
        else:
            self._client = client

        # Auto-discover model ID from endpoint if not provided
        if not model:
            try:
                models = self._client.models.list()
                self._model = models.data[0].id if models.data else "default"
                logger.info("Auto-discovered model: %s", self._model)
            except Exception:
                self._model = "default"
        else:
            self._model = model

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        logger.info(
            "HuggingFaceLLMClient.complete: model=%s, max_tokens=%d",
            self._model or "(endpoint default)",
            max_tokens,
        )
        kwargs: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
        }
        if self._model:
            kwargs["model"] = self._model
        else:
            kwargs["model"] = "default"
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content


_HF_ENDPOINT_REGISTRY: dict[str, str] = {
    "qwen2.5-coder-32b": "https://yenph29p8qghzgb6.us-east-1.aws.endpoints.huggingface.cloud",
}


def get_llm_client(
    provider: str = "claude",
    model: str = "",
    client: Any = None,
    base_url: str = "",
) -> LLMClient:
    """Factory for LLM clients.

    Args:
        provider: "claude", "openai", "ollama", or "huggingface"
        model: Model name override (empty string = use default)
        client: Pre-built API client for DI/testing
        base_url: Base URL for HuggingFace/custom endpoints
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

    if provider == "ollama":
        kwargs = {}
        if model:
            kwargs["model"] = model
        if client is not None:
            kwargs["client"] = client
        return OllamaLLMClient(**kwargs)

    if provider == "huggingface":
        # Default to first registered endpoint if no model/url specified
        default_key = model or next(iter(_HF_ENDPOINT_REGISTRY), "")
        resolved_url = base_url or _HF_ENDPOINT_REGISTRY.get(default_key, "")
        if not resolved_url:
            raise ValueError(
                f"No base_url provided and no registered endpoint for model={model!r}. "
                f"Known endpoints: {list(_HF_ENDPOINT_REGISTRY.keys())}"
            )
        kwargs = {"base_url": resolved_url}
        if model:
            kwargs["model"] = model
        if client is not None:
            kwargs["client"] = client
        return HuggingFaceLLMClient(**kwargs)

    raise ValueError(f"Unknown LLM provider: {provider}")
