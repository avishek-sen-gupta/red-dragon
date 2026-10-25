"""CALL, ENTRY, CANCEL statement lowering."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from cobol_asg.call_target import CallTarget
from cobol_asg.cobol_statements import (
    CallStatement,
    CallUsingParam,
    CancelStatement,
    CobolStatementType,
    EntryStatement,
)
from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_asg.index_types import INDEX_ITEM
from cobol_asg.nonnumeric_literal import literal_characters
from cobol_asg.operand_kind import OperandKind
from cobol_asg.pic_parser import parse_pic
from cobol_asg.ref_mod import RefModExpr, RefModLiteral, RefModOperand
from cobol_memory.field_extent import FieldExtent, Precision
from cobol_memory.region_id import RegionId
from interpreter.cobol.by_value_operand_error import ByValueOperandError
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.cobol.length_of_by_reference_error import LengthOfByReferenceError
from interpreter.cobol.lower_arithmetic import eval_ref_mod_expr
from interpreter.cobol.lower_program_exit import (
    emit_return_code_load,
    emit_return_code_store,
    emit_return_code_value,
)
from interpreter.cobol.lowering_scope import LoweringScope
from interpreter.cobol.pointer_lowering import PointerLowering
from interpreter.cobol.program_figuratives import ProgramFiguratives
from interpreter.cobol.program_object import (
    CANCEL_PREFIX,
    ENTRY_PREFIX,
    INITIAL_STATE_FIELD,
    entry_var,
)
from interpreter.cobol.run_unit import PROGRAM_DIRECTORY
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.undeclared_data_name_error import line_of
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.instructions import (
    AllocRegion,
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    CallWithMemory,
    Label_,
    LoadFieldIndirect,
    LoadVar,
    NewArray,
    NewObject,
    StoreField,
    StoreIndex,
    StoreVar,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import resolve_binop
from interpreter.project.argument_mode import ArgumentMode
from interpreter.register import Register
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)

LITERAL_ARGUMENT = "%LITERAL"
_ZEROS = frozenset({"ZERO", "ZEROS", "ZEROES"})
_FULLWORD = parse_pic("S9(9)", usage="COMP-5")
_COMP2 = parse_pic("", usage="COMP-2")
_LENGTH_REGISTER = parse_pic("9(9)", usage="BINARY")
_DIRECTORY_HOLDS = "dict_contains_key"
_BY_VALUE_CATEGORIES = frozenset(
    {CobolDataCategory.BINARY, CobolDataCategory.COMP1, CobolDataCategory.COMP2}
)
_DISPLAY_CATEGORIES = frozenset(
    {
        CobolDataCategory.ZONED_DECIMAL,
        CobolDataCategory.ALPHANUMERIC,
        CobolDataCategory.ALPHANUMERIC_EDITED,
        CobolDataCategory.NUMERIC_EDITED,
    }
)

type ArgumentAddress = tuple[Register, Register, Register, bool]


def _emit_callee_name(scope: LoweringScope, operand: RefModOperand) -> Register:
    """Emit IR that produces the callee's name from a data item, at run time.

    ``CALL identifier`` names the program by the *contents* of a data item, so
    the name only exists once the field has been read. The operand is the same
    ``RefModOperand`` MOVE and STRING consume, so its subscripts, ``OF``/``IN``
    qualifiers and reference-modification bounds are honoured by the machinery
    that already handles them — ``CALL WS-PROG(1:8)`` is the common idiom, since
    a program name is 8 characters and the holding field is usually wider.
    """
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    if not ctx.has_field(operand.name, materialised):
        raise ValueError(
            f"CALL {operand.name}: the callee is a data name that resolves to no "
            "field, so the program to call cannot be determined"
        )

    field_ref, region_reg = ctx.resolve_field_ref(
        operand.name,
        materialised,
        qualifiers=operand.qualifiers,
        subscripts=operand.subscripts,
        span=span,
    )
    decoded_reg = ctx.emit_decode_field(
        region_reg,
        field_ref.fl,
        field_ref.offset_reg,
        extent=field_ref.extent,
        span=span,
    )
    name_reg = ctx.emit_to_string(decoded_reg, span=span)

    if operand.ref_mod_start is None:
        return name_reg

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
    if operand.ref_mod_length is not None:
        length_reg = eval_ref_mod_expr(
            ctx, operand.ref_mod_length, materialised, span=span
        )
    else:
        length_reg = ctx.const_to_reg(9999, span=span)
    sliced_reg = ctx.fresh_reg()
    ctx.emit_inst(
        CallFunction(
            result_reg=sliced_reg,
            func_name=FuncName(BuiltinName.STRING_SLICE),
            args=(name_reg, start_0indexed_reg, length_reg),
        ),
        span=span,
    )
    return sliced_reg


def _emit_program_name(scope: LoweringScope, operand: RefModOperand) -> Register:
    """The program an identifier names, computed in IR: the field's text trimmed
    of spaces and upper-cased (COBOL program names ignore case)."""
    name_reg = _emit_callee_name(scope, operand)
    trimmed = _emit_builtin(scope, BuiltinName.TRIM, (name_reg,))
    return _emit_builtin(scope, BuiltinName.UPPER_CASE, (trimmed,))


def _emit_entry_var_name(scope: LoweringScope, operand: RefModOperand) -> Register:
    """The entry variable a ``CALL identifier`` names: the program name, prefixed,
    so the VM looks it up as it is."""
    upper = _emit_program_name(scope, operand)
    prefix = scope.ctx.const_to_reg(ENTRY_PREFIX, span=scope.span)
    return _emit_builtin(scope, BuiltinName.STRING_CONCAT_PAIR, (prefix, upper))


def _emit_builtin(
    scope: LoweringScope, name: str, args: tuple[Register, ...]
) -> Register:
    result = scope.ctx.fresh_reg()
    scope.ctx.emit_inst(
        CallFunction(result_reg=result, func_name=FuncName(name), args=args),
        span=scope.span,
    )
    return result


def lower_call(
    ctx: EmitContext,
    stmt: CallStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CALL (identifier | literal) USING params — one address per argument.

    The callee receives an argument array: per USING argument, by position, a
    region and an offset into it. BY REFERENCE passes the argument's own bytes,
    so the callee's writes land in the caller as they happen and nothing is
    copied back; BY CONTENT, BY VALUE and a literal pass a fresh copy; OMITTED
    passes a marker. The callee binds each LINKAGE 01 to its argument.
    """
    scope = LoweringScope(ctx, materialised, stmt.span)
    args_reg = _argument_array(scope, stmt.using)
    location = (
        _emit_entry_var_name(scope, stmt.target.identifier)
        if stmt.target.identifier is not None
        else entry_var(stmt.target.literal)
    )

    if stmt.on_exception:
        _lower_guarded_call(scope, stmt, location, args_reg)
    else:
        _emit_program_call(scope, stmt, location, args_reg)
        _lower_statements(scope, stmt.not_on_exception)

    logger.info(
        "CALL %s with %d params (CallWithMemory)",
        stmt.target.describe(),
        len(stmt.using),
    )


