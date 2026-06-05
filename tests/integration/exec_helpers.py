"""Shared execution helper for single-source frontend integration tests.

Centralizes the common ``run(source) -> unwrap top-level locals`` pattern used
across the per-language ``test_<lang>_*_execution`` modules so the VM call
shape is defined exactly once.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def run_locals(source: str, language: Language, max_steps: int = 500) -> dict:
    """Run a single-source program at top level; return the unwrapped top-frame locals."""
    vm = run(
        source,
        language=language,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)
