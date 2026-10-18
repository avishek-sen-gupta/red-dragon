"""Emits IR built from primitive builtins, with branches and loop variables, into a lowering's stream."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from cobol_asg.source_span import SourceSpan
from cobol_numeric.number import CobolNumber
from interpreter.cobol.emit_context import EmitContext
from interpreter.constants import FoundationTypeName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Const,
    Label_,
    LoadVar,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import resolve_binop
from interpreter.register import Register
from interpreter.types.type_expr import array_of, scalar
from interpreter.var_name import VarName


@dataclass(frozen=True)
class IrEmitter:
    """Emits one statement's IR through its EmitContext, all at one source span."""

    ctx: EmitContext
    span: SourceSpan | None

    def int_(self, value: int) -> Register:
        reg = self.ctx.fresh_reg()
        self.ctx.emit_inst(Const.int_(reg, value), span=self.span)
        return reg

    def text(self, value: str) -> Register:
        reg = self.ctx.fresh_reg()
        self.ctx.emit_inst(Const.string(reg, value), span=self.span)
        return reg

    def texts(self, values: Sequence[str]) -> Register:
        reg = self.ctx.fresh_reg()
        self.ctx.emit_inst(
            Const(
                result_reg=reg,
                value=list(values),
                type_expr=array_of(scalar(FoundationTypeName.STRING)),
            ),
            span=self.span,
        )
        return reg

    def decimal(self, value: CobolNumber) -> Register:
        reg = self.ctx.fresh_reg()
        self.ctx.emit_inst(Const.decimal_(reg, value), span=self.span)
        return reg

    def bool_(self, value: bool) -> Register:
        reg = self.ctx.fresh_reg()
        self.ctx.emit_inst(Const.bool_(reg, value), span=self.span)
        return reg

    def call(self, builtin: str, *args: Register) -> Register:
        reg = self.ctx.fresh_reg()
        self.ctx.emit_inst(
            CallFunction(result_reg=reg, func_name=FuncName(builtin), args=args),
            span=self.span,
        )
        return reg

    def binop(self, operator: str, left: Register, right: Register) -> Register:
        reg = self.ctx.fresh_reg()
        self.ctx.emit_inst(
            Binop(
                result_reg=reg,
                operator=resolve_binop(operator),
                left=left,
                right=right,
            ),
            span=self.span,
        )
        return reg

    def var(self, prefix: str, initial: Register) -> VarName:
        name = VarName(self.ctx.fresh_name(prefix))
        self.store(name, initial)
        return name

    def store(self, name: VarName, value: Register) -> None:
        self.ctx.emit_inst(StoreVar(name=name, value_reg=value), span=self.span)

    def load(self, name: VarName) -> Register:
        reg = self.ctx.fresh_reg()
        self.ctx.emit_inst(LoadVar(result_reg=reg, name=name), span=self.span)
        return reg

    def label(self, prefix: str) -> CodeLabel:
        return self.ctx.fresh_label(prefix)

    def place(self, label: CodeLabel) -> None:
        self.ctx.emit_inst(Label_(label=label), span=self.span)

    def jump(self, label: CodeLabel) -> None:
        self.ctx.emit_inst(Branch(label=label), span=self.span)

    def branch_if(
        self, cond: Register, taken: CodeLabel, fallthrough: CodeLabel
    ) -> None:
        self.ctx.emit_inst(
            BranchIf(cond_reg=cond, branch_targets=(taken, fallthrough)),
            span=self.span,
        )

    def skip_if(self, cond: Register, target: CodeLabel) -> None:
        """Branch to ``target`` when ``cond`` holds, else fall through."""
        stay = self.label("stay")
        self.branch_if(cond, target, stay)
        self.place(stay)

    def choose(
        self,
        prefix: str,
        default: Register,
        keep_default: Register,
        otherwise: Callable[[], Register],
    ) -> Register:
        """``default`` when ``keep_default`` holds, else what ``otherwise`` emits."""
        chosen = self.var(prefix, default)
        done = self.label(f"{prefix}_chosen")
        self.skip_if(keep_default, done)
        self.store(chosen, otherwise())
        self.place(done)
        return self.load(chosen)

    def loop(self, prefix: str, body: Callable[[CodeLabel, CodeLabel], None]) -> None:
        """A loop whose ``body`` gets its head and exit labels; reaching the end
        of the body returns to the head."""
        head, done = self.label(f"{prefix}_head"), self.label(f"{prefix}_done")
        self.place(head)
        body(head, done)
        self.jump(head)
        self.place(done)
