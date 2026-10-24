# pyright: standard
"""The entry point and the register state a standalone run enters it with."""

from hlasm_asg.program.default_entry import DefaultEntry
from hlasm_asg.program.hlasm_program import HlasmProgram
from hlasm_asg.program.named_entry import NamedEntry
from hlasm_asg.program.reloc_symbol import RelocSymbol
from hlasm_asg.program.section_kind import SectionKind
from interpreter.hlasm.hlasm_constants import (
    ABEND_VAR,
    ENTRY_ADDRESS_REGISTER,
    ENTRY_PARAMETER_REGISTER,
    ENTRY_RETURN_REGISTER,
    ENTRY_SAVE_AREA_REGISTER,
    NO_ABEND,
    RETURN_SENTINEL,
    SAVE_AREA_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.hlasm_entry import HlasmEntry
from interpreter.instructions import AllocRegion, Const, InstructionBase, StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def resolve_entry(program: HlasmProgram) -> HlasmEntry:
    match program.entry:
        case NamedEntry(name=name):
            symbol = next(
                s
                for s in program.symbols
                if isinstance(s, RelocSymbol) and s.name == name
            )
            return HlasmEntry(name, symbol.section, symbol.offset)
        case DefaultEntry():
            first = next(s for s in program.sections if s.kind == SectionKind.CSECT)
            return HlasmEntry(first.name, first.name, 0)


def entry_address(emitter: HlasmEmitter, entry: HlasmEntry) -> Register:
    base = emitter.section_base(entry.section)
    return emitter.binop(BinopKind.ADD, base, emitter.int_(entry.offset))


def _save_area(emitter: HlasmEmitter) -> Register:
    region = emitter.fresh_reg()
    emitter.emit_inst(
        AllocRegion(result_reg=region, size_reg=emitter.int_(SAVE_AREA_BYTES))
    )
    return region


def entry_state(program: HlasmProgram, module: str) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter("hlasm_entry.", module)
    entry = resolve_entry(program)
    abend = emitter.fresh_reg()
    emitter.emit_inst(Const.string(abend, NO_ABEND))
    emitter.emit_inst(StoreVar(name=ABEND_VAR, value_reg=abend))
    emitter.store_gr32(ENTRY_RETURN_REGISTER, emitter.int_(RETURN_SENTINEL))
    emitter.store_gr32(ENTRY_SAVE_AREA_REGISTER, _save_area(emitter))
    emitter.store_gr32(ENTRY_ADDRESS_REGISTER, entry_address(emitter, entry))
    emitter.store_gr32(ENTRY_PARAMETER_REGISTER, emitter.int_(0))
    return emitter.instructions()
