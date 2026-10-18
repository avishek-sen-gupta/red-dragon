"""Arithmetic and control-flow statement lowering — MOVE, ADD/SUB/MUL/DIV,
COMPUTE, IF, EVALUATE, CONTINUE, EXIT, INITIALIZE, SET, DISPLAY, STOP RUN, GO TO.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from functools import partial, reduce
from itertools import chain, product

from cobol_asg.cobol_expression import (
    AllSubscriptNode,
    ExprNode,
    FieldRefNode,
    FunctionNode,
    LiteralNode,
    RefModNode,
    expr_from_dict,
    expr_to_dict,
)
from cobol_asg.cobol_field import NO_ODO_OBJECT
from cobol_asg.cobol_statements import (
    ArithmeticCorrespondingStatement,
    ArithmeticStatement,
    ComputedGoto,
    ComputeStatement,
    ComputeTarget,
    ContinueStatement,
    DisplayStatement,
    ExitProgramStatement,
    ExitStatement,
    GobackStatement,
    GotoStatement,
    IfStatement,
    InitializeStatement,
    MoveCorrespondingStatement,
    MoveStatement,
    NextSentenceStatement,
    SetStatement,
    SimpleGoto,
    StopRunStatement,
)
from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_asg.edit_picture import de_edit_plan
from cobol_asg.exit_kind import ExitKind
from cobol_asg.initialize_category import InitializeCategory
from cobol_asg.initialize_replacing import InitializeReplacing
from cobol_asg.nonnumeric_literal import literal_characters
from cobol_asg.operand_kind import OperandKind
from cobol_asg.ref_mod import (
    FunctionCallOperand,
    RefModBinOp,
    RefModExpr,
    RefModFunction,
    RefModLengthOf,
    RefModLiteral,
    RefModOperand,
    RefModReference,
)
from cobol_asg.set_operand import SetOperand
from cobol_asg.source_span import SourceSpan
from cobol_asg.switch_status import SwitchStatus
from cobol_memory.region_id import RegionId
from cobol_numeric.number import from_literal
from cobol_numeric.scale import (
    Scale,
    add_scale,
    carry,
    div_scale,
    literal_scale,
    mul_scale,
)
from interpreter.cobol.arithmetic_operation import ArithmeticOperation
from interpreter.cobol.arithmetic_precision import ArithmeticPrecision
from interpreter.cobol.arithmetic_receiver import ArithmeticReceiver
from interpreter.cobol.arithmetic_scale import (
    field_scale,
    is_floating_type,
    receiver_capacity,
    receiver_rounding_places,
)
from interpreter.cobol.arithmetic_scale import receiver_decimals as _receiver_decimals
from interpreter.cobol.arithmetic_value import ArithmeticValue
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.condition_lowering import (
    _float_operand,
    lower_expr_node,
)
from interpreter.cobol.corresponding_pair import CorrespondingPair
from interpreter.cobol.corresponding_paths import (
    PairRule,
    corresponding_paths,
    pairs_for_arithmetic,
    pairs_for_move,
)
from interpreter.cobol.data_layout import DataItemMatch, DataLayout, FieldLayout
from interpreter.cobol.de_edit_ir import emit_de_edit
from interpreter.cobol.digit_image_ir import emit_display_image, emit_field_digit_image
from interpreter.cobol.divide_operands import DivideOperands
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import ResolvedFieldRef, whole_field_extent
from interpreter.cobol.figurative_constants import repeat_to_width
from interpreter.cobol.in_place_operation import InPlaceOperation
from interpreter.cobol.initialize_target import InitializeTarget
from interpreter.cobol.initialize_targets import initialize_targets
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.lower_pointer import is_pointer_set, lower_pointer_set
from interpreter.cobol.lowering_scope import LoweringScope
from interpreter.cobol.lower_program_exit import (
    emit_publish_run_unit_return_code,
    emit_return_code_load,
    lower_program_exit,
)
from interpreter.cobol.move_source import MoveSource, plain_move_source
from interpreter.cobol.receiver_result import ReceiverResult
from interpreter.cobol.run_unit import RANDOM_STATE, RUN_UNIT_LAYOUT, RUN_UNIT_VAR
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.size_error_arm import SizeErrorArm
from interpreter.cobol.size_error_ir import emit_size_error
from interpreter.cobol.size_error_store import SizeErrorGuard, SizeErrorStore
from interpreter.cobol.standard_deviation_ir import emit_standard_deviation
from interpreter.cobol.when_compiled import when_compiled_text
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Halt_,
    Label_,
    LoadVar,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind, resolve_binop
from interpreter.register import Register

logger = logging.getLogger(__name__)

# COBOL special registers the ProLeap bridge does not model as DATA DIVISION
# fields. A MOVE into one of these surfaces with an unresolved/null operand name
# (the bridge's placeholder), so we recognise both forms here.
_SPECIAL_REGISTER_NAMES = frozenset(
    {
        # RETURN-CODE removed (red-dragon-o8uq): it now resolves to a dedicated SR
        # region and lowers via the ordinary encode→WRITE_REGION MOVE path.
        "SORT-RETURN",
        "TALLY",
        "name=[null]",  # bridge placeholder for an unmodelled register operand
    }
)


def _is_special_register(name: str) -> bool:
    """True if ``name`` is an unmodelled COBOL special register (MOVE target)."""
    return str(name).upper() in {n.upper() for n in _SPECIAL_REGISTER_NAMES}


ARITHMETIC_OPS = {
    "ADD": "+",
    "SUBTRACT": "-",
    "MULTIPLY": "*",
    "DIVIDE": "/",
}

_EXACT_VERB_BUILTINS = {
    "ADD": BuiltinName.COBOL_ADD,
    "SUBTRACT": BuiltinName.COBOL_SUBTRACT,
    "MULTIPLY": BuiltinName.COBOL_MULTIPLY,
    "DIVIDE": BuiltinName.COBOL_DIVIDE,
}


def _operand_scale(scope: LoweringScope, operand: RefModOperand) -> Scale:
    ctx = scope.ctx
    name = operand.name
    if operand.names_data:
        return field_scale(
            scope.materialised.resolve(name, operand.qualifiers)[0].type_descriptor
        )
    try:
        from_literal(ctx.figuratives.translate(name))
    except ValueError:
        return Scale(1, 0)
    return literal_scale(ctx.figuratives.translate(name))


_VERB_SCALES: Mapping[str, Callable[[Scale, Scale, int], Scale]] = {
    "ADD": lambda left, right, _dmax: add_scale(left, right),
    "SUBTRACT": lambda left, right, _dmax: add_scale(left, right),
    "MULTIPLY": lambda left, right, _dmax: mul_scale(left, right),
    "DIVIDE": div_scale,
}


def _is_floating_operand(scope: LoweringScope, operand: RefModOperand) -> bool:
    return operand.names_data and is_floating_type(
        scope.materialised.resolve(operand.name, operand.qualifiers)[0].type_descriptor
    )


def _receiver_places(scope: LoweringScope, receivers: Sequence[RefModOperand]) -> int:
    ctx, materialised = scope.ctx, scope.materialised
    return max(
        (
            _receiver_decimals(
                materialised.resolve(r.name, r.qualifiers)[0].type_descriptor,
                r.rounded,
            )
            for r in receivers
            if ctx.has_field(r.name, materialised)
        ),
        default=0,
    )


def _operand_value(
    scope: LoweringScope, operand: RefModOperand, register: Register
) -> ArithmeticValue:
    return ArithmeticValue(
        register=register,
        scale=_operand_scale(scope, operand),
        floating=_is_floating_operand(scope, operand),
    )


def _emit_float_operation(
    scope: LoweringScope, operation: ArithmeticOperation, scale: Scale
) -> ArithmeticValue:
    ctx, span = scope.ctx, scope.span
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result_reg,
            operator=resolve_binop(ARITHMETIC_OPS[operation.op]),
            left=_float_operand(ctx, operation.left.register, True, span=span),
            right=_float_operand(ctx, operation.right.register, True, span=span),
        ),
        span=span,
    )
    return ArithmeticValue(register=result_reg, scale=scale, floating=True)


def _emit_verb_operation(
    scope: LoweringScope,
    operation: ArithmeticOperation,
    receivers: Sequence[RefModOperand],
) -> ArithmeticValue:
    """Emit ``left <op> right``, exact unless IBM's floating-point rule applies."""
    return _emit_scaled_operation(
        scope,
        operation,
        _receiver_places(scope, receivers),
        any(_is_floating_operand(scope, r) for r in receivers),
    )


def _emit_scaled_operation(
    scope: LoweringScope,
    operation: ArithmeticOperation,
    receiver_places: int,
    floating_receiver: bool,
) -> ArithmeticValue:
    ctx, span = scope.ctx, scope.span
    op, left, right = operation.op, operation.left, operation.right
    operand_places = (
        left.scale.decimal_places
        if op == "DIVIDE"
        else max(left.scale.decimal_places, right.scale.decimal_places)
    )
    dmax = max(receiver_places, operand_places)
    scale = carry(_VERB_SCALES[op](left.scale, right.scale, dmax), dmax)
    if left.floating or right.floating or floating_receiver:
        return _emit_float_operation(scope, operation, scale)
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=result_reg,
            func_name=FuncName(_EXACT_VERB_BUILTINS[op]),
            args=(
                left.register,
                right.register,
                ctx.const_to_reg(scale.decimal_places, span=span),
            ),
        ),
        span=span,
    )
    return ArithmeticValue(register=result_reg, scale=scale, floating=False)


