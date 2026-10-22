# pyright: standard
"""BFP arithmetic, compare, load FP integer, divide to integer and test data class: IR splits the operand images, a zarch_float builtin computes, and the trap ladder delivers (ruling R43)."""

from collections.abc import Callable, Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.bfp_layout import (
    EXTENDED_LAYOUT,
    LONG_LAYOUT,
    SHORT_LAYOUT,
    BfpLayout,
)
from interpreter.hlasm.bfp_operation import BfpOperation, bfp_builtin_name
from interpreter.hlasm.bfp_slots import CC_SLOT, INEXACT_BIT, QUOTIENT_SLOT
from interpreter.hlasm.data_movement import (
    Source,
    from_storage_at,
    keep,
    storage_address_at,
)
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    SPECIFICATION_EXCEPTION_ABEND,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.bfp_ir import (
    current_mode,
    emit_ieee_ladder,
    fields_list,
    image_at,
    image_cc,
    list_item,
    load_image,
    outcome_of,
    store_image,
    without,
)
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.operands import mask_operand, optional_mask_operand, reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.register import Register

type Deliver = Callable[[HlasmEmitter, MachineStatement, Register, int], None]
type AfterStore = Callable[[HlasmEmitter, Register], None]
type Quieted = Callable[[MachineStatement], int]

VALID_MODIFIERS = frozenset({0, 1, 3, 4, 5, 6, 7})
INEXACT_CONTROL = 0b0100
DATA_CLASS_BITS = 0xFFF
FIRST, SECOND, THIRD, FOURTH = 0, 1, 2, 3


def _fpr(index: int, layout: BfpLayout) -> Source:
    return lambda emitter, statement: load_image(
        emitter, reg_operand(statement, index), layout
    )


