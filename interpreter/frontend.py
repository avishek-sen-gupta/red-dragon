"""Frontend / AST-to-IR Lowering."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from interpreter.constants import Language
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.refs.class_ref import ClassRef
from interpreter.refs.func_ref import FuncRef
from interpreter.ir import CodeLabel
from interpreter.instructions import InstructionBase
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from interpreter import constants
from interpreter.constants import LLMProvider

if TYPE_CHECKING:
    from interpreter.frontends.symbol_table import SymbolTable

_NO_REPAIR_CLIENT = object()  # sentinel — distinct from None


class Frontend(ABC):
    @abstractmethod
    def lower(self, source: bytes) -> list[InstructionBase]: ...

    @property
    def data_layout(self) -> dict[str, dict]:
        """Language-agnostic data layout mapping field names to offset/length/type info.

        Override in language frontends that produce memory layouts (e.g. COBOL).
        """
        return {}

    @property
    def type_env_builder(self) -> TypeEnvironmentBuilder:
        """Type seeds accumulated during lowering.

        Override in frontends that populate type info during lowering.
        Returns an empty builder by default.
        """
        return TypeEnvironmentBuilder()

    @property
    def func_symbol_table(self) -> dict[CodeLabel, FuncRef]:
        """Function reference symbol table accumulated during lowering."""
        return {}

    @property
    def class_symbol_table(self) -> dict[CodeLabel, ClassRef]:
        """Class reference symbol table accumulated during lowering."""
        return {}

    @property
    def symbol_table(self) -> SymbolTable:
        """Full symbol table accumulated during lowering."""
        from interpreter.frontends.symbol_table import SymbolTable

        return SymbolTable.empty()


def get_frontend(
    language: Language,
    frontend_type: str = constants.FRONTEND_DETERMINISTIC,
    llm_provider: str = LLMProvider.CLAUDE,
    llm_client: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    repair_client: Any = _NO_REPAIR_CLIENT,
) -> Frontend:
    """Build a frontend for the given language.

    Args:
        language: Source language name (e.g. "python", "javascript").
        frontend_type: "deterministic" (tree-sitter based) or "llm".
        llm_provider: LLM provider name when frontend_type="llm".
        llm_client: Pre-built LLMClient for DI/testing (skips factory).
        observer: Timing observer for parse/lower phases.
        repair_client: Optional LLMClient for AST repair. When provided with
            a deterministic frontend, wraps it in RepairingFrontendDecorator.

    Returns:
        A Frontend instance.
    """
    if frontend_type == constants.FRONTEND_COBOL:
        import os

        from interpreter.cobol.cobol_frontend import CobolFrontend
        from interpreter.cobol.cobol_parser import ProLeapCobolParser
        from interpreter.cobol.subprocess_runner import RealSubprocessRunner

        bridge_jar = os.environ.get("PROLEAP_BRIDGE_JAR", "proleap-bridge.jar")
        parser = ProLeapCobolParser(RealSubprocessRunner(), bridge_jar)
        return CobolFrontend(parser, observer=observer)

    if frontend_type == constants.FRONTEND_DETERMINISTIC:
        from interpreter.frontends import get_deterministic_frontend

        frontend = get_deterministic_frontend(language, observer=observer)
        if repair_client is not _NO_REPAIR_CLIENT:
            from interpreter.ast_repair.repairing_frontend_decorator import (
                RepairingFrontendDecorator,
            )
            from interpreter.llm.llm_client import LLMClient
            from interpreter.parser import TreeSitterParserFactory

            if isinstance(repair_client, LLMClient):
                frontend = RepairingFrontendDecorator(
                    inner_frontend=frontend,
                    llm_client=repair_client,
                    parser_factory=TreeSitterParserFactory(),
                    language=language,
                )
        return frontend

    if frontend_type in (constants.FRONTEND_LLM, constants.FRONTEND_CHUNKED_LLM):
        from interpreter.llm.llm_client import LLMClient, get_llm_client
        from interpreter.llm.llm_frontend import LLMFrontend

        if llm_client is None:
            resolved_client = get_llm_client(provider=llm_provider)
        elif isinstance(llm_client, LLMClient):
            resolved_client = llm_client
        else:
            resolved_client = get_llm_client(
                provider=llm_provider, completion_fn=llm_client
            )

        max_tokens = LLMFrontend.DEFAULT_MAX_TOKENS
        if frontend_type == constants.FRONTEND_CHUNKED_LLM:
            max_tokens = 8192

        inner_frontend = LLMFrontend(
            resolved_client,
            language=language,
            max_tokens=max_tokens,
            observer=observer,
        )

        if frontend_type == constants.FRONTEND_CHUNKED_LLM:
            from interpreter.llm.chunked_llm_frontend import ChunkedLLMFrontend
            from interpreter.parser import TreeSitterParserFactory

            return ChunkedLLMFrontend(
                inner_frontend, TreeSitterParserFactory(), language
            )

        return inner_frontend

    raise ValueError(f"Unknown frontend type: {frontend_type}")
