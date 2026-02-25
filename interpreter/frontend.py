"""Frontend / AST-to-IR Lowering."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .ir import IRInstruction
from . import constants


class Frontend(ABC):
    @abstractmethod
    def lower(self, tree, source: bytes) -> list[IRInstruction]: ...


# Backward-compatibility re-export: code that imports PythonFrontend from here still works.
from .frontends.python import PythonFrontend  # noqa: E402, F401


def get_frontend(
    language: str,
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    llm_provider: str = "claude",
    llm_client: Any = None,
) -> Frontend:
    """Build a frontend for the given language.

    Args:
        language: Source language name (e.g. "python", "javascript").
        frontend_type: "deterministic" (tree-sitter based) or "llm".
        llm_provider: LLM provider name when frontend_type="llm".
        llm_client: Pre-built LLMClient for DI/testing (skips factory).

    Returns:
        A Frontend instance.
    """
    if frontend_type == constants.FRONTEND_DETERMINISTIC:
        from .frontends import get_deterministic_frontend

        return get_deterministic_frontend(language)

    if frontend_type == constants.FRONTEND_LLM:
        from .llm_client import LLMClient, get_llm_client
        from .llm_frontend import LLMFrontend

        if llm_client is None:
            resolved_client = get_llm_client(provider=llm_provider)
        elif isinstance(llm_client, LLMClient):
            resolved_client = llm_client
        else:
            resolved_client = get_llm_client(provider=llm_provider, client=llm_client)
        return LLMFrontend(resolved_client, language=language)

    raise ValueError(f"Unknown frontend type: {frontend_type}")
