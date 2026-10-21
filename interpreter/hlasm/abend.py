# pyright: standard
"""Ends the run unit with an abend code recorded in the abend variable."""

from interpreter.hlasm.hlasm_constants import ABEND_VAR
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Const, Halt_, StoreVar


def emit_abend(emitter: HlasmEmitter, code: str) -> None:
    reg = emitter.fresh_reg()
    emitter.emit_inst(Const.string(reg, code))
    emitter.emit_inst(StoreVar(name=ABEND_VAR, value_reg=reg))
    emitter.emit_inst(Halt_())
