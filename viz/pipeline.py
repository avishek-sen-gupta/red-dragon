"""Pipeline wrapper — runs the interpreter and captures all stage outputs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from interpreter.api import lower_source, build_cfg_from_source, execute_traced
from interpreter.cfg import build_cfg
from interpreter.cfg_types import CFG
from interpreter.constants import Language
from interpreter.ir import IRInstruction
from interpreter.registry import build_registry
from interpreter.run import execute_cfg_traced
from interpreter.run_types import VMConfig
from interpreter.trace_types import ExecutionTrace, TraceStep

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    """All stage outputs from a single pipeline run."""

    source: str
    language: str
    ir: list[IRInstruction] = field(default_factory=list)
    cfg: CFG = field(default_factory=CFG)
    trace: ExecutionTrace = field(default_factory=ExecutionTrace)


def run_pipeline(
    source: str,
    language: str = "python",
    max_steps: int = 300,
) -> PipelineResult:
    """Run the full pipeline and return all intermediate results."""
    logger.info("viz pipeline: language=%s, max_steps=%d", language, max_steps)

    ir = lower_source(source, language=language)
    cfg = build_cfg(ir)
    registry = build_registry(ir, cfg)
    config = VMConfig(max_steps=max_steps)
    _vm, trace = execute_cfg_traced(cfg, "", registry, config)

    return PipelineResult(
        source=source,
        language=language,
        ir=ir,
        cfg=cfg,
        trace=trace,
    )