def _compute_overflow_flag(
    scope: LoweringScope, result_reg: Register, td: CobolTypeDescriptor
) -> Register:
    return emit_size_error(scope.emitter, result_reg, receiver_capacity(td))


def eval_ref_mod_expr(
    ctx: EmitContext,
    expr: RefModExpr,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Evaluate a reference modification expression to an IR register.

    Handles three cases:
    - RefModLiteral: numeric literal → Const → register
    - RefModReference: data item name → resolve field → decode → to_string → register
    - RefModBinOp: binary operation → evaluate left/right → emit Binop → register
    """
    if isinstance(expr, RefModLiteral):
        # Literal: numeric value for reference modification.
        # parse_literal converts e.g. "2" → int 2 so arithmetic Binops work.
        return ctx.const_to_reg(ctx.parse_literal(expr.value), span=span)

    elif isinstance(expr, RefModReference):
        # Field reference: resolve field → decode
        # Return the decoded numeric value (don't convert to string)
        name = expr.name
        if ctx.has_field(name, materialised):
            field_ref, rr = ctx.resolve_field_ref(
                name, materialised, qualifiers=expr.qualifiers, span=span
            )
            decoded_reg = ctx.emit_decode_field(
                rr,
                field_ref.fl,
                field_ref.offset_reg,
                extent=field_ref.extent,
                span=span,
            )
            # Return the decoded numeric value directly
            return decoded_reg
        else:
            # Unknown field: treat as literal numeric 0
            return ctx.const_to_reg(0, span=span)

    elif isinstance(expr, RefModLengthOf):
        name = expr.name
        if ctx.has_field(name, materialised):
            return ctx.emit_length_of(name, materialised, expr.qualifiers, span=span)
        logging.warning("eval_ref_mod_expr: LENGTH OF unknown field %s → 0", name)
        return ctx.const_to_reg(0, span=span)

    elif isinstance(expr, RefModFunction):
        # An intrinsic FUNCTION computing a bound: M(1:FUNCTION LENGTH(M)). The
        # call is the bound, never the operand — the operand serializer used to
        # return it in place of the whole sliced reference (red-dragon-pe45).
        return lower_function_operand(
            ctx,
            FunctionCallOperand(name=expr.name, args=expr.args),
            materialised,
            span=span,
        )

    elif isinstance(expr, RefModBinOp):
        # Binary operation: evaluate left and right, emit Binop
        left_reg = eval_ref_mod_expr(ctx, expr.left, materialised, span=span)
        right_reg = eval_ref_mod_expr(ctx, expr.right, materialised, span=span)
        result_reg = ctx.fresh_reg()

        op_str = expr.op
        binop_kind = resolve_binop(op_str)

        ctx.emit_inst(
            Binop(
                operator=binop_kind,
                left=left_reg,
                right=right_reg,
                result_reg=result_reg,
            ),
            span=span,
        )
        return result_reg

    else:
        # Fallback: treat as literal zero
        return ctx.const_to_reg(0, span=span)


# Maps canonical COBOL intrinsic function names to COBOL-layer builtin names.
_INTRINSIC_FUNCTIONS = {
    "UPPER-CASE": BuiltinName.UPPER_CASE,
    "LOWER-CASE": BuiltinName.LOWER_CASE,
    "TRIM": BuiltinName.TRIM,
    "CURRENT-DATE": BuiltinName.CURRENT_DATE,
    "LENGTH": BuiltinName.LENGTH,
    "NUMVAL": BuiltinName.NUMVAL,
    "NUMVAL-C": BuiltinName.NUMVAL_C,
    "TEST-NUMVAL": BuiltinName.TEST_NUMVAL,
    "TEST-NUMVAL-C": BuiltinName.TEST_NUMVAL_C,
    "INTEGER-OF-DATE": BuiltinName.INTEGER_OF_DATE,
    "DATE-OF-INTEGER": BuiltinName.DATE_OF_INTEGER,
    "MOD": BuiltinName.MOD,
    "REVERSE": BuiltinName.REVERSE,
    "MAX": BuiltinName.MAX,
    "MIN": BuiltinName.MIN,
    "SUM": BuiltinName.SUM,
    "ABS": BuiltinName.ABS,
    "SQRT": BuiltinName.SQRT,
    "SIN": BuiltinName.SIN,
    "COS": BuiltinName.COS,
    "TAN": BuiltinName.TAN,
    "ASIN": BuiltinName.ASIN,
    "ACOS": BuiltinName.ACOS,
    "ATAN": BuiltinName.ATAN,
    "RANGE": BuiltinName.RANGE,
    "MEAN": BuiltinName.MEAN,
    "MEDIAN": BuiltinName.MEDIAN,
    "MIDRANGE": BuiltinName.MIDRANGE,
    "VARIANCE": BuiltinName.VARIANCE,
    "ORD-MAX": BuiltinName.ORD_MAX,
    "ORD-MIN": BuiltinName.ORD_MIN,
    "CONCATENATE": BuiltinName.CONCATENATE,
    "EXP": BuiltinName.EXP,
    "LOG": BuiltinName.LOG,
    "FACTORIAL": BuiltinName.FACTORIAL,
    "INTEGER": BuiltinName.INTEGER,
    "INTEGER-PART": BuiltinName.INTEGER_PART,
    "FRACTION-PART": BuiltinName.FRACTION_PART,
    "REM": BuiltinName.REM,
    "SUBSTITUTE": BuiltinName.SUBSTITUTE,
    "EXP10": BuiltinName.EXP10,
    "LOG10": BuiltinName.LOG10,
    "CHAR": BuiltinName.CHAR,
    "ORD": BuiltinName.ORD,
    "DAY-OF-INTEGER": BuiltinName.DAY_OF_INTEGER,
    "INTEGER-OF-DAY": BuiltinName.INTEGER_OF_DAY,
    "ANNUITY": BuiltinName.ANNUITY,
    "PRESENT-VALUE": BuiltinName.PRESENT_VALUE,
    "DATE-TO-YYYYMMDD": BuiltinName.DATE_TO_YYYYMMDD,
    "DAY-TO-YYYYDDD": BuiltinName.DAY_TO_YYYYDDD,
    "YEAR-TO-YYYY": BuiltinName.YEAR_TO_YYYY,
}


def _lower_function_arg_to_string(
    scope: LoweringScope, arg: dict, precision: ArithmeticPrecision
) -> Register:
    """Lower one intrinsic-function argument dict to a string-valued register.

    Field references are decoded then stringified (intrinsics like UPPER-CASE
    operate on character data); literals are parsed as constants.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    kind = arg.get("kind", "lit")
    if kind == "ref":
        return _lower_ref_function_arg(scope, arg)
    if kind == "lit":
        return ctx.const_to_reg(ctx.parse_literal(arg.get("value", "")), span=span)
    from interpreter.cobol.condition_lowering import lower_expr_node

    value_reg = lower_expr_node(
        ctx,
        expr_from_dict(arg),
        materialised,
        receiver_decimals=precision.dmax,
        floating_receiver=precision.floating,
        span=span,
    )
    return ctx.emit_to_string(value_reg, span=span)


def _lower_ref_function_arg(scope: LoweringScope, arg: dict) -> Register:
    # Delegated rather than re-resolved: this path used to call
    # resolve_field_ref with neither the subscripts nor the reference
    # modification the node carries, so FUNCTION f(TBL(I)) always read
    # occurrence 1 (red-dragon-jscx). _lower_expr_dict is the one place that
    # decodes a structured ref, and it honours both.
    from interpreter.cobol.condition_lowering import (
        _lower_expr_dict,
        _unresolvable_operand,
    )

    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    name = arg.get("name", "")
    if not ctx.has_field(name, materialised):
        return _unresolvable_operand(ctx, name, span=span)
    decoded = _lower_expr_dict(ctx, arg, materialised, span=span)
    return ctx.emit_to_string(decoded, span=span)


def lower_function_operand(
    ctx: EmitContext,
    operand: FunctionCallOperand,
    materialised: MaterialisedSectionedLayout,
    *,
    span: SourceSpan | None = None,
) -> Register:
    """Lower an intrinsic FUNCTION call operand to a value register.

    Recognised functions (UPPER-CASE, LOWER-CASE, CURRENT-DATE) are emitted as a
    CallFunction against the COBOL-layer builtins. Unknown functions log a warning
    and fall back to their first argument (or empty string) — never silent wrong data.
    FUNCTION RANDOM keeps its state in the run-unit region, so it lowers on its own.
    """
    from interpreter.cobol.condition_lowering import standalone_precision

    precision = standalone_precision(
        ctx,
        FunctionNode(
            name=operand.name, args=tuple(expr_from_dict(a) for a in operand.args)
        ),
        materialised,
    )
    return lower_function_in_expression(
        LoweringScope(ctx, materialised, span), operand, precision
    )


def lower_function_in_expression(
    scope: LoweringScope, operand: FunctionCallOperand, precision: ArithmeticPrecision
) -> Register:
    lowering = _STATEFUL_FUNCTIONS.get(operand.name.upper(), _lower_builtin_function)
    expanded = replace(
        operand,
        args=tuple(
            chain.from_iterable(
                _all_subscripts_expanded(arg, scope.materialised)
                for arg in operand.args
            )
        ),
    )
    return lowering(scope, expanded, precision)


def _all_subscripts_expanded(
    arg: dict, materialised: MaterialisedSectionedLayout
) -> tuple[dict, ...]:
    return tuple(
        expr_to_dict(node)
        for node in _occurrences_named(expr_from_dict(arg), materialised)
    )


def _occurrences_named(
    node: ExprNode, materialised: MaterialisedSectionedLayout
) -> tuple[ExprNode, ...]:
    if not isinstance(node, (FieldRefNode, RefModNode)) or not any(
        isinstance(sub, AllSubscriptNode) for sub in node.subscripts
    ):
        return (node,)
    match = materialised.resolve_match(node.name, node.qualifiers)[0]
    dimensions = match.occurs_items[-len(node.subscripts) :]
    choices = tuple(
        _subscript_choices(sub, dimension)
        for sub, dimension in zip(node.subscripts, dimensions, strict=True)
    )
    return tuple(replace(node, subscripts=combo) for combo in product(*choices))


def _subscript_choices(
    sub: ExprNode, dimension: FieldLayout | DataLayout
) -> tuple[ExprNode, ...]:
    if not isinstance(sub, AllSubscriptNode):
        return (sub,)
    if dimension.occurs_depending_on != NO_ODO_OBJECT:
        raise ValueError(
            "the subscript ALL over an OCCURS DEPENDING ON table needs its "
            "run-time occurrence count, which an argument list fixed at "
            "lowering cannot carry"
        )
    return tuple(
        LiteralNode(str(occurrence))
        for occurrence in range(1, dimension.occurs_count + 1)
    )


def _lower_builtin_function(
    scope: LoweringScope, operand: FunctionCallOperand, precision: ArithmeticPrecision
) -> Register:
    if operand.name.upper() not in _INTRINSIC_EMITTERS:
        return _lower_unsupported_function(scope, operand, precision)
    arg_regs = tuple(
        _lower_function_arg_to_string(scope, arg, precision) for arg in operand.args
    )
    return _INTRINSIC_EMITTERS[operand.name.upper()](scope.emitter, arg_regs)


def _call_intrinsic_builtin(
    builtin: str, e: IrEmitter, args: tuple[Register, ...]
) -> Register:
    return e.call(builtin, *args)


_INTRINSIC_EMITTERS: Mapping[
    str, Callable[[IrEmitter, tuple[Register, ...]], Register]
] = {
    **{
        name: partial(_call_intrinsic_builtin, builtin)
        for name, builtin in _INTRINSIC_FUNCTIONS.items()
    },
    "STANDARD-DEVIATION": emit_standard_deviation,
}


def _lower_unsupported_function(
    scope: LoweringScope, operand: FunctionCallOperand, precision: ArithmeticPrecision
) -> Register:
    logger.warning(
        "Unsupported COBOL intrinsic FUNCTION %r — falling back to first argument",
        operand.name,
    )
    if not operand.args:
        return scope.ctx.const_to_reg("", span=scope.span)
    return _lower_function_arg_to_string(scope, operand.args[0], precision)


def _lower_random(
    scope: LoweringScope, operand: FunctionCallOperand, precision: ArithmeticPrecision
) -> Register:
    """FUNCTION RANDOM [(seed)]: load the run unit's generator state, step it,
    store it back, and return its value -- one sequence for the whole run unit."""
    ctx, span = scope.ctx, scope.span
    fl = RUN_UNIT_LAYOUT.lookup_or_raise(RANDOM_STATE)
    extent = whole_field_extent(fl, RegionId.RUN_UNIT)
    region_reg, state_reg = ctx.fresh_reg(), ctx.fresh_reg()
    offset_reg = ctx.const_to_reg(fl.offset, span=span)
    ctx.emit_inst(LoadVar(result_reg=region_reg, name=RUN_UNIT_VAR), span=span)
    ctx._emit_load_region(
        result_reg=state_reg,
        region_reg=region_reg,
        offset_reg=offset_reg,
        length=fl.byte_length,
        extent=extent,
        span=span,
    )
    seed_regs = tuple(
        _lower_function_arg_to_string(scope, arg, precision) for arg in operand.args[:1]
    )
    next_reg = _call_builtin(
        scope, BuiltinName.RANDOM_NEXT_STATE, (state_reg, *seed_regs)
    )
    ctx._emit_write_region(
        region_reg=region_reg,
        offset_reg=offset_reg,
        value_reg=next_reg,
        length=fl.byte_length,
        extent=extent,
        span=span,
    )
    return _call_builtin(scope, BuiltinName.RANDOM_VALUE, (next_reg,))


def _call_builtin(
    scope: LoweringScope, builtin: str, args: tuple[Register, ...]
) -> Register:
    result_reg = scope.ctx.fresh_reg()
    scope.ctx.emit_inst(
        CallFunction(result_reg=result_reg, func_name=FuncName(builtin), args=args),
        span=scope.span,
    )
    return result_reg


def _lower_when_compiled(
    scope: LoweringScope, operand: FunctionCallOperand, precision: ArithmeticPrecision
) -> Register:
    return scope.ctx.const_to_reg(
        when_compiled_text(scope.ctx.compiled_at), span=scope.span
    )


_STATEFUL_FUNCTIONS = {"RANDOM": _lower_random, "WHEN-COMPILED": _lower_when_compiled}

_FIXED_POINT_CATEGORIES: frozenset[CobolDataCategory] = frozenset(
    {
        CobolDataCategory.ZONED_DECIMAL,
        CobolDataCategory.COMP3,
        CobolDataCategory.BINARY,
    }
)


def lower_move(
    ctx: EmitContext,
    stmt: MoveStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """MOVE X [( start : length )] TO Y...Z.

    The source is evaluated ONCE and stored into every receiving field, each with
    its own reference modification and PICTURE conversion (COBOL semantics).
    """
    scope = LoweringScope(ctx, materialised, stmt.span)
    span = stmt.span
    emitter = scope.emitter

    # Intrinsic FUNCTION source (e.g. FUNCTION UPPER-CASE(...)): evaluate to a
    # value register, then distribute to every receiving field. Functions carry
    # no source-side reference modification, so the ref-mod block is skipped.
    if isinstance(stmt.source, FunctionCallOperand):
        source_value_reg = lower_function_operand(
            ctx, stmt.source, materialised, span=span
        )
        for target in stmt.targets:
            _store_move_value(scope, target, plain_move_source(source_value_reg))
        return

    if stmt.source.length_of.name:
        name = stmt.source.length_of.name
        if ctx.has_field(name, materialised):
            source_value_reg = ctx.emit_length_of(
                name, materialised, stmt.source.length_of.qualifiers, span=span
            )
        else:
            logger.warning("MOVE LENGTH OF unknown field %r — using 0", name)
            source_value_reg = ctx.const_to_reg(0, span=span)
        for target in stmt.targets:
            _store_move_value(scope, target, plain_move_source(source_value_reg))
        return

    # Raw figurative source (HIGH-VALUES / LOW-VALUES): these denote raw bytes —
    # 0xFF / 0x00 in every receiver position, whatever its category — so they
    # skip the character path, which converts per the receiving PICTURE and
    # would turn a numeric receiver into a number (red-dragon-raxa).
    # Each receiver's whole width is filled with the raw byte. A reference-modified
    # source slice still selects bytes, so it keeps the character path below; a
    # reference-modified TARGET likewise needs the splice path and is excluded here.
    if (
        not stmt.source.names_data
        and not stmt.source.is_reference_modified
        and ctx.figuratives.is_raw(stmt.source.name)
    ):
        for target in stmt.targets:
            _move_raw_figurative(scope, target, stmt.source.name)
        return

    # Resolve the source field once (when it is a field). A numeric-DISPLAY
    # (zoned) source carries an extra character representation, picked per target
    # by category-pair in _store_move_value (red-dragon-0fqr).
    _fill_pattern = ""
    source_fl: FieldLayout | None = None
    # Get the source value (decode field or literal) — evaluated ONCE.
    if stmt.source.names_data:
        source_ref, source_rr = ctx.resolve_field_ref(
            stmt.source.name,
            materialised,
            stmt.source.qualifiers,
            subscripts=stmt.source.subscripts,
            span=span,
        )
        source_fl = source_ref.fl
        # A ref-modified source is sliced as characters, so it must start from the
        # field's character image; without one, a numeric-DISPLAY source is sliced
        # at offsets that have slid left (red-dragon-wlms). An unmodified source
        # keeps the decoded-value reading, which _store_move_value converts per
        # receiving category.
        if stmt.source.is_reference_modified:
            value_str_reg = ctx.emit_decode_field_characters(
                source_rr,
                source_ref.fl,
                source_ref.offset_reg,
                extent=source_ref.extent,
                span=span,
            )
        else:
            decoded_reg = ctx.emit_decode_field(
                source_rr,
                source_ref.fl,
                source_ref.offset_reg,
                extent=source_ref.extent,
                span=span,
            )
            value_str_reg = ctx.emit_to_string(decoded_reg, span=span)
    else:
        literal = literal_characters(ctx.figuratives.translate(stmt.source.name))
        value_str_reg = ctx.const_to_reg(literal, span=span)
        if not stmt.source.is_reference_modified:
            _fill_pattern = (
                literal
                if stmt.source.all_literal
                else ctx.figuratives.characters.get(stmt.source.name.upper(), "")
            )

    # Handle reference modification if present
    if stmt.source.ref_mod_start is not None:
        # Evaluate start and length expressions
        start_reg = eval_ref_mod_expr(
            ctx, stmt.source.ref_mod_start, materialised, span=span
        )
        # COBOL uses 1-indexed positions, but SLICE uses 0-indexed.
        # Convert: start_0indexed = start_1indexed - 1
        one_reg = ctx.const_to_reg(1, span=span)
        start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                operator=BinopKind.SUB,
                left=start_reg,
                right=one_reg,
                result_reg=start_0indexed_reg,
            ),
            span=span,
        )

        if stmt.source.ref_mod_length is not None:
            # Both start and length specified: SLICE operation
            length_reg = eval_ref_mod_expr(
                ctx, stmt.source.ref_mod_length, materialised, span=span
            )
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=result_reg,
                    func_name=FuncName(BuiltinName.STRING_SLICE),
                    args=(value_str_reg, start_0indexed_reg, length_reg),
                ),
                span=span,
            )
            value_str_reg = result_reg
        else:
            # Only start specified, no length: SLICE from start to end
            # Use a large sentinel as length to get the substring to end.
            large_length = ctx.const_to_reg(999999, span=span)
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(
                CallFunction(
                    result_reg=result_reg,
                    func_name=FuncName(BuiltinName.STRING_SLICE),
                    args=(value_str_reg, start_0indexed_reg, large_length),
                ),
                span=span,
            )
            value_str_reg = result_reg

    sent_whole = source_fl is not None and not stmt.source.is_reference_modified
    source = MoveSource(
        value=value_str_reg,
        characters=(
            emit_field_digit_image(emitter, source_rr, source_ref)
            if sent_whole
            and source_ref.fl.type_descriptor.category in _FIXED_POINT_CATEGORIES
            else value_str_reg
        ),
        number=(
            _emit_de_edit(scope, value_str_reg, source_ref.fl)
            if sent_whole
            and source_ref.fl.type_descriptor.category
            == CobolDataCategory.NUMERIC_EDITED
            else value_str_reg
        ),
        group=sent_whole and source_ref.fl.is_group,
    )

    # Store the (once-evaluated) source value into each receiving field. Each
    # target gets its own reference modification and PICTURE conversion; the
    # base source value (source_value_reg) is never clobbered across targets.
    for target in stmt.targets:
        if not ctx.has_field(target.name, materialised) and _is_special_register(
            target.name
        ):
            logger.warning(
                "MOVE into special register %r is not modelled — skipping", target.name
            )
            continue
        # Figurative constants fill ALL receiver positions with the same character.
        # MOVE ZEROES TO PIC X(3) → '000', not '0  '.  Build a target-width
        # repeated string at compile time (constant folding) and use it instead of
        # the single-character source for this target only.  Only applies when
        # there is no target reference modification (a ref-mod write targets a
        # specific slice, so the fill character must remain single for SPLICE).
        effective_source = source
        if (
            _fill_pattern
            and not target.is_reference_modified
            and ctx.has_field(target.name, materialised)
        ):
            tgt_ref, _ = ctx.resolve_field_ref(
                target.name, materialised, target.qualifiers, span=span
            )
            fill_width = tgt_ref.fl.byte_length
            filled = ctx.const_to_reg(
                repeat_to_width(_fill_pattern, fill_width), span=span
            )
            effective_source = plain_move_source(filled)
        _store_move_value(scope, target, effective_source)


