# pyright: standard
"""The image's start-up IR, run once: the machine state, one doubleword-aligned region per module with its sections' variables, one region per common section, the stub range, every TXT record and then every RLD."""

from collections.abc import Sequence

from interpreter.hlasm.binder import Binder, aligned
from interpreter.hlasm.bound_name import BoundName
from interpreter.hlasm.hlasm_constants import (
    ABEND_VAR,
    DOUBLEWORD_BYTES,
    NO_ABEND,
    STUB_BYTES,
    STUBS_HIGH_VAR,
    STUBS_LOW_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.image_module import ImageModule
from interpreter.hlasm.machine import (
    access_register_allocation,
    floating_point_allocation,
    machine_allocation,
)
from interpreter.hlasm.placed_name import PlacedName
from interpreter.hlasm.section_variable import section_var
from interpreter.hlasm.stub_name import StubName
from interpreter.hlasm.weak_zero import WeakZero
from interpreter.instructions import AllocRegion, Const, InstructionBase, StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.project.common_section import CommonSection
from interpreter.project.relocation_record import RelocationRecord
from interpreter.project.relocation_sign import RelocationSign
from interpreter.project.text_record import TextRecord
from interpreter.register import Register


def aligned_region(emitter: HlasmEmitter, length: Register) -> Register:
    slack = emitter.int_(DOUBLEWORD_BYTES - 1)
    region = emitter.fresh_reg()
    emitter.emit_inst(
        AllocRegion(
            result_reg=region, size_reg=emitter.binop(BinopKind.ADD, length, slack)
        )
    )
    end = emitter.binop(BinopKind.ADD, region, slack)
    return emitter.binop(
        BinopKind.SUB,
        end,
        emitter.binop(BinopKind.MOD, end, emitter.int_(DOUBLEWORD_BYTES)),
    )


def _store_section(
    emitter: HlasmEmitter, module: str, section: str, address: Register
) -> None:
    emitter.emit_inst(StoreVar(name=section_var(module, section), value_reg=address))


def _lay_out_module(emitter: HlasmEmitter, binder: Binder, module: str) -> None:
    layout = binder.layouts[module]
    base = aligned_region(emitter, emitter.int_(layout.length))
    _ = [
        _store_section(
            emitter, module, name, emitter.binop(BinopKind.ADD, base, emitter.int_(at))
        )
        for name, at in layout.offsets.items()
    ]


def _lay_out_common(
    emitter: HlasmEmitter, binder: Binder, common: tuple[str, int]
) -> None:
    name, length = common
    address = aligned_region(emitter, emitter.int_(aligned(length, DOUBLEWORD_BYTES)))
    _ = [
        _store_section(emitter, module.name, name, address)
        for module in binder.modules
        if any(
            isinstance(r, CommonSection) and r.name == name
            for r in module.object_module.esd
        )
    ]


def _lay_out_stubs(emitter: HlasmEmitter, binder: Binder) -> None:
    length = emitter.int_(STUB_BYTES * len(binder.stubs))
    low = aligned_region(emitter, length)
    emitter.emit_inst(StoreVar(name=STUBS_LOW_VAR, value_reg=low))
    high = emitter.binop(BinopKind.ADD, low, length)
    emitter.emit_inst(StoreVar(name=STUBS_HIGH_VAR, value_reg=high))


def _write_text(emitter: HlasmEmitter, module: str, record: TextRecord) -> None:
    emitter.store_storage(
        emitter.load_var(section_var(module, record.section)),
        record.offset,
        len(record.image),
        emitter.int_(int.from_bytes(record.image, "big")),
    )


def _unplaced_address(emitter: HlasmEmitter, bound: StubName | WeakZero) -> Register:
    match bound:
        case StubName(index=index):
            low = emitter.load_var(STUBS_LOW_VAR)
            return emitter.binop(BinopKind.ADD, low, emitter.int_(STUB_BYTES * index))
        case WeakZero():
            return emitter.int_(0)


def bound_address(emitter: HlasmEmitter, bound: BoundName) -> Register:
    match bound:
        case PlacedName(module=module, section=section, offset=offset):
            base = emitter.load_var(section_var(module, section))
            return emitter.binop(BinopKind.ADD, base, emitter.int_(offset))
        case _:
            return _unplaced_address(emitter, bound)


def _signed(
    emitter: HlasmEmitter, record: RelocationRecord, address: Register
) -> Register:
    match record.sign:
        case RelocationSign.PLUS:
            return address
        case RelocationSign.MINUS:
            return emitter.binop(BinopKind.SUB, emitter.int_(0), address)


def _relocate(
    emitter: HlasmEmitter, binder: Binder, module: ImageModule, record: RelocationRecord
) -> None:
    address = bound_address(emitter, binder.resolve(module, record.target))
    value = emitter.binop(
        BinopKind.ADD, _signed(emitter, record, address), emitter.int_(record.addend)
    )
    emitter.store_storage(
        emitter.load_var(section_var(module.name, record.section)),
        record.offset,
        record.length,
        value,
    )


def _machine_state(emitter: HlasmEmitter) -> None:
    _ = [emitter.emit_inst(inst) for inst in machine_allocation()]
    abend = emitter.fresh_reg()
    emitter.emit_inst(Const.string(abend, NO_ABEND))
    emitter.emit_inst(StoreVar(name=ABEND_VAR, value_reg=abend))


def _lay_out(emitter: HlasmEmitter, binder: Binder) -> None:
    modules: Sequence[ImageModule] = binder.modules
    commons = binder.commons.items()
    _ = (
        [_lay_out_module(emitter, binder, module.name) for module in modules],
        [_lay_out_common(emitter, binder, c) for c in commons],
    )
    _lay_out_stubs(emitter, binder)


def _load(emitter: HlasmEmitter, binder: Binder) -> None:
    _ = (
        [
            _write_text(emitter, module.name, record)
            for module in binder.modules
            for record in module.object_module.text
        ],
        [
            _relocate(emitter, binder, module, record)
            for module in binder.modules
            for record in module.object_module.relocations
        ],
    )


def bound_start_up(binder: Binder) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter("hlasm_bind.")
    _machine_state(emitter)
    _lay_out(emitter, binder)
    _load(emitter, binder)
    registers = (*access_register_allocation(), *floating_point_allocation())
    _ = [emitter.emit_inst(inst) for inst in registers]
    return emitter.instructions()
