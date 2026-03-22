"""Decorator that wraps any Frontend, repairing tree-sitter parse errors via LLM."""

from __future__ import annotations

import logging

from interpreter.ast_repair.error_span_extractor import extract
from interpreter.ast_repair.repair_config import RepairConfig
from interpreter.ast_repair.repair_prompter import build_prompt, parse_response
from interpreter.ast_repair.source_patcher import patch
from interpreter.constants import Language
from interpreter.frontend import Frontend
from interpreter.ir import IRInstruction
from interpreter.llm.llm_client import LLMClient
from interpreter.parser import ParserFactory
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder

logger = logging.getLogger(__name__)


class RepairingFrontendDecorator(Frontend):
    """Decorator that wraps any Frontend, repairing tree-sitter parse errors via LLM before delegating lowering."""

    def __init__(
        self,
        inner_frontend: Frontend,
        llm_client: LLMClient,
        parser_factory: ParserFactory,
        language: Language,
        config: RepairConfig = RepairConfig(),
    ):
        self._inner_frontend = inner_frontend
        self._llm_client = llm_client
        self._parser_factory = parser_factory
        self._language = language
        self._config = config
        self._last_lowered_source: bytes = b""

    @property
    def data_layout(self) -> dict[str, dict]:
        return self._inner_frontend.data_layout

    @property
    def type_env_builder(self) -> TypeEnvironmentBuilder:
        return self._inner_frontend.type_env_builder

    @property
    def last_lowered_source(self) -> bytes:
        """The source bytes actually passed to the inner frontend on the most recent lower() call.

        After a successful repair this is the repaired source; after fallback
        it is the original (broken) source.  Empty before the first call.
        """
        return self._last_lowered_source

    def lower(self, source: bytes) -> list[IRInstruction]:
        parser = self._parser_factory.get_parser(self._language)
        tree = parser.parse(source)

        if not tree.root_node.has_error:
            logger.debug("No parse errors — delegating directly to inner frontend")
            self._last_lowered_source = source
            return self._inner_frontend.lower(source)

        current_source = source
        for attempt in range(1, self._config.max_retries + 1):
            error_spans = extract(
                tree.root_node, current_source, self._config.context_lines
            )
            if not error_spans:
                break

            logger.info(
                "Repair attempt %d/%d: %d error span(s)",
                attempt,
                self._config.max_retries,
                len(error_spans),
            )

            prompt = build_prompt(self._language.value, error_spans)
            response = self._llm_client.complete(
                prompt.system_prompt, prompt.user_prompt
            )
            fragments = parse_response(response, len(error_spans))
            current_source = patch(current_source, error_spans, fragments)

            tree = parser.parse(current_source)
            if not tree.root_node.has_error:
                logger.info("Repair succeeded on attempt %d", attempt)
                self._last_lowered_source = current_source
                return self._inner_frontend.lower(current_source)

        logger.warning(
            "All %d repair attempts exhausted — falling back to original source",
            self._config.max_retries,
        )
        self._last_lowered_source = source
        return self._inner_frontend.lower(source)
