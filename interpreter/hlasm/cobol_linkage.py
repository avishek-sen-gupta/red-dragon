# pyright: standard
"""Calls between COBOL and HLASM: a COBOL argument array turned into a standard R1 list for an HLASM entry, and an R1 list walked by a COBOL program's USING signature into its argument array."""

from collections.abc import Callable, Sequence

from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.hlasm.binder_start_up import aligned_region, bound_address
from interpreter.hlasm.byte_loop import emit_counted_loop
from interpreter.hlasm.cobol_program import CobolProgram
from interpreter.hlasm.entry_state import enter_registers
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    BINARY_BYTES_TO_INT,
    DOUBLEWORD_BYTES,
    ENTRY_ADDRESS_REGISTER,
    ENTRY_PARAMETER_REGISTER,
    ENTRY_SAVE_AREA_REGISTER,
    HALFWORD_BYTES,
    LAST_PARAMETER_BIT,
    LINK_REGISTER,
    LOW_WORD_MASK,
    MODULE_FUNCTION_PREFIX,
    PROGRAM_ENTRY_PREFIX,
    RETURN_CODE_REGISTER,
    TARGET_VAR,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import IrFunction
from interpreter.hlasm.placed_name import PlacedName
from interpreter.instructions import (
    AllocRegion,
    Branch,
    BranchIf,
    CallWithMemory,
    Const,
    DeclVar,
    Label_,
    LoadField,
    LoadIndex,
    NewArray,
    NewObject,
    Return_,
    StoreField,
    StoreIndex,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.project.argument_mode import ArgumentMode
from interpreter.project.using_parameter import UsingParameter
from interpreter.register import Register
from interpreter.var_name import VarName

FROM_COBOL_FUNCTION = "__hlasm_from_cobol"
COUNT_FIELD = FieldName("count")
MODE_FIELD = FieldName("mode")
LENGTH_FIELD = FieldName("length")
REGION_FIELD = FieldName("region")
OFFSET_FIELD = FieldName("offset")
SLOT_VAR = VarName("__hlasm_slot")
LAST_MODE_VAR = VarName("__hlasm_last_mode")
LAST_SLOT_VAR = VarName("__hlasm_last_slot")
WALKED_VAR = VarName("__hlasm_walked")
SAVED_REGISTERS = (14, 15, *range(13))
SAVE_AREA_REGISTERS_AT = 12
RIGHT_ALIGNED_LENGTHS = (1, 2, 4)
NOTHING_BELOW = 0
CALLED = 0
SIGNED = True

type Case = Callable[[], None]


def _field(emitter: HlasmEmitter, obj: Register, field: FieldName) -> Register:
    value = emitter.fresh_reg()
    emitter.emit_inst(LoadField(result_reg=value, obj_reg=obj, field_name=field))
    return value


def _store(
    emitter: HlasmEmitter, obj: Register, field: FieldName, value: Register
) -> None:
    emitter.emit_inst(StoreField(obj_reg=obj, field_name=field, value_reg=value))


def _case(
    emitter: HlasmEmitter, done: CodeLabel, condition: Register, body: Case
) -> None:
    taken = emitter.fresh_label("hl_cobol_case")
    other = emitter.fresh_label("hl_cobol_next")
    emitter.emit_inst(BranchIf(cond_reg=condition, branch_targets=(taken, other)))
    emitter.emit_inst(Label_(label=taken))
    body()
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=other))


def _cases(
    emitter: HlasmEmitter, cases: Sequence[tuple[Register, Case]], otherwise: Case
) -> None:
    done = emitter.fresh_label("hl_cobol_done")
    _ = [_case(emitter, done, condition, body) for condition, body in cases]
    otherwise()
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=done))


def _is(emitter: HlasmEmitter, value: Register, wanted: Register) -> Register:
    return emitter.binop(BinopKind.EQ, value, wanted)


def _advance(emitter: HlasmEmitter, slot: Register, width: int) -> None:
    after = emitter.binop(BinopKind.ADD, slot, emitter.int_(width))
    emitter.emit_inst(StoreVar(name=SLOT_VAR, value_reg=after))


