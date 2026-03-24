"""Session management for the RedDragon MCP server.

Single-session model: one program loaded at a time. load_session()
eagerly executes the program and records the full trace. Subsequent
step/get_state calls replay the pre-recorded trace.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from interpreter.cfg import build_cfg
from interpreter.cfg_types import CFG
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.interprocedural.types import InterproceduralResult
from interpreter.registry import FunctionRegistry, build_registry
from interpreter.run import build_execution_strategies, execute_cfg_traced
from interpreter.run_types import VMConfig
from interpreter.trace_types import ExecutionTrace
from interpreter.vm.vm_types import VMState

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """A loaded program with its pre-recorded execution trace."""

    source: str
    language: Language
    ir: list[InstructionBase]
    cfg: CFG
    registry: FunctionRegistry
    interprocedural: InterproceduralResult
    vm: VMState
    trace: ExecutionTrace
    step_index: int


def load_session(source: str, language: str, max_steps: int = 300) -> Session:
    """Load, compile, execute, and analyze a program. Returns a ready-to-replay Session."""
    lang = Language(language)
    frontend = get_frontend(lang)
    ir = frontend.lower(source.encode("utf-8"))
    cfg = build_cfg(ir)
    registry = build_registry(
        ir,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    strategies = build_execution_strategies(frontend, ir, registry, lang)
    config = VMConfig(max_steps=max_steps, source_language=lang)
    vm, trace = execute_cfg_traced(cfg, "", registry, config, strategies)
    interprocedural = analyze_interprocedural(cfg, registry)

    return Session(
        source=source,
        language=lang,
        ir=ir,
        cfg=cfg,
        registry=registry,
        interprocedural=interprocedural,
        vm=vm,
        trace=trace,
        step_index=0,
    )


# Module-level session state -- single session per server process.
_current_session: Session | None = None


def get_session() -> Session:
    """Get the current session. Raises if no program is loaded."""
    if _current_session is None:
        raise RuntimeError("No program loaded. Call load_program first.")
    return _current_session


def set_session(session: Session) -> None:
    """Set the current session (replaces any prior session)."""
    global _current_session
    _current_session = session


def clear_session() -> None:
    """Clear the current session."""
    global _current_session
    _current_session = None
