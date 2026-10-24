# pyright: standard
"""Lowers an assembled HLASM program to one IR function entered at its entry point, then defines the IR functions its lowerings called."""

from functools import cached_property

from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.statement import Statement
from interpreter.frontend import Frontend
from interpreter.func_name import FuncName
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.assembly_diagnostics import assembly_diagnostics
from interpreter.hlasm.branch_dispatch import (
    emit_branch,
    emit_dispatch,
    statement_label,
)
from interpreter.hlasm.entry_state import entry_address, entry_state, resolve_entry
from interpreter.hlasm.hlasm_constants import OPERATION_EXCEPTION_ABEND
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import define_called
from interpreter.hlasm.lower_statement import lower_statement
from interpreter.hlasm.machine import (
    access_register_allocation,
    floating_point_allocation,
    machine_allocation,
)
from interpreter.hlasm.machine_statements import MachineStatements
from interpreter.hlasm.program_function import ProgramFunction
from interpreter.hlasm.statement_location import statement_location
from interpreter.hlasm.storage_layout import section_allocation
from interpreter.instructions import Branch, InstructionBase, Label_
from interpreter.ir import CodeLabel
from interpreter.namespace_resolver import NamespaceResolver
from interpreter.project.unit_diagnostic import UnitDiagnostic
from interpreter.refs.func_ref import FuncRef


class HlasmFrontend(Frontend):
    """The assembly is injected already parsed; lower() ignores its source bytes."""

    def __init__(self, program: HlasmProgram) -> None:
        self._program = program
        self._entry = resolve_entry(program)
        self._statements = MachineStatements(program.statements)

    @property
    def entry_name(self) -> str:
        return self._entry.name

    @property
    def diagnostics(self) -> tuple[UnitDiagnostic, ...]:
        return assembly_diagnostics(self._program)

    @property
    def entry_label(self) -> CodeLabel:
        return CodeLabel(f"func_{self._entry.name.lower()}_0")

    @property
    def func_symbol_table(self) -> dict[CodeLabel, FuncRef]:
        label = self.entry_label
        return {
            label: FuncRef(name=FuncName(str(label)), label=label),
            **{
                f.label: FuncRef(name=FuncName(f.name), label=f.label)
                for f in self._lowered[1]
            },
        }

    def start_up_ir(self) -> tuple[InstructionBase, ...]:
        return (
            *machine_allocation(),
            *section_allocation(self._program),
            *entry_state(self._program),
            *access_register_allocation(),
            *floating_point_allocation(),
        )

    def lower(
        self,
        source: bytes,
        namespace_resolver: NamespaceResolver = Frontend._NULL_RESOLVER,
    ) -> list[InstructionBase]:
        return list(self._lowered[0])

    @cached_property
    def _lowered(
        self,
    ) -> tuple[tuple[InstructionBase, ...], tuple[ProgramFunction, ...]]:
        emitter = HlasmEmitter()
        self._lower_entry(emitter)
        functions = define_called(emitter)
        return emitter.instructions(), functions

    def _lower_entry(self, emitter: HlasmEmitter) -> None:
        end_label = CodeLabel(f"end_{self._entry.name.lower()}_1")
        emitter.emit_inst(Label_(label=CodeLabel("entry")))
        emitter.emit_inst(Branch(label=end_label))
        emitter.emit_inst(Label_(label=self.entry_label))
        emit_branch(emitter, entry_address(emitter, self._entry))
        _ = [
            self._lower_placed(emitter, statement, labelled)
            for statement, labelled in self._placed_statements()
        ]
        emit_abend(emitter, OPERATION_EXCEPTION_ABEND)
        emit_dispatch(emitter, self._program)
        emitter.emit_inst(Label_(label=end_label))

    def _placed_statements(self) -> tuple[tuple[Statement, bool], ...]:
        rank = {s.name: at for at, s in enumerate(self._program.sections)}
        positioned = sorted(
            (rank[s.section], s.offset, at)
            for at, s in enumerate(self._program.statements)
        )
        ordered = [self._program.statements[place[2]] for place in positioned]
        first = {
            (s.section, s.offset): at for at, s in reversed(list(enumerate(ordered)))
        }
        return tuple(
            (s, first[(s.section, s.offset)] == at) for at, s in enumerate(ordered)
        )

    def _lower_placed(
        self, emitter: HlasmEmitter, statement: Statement, labelled: bool
    ) -> None:
        if labelled:
            emitter.emit_inst(
                Label_(label=statement_label(statement.section, statement.offset))
            )
        start = emitter.emitted_count()
        lower_statement(emitter, statement, self._statements)
        emitter.locate_from(start, statement_location(statement.origin))