def _storage(index: int, layout: BfpLayout) -> Source:
    return from_storage_at(index, layout.width // BITS_PER_BYTE)


def _fields(image: Source, layout: BfpLayout) -> Source:
    return lambda emitter, statement: fields_list(
        emitter, image(emitter, statement), layout
    )


def _current(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    return current_mode(emitter)


def _modifier(index: int) -> Source:
    def mode(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
        modifier = mask_operand(statement, index)
        if modifier == 0:
            return current_mode(emitter)
        return emitter.int_(modifier)

    return mode


def _no_cc(emitter: HlasmEmitter, image: Register) -> None:
    return None


def _cc_of(layout: BfpLayout) -> AfterStore:
    return lambda emitter, image: emitter.set_cc(image_cc(emitter, image, layout))


def _stored(index: int, layout: BfpLayout, after: AfterStore) -> Deliver:
    def deliver(
        emitter: HlasmEmitter, statement: MachineStatement, result: Register, slot: int
    ) -> None:
        image = image_at(emitter, result, slot, layout)
        store_image(emitter, reg_operand(statement, index), layout, image)
        after(emitter, image)

    return deliver


def _compared(
    emitter: HlasmEmitter, statement: MachineStatement, result: Register, slot: int
) -> None:
    emitter.set_cc(list_item(emitter, result, CC_SLOT))


def _divided(layout: BfpLayout) -> Deliver:
    remainder = _stored(FIRST, layout, _no_cc)
    quotient = _stored(SECOND, layout, _no_cc)

    def deliver(
        emitter: HlasmEmitter, statement: MachineStatement, result: Register, slot: int
    ) -> None:
        remainder(emitter, statement, result, slot)
        quotient(emitter, statement, result, QUOTIENT_SLOT)
        _compared(emitter, statement, result, slot)

    return deliver


def _signals_all(statement: MachineStatement) -> int:
    return 0


def _inexact_control(statement: MachineStatement) -> int:
    controlled = optional_mask_operand(statement, FOURTH, 0) & INEXACT_CONTROL
    return INEXACT_BIT * bool(controlled)


def _ieee(
    builtin: tuple[BfpOperation, BfpLayout],
    arguments: Sequence[Source],
    deliver: Deliver,
    quieted: Quieted = _signals_all,
) -> StatementLowering:
    name = bfp_builtin_name(*builtin)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        args = tuple(argument(emitter, statement) for argument in arguments)
        result = emitter.call(name, args)
        outcome = without(emitter, outcome_of(emitter, result), quieted(statement))
        emit_ieee_ladder(
            emitter, outcome, lambda slot: deliver(emitter, statement, result, slot)
        )

    return lower


def _checked(
    raised: Callable[[MachineStatement], bool], lowering: StatementLowering
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        if raised(statement):
            emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND)
            return
        lowering(emitter, statement)

    return lower


def _invalid_modifier(index: int) -> Callable[[MachineStatement], bool]:
    return lambda statement: mask_operand(statement, index) not in VALID_MODIFIERS


def _shared_registers(statement: MachineStatement) -> bool:
    registers = [reg_operand(statement, index) for index in (FIRST, SECOND, THIRD)]
    return len(set(registers)) < len(registers)


def _extended(
    operands: Sequence[int], lowering: StatementLowering
) -> StatementLowering:
    return pairs(operands, lowering)


def _register_form(
    operation: BfpOperation, layout: BfpLayout, after: AfterStore
) -> StatementLowering:
    operands = (
        _fields(_fpr(FIRST, layout), layout),
        _fields(_fpr(SECOND, layout), layout),
    )
    return _ieee(
        (operation, layout), (_current, *operands), _stored(FIRST, layout, after)
    )


def _storage_form(
    operation: BfpOperation, layout: BfpLayout, after: AfterStore
) -> StatementLowering:
    operands = (
        _fields(_fpr(FIRST, layout), layout),
        _fields(_storage(SECOND, layout), layout),
    )
    return _ieee(
        (operation, layout), (_current, *operands), _stored(FIRST, layout, after)
    )


def _binary(
    operation: BfpOperation,
    names: tuple[str, str, str, str, str],
    after_of: Callable[[BfpLayout], AfterStore],
) -> Mapping[str, StatementLowering]:
    short, long, extended, short_storage, long_storage = names
    return {
        short: _register_form(operation, SHORT_LAYOUT, after_of(SHORT_LAYOUT)),
        long: _register_form(operation, LONG_LAYOUT, after_of(LONG_LAYOUT)),
        extended: _extended(
            (FIRST, SECOND),
            _register_form(operation, EXTENDED_LAYOUT, after_of(EXTENDED_LAYOUT)),
        ),
        short_storage: _storage_form(operation, SHORT_LAYOUT, after_of(SHORT_LAYOUT)),
        long_storage: _storage_form(operation, LONG_LAYOUT, after_of(LONG_LAYOUT)),
    }


def _without_cc(layout: BfpLayout) -> AfterStore:
    return _no_cc


def _square_root(layout: BfpLayout, operand: Source) -> StatementLowering:
    return _ieee(
        (BfpOperation.SQUARE_ROOT, layout),
        (_current, _fields(operand, layout)),
        _stored(FIRST, layout, _no_cc),
    )


def _fused(
    operation: BfpOperation, layout: BfpLayout, second: Source
) -> StatementLowering:
    operands = (_fpr(SECOND, layout), second, _fpr(FIRST, layout))
    return _ieee(
        (operation, layout),
        (_current, *(_fields(operand, layout) for operand in operands)),
        _stored(FIRST, layout, _no_cc),
    )


def _fused_forms(
    operation: BfpOperation, names: tuple[str, str, str, str]
) -> Mapping[str, StatementLowering]:
    short, long, short_storage, long_storage = names
    return {
        short: _fused(operation, SHORT_LAYOUT, _fpr(THIRD, SHORT_LAYOUT)),
        long: _fused(operation, LONG_LAYOUT, _fpr(THIRD, LONG_LAYOUT)),
        short_storage: _fused(operation, SHORT_LAYOUT, _storage(THIRD, SHORT_LAYOUT)),
        long_storage: _fused(operation, LONG_LAYOUT, _storage(THIRD, LONG_LAYOUT)),
    }


def _lengthened(
    source: BfpLayout, target: BfpLayout, second: Source
) -> StatementLowering:
    return _ieee(
        (BfpOperation.MULTIPLY_LENGTHENED, source),
        (_fields(_fpr(FIRST, source), source), _fields(second, source)),
        _stored(FIRST, target, _no_cc),
    )


def _compare(
    operation: BfpOperation, layout: BfpLayout, second: Source
) -> StatementLowering:
    return _ieee(
        (operation, layout),
        (_fields(_fpr(FIRST, layout), layout), _fields(second, layout)),
        _compared,
    )


def _compare_forms(
    operation: BfpOperation, names: tuple[str, str, str, str, str]
) -> Mapping[str, StatementLowering]:
    short, long, extended, short_storage, long_storage = names
    return {
        short: _compare(operation, SHORT_LAYOUT, _fpr(SECOND, SHORT_LAYOUT)),
        long: _compare(operation, LONG_LAYOUT, _fpr(SECOND, LONG_LAYOUT)),
        extended: _extended(
            (FIRST, SECOND),
            _compare(operation, EXTENDED_LAYOUT, _fpr(SECOND, EXTENDED_LAYOUT)),
        ),
        short_storage: _compare(
            operation, SHORT_LAYOUT, _storage(SECOND, SHORT_LAYOUT)
        ),
        long_storage: _compare(operation, LONG_LAYOUT, _storage(SECOND, LONG_LAYOUT)),
    }


def _integral(layout: BfpLayout, quieted: Quieted) -> StatementLowering:
    return _checked(
        _invalid_modifier(SECOND),
        _ieee(
            (BfpOperation.ROUND_TO_INTEGRAL, layout),
            (_modifier(SECOND), _fields(_fpr(THIRD, layout), layout)),
            _stored(FIRST, layout, _no_cc),
            quieted,
        ),
    )


def _divide_to_integer(layout: BfpLayout) -> StatementLowering:
    operands = (
        _fields(_fpr(FIRST, layout), layout),
        _fields(_fpr(THIRD, layout), layout),
    )
    return _checked(
        _invalid_modifier(FOURTH),
        _checked(
            _shared_registers,
            _ieee(
                (BfpOperation.DIVIDE_TO_INTEGER, layout),
                (_modifier(FOURTH), _current, *operands),
                _divided(layout),
            ),
        ),
    )


def _test_data_class(layout: BfpLayout) -> StatementLowering:
    name = bfp_builtin_name(BfpOperation.TEST_DATA_CLASS, layout)
    operand = _fields(_fpr(FIRST, layout), layout)
    address = storage_address_at(SECOND)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        fields = operand(emitter, statement)
        mask = keep(DATA_CLASS_BITS)(emitter, address(emitter, statement))
        emitter.set_cc(emitter.call(name, (fields, mask)))

    return lower


ADD_SUBTRACT: Mapping[str, StatementLowering] = {
    **_binary(BfpOperation.ADD, ("AEBR", "ADBR", "AXBR", "AEB", "ADB"), _cc_of),
    **_binary(BfpOperation.SUBTRACT, ("SEBR", "SDBR", "SXBR", "SEB", "SDB"), _cc_of),
}

MULTIPLY_DIVIDE: Mapping[str, StatementLowering] = {
    **_binary(
        BfpOperation.MULTIPLY, ("MEEBR", "MDBR", "MXBR", "MEEB", "MDB"), _without_cc
    ),
    **_binary(BfpOperation.DIVIDE, ("DEBR", "DDBR", "DXBR", "DEB", "DDB"), _without_cc),
    "MDEBR": _lengthened(SHORT_LAYOUT, LONG_LAYOUT, _fpr(SECOND, SHORT_LAYOUT)),
    "MDEB": _lengthened(SHORT_LAYOUT, LONG_LAYOUT, _storage(SECOND, SHORT_LAYOUT)),
    "MXDBR": _extended(
        (FIRST,), _lengthened(LONG_LAYOUT, EXTENDED_LAYOUT, _fpr(SECOND, LONG_LAYOUT))
    ),
    "MXDB": _extended(
        (FIRST,),
        _lengthened(LONG_LAYOUT, EXTENDED_LAYOUT, _storage(SECOND, LONG_LAYOUT)),
    ),
}

SQUARE_ROOT_FUSED: Mapping[str, StatementLowering] = {
    "SQEBR": _square_root(SHORT_LAYOUT, _fpr(SECOND, SHORT_LAYOUT)),
    "SQDBR": _square_root(LONG_LAYOUT, _fpr(SECOND, LONG_LAYOUT)),
    "SQXBR": _extended(
        (FIRST, SECOND), _square_root(EXTENDED_LAYOUT, _fpr(SECOND, EXTENDED_LAYOUT))
    ),
    "SQEB": _square_root(SHORT_LAYOUT, _storage(SECOND, SHORT_LAYOUT)),
    "SQDB": _square_root(LONG_LAYOUT, _storage(SECOND, LONG_LAYOUT)),
    **_fused_forms(BfpOperation.MULTIPLY_ADD, ("MAEBR", "MADBR", "MAEB", "MADB")),
    **_fused_forms(BfpOperation.MULTIPLY_SUBTRACT, ("MSEBR", "MSDBR", "MSEB", "MSDB")),
}

COMPARE_INTEGRAL: Mapping[str, StatementLowering] = {
    **_compare_forms(BfpOperation.COMPARE, ("CEBR", "CDBR", "CXBR", "CEB", "CDB")),
    **_compare_forms(
        BfpOperation.COMPARE_SIGNALING, ("KEBR", "KDBR", "KXBR", "KEB", "KDB")
    ),
    "FIEBR": _integral(SHORT_LAYOUT, _signals_all),
    "FIDBR": _integral(LONG_LAYOUT, _signals_all),
    "FIXBR": _extended((FIRST, THIRD), _integral(EXTENDED_LAYOUT, _signals_all)),
    "FIEBRA": _integral(SHORT_LAYOUT, _inexact_control),
    "FIDBRA": _integral(LONG_LAYOUT, _inexact_control),
    "FIXBRA": _extended((FIRST, THIRD), _integral(EXTENDED_LAYOUT, _inexact_control)),
    "DIEBR": _divide_to_integer(SHORT_LAYOUT),
    "DIDBR": _divide_to_integer(LONG_LAYOUT),
    "TCEB": _test_data_class(SHORT_LAYOUT),
    "TCDB": _test_data_class(LONG_LAYOUT),
    "TCXB": _extended((FIRST,), _test_data_class(EXTENDED_LAYOUT)),
}

BFP_ARITHMETIC_LOWERINGS: Mapping[str, StatementLowering] = {
    **ADD_SUBTRACT,
    **MULTIPLY_DIVIDE,
    **SQUARE_ROOT_FUSED,
    **COMPARE_INTEGRAL,
}