def _move_raw_figurative(
    scope: LoweringScope, target: RefModOperand, name: str
) -> None:
    """Fill one receiver with HIGH-VALUE's or LOW-VALUE's raw byte; a
    reference-modified receiver takes the byte's character through the SPLICE
    path."""
    if not scope.ctx.has_field(target.name, scope.materialised):
        _warn_unmodelled_special_register(target.name)
        return
    if target.is_reference_modified:
        src_reg = scope.emitter.text(chr(scope.ctx.figuratives.raw_byte(name)))
        _store_move_value(scope, target, plain_move_source(src_reg))
        return
    _fill_whole_receiver(scope, target, name)


def _fill_whole_receiver(
    scope: LoweringScope, target: RefModOperand, name: str
) -> None:
    """An alphanumeric-edited receiver takes the figurative as a literal of its
    size, edited in; any other takes the raw byte in every position."""
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    target_ref, target_rr = ctx.resolve_field_ref(
        target.name,
        materialised,
        target.qualifiers,
        subscripts=target.subscripts,
        span=span,
    )
    if target_ref.fl.type_descriptor.category == CobolDataCategory.ALPHANUMERIC_EDITED:
        fill = _figurative_literal(ctx, name, target_ref.fl.byte_length)
        _store_move_value(scope, target, plain_move_source(scope.emitter.text(fill)))
        return
    ctx.emit_fill_raw_byte(
        target_rr,
        target_ref.fl,
        ctx.figuratives.raw_byte(name),
        target_ref.offset_reg,
        extent=target_ref.extent,
        span=span,
    )