def _copy_value(
    emitter: HlasmEmitter,
    into: tuple[Register, Register],
    address: Register,
    width: int,
) -> Case:
    plist, slot = into
    slot_width = DOUBLEWORD_BYTES if width == DOUBLEWORD_BYTES else WORD_BYTES

    def body() -> None:
        image = emitter.load_bytes(address, emitter.int_(0), width)
        at = emitter.binop(BinopKind.ADD, slot, emitter.int_(slot_width - width))
        emitter.write_bytes(plist, at, width, image)
        _advance(emitter, slot, slot_width)

    return body


def _value_slot(
    emitter: HlasmEmitter, plist: Register, slot: Register, element: Register
) -> None:
    length = _field(emitter, element, LENGTH_FIELD)
    address = emitter.binop(
        BinopKind.ADD,
        _field(emitter, element, REGION_FIELD),
        _field(emitter, element, OFFSET_FIELD),
    )
    _cases(
        emitter,
        tuple(
            (
                _is(emitter, length, emitter.int_(w)),
                _copy_value(emitter, (plist, slot), address, w),
            )
            for w in (*RIGHT_ALIGNED_LENGTHS, DOUBLEWORD_BYTES)
        ),
        lambda: _advance(emitter, slot, WORD_BYTES),
    )


def _address_slot(
    emitter: HlasmEmitter, plist: Register, slot: Register, element: Register
) -> None:
    address = emitter.binop(
        BinopKind.ADD,
        _field(emitter, element, REGION_FIELD),
        _field(emitter, element, OFFSET_FIELD),
    )
    emitter.write_bytes(plist, slot, WORD_BYTES, emitter.image(address, WORD_BYTES))
    _advance(emitter, slot, WORD_BYTES)


def _list_slot(
    emitter: HlasmEmitter, arguments: Register, plist: Register, at: Register
) -> None:
    element = emitter.fresh_reg()
    emitter.emit_inst(LoadIndex(result_reg=element, arr_reg=arguments, index_reg=at))
    mode = _field(emitter, element, MODE_FIELD)
    slot = emitter.load_var(SLOT_VAR)
    emitter.emit_inst(StoreVar(name=LAST_MODE_VAR, value_reg=mode))
    emitter.emit_inst(StoreVar(name=LAST_SLOT_VAR, value_reg=slot))
    _cases(
        emitter,
        (
            (
                _is(emitter, mode, emitter.str_(ArgumentMode.OMITTED.value)),
                lambda: _advance(emitter, slot, WORD_BYTES),
            ),
            (
                _is(emitter, mode, emitter.str_(ArgumentMode.VALUE.value)),
                lambda: _value_slot(emitter, plist, slot, element),
            ),
        ),
        lambda: _address_slot(emitter, plist, slot, element),
    )


def _mark_last(emitter: HlasmEmitter, plist: Register, count: Register) -> None:
    any_argument = emitter.binop(BinopKind.GT, count, emitter.int_(0))
    by_address = emitter.binop(
        BinopKind.NE,
        emitter.load_var(LAST_MODE_VAR),
        emitter.str_(ArgumentMode.VALUE.value),
    )

    def mark() -> None:
        at = emitter.load_var(LAST_SLOT_VAR)
        word = emitter.call(
            BINARY_BYTES_TO_INT,
            (emitter.load_bytes(plist, at, WORD_BYTES), emitter.unsigned_flag()),
        )
        marked = emitter.binop(BinopKind.BIT_OR, word, emitter.int_(LAST_PARAMETER_BIT))
        emitter.write_bytes(plist, at, WORD_BYTES, emitter.image(marked, WORD_BYTES))

    _cases(
        emitter,
        ((emitter.binop(BinopKind.AND, any_argument, by_address), mark),),
        lambda: None,
    )


def _declare(emitter: HlasmEmitter, name: VarName, value: Register) -> None:
    emitter.emit_inst(DeclVar(name=name, value_reg=value))


