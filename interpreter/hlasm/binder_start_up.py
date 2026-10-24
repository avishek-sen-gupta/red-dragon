# pyright: standard
"""The image's start-up IR, run once: the machine state, a bit per module for the far branch, one doubleword-aligned region per module with its sections' variables, one region per common section, the stub range, every TXT record, every RLD (an address, a pseudo-register offset or length, or their total; the signed items at one field, wherever they sit, summed and stored once), and the names table LINK and LOAD read."""

from collections.abc import Callable, Mapping, Sequence
from functools import reduce

from interpreter.hlasm.binder import Binder, aligned
from interpreter.hlasm.bound_name import BoundName
from interpreter.hlasm.hlasm_constants import (
    ABEND_VAR,
    DOUBLEWORD_BYTES,
    LINKING_VAR,
    MODULE_BIT_PREFIX,
    NAME_ADDRESS_FIELD,
    NAME_LENGTH_FIELD,
    NAME_LOADS_FIELD,
    NAMES_VAR,
    NO_ABEND,
    PROGRAM_NAME_BYTES,
    PROGRAM_NAME_CODEC,
    STUB_BYTES,
    STUBS_HIGH_VAR,
    STUBS_LOW_VAR,
    TARGET_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.image_module import ImageModule
from interpreter.hlasm.machine import (
    access_register_allocation,
    floating_point_allocation,
    machine_allocation,
)
from interpreter.hlasm.placed_name import PlacedName
from interpreter.hlasm.pseudo_register import PseudoRegister
from interpreter.hlasm.section_variable import section_var
from interpreter.hlasm.stub_name import StubName
from interpreter.hlasm.weak_zero import WeakZero
from interpreter.instructions import (
    AllocRegion,
    Const,
    InstructionBase,
    NewObject,
    StoreField,
    StoreIndex,
    StoreVar,
)
from interpreter.operator_kind import BinopKind
from interpreter.project.common_section import CommonSection
from interpreter.project.no_relocation_target import NoRelocationTarget
from interpreter.project.relocation_kind import RelocationKind
from interpreter.project.relocation_name import RelocationName
from interpreter.project.relocation_record import RelocationRecord
from interpreter.project.relocation_sign import RelocationSign
from interpreter.project.text_record import TextRecord
from interpreter.register import Register
from interpreter.var_name import VarName

_PSEUDO_REGISTER_FACTS: Mapping[RelocationKind, Callable[[PseudoRegister], int]] = {
    RelocationKind.PR_OFFSET: lambda register: register.offset,
    RelocationKind.CLASS_LENGTH: lambda register: register.length,
}


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


def _named_value(
    emitter: HlasmEmitter,
    binder: Binder,
    module: ImageModule,
    named: tuple[RelocationKind, str],
) -> Register:
    kind, name = named
    if kind in _PSEUDO_REGISTER_FACTS:
        return emitter.int_(_PSEUDO_REGISTER_FACTS[kind](binder.pseudo_registers[name]))
    return bound_address(emitter, binder.resolve(module, name))


def _target_value(
    emitter: HlasmEmitter, binder: Binder, module: ImageModule, record: RelocationRecord
) -> Register:
    match record.target:
        case NoRelocationTarget():
            return emitter.int_(binder.pseudo_register_total)
        case RelocationName(name=name):
            return _named_value(emitter, binder, module, (record.kind, name))


def _item_value(
    emitter: HlasmEmitter, binder: Binder, module: ImageModule, record: RelocationRecord
) -> Register:
    target = _target_value(emitter, binder, module, record)
    return emitter.binop(
        BinopKind.ADD, _signed(emitter, record, target), emitter.int_(record.addend)
    )


def _relocate(
    emitter: HlasmEmitter,
    binder: Binder,
    module: ImageModule,
    records: Sequence[RelocationRecord],
) -> None:
    value = reduce(
        lambda total, record: emitter.binop(
            BinopKind.ADD, total, _item_value(emitter, binder, module, record)
        ),
        records[1:],
        _item_value(emitter, binder, module, records[0]),
    )
    field = records[0]
    emitter.store_storage(
        emitter.load_var(section_var(module.name, field.section)),
        field.offset,
        field.length,
        value,
    )


def _fields(module: ImageModule) -> tuple[tuple[RelocationRecord, ...], ...]:
    relocations = module.object_module.relocations
    places = tuple(map(_place, relocations))
    return tuple(
        tuple(r for r in relocations if _place(r) == place)
        for at, place in enumerate(places)
        if place not in places[:at]
    )


def _place(record: RelocationRecord) -> tuple[str, int]:
    return record.section, record.offset


def _machine_state(emitter: HlasmEmitter) -> None:
    _ = [emitter.emit_inst(inst) for inst in machine_allocation()]
    abend = emitter.fresh_reg()
    emitter.emit_inst(Const.string(abend, NO_ABEND))
    emitter.emit_inst(StoreVar(name=ABEND_VAR, value_reg=abend))
    _dispatch_state(emitter)


def _dispatch_state(emitter: HlasmEmitter) -> None:
    _ = [
        emitter.emit_inst(StoreVar(name=name, value_reg=emitter.int_(0)))
        for name in (TARGET_VAR, LINKING_VAR)
    ]


def program_name_image(name: str) -> int:
    return int.from_bytes(
        name.ljust(PROGRAM_NAME_BYTES).encode(PROGRAM_NAME_CODEC), "big"
    )


def _name_entry(
    emitter: HlasmEmitter, binder: Binder, named: tuple[str, PlacedName]
) -> None:
    name, placed = named
    entry = emitter.fresh_reg()
    emitter.emit_inst(NewObject(result_reg=entry))
    fields = (
        (NAME_ADDRESS_FIELD, bound_address(emitter, placed)),
        (
            NAME_LENGTH_FIELD,
            emitter.int_(binder.layouts[placed.module].length // DOUBLEWORD_BYTES),
        ),
        (NAME_LOADS_FIELD, emitter.int_(0)),
    )
    _ = [
        emitter.emit_inst(StoreField(obj_reg=entry, field_name=f, value_reg=v))
        for f, v in fields
    ]
    emitter.emit_inst(
        StoreIndex(
            arr_reg=emitter.load_var(NAMES_VAR),
            index_reg=emitter.int_(program_name_image(name)),
            value_reg=entry,
        )
    )


def _names(emitter: HlasmEmitter, binder: Binder) -> None:
    table = emitter.fresh_reg()
    emitter.emit_inst(NewObject(result_reg=table))
    emitter.emit_inst(StoreVar(name=NAMES_VAR, value_reg=table))
    _ = [_name_entry(emitter, binder, named) for named in binder.entry_points().items()]


def _module_bits(emitter: HlasmEmitter, binder: Binder) -> None:
    _ = [
        emitter.emit_inst(
            StoreVar(
                name=VarName(f"{MODULE_BIT_PREFIX}{module.name}"),
                value_reg=emitter.int_(1 << index),
            )
        )
        for index, module in enumerate(binder.modules)
    ]


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
            _relocate(emitter, binder, module, records)
            for module in binder.modules
            for records in _fields(module)
        ],
    )


def bound_start_up(binder: Binder) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter("hlasm_bind.")
    _machine_state(emitter)
    _module_bits(emitter, binder)
    _lay_out(emitter, binder)
    _load(emitter, binder)
    _names(emitter, binder)
    registers = (*access_register_allocation(), *floating_point_allocation())
    _ = [emitter.emit_inst(inst) for inst in registers]
    return emitter.instructions()