def _lower_guarded_call(
    scope: LoweringScope,
    stmt: CallStatement,
    location: VarName | Register,
    args_reg: Register,
) -> None:
    ctx, span = scope.ctx, scope.span
    call_label, exception_label, end_label = (
        ctx.fresh_label(name)
        for name in ("call_available", "call_exception", "call_end")
    )
    _emit_presence_branch(scope, location, (call_label, exception_label))
    ctx.emit_inst(Label_(label=exception_label), span=span)
    _lower_statements(scope, stmt.on_exception)
    ctx.emit_inst(Branch(label=end_label), span=span)
    ctx.emit_inst(Label_(label=call_label), span=span)
    _emit_program_call(scope, stmt, location, args_reg)
    _lower_statements(scope, stmt.not_on_exception)
    ctx.emit_inst(Branch(label=end_label), span=span)
    ctx.emit_inst(Label_(label=end_label), span=span)


def _emit_presence_branch(
    scope: LoweringScope,
    location: VarName | Register,
    targets: tuple[CodeLabel, CodeLabel],
) -> None:
    name_reg = (
        location
        if isinstance(location, Register)
        else scope.ctx.const_to_reg(str(location), span=scope.span)
    )
    present_reg = _emit_builtin(scope, BuiltinName.PROGRAM_PRESENT, (name_reg,))
    scope.ctx.emit_inst(
        BranchIf(cond_reg=present_reg, branch_targets=targets),
        span=scope.span,
    )


def _lower_statements(
    scope: LoweringScope, statements: Sequence[CobolStatementType]
) -> None:
    for statement in statements:
        scope.ctx.lower_statement(statement, scope.materialised)


