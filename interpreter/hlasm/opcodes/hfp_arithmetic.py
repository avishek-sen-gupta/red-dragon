# pyright: standard
"""HFP add, subtract, compare, multiply, divide, halve, square root, load FP integer and the multiply-and-add forms: IR splits the operand images, a zarch_float builtin computes, and the program-mask ladder delivers (ruling R46)."""

from collections.abc import Callable, Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.conditional import pick
from interpreter.hlasm.data_movement import Source
from interpreter.hlasm.hfp_layout import (
    EXTENDED_HFP,
    LONG_HFP,
    PART_WIDTH,
    SHORT_HFP,
    HfpLayout,
)
from interpreter.hlasm.hfp_operation import HfpOperation, hfp_builtin_name
from interpreter.hlasm.hfp_slots import (
    DIVIDE_BIT,
    OVERFLOW_BIT,
    SIGNIFICANCE_BIT,
    SQUARE_ROOT_BIT,
    UNDERFLOW_BIT,
)
from interpreter.hlasm.hlasm_constants import (
    REGISTER_MASK,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.floating_point_support import PAIR_PARTNER, pairs
from interpreter.hlasm.opcodes.fpr_images import (
    FIRST,
    SECOND,
    THIRD,
    fpr,
    storage,
    store_image,
)
from interpreter.hlasm.opcodes.hfp_ir import (
    LowCharacteristic,
    emit_program_mask_ladder,
    field_sources,
    image_cc,
    result_image,
    true_zero_low,
    wrapped_low,
)
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Deliver = Callable[[HlasmEmitter, MachineStatement, Register, Register], None]
type Target = Callable[[MachineStatement], int]
type Place = Callable[[HlasmEmitter, Register], Register]
type AfterStore = Callable[[HlasmEmitter, Register, HfpLayout], None]
type Second = Callable[[int, HfpLayout], Source]
type Form = tuple[HfpLayout, Second]
type FormLowering = Callable[[HfpLayout, Second], StatementLowering]

RAISES: Mapping[HfpOperation, int] = {
    HfpOperation.ADD: OVERFLOW_BIT | UNDERFLOW_BIT | SIGNIFICANCE_BIT,
    HfpOperation.SUBTRACT: OVERFLOW_BIT | UNDERFLOW_BIT | SIGNIFICANCE_BIT,
    HfpOperation.ADD_UNNORMALIZED: OVERFLOW_BIT | SIGNIFICANCE_BIT,
    HfpOperation.SUBTRACT_UNNORMALIZED: OVERFLOW_BIT | SIGNIFICANCE_BIT,
    HfpOperation.MULTIPLY: OVERFLOW_BIT | UNDERFLOW_BIT,
    HfpOperation.MULTIPLY_LENGTHENED: OVERFLOW_BIT | UNDERFLOW_BIT,
    HfpOperation.MULTIPLY_ADD: OVERFLOW_BIT | UNDERFLOW_BIT,
    HfpOperation.MULTIPLY_SUBTRACT: OVERFLOW_BIT | UNDERFLOW_BIT,
    HfpOperation.DIVIDE: DIVIDE_BIT | OVERFLOW_BIT | UNDERFLOW_BIT,
    HfpOperation.HALVE: UNDERFLOW_BIT,
    HfpOperation.SQUARE_ROOT: SQUARE_ROOT_BIT,
    HfpOperation.LOAD_FP_INTEGER: 0,
    HfpOperation.MULTIPLY_UNNORMALIZED: 0,
    HfpOperation.MULTIPLY_ADD_UNNORMALIZED: 0,
}

SHORT_REGISTER: Form = (SHORT_HFP, fpr)
LONG_REGISTER: Form = (LONG_HFP, fpr)
EXTENDED_REGISTER: Form = (EXTENDED_HFP, fpr)
SHORT_STORAGE: Form = (SHORT_HFP, storage)
LONG_STORAGE: Form = (LONG_HFP, storage)
ALL_FORMS = (
    SHORT_REGISTER,
    LONG_REGISTER,
    EXTENDED_REGISTER,
    SHORT_STORAGE,
    LONG_STORAGE,
)
UNNORMALIZED_FORMS = (SHORT_REGISTER, LONG_REGISTER, SHORT_STORAGE, LONG_STORAGE)
REGISTER_FORMS = (SHORT_REGISTER, LONG_REGISTER, EXTENDED_REGISTER)


def _forms(
    lowering: FormLowering, names: str, forms: Sequence[Form]
) -> Mapping[str, StatementLowering]:
    return {
        name: lowering(*form) for name, form in zip(names.split(), forms, strict=True)
    }


def _paired(
    layout: HfpLayout, operands: tuple[int, ...], lowering: StatementLowering
) -> StatementLowering:
    if layout is EXTENDED_HFP:
        return pairs(operands, lowering)
    return lowering


def _register(statement: MachineStatement) -> int:
    return reg_operand(statement, FIRST)


def _pair_holding(statement: MachineStatement) -> int:
    return reg_operand(statement, FIRST) & ~PAIR_PARTNER


def _whole(emitter: HlasmEmitter, image: Register) -> Register:
    return image


def _high_part(emitter: HlasmEmitter, image: Register) -> Register:
    return emitter.binop(BinopKind.RSHIFT, image, emitter.int_(PART_WIDTH))


def _low_part(emitter: HlasmEmitter, image: Register) -> Register:
    return emitter.binop(BinopKind.BIT_AND, image, emitter.int_(REGISTER_MASK))


def _no_cc(emitter: HlasmEmitter, image: Register, layout: HfpLayout) -> None:
    return None


def _cc(emitter: HlasmEmitter, image: Register, layout: HfpLayout) -> None:
    emitter.set_cc(image_cc(emitter, image, layout))


def _stored(
    target: Target,
    layouts: tuple[HfpLayout, HfpLayout],
    placing: tuple[Place, LowCharacteristic],
    after: AfterStore,
) -> Deliver:
    result_layout, register_layout = layouts
    place, low = placing

    def deliver(
        emitter: HlasmEmitter,
        statement: MachineStatement,
        result: Register,
        zeroed: Register,
    ) -> None:
        image = place(emitter, result_image(emitter, result, result_layout, low))
        kept = pick(emitter, zeroed, emitter.int_(0), image)
        store_image(emitter, target(statement), register_layout, kept)
        after(emitter, kept, register_layout)

    return deliver


def _into(layout: HfpLayout, after: AfterStore) -> Deliver:
    return _stored(_register, (layout, layout), (_whole, true_zero_low), after)


def hfp_call(
    builtin: tuple[HfpOperation, HfpLayout],
    arguments: Sequence[Source],
    deliver: Deliver,
) -> StatementLowering:
    name = hfp_builtin_name(*builtin)
    raisable = RAISES[builtin[0]]

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        args = tuple(argument(emitter, statement) for argument in arguments)
        result = emitter.call(name, args)
        emit_program_mask_ladder(
            emitter,
            result,
            raisable,
            lambda zeroed: deliver(emitter, statement, result, zeroed),
        )

    return lower


def _pair_operands(layout: HfpLayout, second: Second) -> tuple[Source, ...]:
    return field_sources(layout, (fpr(FIRST, layout), second(SECOND, layout)))


def _arithmetic(operation: HfpOperation, after: AfterStore) -> FormLowering:
    def lowering(layout: HfpLayout, second: Second) -> StatementLowering:
        operands = _pair_operands(layout, second)
        lowered = hfp_call((operation, layout), operands, _into(layout, after))
        return _paired(layout, (FIRST, SECOND), lowered)

    return lowering


def _compare(layout: HfpLayout, second: Second) -> StatementLowering:
    name = hfp_builtin_name(HfpOperation.COMPARE, layout)
    operands = _pair_operands(layout, second)

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        args = tuple(operand(emitter, statement) for operand in operands)
        emitter.set_cc(emitter.call(name, args))

    return _paired(layout, (FIRST, SECOND), lower)


def _lengthened(target: HfpLayout) -> FormLowering:
    def lowering(source: HfpLayout, second: Second) -> StatementLowering:
        operands = _pair_operands(source, second)
        deliver = _into(target, _no_cc)
        lowered = hfp_call(
            (HfpOperation.MULTIPLY_LENGTHENED, source), operands, deliver
        )
        return _paired(target, (FIRST,), lowered)

    return lowering


def _unary(operation: HfpOperation) -> FormLowering:
    def lowering(layout: HfpLayout, second: Second) -> StatementLowering:
        operands = field_sources(layout, (second(SECOND, layout),))
        lowered = hfp_call((operation, layout), operands, _into(layout, _no_cc))
        return _paired(layout, (FIRST, SECOND), lowered)

    return lowering


def _fused(operation: HfpOperation) -> FormLowering:
    def lowering(layout: HfpLayout, second: Second) -> StatementLowering:
        sources = (fpr(SECOND, layout), second(THIRD, layout), fpr(FIRST, layout))
        deliver = _into(layout, _no_cc)
        return hfp_call((operation, layout), field_sources(layout, sources), deliver)

    return lowering


def _product(second: Second) -> tuple[Source, ...]:
    return field_sources(LONG_HFP, (fpr(SECOND, LONG_HFP), second(THIRD, LONG_HFP)))


def _unnormalized_product(deliver: Deliver) -> FormLowering:
    return lambda layout, second: hfp_call(
        (HfpOperation.MULTIPLY_UNNORMALIZED, LONG_HFP), _product(second), deliver
    )


def _unnormalized_sum(deliver: Deliver) -> FormLowering:
    return lambda layout, second: hfp_call(
        (HfpOperation.MULTIPLY_ADD_UNNORMALIZED, LONG_HFP),
        (*_product(second), *field_sources(LONG_HFP, (fpr(FIRST, LONG_HFP),))),
        deliver,
    )


def _part(place: Place) -> Deliver:
    return _stored(_register, (EXTENDED_HFP, LONG_HFP), (place, wrapped_low), _no_cc)


def _extended(target: Target) -> Deliver:
    return _stored(target, (EXTENDED_HFP, EXTENDED_HFP), (_whole, wrapped_low), _no_cc)


def _paired_first(lowering: FormLowering) -> FormLowering:
    return lambda layout, second: pairs((FIRST,), lowering(layout, second))


LONG_FORMS = (LONG_REGISTER, LONG_STORAGE)

ADD_SUBTRACT: Mapping[str, StatementLowering] = {
    **_forms(_arithmetic(HfpOperation.ADD, _cc), "AER ADR AXR AE AD", ALL_FORMS),
    **_forms(_arithmetic(HfpOperation.SUBTRACT, _cc), "SER SDR SXR SE SD", ALL_FORMS),
    **_forms(
        _arithmetic(HfpOperation.ADD_UNNORMALIZED, _cc),
        "AUR AWR AU AW",
        UNNORMALIZED_FORMS,
    ),
    **_forms(
        _arithmetic(HfpOperation.SUBTRACT_UNNORMALIZED, _cc),
        "SUR SWR SU SW",
        UNNORMALIZED_FORMS,
    ),
    **_forms(_compare, "CER CDR CXR CE CD", ALL_FORMS),
}

MULTIPLY_DIVIDE: Mapping[str, StatementLowering] = {
    **_forms(
        _arithmetic(HfpOperation.MULTIPLY, _no_cc), "MEER MDR MXR MEE MD", ALL_FORMS
    ),
    **_forms(_arithmetic(HfpOperation.DIVIDE, _no_cc), "DER DDR DXR DE DD", ALL_FORMS),
    **_forms(
        _lengthened(LONG_HFP),
        "MDER MER MDE ME",
        (SHORT_REGISTER, SHORT_REGISTER, SHORT_STORAGE, SHORT_STORAGE),
    ),
    **_forms(_lengthened(EXTENDED_HFP), "MXDR MXD", LONG_FORMS),
}

UNARY: Mapping[str, StatementLowering] = {
    **_forms(_unary(HfpOperation.HALVE), "HER HDR", REGISTER_FORMS[:2]),
    **_forms(_unary(HfpOperation.SQUARE_ROOT), "SQER SQDR SQXR SQE SQD", ALL_FORMS),
    **_forms(_unary(HfpOperation.LOAD_FP_INTEGER), "FIER FIDR FIXR", REGISTER_FORMS),
}

FUSED: Mapping[str, StatementLowering] = {
    **_forms(
        _fused(HfpOperation.MULTIPLY_ADD),
        "MAER MADR MAE MAD",
        UNNORMALIZED_FORMS,
    ),
    **_forms(
        _fused(HfpOperation.MULTIPLY_SUBTRACT),
        "MSER MSDR MSE MSD",
        UNNORMALIZED_FORMS,
    ),
}

UNNORMALIZED: Mapping[str, StatementLowering] = {
    **_forms(
        _paired_first(_unnormalized_product(_extended(_register))), "MYR MY", LONG_FORMS
    ),
    **_forms(_unnormalized_product(_part(_high_part)), "MYHR MYH", LONG_FORMS),
    **_forms(_unnormalized_product(_part(_low_part)), "MYLR MYL", LONG_FORMS),
    **_forms(_unnormalized_sum(_extended(_pair_holding)), "MAYR MAY", LONG_FORMS),
    **_forms(_unnormalized_sum(_part(_high_part)), "MAYHR MAYH", LONG_FORMS),
    **_forms(_unnormalized_sum(_part(_low_part)), "MAYLR MAYL", LONG_FORMS),
}

HFP_ARITHMETIC_LOWERINGS: Mapping[str, StatementLowering] = {
    **ADD_SUBTRACT,
    **MULTIPLY_DIVIDE,
    **UNARY,
    **FUSED,
    **UNNORMALIZED,
}