def _warn_unmodelled_special_register(name: str) -> None:
    if _is_special_register(name):
        logger.warning("MOVE into special register %r is not modelled — skipping", name)


def _figurative_literal(ctx: EmitContext, name: str, width: int) -> str:
    """A figurative constant as the alphanumeric literal of the given size."""
    return repeat_to_width(ctx.figuratives.characters[name.upper()], width)


def _emit_de_edit(
    scope: LoweringScope, image_reg: Register, source_fl: FieldLayout
) -> Register:
    """The value of a numeric-edited source, de-edited by IR fixed by its
    PICTURE (interpreter.cobol.de_edit_ir)."""
    td = source_fl.type_descriptor
    value = emit_de_edit(
        scope.emitter,
        image_reg,
        de_edit_plan(td.pic_string, td.currency, td.decimal_point_is_comma),
    )
    return scope.ctx.emit_to_string(value, span=scope.span)


def _store_move_value(
    scope: LoweringScope, target: RefModOperand, source: MoveSource
) -> None:
    """Store an already-evaluated MOVE source value into one receiving field.

    Applies the target's own reference modification (SPLICE write path) and
    PICTURE conversion. The source value register is never clobbered.

    A numeric sender moved to a character receiver sends its digit image (an
    unsigned integer of its digit positions, P positions as zeros) rather than
    its value; a numeric-edited sender moved to a numeric or numeric-edited
    receiver is de-edited first. Neither applies to a reference-modified
    receiver (MoveSource.value_for).

    A group sender is an alphanumeric move with no conversion (ANSI X3.23-1985
    MOVE; IBM Enterprise COBOL LR, group moves): its characters fill the
    receiver as one alphanumeric item, whatever the receiver's category
    (MoveSource.storage_for).
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    target_ref, target_rr = ctx.resolve_field_ref(
        target.name,
        materialised,
        target.qualifiers,
        subscripts=target.subscripts,
        span=span,
    )
    source_value_reg = source.value_for(target, target_ref.fl)
    target_value_reg = source_value_reg

    # Handle target reference modification (write path): MOVE X TO Y(start:length)
    if target.ref_mod_start is not None:
        # Load current target field value as string (needed for SPLICE)
        target_decoded = ctx.emit_decode_field(
            target_rr,
            target_ref.fl,
            target_ref.offset_reg,
            extent=target_ref.extent,
            span=span,
        )
        target_str_reg = ctx.emit_to_string(target_decoded, span=span)

        # Evaluate target ref mod start; convert 1-indexed → 0-indexed
        tgt_start_reg = eval_ref_mod_expr(
            ctx, target.ref_mod_start, materialised, span=span
        )
        one_reg = ctx.const_to_reg(1, span=span)
        tgt_start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                operator=BinopKind.SUB,
                left=tgt_start_reg,
                right=one_reg,
                result_reg=tgt_start_0indexed_reg,
            ),
            span=span,
        )

        # Evaluate target ref mod length (or use large sentinel for "to end")
        if target.ref_mod_length is not None:
            tgt_length_reg = eval_ref_mod_expr(
                ctx, target.ref_mod_length, materialised, span=span
            )
        else:
            tgt_length_reg = ctx.const_to_reg(999999, span=span)

        # Emit SPLICE: replace substring in target with source value
        spliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=spliced_reg,
                func_name=FuncName(BuiltinName.STRING_SPLICE),
                args=(
                    target_str_reg,
                    tgt_start_0indexed_reg,
                    tgt_length_reg,
                    source_value_reg,
                ),
            ),
            span=span,
        )
        target_value_reg = spliced_reg

    ctx.emit_encode_and_write(
        target_rr,
        source.storage_for(target, target_ref.fl),
        target_value_reg,
        target_ref.offset_reg,
        extent=target_ref.extent,
        span=span,
    )


def lower_move_corresponding(
    ctx: EmitContext,
    stmt: MoveCorrespondingStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """MOVE CORRESPONDING src TO dst: each corresponding pair is a separate MOVE."""
    moves = [
        MoveStatement(source=pair.source, targets=[pair.target], span=stmt.span)
        for target in stmt.targets
        for pair in _corresponding_pairs(
            stmt.source, target, pairs_for_move, materialised
        )
    ]
    for move in moves:
        lower_move(ctx, move, materialised)


def _corresponding_pairs(
    source: RefModOperand,
    target: RefModOperand,
    pairs_with: PairRule,
    materialised: MaterialisedSectionedLayout,
) -> tuple[CorrespondingPair, ...]:
    source_match, source_group = _require_group(source, materialised)
    target_match, target_group = _require_group(target, materialised)
    return tuple(
        CorrespondingPair(
            source=_corresponding_operand(source, source_match, path),
            target=_corresponding_operand(target, target_match, path),
        )
        for path in corresponding_paths(source_group, target_group, pairs_with)
    )


def _corresponding_operand(
    group: RefModOperand, match: DataItemMatch, path: tuple[str, ...]
) -> RefModOperand:
    """The item at ``path`` below a CORRESPONDING operand, qualified by every
    group above it and subscripted by the operand's own subscripts."""
    return RefModOperand(
        name=path[-1],
        qualifiers=(
            *reversed(path[:-1]),
            match.name,
            *(name for name, _ in reversed(match.ancestors)),
        ),
        subscripts=group.subscripts,
        rounded=group.rounded,
    )