def _emit_program_call(
    scope: LoweringScope,
    stmt: CallStatement,
    location: VarName | Register,
    args_reg: Register,
) -> None:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    # The callee returns its RETURN-CODE in result_reg, and the copy-up below
    # writes it into the caller's. Seeding that same register with the caller's
    # OWN value first is what makes a callee that returns nothing harmless: a
    # VOID return is deliberately not written back into the caller's register
    # (see run.py), so an unseeded result_reg would still be unwritten and would
    # resolve to the literal string "%n" — which the copy-up would then store
    # into RETURN-CODE as garbage.
    result_reg = emit_return_code_load(ctx, materialised, span=span)
    ctx.emit_inst(
        CallWithMemory(result_reg=result_reg, location=location, memory=args_reg),
        span=span,
    )

    # Copy-up: a returning COBOL program leaves its RETURN-CODE in register 15
    # and its caller stores R15 into its own. result_reg is that R15.
    emit_return_code_store(ctx, materialised, result_reg, span=span)

    # Restore the caller's __ws_region binding. CallWithMemory dispatches into the
    # callee's func_init_params, whose body re-binds the shared __ws_region var to
    # the CALLEE's WS region. When the callee frame is popped on EXIT PROGRAM the
    # caller's __ws_region binding does not reliably survive, so consumers that
    # read __ws_region directly (e.g. CICS SEND/RECEIVE MAP via
    # _get_ws_region_addr) would otherwise see the callee's region after the CALL.
    # caller_ws_reg holds the caller's WS region (loaded at function entry), so
    # re-binding __ws_region to it is a no-op for field access but repairs the var
    # for direct readers. (Field access reloads via the singleton, so it was never
    # affected; this only matters for the shared __ws_region var.)
    _ws_layout, caller_ws_reg = materialised.working_storage
    ctx.emit_inst(
        StoreVar(name=VarName("__ws_region"), value_reg=caller_ws_reg), span=span
    )

    _store_giving(scope, stmt.giving)


def _store_giving(scope: LoweringScope, giving: RefModOperand) -> None:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    if giving.name and ctx.has_field(giving.name, materialised):
        giving_ref, giving_rr = ctx.resolve_field_ref(
            giving.name,
            materialised,
            giving.qualifiers,
            giving.subscripts,
            span=span,
        )
        str_reg = ctx.emit_to_string(
            emit_return_code_value(ctx, materialised, span=span), span=span
        )
        ctx.emit_encode_and_write(
            giving_rr,
            giving_ref.fl,
            str_reg,
            giving_ref.offset_reg,
            extent=giving_ref.extent,
            span=span,
        )


def _argument_array(scope: LoweringScope, using: Sequence[CallUsingParam]) -> Register:
    """One element per USING argument, by position: its argument mode, its byte
    length, and, unless OMITTED, whether it is signed, a region and an offset."""
    ctx, span = scope.ctx, scope.span
    args = ctx.fresh_reg()
    ctx.emit_inst(
        NewArray(result_reg=args, size_reg=ctx.const_to_reg(len(using), span=span)),
        span=span,
    )
    _store_field(scope, args, "count", ctx.const_to_reg(len(using), span=span))
    for position, param in enumerate(using):
        ctx.emit_inst(
            StoreIndex(
                arr_reg=args,
                index_reg=ctx.const_to_reg(position, span=span),
                value_reg=_argument(scope, param),
            ),
            span=span,
        )
    return args


def _argument(scope: LoweringScope, param: CallUsingParam) -> Register:
    ctx, span = scope.ctx, scope.span
    element = ctx.fresh_reg()
    ctx.emit_inst(NewObject(result_reg=element), span=span)
    mode = ArgumentMode.OMITTED if param.omitted else ArgumentMode(param.param_type)
    _store_field(scope, element, "mode", ctx.const_to_reg(mode.value, span=span))
    if param.omitted:
        _store_field(scope, element, "length", ctx.const_to_reg(0, span=span))
        return element
    _store_address(scope, element, _address(scope, param))
    return element


def _store_address(
    scope: LoweringScope, element: Register, address: ArgumentAddress
) -> None:
    region, offset, length, signed = address
    _store_field(scope, element, "length", length)
    _store_field(
        scope, element, "signed", scope.ctx.const_to_reg(signed, span=scope.span)
    )
    _store_field(scope, element, "region", region)
    _store_field(scope, element, "offset", offset)


