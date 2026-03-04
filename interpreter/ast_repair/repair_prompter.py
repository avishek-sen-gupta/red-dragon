"""Builds LLM prompts for syntax repair and parses responses."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from interpreter.ast_repair.error_span import ErrorSpan

logger = logging.getLogger(__name__)

FRAGMENT_DELIMITER = "===FRAGMENT==="


@dataclass(frozen=True)
class RepairPrompt:
    """A fully-formed system + user prompt pair for syntax repair."""

    system_prompt: str
    user_prompt: str


def build_prompt(language: str, error_spans: list[ErrorSpan]) -> RepairPrompt:
    """Build system and user prompts for LLM-based syntax repair.

    Each span becomes a delimited section in the user prompt.
    """
    system_prompt = (
        f"Fix ONLY syntax errors in this {language} code. "
        f"Return ONLY the repaired fragment(s). No markdown, no explanation. "
        f"If there are multiple fragments, separate them with a line containing "
        f"only '{FRAGMENT_DELIMITER}'."
    )
    sections = [_format_span(span) for span in error_spans]
    user_prompt = f"\n{FRAGMENT_DELIMITER}\n".join(sections)
    return RepairPrompt(system_prompt=system_prompt, user_prompt=user_prompt)


def _format_span(span: ErrorSpan) -> str:
    """Format a single error span with context for the LLM."""
    parts: list[str] = []
    if span.context_before:
        parts.append(f"# Context before:\n{span.context_before}\n")
    parts.append(f"# Broken code:\n{span.error_text}\n")
    if span.context_after:
        parts.append(f"# Context after:\n{span.context_after}")
    return "\n".join(parts)


def parse_response(response: str, expected_count: int) -> list[str]:
    """Parse the LLM response into repaired fragments.

    Returns exactly *expected_count* fragments. If the response contains
    the wrong number, logs a warning and pads/truncates to match.
    """
    fragments = [fragment.strip() for fragment in response.split(FRAGMENT_DELIMITER)]
    # Filter out empty fragments from leading/trailing delimiters
    fragments = [f for f in fragments if f]

    if len(fragments) == expected_count:
        return fragments

    logger.warning(
        "Expected %d fragment(s) but got %d from LLM response",
        expected_count,
        len(fragments),
    )
    if len(fragments) > expected_count:
        return fragments[:expected_count]
    # Pad with empty strings — the patcher will replace error spans with empty text,
    # which is better than crashing
    return fragments + [""] * (expected_count - len(fragments))
