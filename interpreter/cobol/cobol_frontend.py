# pyright: standard
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

from interpreter.cobol.condition_name_index import build_condition_index
from interpreter.cobol.data_layout import DataLayout, build_data_layout
from interpreter.cobol.emit_context import EmitContext
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.cobol.field_resolution import (
    ResolvedFieldRef,
    parse_subscript_notation,
)
from interpreter.cobol.cobol_parser import CobolParser
from interpreter.cobol.lower_data_division import lower_data_division
from interpreter.cobol.lower_procedure import lower_procedure_division
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.frontend import Frontend
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.instructions import InstructionBase, Label_
from interpreter.ir import Opcode, CodeLabel

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
        cobol_parser: CobolParser,
        observer: FrontendObserver = NullFrontendObserver(),
    ):
        self._parser = cobol_parser
        self._observer = observer
        self._layout = DataLayout()
        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=observer,
        )

    @property
    def symbol_table(self) -> SymbolTable:
        return self._symbol_table

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
    def _instructions(self) -> list[InstructionBase]:
        return self._ctx._instructions

    @_instructions.setter
    def _instructions(self, value: list[InstructionBase]) -> None:
        self._ctx._instructions = value

    def _resolve_field_ref(
        self, name: str, layout: DataLayout, region_reg: str
    ) -> ResolvedFieldRef:
        return self._ctx.resolve_field_ref(name, layout, region_reg)

    def _has_field(self, name: str, layout: DataLayout) -> bool:
        return self._ctx.has_field(name, layout)

    # ── Main entry point ──────────────────────────────────────────

    @property
    def data_layout(self) -> dict[str, dict]:
        """Expose the COBOL data layout as a language-agnostic dict.

        Available after lower() has been called. Maps field names to
        offset, length, and type category info.
        """
        return {
            name: {
                "offset": fl.offset,
                "length": fl.byte_length,
                "category": fl.type_descriptor.category.value,
                "total_digits": fl.type_descriptor.total_digits,
                "decimal_digits": fl.type_descriptor.decimal_digits,
                "signed": fl.type_descriptor.signed,
            }
            for name, fl in self._layout.fields.items()
        }

    def lower(self, source: bytes) -> list[InstructionBase]:
        """Lower COBOL source to IR via the ProLeap bridge."""
        asg = self._parser.parse(source)
        layout = build_data_layout(asg.data_fields)
        self._layout = layout
        self._symbol_table = SymbolTable.from_data_layout(layout)
        condition_index = build_condition_index(layout.fields)

        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=self._observer,
            condition_index=condition_index,
        )

        self._ctx.emit_inst(Label_(label=CodeLabel("entry")))

        region_reg = lower_data_division(self._ctx, layout)
        lower_procedure_division(self._ctx, asg, layout, region_reg)

        logger.info(
            "COBOL frontend produced %d IR instructions",
            len(self._ctx.instructions),
        )
        return self._ctx.instructions