def _address(scope: LoweringScope, param: CallUsingParam) -> ArgumentAddress:
    """BY REFERENCE: the argument's own bytes. Anything else: a fresh copy. With
    the argument's byte length and whether it is signed."""
    if param.address_of or param.is_literal or param.kind is OperandKind.LENGTH_OF:
        return _computed_argument(scope, param)
    return _data_argument(scope, param)


def _computed_argument(scope: LoweringScope, param: CallUsingParam) -> ArgumentAddress:
    if param.address_of:
        return _pointer_argument(scope, param)
    if param.is_literal:
        return _literal_copy(scope, param)
    return _length_of_copy(scope, param)


def _data_argument(scope: LoweringScope, param: CallUsingParam) -> ArgumentAddress:
    ctx, materialised, span = scope.ctx, scope.materialised, scope.span
    ref, region_reg = ctx.resolve_field_ref(
        param.name, materialised, param.qualifiers, param.subscripts, span=span
    )
    _refuse_by_value(param, ref.fl, line_of(span))
    if param.ref_mod.is_reference_modified:
        return _substring_argument(scope, param, ref, region_reg)
    if param.param_type == "REFERENCE":
        return (
            region_reg,
            ref.offset_reg,
            ctx.const_to_reg(ref.fl.byte_length, span=span),
            ref.fl.type_descriptor.signed,
        )
    return _content_copy(scope, ref, region_reg, param.name)


def _substring_argument(
    scope: LoweringScope,
    param: CallUsingParam,
    ref: ResolvedFieldRef,
    region_reg: Register,
) -> ArgumentAddress:
    """A reference-modified operand: BY REFERENCE the substring's own bytes,
    anything else the substring in a fresh copy of the whole item."""
    start = _substring_start(scope, param.ref_mod)
    length = _substring_length(scope, param.ref_mod, ref.fl, start)
    if param.param_type == "REFERENCE":
        return region_reg, _binop(scope, "+", ref.offset_reg, start), length, False
    copy, _offset, _length, _signed = _content_copy(scope, ref, region_reg, param.name)
    return copy, start, length, False


def _substring_length(
    scope: LoweringScope, operand: RefModOperand, field: FieldLayout, start: Register
) -> Register:
    match operand.ref_mod_length:
        case None:
            return _binop(scope, "-", field.byte_length, start)
        case length:
            return _bound(scope, length)


def _substring_start(scope: LoweringScope, operand: RefModOperand) -> Register:
    match operand.ref_mod_start:
        case None:
            return scope.ctx.const_to_reg(0, span=scope.span)
        case start:
            return _binop(scope, "-", _bound(scope, start), 1)


def _bound(scope: LoweringScope, expr: RefModExpr) -> Register:
    return eval_ref_mod_expr(scope.ctx, expr, scope.materialised, span=scope.span)


def _binop(
    scope: LoweringScope, operator: str, left: Register | int, right: Register | int
) -> Register:
    ctx, span = scope.ctx, scope.span
    result = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result,
            operator=resolve_binop(operator),
            left=_register(scope, left),
            right=_register(scope, right),
        ),
        span=span,
    )
    return result


def _register(scope: LoweringScope, value: Register | int) -> Register:
    match value:
        case Register():
            return value
        case int():
            return scope.ctx.const_to_reg(value, span=scope.span)


def _refuse_by_value(param: CallUsingParam, field: FieldLayout, line: int) -> None:
    if param.param_type == "VALUE" and not allowed_by_value(field, param.ref_mod):
        raise ByValueOperandError(param.name, line)


def allowed_by_value(field: FieldLayout, ref_mod: RefModOperand) -> bool:
    """IBM's CALL BY VALUE operands: an elementary binary, COMP-1, COMP-2 or
    pointer item, one alphanumeric character, or a reference-modified DISPLAY
    item of length 1."""
    descriptor = field.type_descriptor
    if field.is_group or descriptor == INDEX_ITEM:
        return False
    if ref_mod.is_reference_modified:
        return descriptor.category in _DISPLAY_CATEGORIES and _one_long(ref_mod)
    return descriptor.category in _BY_VALUE_CATEGORIES or (
        descriptor.category is CobolDataCategory.ALPHANUMERIC and field.byte_length == 1
    )


def _one_long(ref_mod: RefModOperand) -> bool:
    match ref_mod.ref_mod_length:
        case RefModLiteral(value=value):
            return value.isdigit() and int(value) == 1
        case _:
            return False


