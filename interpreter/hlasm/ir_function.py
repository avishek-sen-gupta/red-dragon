# pyright: standard
"""An IR function the lowering emits once per program and calls by name: its body, parameters, definition and declaration; and the definition of every function called, those called from other function bodies included."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from interpreter.func_name import FuncName
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.program_function import ProgramFunction
from interpreter.instructions import (
    Branch,
    Const,
    DeclVar,
    Label_,
    Return_,
    Symbolic,
)
from interpreter.ir import CodeLabel
from interpreter.register import Register
from interpreter.var_name import VarName

type Body = Callable[[HlasmEmitter, Sequence[Register]], Register]


@dataclass(frozen=True)
class IrFunction(ProgramFunction):
    name: str
    arity: int
    body: Body

    @property
    def label(self) -> CodeLabel:
        return CodeLabel(f"func_{self.name}_0")

    def _parameter(self, emitter: HlasmEmitter, at: int) -> Register:
        name = VarName(f"{self.name}_{at}")
        value = emitter.fresh_reg()
        emitter.emit_inst(Symbolic(result_reg=value, hint=f"param:{name}"))
        emitter.emit_inst(DeclVar(name=name, value_reg=value))
        return emitter.load_var(name)

    def define(self, emitter: HlasmEmitter) -> None:
        end = CodeLabel(f"end_{self.name}_1")
        emitter.emit_inst(Branch(label=end))
        emitter.emit_inst(Label_(label=self.label))
        parameters = [self._parameter(emitter, at) for at in range(self.arity)]
        emitter.emit_inst(Return_(value_reg=self.body(emitter, parameters)))
        emitter.emit_inst(Label_(label=end))
        reference = emitter.fresh_reg()
        emitter.emit_inst(Const.func_ref(reference, self.label))
        emitter.emit_inst(DeclVar(name=VarName(self.name), value_reg=reference))

    def call(self, emitter: HlasmEmitter, arguments: Sequence[Register]) -> Register:
        emitter.use_function(self)
        return emitter.call(FuncName(self.name), tuple(arguments))


def define_called(
    emitter: HlasmEmitter, defined: tuple[ProgramFunction, ...] = ()
) -> tuple[ProgramFunction, ...]:
    names = {function.name for function in defined}
    pending = tuple(f for f in emitter.used_functions() if f.name not in names)
    if not pending:
        return defined
    _ = [function.define(emitter) for function in pending]
    return define_called(emitter, (*defined, *pending))