def _require_group(
    operand: RefModOperand, materialised: MaterialisedSectionedLayout
) -> tuple[DataItemMatch, DataLayout]:
    match, _, _ = materialised.resolve_match(operand.name, operand.qualifiers)
    if not isinstance(match.item, DataLayout):
        raise LookupError(f"CORRESPONDING operand is not a group: {operand.name!r}")
    return match, match.item


def lower_arithmetic_corresponding(
    ctx: EmitContext,
    stmt: ArithmeticCorrespondingStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ADD/SUBTRACT CORRESPONDING: each pair is a separate ADD/SUBTRACT with the
    statement's ROUNDED, and its size error phrases run once after every pair."""
    scope = LoweringScope(ctx, materialised, stmt.span)
    pairs = _corresponding_pairs(
        stmt.source, stmt.target, pairs_for_arithmetic, materialised
    )
    step = partial(_corresponding_step, scope, stmt.op)
    _store(
        scope,
        SizeErrorStore(
            stmt=stmt,
            guard=_no_size_error_guard,
            receivers=pairs,
            step=step,
            follow_up=_no_follow_up,
        ),
    )


def _corresponding_step(
    scope: LoweringScope, op: str, pair: CorrespondingPair
) -> ReceiverResult:
    sending = _decode_operand(scope, pair.source)
    return _in_place_step(scope, InPlaceOperation(op=op, sending=sending), pair.target)


def _emit_arithmetic_writeback(
    scope: LoweringScope, receiver: ArithmeticReceiver, result_str_reg: Register
) -> None:
    """Write arithmetic result into target, applying target ref-mod if present.

    Plain write: encode result_str_reg into the target field.
    Ref-mod write (ARITHMETIC TARGET REF-MOD): decode existing target value,
    splice the result string into the requested substring position, then encode
    and write back the spliced whole — identical to the MOVE target ref-mod path.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    target_op, target_ref, target_rr = receiver.operand, receiver.ref, receiver.region
    fl = target_ref.fl
    offset_reg = target_ref.offset_reg

    if target_op.ref_mod_start is not None:
        target_decoded = ctx.emit_decode_field(
            target_rr, fl, offset_reg, extent=target_ref.extent, span=span
        )
        target_str_reg = ctx.emit_to_string(target_decoded, span=span)

        tgt_start_reg = eval_ref_mod_expr(
            ctx, target_op.ref_mod_start, materialised, span=span
        )
        one_reg = ctx.const_to_reg(1, span=span)
        tgt_start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                operator=BinopKind.SUB,
                left=tgt_start_reg,
                right=one_reg,
                result_reg=tgt_start_0indexed_reg,
            ),
            span=span,
        )

        tgt_length_reg = _ref_mod_length(scope, target_op)

        # Parse the text as an exact number, then normalise → int → zero-padded
        # string ('015') before splicing to fill the exact ref-mod width.
        parsed_norm = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=parsed_norm,
                func_name=FuncName(BuiltinName.COBOL_PARSE_NUMBER),
                args=(result_str_reg,),
            ),
            span=span,
        )
        int_norm = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=int_norm, func_name=FuncName("int"), args=(parsed_norm,)
            ),
            span=span,
        )
        int_str_reg = ctx.emit_to_string(int_norm, span=span)
        padded_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=padded_reg,
                func_name=FuncName(BuiltinName.STRING_ZFILL),
                args=(int_str_reg, tgt_length_reg),
            ),
            span=span,
        )

        spliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=spliced_reg,
                func_name=FuncName(BuiltinName.STRING_SPLICE),
                args=(
                    target_str_reg,
                    tgt_start_0indexed_reg,
                    tgt_length_reg,
                    padded_reg,
                ),
            ),
            span=span,
        )
        ctx.emit_encode_and_write(
            target_rr, fl, spliced_reg, offset_reg, extent=target_ref.extent, span=span
        )
    else:
        ctx.emit_encode_and_write(
            target_rr,
            fl,
            result_str_reg,
            offset_reg,
            extent=target_ref.extent,
            span=span,
        )


def _ref_mod_length(scope: LoweringScope, operand: RefModOperand) -> Register:
    match operand.ref_mod_length:
        case None:
            return scope.ctx.const_to_reg(999999, span=scope.span)
        case length:
            return eval_ref_mod_expr(
                scope.ctx, length, scope.materialised, span=scope.span
            )


def _ref_mod_number(
    scope: LoweringScope, decoded: Register, operand: RefModOperand, start: RefModExpr
) -> Register:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    start_0indexed = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            operator=BinopKind.SUB,
            left=eval_ref_mod_expr(ctx, start, materialised, span=span),
            right=ctx.const_to_reg(1, span=span),
            result_reg=start_0indexed,
        ),
        span=span,
    )
    sliced = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=sliced,
            func_name=FuncName(BuiltinName.STRING_SLICE),
            args=(
                ctx.emit_to_string(decoded, span=span),
                start_0indexed,
                _ref_mod_length(scope, operand),
            ),
        ),
        span=span,
    )
    number = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=number,
            func_name=FuncName(BuiltinName.COBOL_PARSE_NUMBER),
            args=(sliced,),
        ),
        span=span,
    )
    return number


def _read_receiver(scope: LoweringScope, receiver: ArithmeticReceiver) -> Register:
    decoded = scope.ctx.emit_decode_field(
        receiver.region,
        receiver.ref.fl,
        receiver.ref.offset_reg,
        extent=receiver.ref.extent,
        span=scope.span,
    )
    match receiver.operand.ref_mod_start:
        case None:
            return decoded
        case start:
            return _ref_mod_number(scope, decoded, receiver.operand, start)


def _resolve_receiver(
    scope: LoweringScope, operand: RefModOperand
) -> ArithmeticReceiver:
    ref, region = scope.ctx.resolve_field_ref(
        operand.name,
        scope.materialised,
        operand.qualifiers,
        subscripts=operand.subscripts,
        span=scope.span,
    )
    return ArithmeticReceiver(operand=operand, ref=ref, region=region)


def _decode_operand(scope: LoweringScope, operand: RefModOperand) -> ArithmeticValue:
    ctx = scope.ctx
    if not operand.names_data:
        literal = ctx.parse_literal(ctx.figuratives.translate(operand.name))
        return _operand_value(
            scope, operand, ctx.const_to_reg(literal, span=scope.span)
        )
    receiver = _resolve_receiver(scope, operand)
    return _operand_value(scope, operand, _read_receiver(scope, receiver))


def _sum_operands(
    scope: LoweringScope,
    operands: Sequence[RefModOperand],
    receivers: Sequence[RefModOperand],
) -> ArithmeticValue:
    values = [_decode_operand(scope, o) for o in operands]
    return reduce(
        lambda total, value: _emit_verb_operation(
            scope, ArithmeticOperation(op="ADD", left=total, right=value), receivers
        ),
        values[1:],
        values[0],
    )


def _write_result(scope: LoweringScope, result: ReceiverResult) -> None:
    _emit_arithmetic_writeback(
        scope,
        result.receiver,
        scope.ctx.emit_to_string(result.value, span=scope.span),
    )


def _stored_value(scope: LoweringScope, result: ReceiverResult) -> ReceiverResult:
    ctx, span = scope.ctx, scope.span
    receiver = result.receiver
    if not receiver.operand.rounded:
        return result
    rounded = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=rounded,
            func_name=FuncName(BuiltinName.COBOL_ROUND),
            args=(
                result.value,
                ctx.const_to_reg(
                    receiver_rounding_places(receiver.ref.fl.type_descriptor),
                    span=span,
                ),
            ),
        ),
        span=span,
    )
    return ReceiverResult(receiver=receiver, value=rounded)


def _write_unless_size_error(scope: LoweringScope, result: ReceiverResult) -> Register:
    ctx, span = scope.ctx, scope.span
    stored = _stored_value(scope, result)
    overflow = _compute_overflow_flag(
        scope, stored.value, stored.receiver.ref.fl.type_descriptor
    )
    write_label = ctx.fresh_label("size_ok")
    skip_label = ctx.fresh_label("size_err_skip")
    ctx.emit_inst(
        BranchIf(cond_reg=overflow, branch_targets=(skip_label, write_label)),
        span=span,
    )
    ctx.emit_inst(Label_(label=write_label), span=span)
    _write_result(scope, stored)
    ctx.emit_inst(Branch(label=skip_label), span=span)
    ctx.emit_inst(Label_(label=skip_label), span=span)
    return overflow


def _any_flag(scope: LoweringScope, flags: Sequence[Register]) -> Register:
    ctx, span = scope.ctx, scope.span

    def _or(left: Register, right: Register) -> Register:
        combined = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=combined,
                operator=resolve_binop("or"),
                left=left,
                right=right,
            ),
            span=span,
        )
        return combined

    match flags:
        case [first, *rest]:
            return reduce(_or, rest, first)
        case _:
            return ctx.const_to_reg(False, span=span)


def _emit_zero_divisor_guard(
    scope: LoweringScope, divisor: ArithmeticValue, on_size_err_label: CodeLabel
) -> None:
    ctx, span = scope.ctx, scope.span
    is_zero = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=is_zero,
            operator=resolve_binop("=="),
            left=divisor.register,
            right=ctx.const_to_reg(0, span=span),
        ),
        span=span,
    )
    compute_label = ctx.fresh_label("divide_compute")
    ctx.emit_inst(
        BranchIf(cond_reg=is_zero, branch_targets=(on_size_err_label, compute_label)),
        span=span,
    )
    ctx.emit_inst(Label_(label=compute_label), span=span)


def _emit_size_error_arm(scope: LoweringScope, arm: SizeErrorArm) -> None:
    ctx, span = scope.ctx, scope.span
    ctx.emit_inst(Label_(label=arm.label), span=span)
    arm.follow_up()
    for child in arm.statements:
        ctx.lower_statement(child, scope.materialised)
    ctx.emit_inst(Branch(label=arm.end), span=span)


def _store_guarded[R](scope: LoweringScope, store: SizeErrorStore[R]) -> None:
    ctx, span = scope.ctx, scope.span
    on_label = ctx.fresh_label("on_size_err")
    not_on_label = ctx.fresh_label("not_on_size_err")
    end_label = ctx.fresh_label("size_err_end")
    store.guard(on_label)
    flags = [
        _write_unless_size_error(scope, store.step(target))
        for target in store.receivers
    ]
    ctx.emit_inst(
        BranchIf(
            cond_reg=_any_flag(scope, flags),
            branch_targets=(on_label, not_on_label),
        ),
        span=span,
    )
    _emit_size_error_arm(
        scope,
        SizeErrorArm(
            label=on_label,
            statements=store.stmt.on_size_error,
            follow_up=_no_follow_up,
            end=end_label,
        ),
    )
    _emit_size_error_arm(
        scope,
        SizeErrorArm(
            label=not_on_label,
            statements=store.stmt.not_on_size_error,
            follow_up=store.follow_up,
            end=end_label,
        ),
    )
    ctx.emit_inst(Label_(label=end_label), span=span)


def _store_unguarded(scope: LoweringScope, result: ReceiverResult) -> None:
    _write_result(scope, _stored_value(scope, result))


def _store[R](scope: LoweringScope, store: SizeErrorStore[R]) -> None:
    if store.stmt.on_size_error or store.stmt.not_on_size_error:
        _store_guarded(scope, store)
        return
    for target in store.receivers:
        _store_unguarded(scope, store.step(target))
    store.follow_up()


def _no_size_error_guard(_on_label: CodeLabel) -> None:
    return None


def _no_follow_up() -> None:
    return None


def _in_place_step(
    scope: LoweringScope, operation: InPlaceOperation, target: RefModOperand
) -> ReceiverResult:
    receiver = _resolve_receiver(scope, target)
    current = _operand_value(scope, target, _read_receiver(scope, receiver))
    return ReceiverResult(
        receiver=receiver,
        value=_emit_verb_operation(
            scope,
            ArithmeticOperation(op=operation.op, left=current, right=operation.sending),
            (target,),
        ).register,
    )


def _giving_step(
    scope: LoweringScope, result: Register, target: RefModOperand
) -> ReceiverResult:
    return ReceiverResult(receiver=_resolve_receiver(scope, target), value=result)


def _emit_remainder(
    scope: LoweringScope, stmt: ArithmeticStatement, operands: DivideOperands
) -> None:
    match stmt.remainder:
        case None:
            return
        case remainder_op:
            quotient_op = stmt.giving[0]
            value = _remainder_value(
                scope.emitter,
                operands,
                field_scale(
                    scope.materialised.resolve(
                        quotient_op.name, quotient_op.qualifiers
                    )[0].type_descriptor
                ).decimal_places,
            )
            receiver = _resolve_receiver(scope, remainder_op)
            _write_result(scope, ReceiverResult(receiver=receiver, value=value))


def _remainder_value(
    e: IrEmitter, operands: DivideOperands, quotient_places: int
) -> Register:
    dividend, divisor = operands.dividend, operands.divisor
    product_places = quotient_places + divisor.scale.decimal_places
    quotient = e.call(
        BuiltinName.COBOL_DIVIDE,
        dividend.register,
        divisor.register,
        e.int_(quotient_places),
    )
    product = e.call(
        BuiltinName.COBOL_MULTIPLY, quotient, divisor.register, e.int_(product_places)
    )
    return e.call(
        BuiltinName.COBOL_SUBTRACT,
        dividend.register,
        product,
        e.int_(max(dividend.scale.decimal_places, product_places)),
    )


def _divisor_guard(
    scope: LoweringScope, op: str, divisor: ArithmeticValue
) -> SizeErrorGuard:
    if op != "DIVIDE":
        return _no_size_error_guard
    return partial(_emit_zero_divisor_guard, scope, divisor)


def lower_arithmetic(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """ADD/SUBTRACT/MULTIPLY/DIVIDE with every sending operand applied to every receiver."""
    scope = LoweringScope(ctx, materialised, stmt.span)
    if stmt.giving:
        _lower_arithmetic_giving(scope, stmt)
        return
    sending = _sum_operands(scope, stmt.operands, stmt.targets)
    step = partial(_in_place_step, scope, InPlaceOperation(op=stmt.op, sending=sending))
    _store(
        scope,
        SizeErrorStore(
            stmt=stmt,
            guard=_divisor_guard(scope, stmt.op, sending),
            receivers=tuple(stmt.targets),
            step=step,
            follow_up=_no_follow_up,
        ),
    )


def _lower_arithmetic_giving(scope: LoweringScope, stmt: ArithmeticStatement) -> None:
    first = _decode_operand(scope, stmt.operands[0])
    rest = _sum_operands(scope, stmt.operands[1:], stmt.giving)
    result = _emit_verb_operation(
        scope, ArithmeticOperation(op=stmt.op, left=first, right=rest), stmt.giving
    )
    step = partial(_giving_step, scope, result.register)
    remainder = partial(
        _emit_remainder, scope, stmt, DivideOperands(dividend=first, divisor=rest)
    )
    _store(
        scope,
        SizeErrorStore(
            stmt=stmt,
            guard=_divisor_guard(scope, stmt.op, rest),
            receivers=tuple(stmt.giving),
            step=step,
            follow_up=remainder,
        ),
    )


def _compute_operand(target: ComputeTarget) -> RefModOperand:
    return RefModOperand(
        name=target.name,
        qualifiers=target.qualifiers,
        subscripts=target.subscripts,
        rounded=target.rounded,
    )


def _known_compute_target(scope: LoweringScope, target: ComputeTarget) -> bool:
    if scope.ctx.has_field(target.name, scope.materialised):
        return True
    logger.warning("COMPUTE target %s not found in layout", target.name)
    return False


def lower_compute(
    ctx: EmitContext,
    stmt: ComputeStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """COMPUTE target(s) = arithmetic-expression."""
    scope = LoweringScope(ctx, materialised, stmt.span)
    span = stmt.span
    targets = [
        _compute_operand(t) for t in stmt.targets if _known_compute_target(scope, t)
    ]
    target_types = [
        (materialised.resolve(t.name, t.qualifiers)[0].type_descriptor, t.rounded)
        for t in targets
    ]
    result_reg = lower_expr_node(
        ctx,
        stmt.expression,
        materialised,
        receiver_decimals=max(
            (_receiver_decimals(td, rounded) for td, rounded in target_types), default=0
        ),
        floating_receiver=any(is_floating_type(td) for td, _ in target_types),
        span=span,
    )
    if not targets:
        return
    step = partial(_giving_step, scope, result_reg)
    _store(
        scope,
        SizeErrorStore(
            stmt=stmt,
            guard=_no_size_error_guard,
            receivers=tuple(targets),
            step=step,
            follow_up=_no_follow_up,
        ),
    )


def lower_if(
    ctx: EmitContext,
    stmt: IfStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """IF condition ... [ELSE ...] END-IF."""
    span = stmt.span
    cond_reg = ctx.lower_condition(stmt.condition, materialised, span=span)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")

    ctx.emit_inst(
        BranchIf(
            cond_reg=cond_reg,
            branch_targets=(true_label, false_label),
        ),
        span=span,
    )

    ctx.emit_inst(Label_(label=true_label), span=span)
    for child in stmt.children:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)

    ctx.emit_inst(Label_(label=false_label), span=span)
    for child in stmt.else_children:
        ctx.lower_statement(child, materialised)
    ctx.emit_inst(Branch(label=end_label), span=span)

    ctx.emit_inst(Label_(label=end_label), span=span)


def lower_continue(
    ctx: EmitContext,
    stmt: ContinueStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CONTINUE — no-op, emit nothing."""
    pass


def lower_next_sentence(
    ctx: EmitContext,
    stmt: NextSentenceStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """NEXT SENTENCE — branch past the period ending the enclosing sentence."""
    ctx.emit_inst(Branch(label=ctx.sentence_exit()), span=stmt.span)


def lower_exit(
    ctx: EmitContext,
    stmt: ExitStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """EXIT PARAGRAPH / SECTION / PERFORM [CYCLE] branch past what they leave.

    A plain EXIT is the paragraph-end no-op and emits nothing.
    """
    if stmt.kind not in _EXIT_TARGETS:
        return
    ctx.emit_inst(Branch(label=_EXIT_TARGETS[stmt.kind](ctx)), span=stmt.span)


_EXIT_TARGETS: Mapping[ExitKind, Callable[[EmitContext], CodeLabel]] = {
    ExitKind.PARAGRAPH: EmitContext.paragraph_exit,
    ExitKind.SECTION: EmitContext.section_exit,
    ExitKind.PERFORM: EmitContext.perform_leave,
    ExitKind.PERFORM_CYCLE: EmitContext.perform_cycle,
}


_DEFAULT_SPACES = RefModOperand(name="SPACES", kind=OperandKind.FIGURATIVE)
_DEFAULT_ZERO = RefModOperand(name="ZERO", kind=OperandKind.FIGURATIVE)

_INITIALIZE_CATEGORY = {
    CobolDataCategory.ZONED_DECIMAL: InitializeCategory.NUMERIC,
    CobolDataCategory.COMP3: InitializeCategory.NUMERIC,
    CobolDataCategory.BINARY: InitializeCategory.NUMERIC,
    CobolDataCategory.COMP1: InitializeCategory.NUMERIC,
    CobolDataCategory.COMP2: InitializeCategory.NUMERIC,
    CobolDataCategory.ALPHANUMERIC: InitializeCategory.ALPHANUMERIC,
    CobolDataCategory.ALPHANUMERIC_EDITED: InitializeCategory.ALPHANUMERIC_EDITED,
    CobolDataCategory.NUMERIC_EDITED: InitializeCategory.NUMERIC_EDITED,
}


def lower_initialize(
    ctx: EmitContext,
    stmt: InitializeStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """INITIALIZE is a MOVE into each elementary item of each operand.

    Without REPLACING a character item receives SPACES and a numeric or
    numeric-edited one ZERO. With REPLACING only the items of a named category are
    moved into, each receiving its category's value; the rest are left alone.
    """
    scope = LoweringScope(ctx, materialised, stmt.span)
    moves = [
        MoveStatement(source=value, targets=[target.operand], span=stmt.span)
        for operand in stmt.operands
        for target in _initialize_targets(scope, operand)
        for value in _initial_values(target.storage.type_descriptor, stmt.replacing)
    ]
    for move in moves:
        lower_move(ctx, move, materialised)


def _initialize_targets(
    scope: LoweringScope, operand: RefModOperand
) -> tuple[InitializeTarget, ...]:
    if not scope.ctx.has_field(operand.name, scope.materialised):
        logger.warning("INITIALIZE target %s not found in layout", operand.name)
        return ()
    match, _, _ = scope.materialised.resolve_match(operand.name, operand.qualifiers)
    return initialize_targets(operand, match)


def _initial_values(
    td: CobolTypeDescriptor, replacing: Sequence[InitializeReplacing]
) -> tuple[RefModOperand, ...]:
    if not replacing:
        return (_DEFAULT_SPACES if td.holds_characters else _DEFAULT_ZERO,)
    category = (
        InitializeCategory.ALPHABETIC
        if td.alphabetic
        else _INITIALIZE_CATEGORY[td.category]
    )
    return tuple(phrase.by for phrase in replacing if phrase.category is category)


def _set_condition_name(
    scope: LoweringScope, target: SetOperand, value_str: str
) -> None:
    """SET <88-condition-name> TO TRUE|FALSE — write the VALUE into the parent.

    For TRUE: write the first ConditionValue's literal into the parent elementary
    field (mirrors the condition-read path in condition_lowering). For FALSE: the
    ConditionNameIndex/ConditionValue carries no FALSE-value, so we warn and skip
    rather than guessing (never silently behave as TRUE).
    """
    ctx, span = scope.ctx, scope.span
    truth = str(value_str).strip().upper()
    condition_name = target.name
    entry = ctx._condition_index.lookup(condition_name, target.qualifiers)
    parent = replace(target, name=entry.parent.name, qualifiers=entry.parent.qualifiers)

    if truth == "FALSE":
        if not entry.parent.name:
            logger.warning(
                "SET %s TO FALSE: condition not in index — skipping", condition_name
            )
            return
        parent_ref, parent_rr = _set_operand_ref(scope, parent)
        if parent_ref.fl.type_descriptor.holds_characters:
            # WHEN SET TO FALSE IS not in scope — write SPACES (field-length fill)
            false_val: object = " " * max(parent_ref.fl.byte_length, 1)
        else:
            false_val = 0
        ctx.emit_encode_and_write(
            parent_rr,
            parent_ref.fl,
            ctx.const_to_reg(false_val, span=span),
            parent_ref.offset_reg,
            extent=parent_ref.extent,
            span=span,
        )
        return

    if truth != "TRUE":
        logger.warning(
            "SET %s TO %r is not a TRUE/FALSE condition assignment — skipping",
            condition_name,
            value_str,
        )
        return

    if not entry.values:
        logger.warning(
            "SET %s TO TRUE has no condition VALUE to write — skipping",
            condition_name,
        )
        return

    # First discrete value / range-low is what makes the condition true.
    cv = entry.values[0]
    parent_ref, parent_rr = _set_operand_ref(scope, parent)

    # For an ALPHANUMERIC (PIC X) parent, the 88 VALUE is a character literal —
    # write its characters verbatim. It must reach the alphanumeric encoder as a
    # quoted string-literal Const so the VM keeps it a str; an unquoted digit
    # literal (VALUE '1', '0') is parsed as an int, which __string_to_bytes then
    # rejects as non-str and silently drops, leaving the byte unchanged
    # (red-dragon-0sq2). Numeric parents keep the parsed numeric literal.
    #
    # A figurative-constant VALUE (LOW-VALUES / SPACES / ZEROS / HIGH-VALUES) must
    # expand to its fill character repeated to the parent's byte length — NOT be
    # written as the literal text 'LOW-VALUES' (CardDemo COACTUPC
    # ACUP-DETAILS-NOT-FETCHED VALUES LOW-VALUES, SPACES).
    figuratives = ctx.figuratives.characters if cv.figurative else {}
    fig_fill = figuratives.get(cv.from_val.upper())
    if parent_ref.fl.type_descriptor.holds_characters:
        if fig_fill is not None:
            filled = fig_fill * max(parent_ref.fl.byte_length, 1)
            value_reg = ctx.const_to_reg(filled, span=span)
        else:
            value_reg = ctx.const_to_reg(cv.from_val, span=span)
    elif fig_fill is not None and cv.from_val.upper() in ("ZERO", "ZEROS", "ZEROES"):
        value_reg = ctx.const_to_reg(0, span=span)
    else:
        value_reg = ctx.const_to_reg(ctx.parse_literal(cv.from_val), span=span)
    ctx.emit_encode_and_write(
        parent_rr,
        parent_ref.fl,
        value_reg,
        parent_ref.offset_reg,
        extent=parent_ref.extent,
        span=span,
    )


def _set_operand_ref(
    scope: LoweringScope, operand: SetOperand
) -> tuple[ResolvedFieldRef, Register]:
    """The field a SET operand names, at the occurrence its subscripts select."""
    return scope.ctx.resolve_field_ref(
        operand.name,
        scope.materialised,
        qualifiers=operand.qualifiers,
        subscripts=tuple(expr_from_dict(s) for s in operand.subscripts),
        span=scope.span,
    )


def _decode_set_operand(scope: LoweringScope, operand: SetOperand) -> Register:
    """The value of the data item a SET operand names."""
    ref, region_reg = _set_operand_ref(scope, operand)
    return scope.ctx.emit_decode_field(
        region_reg, ref.fl, ref.offset_reg, extent=ref.extent, span=scope.span
    )


def _set_switch(scope: LoweringScope, mnemonic_name: str, value: SetOperand) -> None:
    """SET mnemonic-name TO ON|OFF: the switch the mnemonic names takes that
    status for the rest of the run."""
    ctx, span = scope.ctx, scope.span
    ctx.emit_inst(
        CallFunction(
            result_reg=ctx.fresh_reg(),
            func_name=FuncName("__cobol_set_switch"),
            args=(
                ctx.const_to_reg(ctx.switches.environment_of(mnemonic_name), span=span),
                ctx.const_to_reg(SwitchStatus(value.value).value, span=span),
            ),
        ),
        span=span,
    )


def _set_to(scope: LoweringScope, target: SetOperand, value: SetOperand) -> None:
    """One target of SET ... TO, with the value its own TO phrase gives it."""
    ctx = scope.ctx
    target_name = target.text
    if ctx.switches.has_mnemonic(target_name):
        _set_switch(scope, target_name, value)
        return
    if ctx._condition_index.has_condition(target_name):
        _set_condition_name(scope, target, value.text)
        return
    if not ctx.has_field(target_name, scope.materialised):
        logger.warning("SET target %s not found in layout", target_name)
        return
    _set_data_item(scope, target, value)


def _set_data_item(scope: LoweringScope, target: SetOperand, value: SetOperand) -> None:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    target_ref, target_rr = _set_operand_ref(scope, target)
    # SET A TO B is legal when B is a data item; the value is raw operand text
    # from the bridge and is never tested for being a name. Untested, it wrote
    # the two characters "B" — which encodes into a numeric field as 0, so the
    # symptom is a plausible zero, not a crash.
    value_str_reg = (
        _decode_set_operand(scope, value)
        if ctx.has_field(value.text, materialised)
        else ctx.const_to_reg(value.text, span=span)
    )
    ctx.emit_encode_and_write(
        target_rr,
        target_ref.fl,
        value_str_reg,
        target_ref.offset_reg,
        extent=target_ref.extent,
        span=span,
    )


def lower_set(
    ctx: EmitContext,
    stmt: SetStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """SET target TO value / SET target UP|DOWN BY value.

    A target that names a level-88 condition (e.g. SET FLG-ON TO TRUE) writes the
    condition's VALUE into its parent elementary field, so a later test of that 88
    reads true. SET <88> TO FALSE requires a captured false-value; absent one it
    warns rather than guessing.
    """
    if is_pointer_set(ctx, stmt, materialised):
        lower_pointer_set(ctx, stmt, materialised)
        return
    scope = LoweringScope(ctx, materialised, stmt.span)
    span = stmt.span
    if stmt.set_type == "TO":
        for target, value in zip(stmt.targets, stmt.values, strict=True):
            _set_to(scope, target, value)
    elif stmt.set_type == "BY":
        step_val = stmt.values[0].text if stmt.values else "1"
        op = "+" if stmt.by_type == "UP" else "-"
        for target in stmt.targets:
            if not ctx.has_field(target.text, materialised):
                logger.warning("SET target %s not found in layout", target.text)
                continue
            target_ref, target_rr = _set_operand_ref(scope, target)
            tgt_decoded = ctx.emit_decode_field(
                target_rr,
                target_ref.fl,
                target_ref.offset_reg,
                extent=target_ref.extent,
                span=span,
            )
            # SET ... UP/DOWN BY <data-item> takes the same path as TO above.
            if ctx.has_field(str(step_val), materialised):
                step_reg = _decode_set_operand(scope, stmt.values[0])
            else:
                step_reg = ctx.const_to_reg(ctx.parse_literal(step_val), span=span)
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=result_reg,
                    operator=resolve_binop(op),
                    left=tgt_decoded,
                    right=step_reg,
                ),
                span=span,
            )
            result_str_reg = ctx.emit_to_string(result_reg, span=span)
            ctx.emit_encode_and_write(
                target_rr,
                target_ref.fl,
                result_str_reg,
                target_ref.offset_reg,
                extent=target_ref.extent,
                span=span,
            )


_DISPLAYED_AS_ZONED = frozenset({CobolDataCategory.BINARY, CobolDataCategory.COMP3})


def _lower_display_operand(scope: LoweringScope, operand: RefModOperand) -> Register:
    """Lower one DISPLAY operand to a register holding its display string."""
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    if operand.names_data:
        ref, rr = ctx.resolve_field_ref(
            operand.name,
            materialised,
            operand.qualifiers,
            subscripts=operand.subscripts,
            span=span,
        )
        td = ref.fl.type_descriptor
        display_reg = (
            emit_display_image(
                scope.emitter,
                ctx.emit_decode_field(
                    rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
                ),
                td,
            )
            if td.category in _DISPLAYED_AS_ZONED
            else ctx.emit_decode_field_characters(
                rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
            )
        )
    else:
        display_reg = ctx.const_to_reg(
            ctx.figuratives.characters.get(
                operand.name.upper(), literal_characters(operand.name)
            ),
            span=span,
        )

    if operand.ref_mod_start is not None:
        raw_start_reg = eval_ref_mod_expr(
            ctx, operand.ref_mod_start, materialised, span=span
        )
        one_reg = ctx.const_to_reg(1, span=span)
        start_0indexed_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=start_0indexed_reg,
                operator=resolve_binop("-"),
                left=raw_start_reg,
                right=one_reg,
            ),
            span=span,
        )
        length_reg = (
            eval_ref_mod_expr(ctx, operand.ref_mod_length, materialised, span=span)
            if operand.ref_mod_length is not None
            else ctx.const_to_reg(9999, span=span)
        )
        sliced_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=sliced_reg,
                func_name=FuncName(BuiltinName.STRING_SLICE),
                args=(display_reg, start_0indexed_reg, length_reg),
            ),
            span=span,
        )
        display_reg = sliced_reg

    return display_reg