def _pointer_argument(scope: LoweringScope, param: CallUsingParam) -> ArgumentAddress:
    ctx = scope.ctx
    length = ctx.addressing_mode.pointer_type.byte_length
    region, offset = PointerLowering(
        ctx, scope.materialised, scope.span
    ).address_argument(
        param.name, param.qualifiers, _copy_extent(length, LITERAL_ARGUMENT)
    )
    return region, offset, ctx.const_to_reg(length, span=scope.span), False


def _length_of_copy(scope: LoweringScope, param: CallUsingParam) -> ArgumentAddress:
    """LENGTH OF an item, in a fresh copy of the special register, PIC 9(9) BINARY.
    IBM passes it only BY CONTENT or BY VALUE."""
    if param.param_type == "REFERENCE":
        raise LengthOfByReferenceError(param.name, line_of(scope.span))
    length = scope.ctx.emit_length_of(
        param.name, scope.materialised, param.qualifiers, span=scope.span
    )
    return _value_copy(scope, _layout(_LENGTH_REGISTER), length)


def _literal_copy(scope: LoweringScope, param: CallUsingParam) -> ArgumentAddress:
    """A literal argument in the representation IBM defines for it, in a fresh copy."""
    ctx = scope.ctx
    layout = _layout(_literal_type(param, ctx.figuratives))
    value = ctx.const_to_reg(_literal_value(param, ctx.figuratives), span=scope.span)
    return _value_copy(scope, layout, value)


def _value_copy(
    scope: LoweringScope, layout: FieldLayout, value: Register
) -> ArgumentAddress:
    ctx, span = scope.ctx, scope.span
    copy = ctx.fresh_reg()
    ctx.emit_inst(
        AllocRegion(
            result_reg=copy, size_reg=ctx.const_to_reg(layout.byte_length, span=span)
        ),
        span=span,
    )
    zero = ctx.const_to_reg(0, span=span)
    ctx.emit_encode_and_write(
        copy,
        layout,
        value,
        zero,
        extent=_copy_extent(layout.byte_length, LITERAL_ARGUMENT),
        span=span,
    )
    return (
        copy,
        zero,
        ctx.const_to_reg(layout.byte_length, span=span),
        layout.type_descriptor.signed,
    )


def _literal_type(
    param: CallUsingParam, figuratives: ProgramFiguratives
) -> CobolTypeDescriptor:
    """BY VALUE: a numeric literal or ZERO as a fullword binary, a floating-point
    literal as COMP-2. Anything else: its characters, a figurative constant one."""
    word = param.name.upper()
    if param.param_type == "VALUE" and param.numeric:
        return _COMP2 if "E" in word else _FULLWORD
    if param.param_type == "VALUE" and _is_zero(param):
        return _FULLWORD
    return parse_pic(f"X({max(len(_literal_value(param, figuratives)), 1)})")


def _is_zero(param: CallUsingParam) -> bool:
    return param.kind is OperandKind.FIGURATIVE and param.name.upper() in _ZEROS


def _literal_value(param: CallUsingParam, figuratives: ProgramFiguratives) -> str:
    if param.kind is OperandKind.FIGURATIVE:
        return figuratives.characters.get(param.name.upper(), param.name)
    return literal_characters(param.name)


def _layout(type_descriptor: CobolTypeDescriptor) -> FieldLayout:
    return FieldLayout(
        name=LITERAL_ARGUMENT,
        type_descriptor=type_descriptor,
        offset=0,
        byte_length=type_descriptor.byte_length,
    )


def _content_copy(
    scope: LoweringScope,
    ref: ResolvedFieldRef,
    region_reg: Register,
    name: str,
) -> ArgumentAddress:
    ctx, span = scope.ctx, scope.span
    length = ref.fl.byte_length
    copy = ctx.fresh_reg()
    ctx.emit_inst(
        AllocRegion(result_reg=copy, size_reg=ctx.const_to_reg(length, span=span)),
        span=span,
    )
    value = ctx.fresh_reg()
    ctx._emit_load_region(
        result_reg=value,
        region_reg=region_reg,
        offset_reg=ref.offset_reg,
        length=length,
        extent=ref.extent,
        span=span,
    )
    zero = ctx.const_to_reg(0, span=span)
    ctx._emit_write_region(
        region_reg=copy,
        offset_reg=zero,
        value_reg=value,
        length=length,
        extent=_copy_extent(length, name),
        span=span,
    )
    return (
        copy,
        zero,
        ctx.const_to_reg(length, span=span),
        ref.fl.type_descriptor.signed,
    )


