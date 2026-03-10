"""Lowering trace — captures the AST→IR mapping during frontend lowering."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from interpreter.cfg import build_cfg
from interpreter.cfg_types import CFG
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.frontends.context import TreeSitterEmitContext, GrammarConstants
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.ir import IRInstruction, Opcode, SourceLocation, NO_SOURCE_LOCATION
from interpreter.parser import TreeSitterParserFactory
from interpreter.type_environment_builder import TypeEnvironmentBuilder

logger = logging.getLogger(__name__)


@dataclass
class LoweringEvent:
    """A single handler invocation during lowering."""

    ast_node_type: str
    ast_text: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    handler_name: str
    handler_module: str
    is_shared: bool
    dispatch_type: str  # "expr", "stmt", "block", "fallback"
    instructions_emitted: list[IRInstruction] = field(default_factory=list)
    children: list[LoweringEvent] = field(default_factory=list)


@dataclass(frozen=True)
class LoweringResult:
    """Complete result of a traced lowering pass."""

    source: str
    language: str
    events: list[LoweringEvent] = field(default_factory=list)
    ir: list[IRInstruction] = field(default_factory=list)
    cfg: CFG = field(default_factory=CFG)


class TracingEmitContext(TreeSitterEmitContext):
    """Wraps TreeSitterEmitContext to capture handler invocations as a tree."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._event_stack: list[LoweringEvent] = []
        self._root_events: list[LoweringEvent] = []
        self._ir_before_count: int = 0

    def lower_stmt(self, node) -> None:
        ntype = node.type
        if ntype in self.constants.comment_types or ntype in self.constants.noise_types:
            return

        handler = self.stmt_dispatch.get(ntype)
        if handler:
            event = self._make_event(node, handler, "stmt")
            self._push_event(event)
            handler(self, node)
            self._pop_event(event)
            return

        if ntype in self.constants.block_node_types:
            self.lower_block(node)
            return

        self.lower_expr(node)

    def lower_expr(self, node) -> str:
        handler = self.expr_dispatch.get(node.type)
        if handler:
            event = self._make_event(node, handler, "expr")
            self._push_event(event)
            result = handler(self, node)
            self._pop_event(event)
            return result

        # Fallback: symbolic
        event = self._make_event(node, None, "fallback")
        self._push_event(event)
        reg = self.fresh_reg()
        self.emit(
            Opcode.SYMBOLIC,
            result_reg=reg,
            operands=[f"unsupported:{node.type}"],
            node=node,
        )
        self._pop_event(event)
        return reg

    def _make_event(self, node, handler, dispatch_type: str) -> LoweringEvent:
        text = self.node_text(node)
        if len(text) > 80:
            text = text[:77] + "..."

        handler_name = getattr(handler, "__name__", "?") if handler else "(fallback)"
        handler_module = getattr(handler, "__module__", "") if handler else ""
        is_shared = ".common." in handler_module

        return LoweringEvent(
            ast_node_type=node.type,
            ast_text=text,
            start_line=node.start_point.row + 1,
            start_col=node.start_point.column,
            end_line=node.end_point.row + 1,
            end_col=node.end_point.column,
            handler_name=handler_name,
            handler_module=handler_module,
            is_shared=is_shared,
            dispatch_type=dispatch_type,
        )

    def _push_event(self, event: LoweringEvent) -> None:
        if self._event_stack:
            self._event_stack[-1].children.append(event)
        else:
            self._root_events.append(event)
        self._event_stack.append(event)
        self._ir_before_count = len(self.instructions)

    def _pop_event(self, event: LoweringEvent) -> None:
        # Capture instructions emitted during this handler (not by children)
        new_instructions = self.instructions[self._ir_before_count :]
        # Only record instructions that aren't already captured by child events
        child_instructions = {
            id(inst) for child in event.children for inst in child.instructions_emitted
        }
        event.instructions_emitted = [
            inst for inst in new_instructions if id(inst) not in child_instructions
        ]
        self._event_stack.pop()
        if self._event_stack:
            self._ir_before_count = len(self.instructions)


def trace_lowering(
    source: str,
    language: str = "python",
) -> LoweringResult:
    """Run frontend lowering with tracing enabled, returning the event tree."""
    logger.info("trace_lowering: language=%s", language)

    frontend = get_frontend(language, frontend_type="deterministic")
    source_bytes = source.encode("utf-8")

    # Parse
    parser = TreeSitterParserFactory().get_parser(language)
    tree = parser.parse(source_bytes)

    # Build tracing context (mirrors BaseFrontend._lower_with_context)
    constants = frontend._build_constants()
    ctx = TracingEmitContext(
        source=source_bytes,
        language=Language(language),
        observer=NullFrontendObserver(),
        constants=constants,
        stmt_dispatch=frontend._build_stmt_dispatch(),
        expr_dispatch=frontend._build_expr_dispatch(),
        type_map=frontend._build_type_map(),
        type_env_builder=TypeEnvironmentBuilder(),
    )

    # Lower with tracing
    from interpreter import constants as const

    ctx.emit(Opcode.LABEL, label=const.CFG_ENTRY_LABEL)
    ctx.lower_block(tree.root_node)

    ir = ctx.instructions
    cfg = build_cfg(ir)

    return LoweringResult(
        source=source,
        language=language,
        events=ctx._root_events,
        ir=ir,
        cfg=cfg,
    )
