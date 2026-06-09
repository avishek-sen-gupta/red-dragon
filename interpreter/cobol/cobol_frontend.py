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
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.cobol.cobol_parser import CobolParser
from interpreter.cobol.lower_data_division import (
    lower_sectioned_data_division,
)
from interpreter.cobol.lower_program_init import (
    lower_program_init,
    lower_ws_from_singleton,
)
from interpreter.refs.func_ref import FuncRef
from interpreter.cobol.lower_procedure import lower_procedure_division
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.frontend import Frontend
from interpreter.namespace_resolver import NamespaceResolver
from interpreter.path_name import PathName
from interpreter.cics.strategy import CatchAllLoweringStrategy, ExecCicsStrategy
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.instructions import InstructionBase, Label_
from interpreter.ir import CodeLabel
from interpreter.register import Register

logger = logging.getLogger(__name__)


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
        exec_cics_strategy: ExecCicsStrategy = CatchAllLoweringStrategy(),  # type: ignore[assignment]  # Pyright can't infer structural Protocol match for default args
    ):
        self._parser = cobol_parser
        self._observer = observer
        self._exec_cics_strategy = exec_cics_strategy
        self._layout = DataLayout()
        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=observer,
            exec_cics_strategy=exec_cics_strategy,
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

    @property
    def program_id(self) -> str:
        """COBOL PROGRAM-ID value. Available after lower() has been called."""
        return getattr(self, "_program_id", "MAIN")

    @property
    def func_symbol_table(self) -> dict[CodeLabel, FuncRef]:
        """Expose func_PROGRAMID_0 and func_init_params_PROGRAMID_0 so that
        Const instructions in the init block resolve to BoundFuncRef at runtime."""
        from interpreter.func_name import FuncName

        pid = self.program_id
        if not pid:
            return {}
        pid_lower = pid.lower()
        proc_label = CodeLabel(f"func_{pid_lower}_0")
        init_params_label = CodeLabel(f"func_init_params_{pid_lower}_0")
        return {
            proc_label: FuncRef(name=FuncName(str(proc_label)), label=proc_label),
            init_params_label: FuncRef(
                name=FuncName(str(init_params_label)), label=init_params_label
            ),
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
        self._program_id = asg.program_id or "MAIN"
        self._layout = sectioned.working_storage
        self._symbol_table = SymbolTable.from_data_layout(sectioned.working_storage)
        condition_index = build_condition_index(sectioned.working_storage)

        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=self._observer,
            condition_index=condition_index,
            exec_cics_strategy=self._exec_cics_strategy,
        )

        self._ctx.emit_inst(Label_(label=CodeLabel("entry")))

        # Emit singleton init block (ALLOC_REGION for WS lives here, runs once)
        after_label = lower_program_init(
            self._ctx, self._program_id, sectioned.working_storage
        )

        # Procedure division function — reachable only via __init_params__ dispatch
        proc_label = CodeLabel(f"func_{self._program_id.lower()}_0")
        self._ctx.emit_inst(Label_(label=proc_label))

        # Load persistent WS from singleton into __ws_region
        lower_ws_from_singleton(self._ctx, self._program_id)

        # Bind LINKAGE to __params_region (injected by handler); alloc fresh LS
        materialised = lower_sectioned_data_division(self._ctx, sectioned)
        lower_procedure_division(self._ctx, asg, materialised)

        # Skip target — init block branches here to skip past procedure body
        self._ctx.emit_inst(Label_(label=after_label))

        logger.info(
            "COBOL frontend produced %d IR instructions",
            len(self._ctx.instructions),
        )
        return self._ctx.instructions