def _copy_extent(length: int, name: str) -> FieldExtent:
    return FieldExtent(RegionId.CALL_ARGUMENT, 0, length, Precision.EXACT, name)


def _store_field(
    scope: LoweringScope, obj: Register, name: str, value: Register
) -> None:
    scope.ctx.emit_inst(
        StoreField(obj_reg=obj, field_name=FieldName(name), value_reg=value),
        span=scope.span,
    )


def lower_entry(
    ctx: EmitContext,
    stmt: EntryStatement,
    _materialised: MaterialisedSectionedLayout,
) -> None:
    """ENTRY 'name' — alternate entry point for a subprogram."""
    if stmt.entry_name:
        ctx.emit_inst(
            Label_(label=CodeLabel(f"entry_{stmt.entry_name}")), span=stmt.span
        )
        logger.info("ENTRY %s", stmt.entry_name)


def lower_cancel(
    ctx: EmitContext,
    stmt: CancelStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """CANCEL program ... — each named program in the run unit is put back in its
    initial state, so its next CALL re-initialises its WORKING-STORAGE. A literal
    names the program; an identifier's contents do, read at run time as CALL
    identifier reads them. A name not in the run unit's program directory is
    passed over."""
    scope = LoweringScope(ctx, materialised, stmt.span)
    _ = [_cancel_program(scope, target) for target in stmt.programs]


def _cancel_program(scope: LoweringScope, target: CallTarget) -> None:
    ctx, span = scope.ctx, scope.span
    name = _cancelled_name(scope, target)
    directory, present = _directory_lookup(scope, name)
    reset_label, end_label = (
        ctx.fresh_label(label) for label in ("cancel_reset", "cancel_end")
    )
    ctx.emit_inst(
        BranchIf(cond_reg=present, branch_targets=(reset_label, end_label)),
        span=span,
    )
    ctx.emit_inst(Label_(label=reset_label), span=span)
    _reset_program(scope, directory, name)
    ctx.emit_inst(Branch(label=end_label), span=span)
    ctx.emit_inst(Label_(label=end_label), span=span)
    logger.info("CANCEL %s", target.describe())


def _directory_lookup(
    scope: LoweringScope, name: Register
) -> tuple[Register, Register]:
    """The run unit's program directory, and whether it holds ``name``."""
    directory = scope.ctx.fresh_reg()
    scope.ctx.emit_inst(
        LoadVar(result_reg=directory, name=PROGRAM_DIRECTORY), span=scope.span
    )
    return directory, _emit_builtin(scope, _DIRECTORY_HOLDS, (directory, name))


def _cancelled_name(scope: LoweringScope, target: CallTarget) -> Register:
    """The program a CANCEL operand names: a literal as written, an identifier's
    contents as CALL identifier reads them; upper-cased either way, as the
    program directory is keyed."""
    match target.identifier:
        case RefModOperand() as operand:
            return _emit_program_name(scope, operand)
        case _:
            return scope.ctx.const_to_reg(target.literal.upper(), span=scope.span)


def _reset_program(scope: LoweringScope, directory: Register, name: Register) -> None:
    """IBM's initial state for the next CALL, and the program's open files closed."""
    _mark_initial_state(scope, directory, name)
    _call_cancel_routine(scope, name)


def _mark_initial_state(
    scope: LoweringScope, directory: Register, name: Register
) -> None:
    ctx, span = scope.ctx, scope.span
    program = ctx.fresh_reg()
    ctx.emit_inst(
        LoadFieldIndirect(result_reg=program, obj_reg=directory, name_reg=name),
        span=span,
    )
    ctx.emit_inst(
        StoreField(
            obj_reg=program,
            field_name=INITIAL_STATE_FIELD,
            value_reg=ctx.const_to_reg(True, span=span),
        ),
        span=span,
    )


def _call_cancel_routine(scope: LoweringScope, name: Register) -> None:
    """The cancelled program's own routine closes the files it left open."""
    ctx, span = scope.ctx, scope.span
    prefix = ctx.const_to_reg(CANCEL_PREFIX, span=span)
    location = _emit_builtin(scope, BuiltinName.STRING_CONCAT_PAIR, (prefix, name))
    ctx.emit_inst(
        CallWithMemory(
            result_reg=ctx.fresh_reg(),
            location=location,
            memory=_argument_array(scope, ()),
        ),
        span=span,
    )
