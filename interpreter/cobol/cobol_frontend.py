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
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    build_sectioned_layout,
)
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.cobol.field_resolution import (
    ResolvedFieldRef,
    parse_subscript_notation,
)
from interpreter.cobol.cobol_parser import CobolParser
from interpreter.cobol.lower_data_division import (
    lower_data_division,
    lower_sectioned_data_division,
)
from interpreter.cobol.lower_procedure import lower_procedure_division
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.frontend import Frontend
from interpreter.namespace_resolver import NamespaceResolver
from interpreter.path_name import PathName
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.instructions import InstructionBase, Label_, StoreVar
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName

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
        self, name: str, materialised: MaterialisedSectionedLayout
    ) -> tuple[ResolvedFieldRef, Register]:
        return self._ctx.resolve_field_ref(name, materialised)

    def _has_field(self, name: str, materialised: MaterialisedSectionedLayout) -> bool:
        return self._ctx.has_field(name, materialised)

    # ── Main entry point ──────────────────────────────────────────

    @property
    def data_layout(self) -> dict[str, dict]:
        """Expose the COBOL data layout as a language-agnostic dict.

        Available after lower() has been called. Maps field names to
        offset, length, and type category info.
        """
        return {
            fl.name: {
                "offset": fl.offset,
                "length": fl.byte_length,
                "category": fl.type_descriptor.category.value,
                "total_digits": fl.type_descriptor.total_digits,
                "decimal_digits": fl.type_descriptor.decimal_digits,
                "signed": fl.type_descriptor.signed,
            }
            for fl in self._layout.all_fields()
        }

    def lower(
        self,
        source: bytes,
        namespace_resolver: NamespaceResolver = Frontend._NULL_RESOLVER,
        resolved_imports: dict[str, PathName] | None = None,
    ) -> list[InstructionBase]:
        """Lower COBOL source to IR via the ProLeap bridge."""
        asg = self._parser.parse(source)
        sectioned = build_sectioned_layout(asg)
        self._layout = sectioned.working_storage
        self._symbol_table = SymbolTable.from_data_layout(sectioned.working_storage)
        condition_index = build_condition_index(sectioned.working_storage)

        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=self._observer,
            condition_index=condition_index,
        )

        self._ctx.emit_inst(Label_(label=CodeLabel("entry")))

        # TODO(Task 5): remove this inline alloc once CobolFrontend emits a
        # proper init block via lower_program_init.  In the full singleton
        # model the allocation happens inside the init block; for the current
        # standalone / test execution path we emit it inline here so that
        # lower_sectioned_data_division (which emits LOAD_VAR __ws_region)
        # finds the variable in scope.
        ws_reg = lower_data_division(self._ctx, sectioned.working_storage)
        self._ctx.emit_inst(StoreVar(name=VarName("__ws_region"), value_reg=ws_reg))

        materialised = lower_sectioned_data_division(self._ctx, sectioned)
        lower_procedure_division(self._ctx, asg, materialised)

        logger.info(
            "COBOL frontend produced %d IR instructions",
            len(self._ctx.instructions),
        )
        return self._ctx.instructions
