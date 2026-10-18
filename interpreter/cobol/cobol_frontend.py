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
from collections.abc import Sequence
from typing import TYPE_CHECKING

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_parser import CobolParser
from cobol_asg.cobol_statements import dialect_parsers_in_scope
from cobol_asg.frontend_extension import DialectParser
from interpreter.cobol.compile_options import CompileOptions
from interpreter.cobol.condition_name_index import build_condition_index_over
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.cobol.file_declarations import lower_file_declarations
from interpreter.cobol.file_definitions_data import file_definitions_data
from interpreter.cobol.layout_data import layout_data
from interpreter.cobol.lower_data_division import (
    lower_sectioned_data_division,
)
from interpreter.cobol.lower_external import lower_external_areas
from interpreter.cobol.lower_procedure import lower_procedure_division
from interpreter.cobol.lower_program_init import (
    lower_program_init,
    lower_ws_from_singleton,
)
from interpreter.cobol.program_object import UNNAMED_PROGRAM, program_name
from interpreter.cobol.run_unit import run_unit_allocation
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    build_sectioned_layout,
)
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.frontend import Frontend
from interpreter.frontend_extension_lowering import RedDragonExtensionLoweringStrategy
from interpreter.frontend_observer import FrontendObserver, NullFrontendObserver
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.instructions import InstructionBase, Label_
from interpreter.ir import CodeLabel
from interpreter.namespace_resolver import NamespaceResolver
from interpreter.path_name import PathName
from interpreter.refs.func_ref import FuncRef
from interpreter.register import Register

if TYPE_CHECKING:
    from cobol_asg.cobol_expression import ExprNode

logger = logging.getLogger(__name__)
_DEFAULT_OPTIONS = CompileOptions()


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
        extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
        dialect_parsers: Sequence[DialectParser] = (),
        options: CompileOptions = _DEFAULT_OPTIONS,
    ):
        self._parser = cobol_parser
        self._options = options
        self._addressing_mode = options.addressing_mode
        self._observer = observer
        self._extension_strategies = tuple(extension_strategies)
        self._dialect_parsers = tuple(dialect_parsers)
        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=observer,
            extension_strategies=self._extension_strategies,
            options=options,
        )

    def start_up_ir(self) -> tuple[InstructionBase, ...]:
        return run_unit_allocation()

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
        self,
        name: str,
        materialised: MaterialisedSectionedLayout,
        qualifiers: tuple[str, ...] = (),
        subscripts: tuple[ExprNode, ...] = (),
    ) -> tuple[ResolvedFieldRef, Register]:
        return self._ctx.resolve_field_ref(
            name, materialised, qualifiers=qualifiers, subscripts=subscripts
        )

    def _has_field(self, name: str, materialised: MaterialisedSectionedLayout) -> bool:
        return self._ctx.has_field(name, materialised)

    # ── Main entry point ──────────────────────────────────────────

    @property
    def program_id(self) -> str:
        """COBOL PROGRAM-ID value. Available after lower() has been called."""
        return getattr(self, "_program_id", UNNAMED_PROGRAM)

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
        resolved_imports: dict[str, PathName] = {},
    ) -> list[InstructionBase]:
        """Lower the first program of COBOL source to IR via the ProLeap bridge."""

        def _chained_preprocess(data: dict) -> dict:
            for strat in self._extension_strategies:
                data = strat.preprocess_program_dict(data)
            return data

        with dialect_parsers_in_scope(self._dialect_parsers):
            unit = self._parser.parse(source, preprocessor=_chained_preprocess)
        return self._lower_asg(unit.first_program)

    def lower_from_ast_dict(self, data: dict) -> list[InstructionBase]:
        """Lower one program from its raw bridge JSON dict — no subprocess, no
        source bytes. *data* is one program object of a compilation unit, as
        :func:`cobol_asg.compilation_unit.programs_in_preorder` yields it.

        Applies extension strategy preprocessors (same as lower()) then lowers
        the resulting ASG to IR. Use this in Phase 2 of the AST cache pipeline
        after parse_to_file has written ASTs to disk.
        """
        with dialect_parsers_in_scope(self._dialect_parsers):
            for strat in self._extension_strategies:
                data = strat.preprocess_program_dict(data)
            asg = CobolASG.from_dict(data, self._addressing_mode)
        return self._lower_asg(asg)

    def _lower_asg(self, asg: CobolASG) -> list[InstructionBase]:
        """Shared lowering core: ASG → IR. Called by lower() and lower_from_ast_dict()."""
        sectioned = build_sectioned_layout(asg)
        self._program_id = program_name(asg)
        logger.debug(
            "lowering %s: %d sections, %d paragraphs",
            self._program_id,
            len(asg.sections),
            len(asg.paragraphs),
        )
        self._symbol_table = SymbolTable.from_data_layout(sectioned.working_storage)
        condition_index = build_condition_index_over(
            (
                sectioned.file,
                sectioned.linkage,
                sectioned.local_storage,
                sectioned.working_storage,
                sectioned.external,
            )
        )

        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=self._observer,
            condition_index=condition_index,
            extension_strategies=self._extension_strategies,
            asg=asg,
            options=self._options,
        )

        self._ctx.emit_inst(Label_(label=CodeLabel("entry")))
        self._ctx.emit_inst(file_definitions_data(asg))
        self._ctx.emit_inst(layout_data(sectioned.working_storage.all_fields()))
        lower_file_declarations(self._ctx, sectioned)
        lower_external_areas(self._ctx, sectioned.external_areas)

        # Emit singleton init block (ALLOC_REGION for WS lives here, runs once)
        after_label = lower_program_init(
            self._ctx, self._program_id, sectioned.working_storage
        )

        # Procedure division function — entered through the program's entry function
        proc_label = CodeLabel(f"func_{self._program_id.lower()}_0")
        self._ctx.emit_inst(Label_(label=proc_label))

        # Load persistent WS from singleton into __ws_region
        lower_ws_from_singleton(self._ctx, self._program_id)

        # Bind each LINKAGE 01 to its argument in __call_arguments; alloc fresh LS
        materialised = lower_sectioned_data_division(
            self._ctx, sectioned, self._program_id
        )
        lower_procedure_division(self._ctx, asg, materialised)

        # Skip target — init block branches here to skip past procedure body
        self._ctx.emit_inst(Label_(label=after_label))

        logger.debug(
            "COBOL frontend produced %d IR instructions",
            len(self._ctx.instructions),
        )
        return self._ctx.instructions
