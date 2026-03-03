"""COBOL frontend — lowers ProLeap JSON ASG to RedDragon IR.

Direct Frontend subclass (not BaseFrontend) since COBOL does not
use tree-sitter. Consumes CobolASG from the ProLeap bridge and
produces IR instructions for the VM.

This module is a slim orchestrator: it creates an EmitContext,
delegates lowering to focused modules, and re-exports symbols
for backward compatibility.
"""

from __future__ import annotations

import logging
from typing import Any

from interpreter.cobol.data_layout import DataLayout, build_data_layout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import (
    ResolvedFieldRef,
    parse_subscript_notation,
)
from interpreter.cobol.lower_data_division import lower_data_division
from interpreter.cobol.lower_procedure import lower_procedure_division
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.frontend import Frontend
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.ir import IRInstruction, Opcode

logger = logging.getLogger(__name__)

# Re-export for backward compatibility (used by test_occurs_frontend.py)
_parse_subscript_notation = parse_subscript_notation


class CobolFrontend(Frontend):
    """Lowers COBOL ASG (from ProLeap bridge) to RedDragon IR.

    Architecture: The ProLeap bridge (separate Java repo) parses COBOL
    source and emits JSON ASG. This frontend consumes that ASG and
    produces IR instructions.
    """

    def __init__(
        self,
        cobol_parser: Any,
        observer: FrontendObserver = NullFrontendObserver(),
    ):
        self._parser = cobol_parser
        self._observer = observer
        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=observer,
        )

    # ── Test-compatibility property proxies ────────────────────────

    @property
    def _reg_counter(self) -> int:
        return self._ctx._reg_counter

    @_reg_counter.setter
    def _reg_counter(self, value: int) -> None:
        self._ctx._reg_counter = value

    @property
    def _label_counter(self) -> int:
        return self._ctx._label_counter

    @_label_counter.setter
    def _label_counter(self, value: int) -> None:
        self._ctx._label_counter = value

    @property
    def _instructions(self) -> list[IRInstruction]:
        return self._ctx._instructions

    @_instructions.setter
    def _instructions(self, value: list[IRInstruction]) -> None:
        self._ctx._instructions = value

    def _resolve_field_ref(
        self, name: str, layout: DataLayout, region_reg: str
    ) -> ResolvedFieldRef:
        return self._ctx.resolve_field_ref(name, layout, region_reg)

    def _has_field(self, name: str, layout: DataLayout) -> bool:
        return self._ctx.has_field(name, layout)

    # ── Main entry point ──────────────────────────────────────────

    def lower(self, source: bytes) -> list[IRInstruction]:
        """Lower COBOL source to IR via the ProLeap bridge."""
        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=self._observer,
        )

        asg = self._parser.parse(source)
        layout = build_data_layout(asg.data_fields)

        self._ctx.emit(Opcode.LABEL, label="entry")

        region_reg = lower_data_division(self._ctx, layout)
        lower_procedure_division(self._ctx, asg, layout, region_reg)

        logger.info(
            "COBOL frontend produced %d IR instructions",
            len(self._ctx.instructions),
        )
        return self._ctx.instructions
