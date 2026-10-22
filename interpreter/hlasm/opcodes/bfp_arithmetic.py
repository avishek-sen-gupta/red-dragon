# pyright: standard
"""BFP arithmetic, compare, load FP integer, divide to integer and test data class: IR splits the operand images, a zarch_float builtin computes, and the trap ladder delivers (ruling R43)."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.bfp_layout import (
    EXTENDED_LAYOUT,
    LONG_LAYOUT,
    SHORT_LAYOUT,
    BfpLayout,
)
from interpreter.hlasm.bfp_operation import BfpOperation
from interpreter.hlasm.bfp_slots import CC_SLOT, QUOTIENT_SLOT
from interpreter.hlasm.data_movement import Source
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.bfp_forms import (
    FIRST,
    FOURTH,
    SECOND,
    THIRD,
    AfterStore,
    Deliver,
    SuppressedBits,
    cc_of,
    checked,
    current,
    fields,
    fpr,
    ieee,
    inexact_control,
    invalid_modifier,
    modifier,
    no_cc,
    signals_all,
    storage,
    stored,
)
from interpreter.hlasm.opcodes.bfp_ir import list_item
from interpreter.hlasm.opcodes.floating_point_support import pairs
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.register import Register


def _result_cc(
    emitter: HlasmEmitter, statement: MachineStatement, result: Register, slot: Register
) -> None:
    emitter.set_cc(list_item(emitter, result, CC_SLOT))


def _divided(layout: BfpLayout) -> Deliver:
    remainder = stored(FIRST, layout, no_cc)
    quotient = stored(SECOND, layout, no_cc)

    def deliver(
        emitter: HlasmEmitter,
        statement: MachineStatement,
        result: Register,
        slot: Register,
    ) -> None:
        remainder(emitter, statement, result, slot)
        quotient(emitter, statement, result, emitter.int_(QUOTIENT_SLOT))
        _result_cc(emitter, statement, result, slot)

    return deliver


def _shared_registers(statement: MachineStatement) -> bool:
    registers = [reg_operand(statement, index) for index in (FIRST, SECOND, THIRD)]
    return len(set(registers)) < len(registers)


def _two_operand(
    operation: BfpOperation,
    layout: BfpLayout,
    second: Callable[[int, BfpLayout], Source],
    after: AfterStore,
) -> StatementLowering:
    operands = (
        fields(fpr(FIRST, layout), layout),
        fields(second(SECOND, layout), layout),
    )
    return ieee((operation, layout), (current, *operands), stored(FIRST, layout, after))


def _binary(
    operation: BfpOperation,
    names: tuple[str, str, str, str, str],
    after_of: Callable[[BfpLayout], AfterStore],
) -> Mapping[str, StatementLowering]:
    short, long, extended, short_storage, long_storage = names
    return {
        short: _two_operand(operation, SHORT_LAYOUT, fpr, after_of(SHORT_LAYOUT)),
        long: _two_operand(operation, LONG_LAYOUT, fpr, after_of(LONG_LAYOUT)),
        extended: pairs(
            (FIRST, SECOND),
            _two_operand(operation, EXTENDED_LAYOUT, fpr, after_of(EXTENDED_LAYOUT)),
        ),
        short_storage: _two_operand(
            operation, SHORT_LAYOUT, storage, after_of(SHORT_LAYOUT)
        ),
        long_storage: _two_operand(
            operation, LONG_LAYOUT, storage, after_of(LONG_LAYOUT)
        ),
    }


def _without_cc(layout: BfpLayout) -> AfterStore:
    return no_cc


def _square_root(layout: BfpLayout, operand: Source) -> StatementLowering:
    return ieee(
        (BfpOperation.SQUARE_ROOT, layout),
        (current, fields(operand, layout)),
        stored(FIRST, layout, no_cc),
    )


def _fused(
    operation: BfpOperation, layout: BfpLayout, second: Source
) -> StatementLowering:
    operands = (fpr(SECOND, layout), second, fpr(FIRST, layout))
    return ieee(
        (operation, layout),
        (current, *(fields(operand, layout) for operand in operands)),
        stored(FIRST, layout, no_cc),
    )


def _fused_forms(
    operation: BfpOperation, names: tuple[str, str, str, str]
) -> Mapping[str, StatementLowering]:
    short, long, short_storage, long_storage = names
    return {
        short: _fused(operation, SHORT_LAYOUT, fpr(THIRD, SHORT_LAYOUT)),
        long: _fused(operation, LONG_LAYOUT, fpr(THIRD, LONG_LAYOUT)),
        short_storage: _fused(operation, SHORT_LAYOUT, storage(THIRD, SHORT_LAYOUT)),
        long_storage: _fused(operation, LONG_LAYOUT, storage(THIRD, LONG_LAYOUT)),
    }


def _lengthened(
    source: BfpLayout, target: BfpLayout, second: Source
) -> StatementLowering:
    return ieee(
        (BfpOperation.MULTIPLY_LENGTHENED, source),
        (fields(fpr(FIRST, source), source), fields(second, source)),
        stored(FIRST, target, no_cc),
    )


def _integral(layout: BfpLayout, suppressed: SuppressedBits) -> StatementLowering:
    return checked(
        invalid_modifier(SECOND),
        ieee(
            (BfpOperation.ROUND_TO_INTEGRAL, layout),
            (modifier(SECOND), fields(fpr(THIRD, layout), layout)),
            stored(FIRST, layout, no_cc),
            suppressed,
        ),
    )


def _divide_to_integer(layout: BfpLayout) -> StatementLowering:
    operands = (
        fields(fpr(FIRST, layout), layout),
        fields(fpr(THIRD, layout), layout),
    )
    return checked(
        invalid_modifier(FOURTH),
        checked(
            _shared_registers,
            ieee(
                (BfpOperation.DIVIDE_TO_INTEGER, layout),
                (modifier(FOURTH), current, *operands),
                _divided(layout),
            ),
        ),
    )


ADD_SUBTRACT: Mapping[str, StatementLowering] = {
    **_binary(BfpOperation.ADD, ("AEBR", "ADBR", "AXBR", "AEB", "ADB"), cc_of),
    **_binary(BfpOperation.SUBTRACT, ("SEBR", "SDBR", "SXBR", "SEB", "SDB"), cc_of),
}

MULTIPLY_DIVIDE: Mapping[str, StatementLowering] = {
    **_binary(
        BfpOperation.MULTIPLY, ("MEEBR", "MDBR", "MXBR", "MEEB", "MDB"), _without_cc
    ),
    **_binary(BfpOperation.DIVIDE, ("DEBR", "DDBR", "DXBR", "DEB", "DDB"), _without_cc),
    "MDEBR": _lengthened(SHORT_LAYOUT, LONG_LAYOUT, fpr(SECOND, SHORT_LAYOUT)),
    "MDEB": _lengthened(SHORT_LAYOUT, LONG_LAYOUT, storage(SECOND, SHORT_LAYOUT)),
    "MXDBR": pairs(
        (FIRST,), _lengthened(LONG_LAYOUT, EXTENDED_LAYOUT, fpr(SECOND, LONG_LAYOUT))
    ),
    "MXDB": pairs(
        (FIRST,),
        _lengthened(LONG_LAYOUT, EXTENDED_LAYOUT, storage(SECOND, LONG_LAYOUT)),
    ),
}

SQUARE_ROOT_FUSED: Mapping[str, StatementLowering] = {
    "SQEBR": _square_root(SHORT_LAYOUT, fpr(SECOND, SHORT_LAYOUT)),
    "SQDBR": _square_root(LONG_LAYOUT, fpr(SECOND, LONG_LAYOUT)),
    "SQXBR": pairs(
        (FIRST, SECOND), _square_root(EXTENDED_LAYOUT, fpr(SECOND, EXTENDED_LAYOUT))
    ),
    "SQEB": _square_root(SHORT_LAYOUT, storage(SECOND, SHORT_LAYOUT)),
    "SQDB": _square_root(LONG_LAYOUT, storage(SECOND, LONG_LAYOUT)),
    **_fused_forms(BfpOperation.MULTIPLY_ADD, ("MAEBR", "MADBR", "MAEB", "MADB")),
    **_fused_forms(BfpOperation.MULTIPLY_SUBTRACT, ("MSEBR", "MSDBR", "MSEB", "MSDB")),
}

INTEGRAL: Mapping[str, StatementLowering] = {
    "FIEBR": _integral(SHORT_LAYOUT, signals_all),
    "FIDBR": _integral(LONG_LAYOUT, signals_all),
    "FIXBR": pairs((FIRST, THIRD), _integral(EXTENDED_LAYOUT, signals_all)),
    "FIEBRA": _integral(SHORT_LAYOUT, inexact_control),
    "FIDBRA": _integral(LONG_LAYOUT, inexact_control),
    "FIXBRA": pairs((FIRST, THIRD), _integral(EXTENDED_LAYOUT, inexact_control)),
    "DIEBR": _divide_to_integer(SHORT_LAYOUT),
    "DIDBR": _divide_to_integer(LONG_LAYOUT),
}

BFP_ARITHMETIC_LOWERINGS: Mapping[str, StatementLowering] = {
    **ADD_SUBTRACT,
    **MULTIPLY_DIVIDE,
    **SQUARE_ROOT_FUSED,
    **INTEGRAL,
}
