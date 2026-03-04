"""Configuration for LLM-assisted AST repair."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairConfig:
    """Tuning knobs for the repair loop."""

    max_retries: int = 3
    context_lines: int = 3