def _from_cobol_body(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
    arguments, entry = parameters
    count = _field(emitter, arguments, COUNT_FIELD)
    size = emitter.binop(BinopKind.MUL, count, emitter.int_(DOUBLEWORD_BYTES))
    plist = aligned_region(emitter, size)
    _ = [
        _declare(emitter, name, value)
        for name, value in (
            (SLOT_VAR, emitter.int_(0)),
            (LAST_SLOT_VAR, emitter.int_(0)),
            (LAST_MODE_VAR, emitter.str_(ArgumentMode.VALUE.value)),
        )
    ]
    emit_counted_loop(
        emitter,
        (emitter.int_(0), count),
        1,
        lambda at: _list_slot(emitter, arguments, plist, at),
    )
    _mark_last(emitter, plist, count)
    enter_registers(emitter, entry, plist)
    return emitter.int_(CALLED)


FROM_COBOL = IrFunction(FROM_COBOL_FUNCTION, 2, _from_cobol_body)


def _return_code_image(emitter: HlasmEmitter) -> Register:
    halfword = emitter.binop(
        BinopKind.MOD,
        emitter.load_gr32(RETURN_CODE_REGISTER),
        emitter.int_(1 << (8 * HALFWORD_BYTES)),
    )
    return emitter.image(halfword, HALFWORD_BYTES)


def cobol_entry(name: str, entry: PlacedName) -> IrFunction:
    def body(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
        (arguments,) = parameters
        FROM_COBOL.call(emitter, (arguments, bound_address(emitter, entry)))
        emitter.call(
            FuncName(f"{MODULE_FUNCTION_PREFIX}{entry.module}"),
            (
                emitter.load_gr32(ENTRY_ADDRESS_REGISTER),
                emitter.int_(NOTHING_BELOW),
            ),
        )
        return _return_code_image(emitter)

    return IrFunction(f"{PROGRAM_ENTRY_PREFIX}{name.upper()}", 1, body)


def _new(
    emitter: HlasmEmitter, fields: Sequence[tuple[FieldName, Register]]
) -> Register:
    element = emitter.fresh_reg()
    emitter.emit_inst(NewObject(result_reg=element))
    _ = [_store(emitter, element, field, value) for field, value in fields]
    return element


def _address_element(
    emitter: HlasmEmitter, plist: Register, offset: int, parameter: UsingParameter
) -> Register:
    word = emitter.load_storage(plist, offset, WORD_BYTES)
    address = emitter.binop(BinopKind.BIT_AND, word, emitter.int_(ADDRESS_MASK_31))
    omitted = _is(emitter, address, emitter.int_(0))
    mode = emitter.fresh_reg()

    def named(wanted: ArgumentMode) -> Case:
        def body() -> None:
            emitter.emit_inst(Const.string(mode, wanted.value))

        return body

    _cases(
        emitter,
        ((omitted, named(ArgumentMode.OMITTED)),),
        named(ArgumentMode.REFERENCE),
    )
    return _new(
        emitter,
        (
            (MODE_FIELD, mode),
            (LENGTH_FIELD, emitter.int_(parameter.length)),
            (REGION_FIELD, address),
            (OFFSET_FIELD, emitter.int_(0)),
        ),
    )


def _value_width(length: int) -> int:
    return DOUBLEWORD_BYTES if length == DOUBLEWORD_BYTES else WORD_BYTES


def _value_element(
    emitter: HlasmEmitter, plist: Register, offset: int, parameter: UsingParameter
) -> Register:
    length = parameter.length
    copy = emitter.fresh_reg()
    emitter.emit_inst(AllocRegion(result_reg=copy, size_reg=emitter.int_(length)))
    if length in (*RIGHT_ALIGNED_LENGTHS, DOUBLEWORD_BYTES):
        at = emitter.int_(offset + _value_width(length) - length)
        emitter.write_bytes(
            copy, emitter.int_(0), length, emitter.load_bytes(plist, at, length)
        )
    return _new(
        emitter,
        (
            (MODE_FIELD, emitter.str_(ArgumentMode.VALUE.value)),
            (LENGTH_FIELD, emitter.int_(length)),
            (REGION_FIELD, copy),
            (OFFSET_FIELD, emitter.int_(0)),
        ),
    )


def _ends_list(
    emitter: HlasmEmitter, plist: Register, offset: int, walked: int, done: CodeLabel
) -> None:
    word = emitter.load_storage(plist, offset, WORD_BYTES)
    last = emitter.binop(
        BinopKind.NE,
        emitter.binop(BinopKind.BIT_AND, word, emitter.int_(LAST_PARAMETER_BIT)),
        emitter.int_(0),
    )
    ended, more = emitter.fresh_label("hl_cobol_ended"), emitter.fresh_label(
        "hl_cobol_more"
    )
    emitter.emit_inst(BranchIf(cond_reg=last, branch_targets=(ended, more)))
    emitter.emit_inst(Label_(label=ended))
    emitter.emit_inst(StoreVar(name=WALKED_VAR, value_reg=emitter.int_(walked)))
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=more))