def lower_display(
    ctx: EmitContext,
    stmt: DisplayStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """DISPLAY operand [operand ...] [WITH NO ADVANCING] — one line per statement.

    COBOL concatenates the operands with no separator; we lower each to its
    display string, fold them with string-concat, and print the result ONCE.
    The device then moves to the next line, unless WITH NO ADVANCING leaves it
    where the last operand ended.
    """
    scope = LoweringScope(ctx, materialised, stmt.span)
    span = stmt.span
    operand_regs = [_lower_display_operand(scope, operand) for operand in stmt.operands]
    if not operand_regs:
        return

    combined_reg = operand_regs[0]
    for next_reg in operand_regs[1:]:
        folded = ctx.fresh_reg()
        ctx.emit_inst(
            CallFunction(
                result_reg=folded,
                func_name=FuncName(BuiltinName.STRING_CONCAT_PAIR),
                args=(combined_reg, next_reg),
            ),
            span=span,
        )
        combined_reg = folded

    ctx.emit_inst(
        CallFunction(
            result_reg=ctx.fresh_reg(),
            func_name=FuncName("print" if stmt.no_advancing else "println"),
            args=(combined_reg,),
        ),
        span=span,
    )


def lower_stop_run(
    ctx: EmitContext,
    stmt: StopRunStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """STOP RUN — unconditionally terminates the entire run unit, unlike
    GOBACK/EXIT PROGRAM (which return control to the caller).

    Nothing is returned, so there is no caller to copy RETURN-CODE up to — but the
    run unit ends HERE, wherever "here" is, so this program's RETURN-CODE is the
    one the operating system receives, even when STOP RUN is issued inside a
    subprogram and the entry program never finishes (red-dragon-cvwu).
    """
    emit_publish_run_unit_return_code(
        ctx,
        emit_return_code_load(ctx, materialised, span=stmt.span),
        span=stmt.span,
    )
    ctx.emit_inst(Halt_(), span=stmt.span)


def lower_goback(
    ctx: EmitContext,
    stmt: GobackStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """GOBACK — return control to the caller, carrying RETURN-CODE."""
    lower_program_exit(ctx, materialised, span=stmt.span)


def lower_exit_program(
    ctx: EmitContext,
    stmt: ExitProgramStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """EXIT PROGRAM — return control to the caller, carrying RETURN-CODE."""
    lower_program_exit(ctx, materialised, span=stmt.span)


def _lower_computed_goto(scope: LoweringScope, computed: ComputedGoto) -> None:
    """GO TO p1 ... pN DEPENDING ON idx — branch to the idx-th (1-based) target;
    out-of-range (idx <= 0 or idx > N) falls through to the next statement."""
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    index = computed.index
    ref, rr = ctx.resolve_field_ref(
        index.name,
        materialised,
        index.qualifiers,
        subscripts=index.subscripts,
        span=span,
    )
    idx_reg = ctx.emit_decode_field(
        rr, ref.fl, ref.offset_reg, extent=ref.extent, span=span
    )
    for k, target in enumerate(computed.targets, start=1):
        k_reg = ctx.const_to_reg(k, span=span)
        cmp_reg = ctx.fresh_reg()
        ctx.emit_inst(
            Binop(
                result_reg=cmp_reg,
                operator=resolve_binop("=="),
                left=Register(str(idx_reg)),
                right=Register(str(k_reg)),
            ),
            span=span,
        )
        match_lbl = ctx.fresh_label("goto_dep_match")
        next_lbl = ctx.fresh_label("goto_dep_next")
        ctx.emit_inst(
            BranchIf(cond_reg=cmp_reg, branch_targets=(match_lbl, next_lbl)),
            span=span,
        )
        ctx.emit_inst(Label_(label=match_lbl), span=span)
        ctx.emit_inst(Branch(label=ctx.procedure_label(target)), span=span)
        ctx.emit_inst(Label_(label=next_lbl), span=span)


def lower_goto(
    ctx: EmitContext,
    stmt: GotoStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """GO TO — simple, computed (DEPENDING ON), or altered."""
    span = stmt.span
    form = stmt.form
    if isinstance(form, SimpleGoto):
        ctx.emit_inst(Branch(label=ctx.procedure_label(form.target)), span=span)
    elif isinstance(form, ComputedGoto):
        _lower_computed_goto(LoweringScope(ctx, materialised, span), form)
    # AlteredGoto: GO TO. with target supplied by ALTER — no-op, behavior
    # intentionally unchanged (not exercised by any test).
