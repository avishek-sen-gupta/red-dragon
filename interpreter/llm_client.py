"""Shared LLM client infrastructure — used by both frontend and backend."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

_LAZY_IMPORT = object()


class LLMClient(ABC):
    """Abstract base for LLM API clients."""

    @abstractmethod
    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        """Send a prompt to the LLM and return the raw text response."""
        ...


@dataclass(frozen=True)
class _ProviderDefaults:
    """Default model and optional base_url per provider."""

    model: str
    base_url: str = ""


_PROVIDER_DEFAULTS: dict[str, _ProviderDefaults] = {
    "claude": _ProviderDefaults(model="claude-sonnet-4-20250514"),
    "openai": _ProviderDefaults(model="gpt-4o"),
    "ollama": _ProviderDefaults(
        model="qwen2.5-coder:7b-instruct",
        base_url="http://localhost:11434",
    ),
    "huggingface": _ProviderDefaults(model=""),
}

_HF_ENDPOINT_REGISTRY: dict[str, str] = {
    "qwen2.5-coder-32b": "https://yenph29p8qghzgb6.us-east-1.aws.endpoints.huggingface.cloud",
}


def _resolve_model(provider: str, model: str, base_url: str) -> tuple[str, str]:
    """Resolve provider + model into a LiteLLM model string and api_base.

    Returns:
        (litellm_model_string, api_base_or_empty)
    """
    defaults = _PROVIDER_DEFAULTS.get(provider)
    if defaults is None:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Known providers: {list(_PROVIDER_DEFAULTS.keys())}"
        )

    resolved_model = model or defaults.model
    resolved_base = base_url or defaults.base_url

    if provider == "claude":
        return (resolved_model, "")

    if provider == "openai":
        return (resolved_model, "")

    if provider == "ollama":
        return (f"ollama/{resolved_model}", resolved_base)

    if provider == "huggingface":
        default_key = model or next(iter(_HF_ENDPOINT_REGISTRY), "")
        resolved_base = base_url or _HF_ENDPOINT_REGISTRY.get(default_key, "")
        if not resolved_base:
            raise ValueError(
                f"No base_url provided and no registered endpoint for model={model!r}. "
                f"Known endpoints: {list(_HF_ENDPOINT_REGISTRY.keys())}"
            )
        hf_model = resolved_model or "default"
        return (f"huggingface/{hf_model}", resolved_base)

    raise ValueError(f"Unknown LLM provider: {provider}")


class LiteLLMClient(LLMClient):
    """Unified LLM client backed by litellm.completion()."""

    def __init__(
        self,
        model: str,
        api_base: str = "",
        completion_fn: Callable[..., Any] = _LAZY_IMPORT,
    ):
        if completion_fn is _LAZY_IMPORT:
            import litellm

            self._completion_fn = litellm.completion
        else:
            self._completion_fn = completion_fn
        self._model = model
        self._api_base = api_base

    def complete(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        logger.info(
            "LiteLLMClient.complete: model=%s, max_tokens=%d",
            self._model,
            max_tokens,
        )
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
        }
        if self._api_base:
            kwargs["api_base"] = self._api_base

        response = self._completion_fn(**kwargs)
        return response.choices[0].message.content


def get_llm_client(
    provider: str = "claude",
    model: str = "",
    completion_fn: Callable[..., Any] = _LAZY_IMPORT,
    base_url: str = "",
) -> LLMClient:
    """Factory for LLM clients.

    Args:
        provider: "claude", "openai", "ollama", or "huggingface"
        model: Model name override (empty string = use default)
        completion_fn: Callable matching litellm.completion() signature for DI/testing
        base_url: Base URL for Ollama/HuggingFace/custom endpoints
    """
    litellm_model, api_base = _resolve_model(provider, model, base_url)
    return LiteLLMClient(
        model=litellm_model,
        api_base=api_base,
        completion_fn=completion_fn,
    )
