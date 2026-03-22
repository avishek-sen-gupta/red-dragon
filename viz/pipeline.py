"""Pipeline wrapper — runs the interpreter and captures all stage outputs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from interpreter.cfg import build_cfg
from interpreter.cfg_types import CFG
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.interprocedural.analyze import analyze_interprocedural
from interpreter.interprocedural.types import InterproceduralResult
from interpreter.ir import IRInstruction
from interpreter.parser import TreeSitterParserFactory
from interpreter.registry import build_registry
from interpreter.run import execute_cfg_traced
from interpreter.run_types import VMConfig
from interpreter.trace_types import ExecutionTrace

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ASTNode:
    """Lightweight serialisable representation of a tree-sitter AST node."""

    node_type: str
    text: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    children: list[ASTNode] = field(default_factory=list)
    is_named: bool = True


def _ast_from_ts_node(node, source_bytes: bytes) -> ASTNode:
    """Recursively convert a tree-sitter node into an ASTNode."""
    text_preview = source_bytes[node.start_byte : node.end_byte].decode(
        "utf-8", errors="replace"
    )
    # Truncate long text for display
    if len(text_preview) > 60:
        text_preview = text_preview[:57] + "..."

    children = [_ast_from_ts_node(c, source_bytes) for c in node.children]
    return ASTNode(
        node_type=node.type,
        text=text_preview,
        start_line=node.start_point.row + 1,
        start_col=node.start_point.column,
        end_line=node.end_point.row + 1,
        end_col=node.end_point.column,
        children=children,
        is_named=node.is_named,
    )


@dataclass(frozen=True)
class PipelineResult:
    """All stage outputs from a single pipeline run."""

    source: str
    language: str
    ast: ASTNode | None = None
    ir: list[IRInstruction] = field(default_factory=list)
    cfg: CFG = field(default_factory=CFG)
    trace: ExecutionTrace = field(default_factory=ExecutionTrace)
    interprocedural: InterproceduralResult | None = None


def run_pipeline(
    source: str,
    language: str = "python",
    max_steps: int = 300,
) -> PipelineResult:
    """Run the full pipeline and return all intermediate results."""
    logger.info("viz pipeline: language=%s, max_steps=%d", language, max_steps)

    # Parse AST
    source_bytes = source.encode("utf-8")
    parser = TreeSitterParserFactory().get_parser(language)
    tree = parser.parse(source_bytes)
    ast = _ast_from_ts_node(tree.root_node, source_bytes)

    frontend = get_frontend(Language(language))
    ir = frontend.lower(source_bytes)
    cfg = build_cfg(ir)
    registry = build_registry(
        ir,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    config = VMConfig(max_steps=max_steps)
    _vm, trace = execute_cfg_traced(cfg, "", registry, config)

    try:
        interprocedural = analyze_interprocedural(cfg, registry)
    except Exception:
        logger.warning("Interprocedural analysis failed", exc_info=True)
        interprocedural = None

    return PipelineResult(
        source=source,
        language=language,
        ast=ast,
        ir=ir,
        cfg=cfg,
        trace=trace,
        interprocedural=interprocedural,
    )
