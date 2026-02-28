"""Run pipeline data types (pure data, no business logic)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UnresolvedCallStrategy(Enum):
    """Strategy for resolving calls to unknown functions/methods."""

    SYMBOLIC = "symbolic"
    LLM = "llm"


@dataclass(frozen=True)
class VMConfig:
    """Groups VM execution configuration."""

    backend: str = "claude"
    max_steps: int = 100
    verbose: bool = False
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC
    source_language: str = ""


@dataclass
class ExecutionStats:
    """Returned execution metrics from execute_cfg."""

    steps: int = 0
    llm_calls: int = 0
    final_heap_objects: int = 0
    final_symbolic_count: int = 0
    closures_captured: int = 0


@dataclass
class PipelineStats:
    """Timing and size statistics for each pipeline stage."""

    source_bytes: int = 0
    source_lines: int = 0
    language: str = ""
    frontend_type: str = ""

    # Stage timings (seconds)
    parse_time: float = 0.0
    lower_time: float = 0.0
    cfg_time: float = 0.0
    registry_time: float = 0.0
    execution_time: float = 0.0
    total_time: float = 0.0

    # Output sizes
    ir_instruction_count: int = 0
    cfg_block_count: int = 0
    registry_functions: int = 0
    registry_classes: int = 0

    # Execution stats
    execution_steps: int = 0
    llm_calls: int = 0
    final_heap_objects: int = 0
    final_symbolic_count: int = 0
    closures_captured: int = 0

    def report(self) -> str:
        lines = [
            "═══ Pipeline Statistics ═══",
            f"  Source: {self.source_lines} lines, {self.source_bytes} bytes ({self.language}, {self.frontend_type} frontend)",
            "",
            f"  {'Stage':<20} {'Time':>10}  {'Output':>30}",
            f"  {'─' * 20} {'─' * 10}  {'─' * 30}",
        ]

        stages = [
            ("Parse", self.parse_time, ""),
            (
                "Lower (frontend)",
                self.lower_time,
                f"{self.ir_instruction_count} IR instructions",
            ),
            ("Build CFG", self.cfg_time, f"{self.cfg_block_count} basic blocks"),
            (
                "Build registry",
                self.registry_time,
                f"{self.registry_functions} functions, {self.registry_classes} classes",
            ),
            (
                "Execute (VM)",
                self.execution_time,
                f"{self.execution_steps} steps, {self.llm_calls} LLM calls",
            ),
        ]
        for name, t, output in stages:
            time_str = f"{t * 1000:>8.1f}ms"
            lines.append(f"  {name:<20} {time_str:>10}  {output:>30}")

        lines.append(f"  {'─' * 20} {'─' * 10}  {'─' * 30}")
        lines.append(f"  {'Total':<20} {self.total_time * 1000:>8.1f}ms")
        lines.append("")
        lines.append(
            f"  Final state: {self.final_heap_objects} heap objects,"
            f" {self.final_symbolic_count} symbolic values,"
            f" {self.closures_captured} closures"
        )
        return "\n".join(lines)