def _offsets(using: Sequence[UsingParameter]) -> tuple[int, ...]:
    widths = [
        _value_width(p.length) if p.mode == ArgumentMode.VALUE else WORD_BYTES
        for p in using
    ]
    return tuple(sum(widths[:at]) for at in range(len(widths)))


def _walk_position(
    emitter: HlasmEmitter,
    request: tuple[Register, Register, CodeLabel],
    position: tuple[int, int, UsingParameter],
) -> None:
    plist, arguments, done = request
    at, offset, parameter = position
    by_value = parameter.mode == ArgumentMode.VALUE
    element = (
        _value_element(emitter, plist, offset, parameter)
        if by_value
        else _address_element(emitter, plist, offset, parameter)
    )
    emitter.emit_inst(
        StoreIndex(arr_reg=arguments, index_reg=emitter.int_(at), value_reg=element)
    )
    if not by_value:
        _ends_list(emitter, plist, offset, at + 1, done)


def _argument_array(emitter: HlasmEmitter, using: Sequence[UsingParameter]) -> Register:
    plist = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(ENTRY_PARAMETER_REGISTER),
        emitter.int_(ADDRESS_MASK_31),
    )
    arguments = emitter.fresh_reg()
    emitter.emit_inst(NewArray(result_reg=arguments, size_reg=emitter.int_(len(using))))
    _declare(emitter, WALKED_VAR, emitter.int_(len(using)))
    done = emitter.fresh_label("hl_cobol_walked")
    _ = [
        _walk_position(emitter, (plist, arguments, done), (at, offset, parameter))
        for at, (offset, parameter) in enumerate(
            zip(_offsets(using), using, strict=True)
        )
    ]
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=done))
    _store(emitter, arguments, COUNT_FIELD, emitter.load_var(WALKED_VAR))
    return arguments


def _save_registers(emitter: HlasmEmitter, save_area: Register) -> None:
    _ = [
        emitter.store_storage(
            save_area,
            SAVE_AREA_REGISTERS_AT + WORD_BYTES * k,
            WORD_BYTES,
            emitter.load_gr32(r),
        )
        for k, r in enumerate(SAVED_REGISTERS)
    ]


def _restore_registers(emitter: HlasmEmitter, save_area: Register) -> None:
    _ = [
        emitter.store_gr32(
            r,
            emitter.load_storage(
                save_area, SAVE_AREA_REGISTERS_AT + WORD_BYTES * k, WORD_BYTES
            ),
        )
        for k, r in enumerate(SAVED_REGISTERS)
    ]


def emit_cobol_call(emitter: HlasmEmitter, program: CobolProgram) -> None:
    arguments = _argument_array(emitter, program.using)
    save_area = emitter.load_gr32(ENTRY_SAVE_AREA_REGISTER)
    _save_registers(emitter, save_area)
    returned = emitter.fresh_reg()
    emitter.emit_inst(
        CallWithMemory(
            result_reg=returned,
            location=VarName(f"{PROGRAM_ENTRY_PREFIX}{program.name.upper()}"),
            memory=arguments,
        )
    )
    return_code = emitter.call(BINARY_BYTES_TO_INT, (returned, _signed(emitter)))
    _restore_registers(emitter, save_area)
    emitter.store_gr32(
        RETURN_CODE_REGISTER,
        emitter.binop(BinopKind.BIT_AND, return_code, emitter.int_(LOW_WORD_MASK)),
    )
    emitter.emit_inst(
        StoreVar(name=TARGET_VAR, value_reg=emitter.load_gr32(LINK_REGISTER))
    )
    emitter.emit_inst(Return_(value_reg=emitter.int_(CALLED)))


def _signed(emitter: HlasmEmitter) -> Register:
    flag = emitter.fresh_reg()
    emitter.emit_inst(Const.bool_(flag, SIGNED))
    return flag
