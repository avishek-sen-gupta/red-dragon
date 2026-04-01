"""Arithmetic and control-flow statement lowering — MOVE, ADD/SUB/MUL/DIV,
COMPUTE, IF, EVALUATE, CONTINUE, EXIT, INITIALIZE, SET, DISPLAY, STOP RUN, GO TO.
"""

from __future__ import annotations

import logging

from interpreter.cobol.cobol_expression import parse_expression
from interpreter.cobol.cobol_statements import (
    ArithmeticStatement,
    ComputeStatement,
    ContinueStatement,
    DisplayStatement,
    EvaluateStatement,
    ExitStatement,
    GotoStatement,
    IfStatement,
    InitializeStatement,
    MoveStatement,
    SetStatement,
    StopRunStatement,
    WhenOtherStatement,
    WhenStatement,
)
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.condition_lowering import lower_expr_node
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.operator_kind import resolve_binop
from interpreter.func_name import FuncName
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Const,
    Label_,
    Return_,
)
from interpreter.ir import CodeLabel
from interpreter.register import Register

logger = logging.getLogger(__name__)

ARITHMETIC_OPS = {
    "ADD": "+",
    "SUBTRACT": "-",
    "MULTIPLY": "*",
    "DIVIDE": "/",
}


def lower_move(
    ctx: EmitContext,
    stmt: MoveStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """MOVE X TO Y: decode X, encode as Y's type, write to Y's region."""
    target_ref = ctx.resolve_field_ref(stmt.target, layout, region_reg)

    if ctx.has_field(stmt.source, layout):
        source_ref = ctx.resolve_field_ref(stmt.source, layout, region_reg)
        decoded_reg = ctx.emit_decode_field(
            region_reg, source_ref.fl, source_ref.offset_reg
        )
        value_str_reg = ctx.emit_to_string(decoded_reg)
    else:
        value_str_reg = ctx.const_to_reg(str(stmt.source))

    ctx.emit_encode_and_write(
        region_reg, target_ref.fl, value_str_reg, target_ref.offset_reg
    )


def lower_arithmetic(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """ADD/SUBTRACT/MULTIPLY/DIVIDE X TO/FROM/BY/INTO Y [GIVING Z]."""
    if stmt.giving:
        lower_arithmetic_giving(ctx, stmt, layout, region_reg)
        return

    target_ref = ctx.resolve_field_ref(stmt.target, layout, region_reg)

    if ctx.has_field(stmt.source, layout):
        source_ref = ctx.resolve_field_ref(stmt.source, layout, region_reg)
        src_decoded = ctx.emit_decode_field(
            region_reg, source_ref.fl, source_ref.offset_reg
        )
    else:
        src_decoded = ctx.const_to_reg(float(stmt.source))

    tgt_decoded = ctx.emit_decode_field(
        region_reg, target_ref.fl, target_ref.offset_reg
    )

    op = ARITHMETIC_OPS[stmt.op]
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result_reg,
            operator=resolve_binop(op),
            left=Register(str(tgt_decoded)),
            right=Register(str(src_decoded)),
        )
    )

    result_str_reg = ctx.emit_to_string(result_reg)
    ctx.emit_encode_and_write(
        region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
    )


def lower_arithmetic_giving(
    ctx: EmitContext,
    stmt: ArithmeticStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """MULTIPLY/DIVIDE X BY/INTO Y GIVING Z."""

    def _decode_operand(name: str) -> str:
        if ctx.has_field(name, layout):
            ref = ctx.resolve_field_ref(name, layout, region_reg)
            return ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
        return ctx.const_to_reg(float(name))

    left_reg = _decode_operand(stmt.source)
    right_reg = _decode_operand(stmt.target)

    op = ARITHMETIC_OPS[stmt.op]
    result_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=result_reg,
            operator=resolve_binop(op),
            left=Register(str(left_reg)),
            right=Register(str(right_reg)),
        )
    )

    for giving_name in stmt.giving:
        giving_ref = ctx.resolve_field_ref(giving_name, layout, region_reg)
        result_str_reg = ctx.emit_to_string(result_reg)
        ctx.emit_encode_and_write(
            region_reg, giving_ref.fl, result_str_reg, giving_ref.offset_reg
        )


def lower_compute(
    ctx: EmitContext,
    stmt: ComputeStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """COMPUTE target(s) = arithmetic-expression."""
    expr_tree = parse_expression(stmt.expression)
    result_reg = lower_expr_node(ctx, expr_tree, layout, region_reg)

    result_str_reg = ctx.emit_to_string(result_reg)
    for target_name in stmt.targets:
        if not ctx.has_field(target_name, layout):
            logger.warning("COMPUTE target %s not found in layout", target_name)
            continue
        target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
        ctx.emit_encode_and_write(
            region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
        )


def lower_if(
    ctx: EmitContext,
    stmt: IfStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """IF condition ... [ELSE ...] END-IF."""
    cond_reg = ctx.lower_condition(stmt.condition, layout, region_reg)
    true_label = ctx.fresh_label("if_true")
    false_label = ctx.fresh_label("if_false")
    end_label = ctx.fresh_label("if_end")

    ctx.emit_inst(
        BranchIf(
            cond_reg=Register(str(cond_reg)),
            branch_targets=(true_label, false_label),
        )
    )

    ctx.emit_inst(Label_(label=true_label))
    for child in stmt.children:
        ctx.lower_statement(child, layout, region_reg)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=false_label))
    for child in stmt.else_children:
        ctx.lower_statement(child, layout, region_reg)
    ctx.emit_inst(Branch(label=end_label))

    ctx.emit_inst(Label_(label=end_label))


def lower_evaluate(
    ctx: EmitContext,
    stmt: EvaluateStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """EVALUATE subject WHEN value ..."""
    end_label = ctx.fresh_label("eval_end")

    for child in stmt.children:
        if isinstance(child, WhenStatement) and child.condition:
            if stmt.subject and stmt.subject.upper() != "TRUE":
                full_condition = f"{stmt.subject} = {child.condition}"
            else:
                full_condition = child.condition
            cond_reg = ctx.lower_condition(full_condition, layout, region_reg)
            when_true = ctx.fresh_label("when_true")
            when_false = ctx.fresh_label("when_false")
            ctx.emit_inst(
                BranchIf(
                    cond_reg=Register(str(cond_reg)),
                    branch_targets=(when_true, when_false),
                )
            )
            ctx.emit_inst(Label_(label=when_true))
            for grandchild in child.children:
                ctx.lower_statement(grandchild, layout, region_reg)
            ctx.emit_inst(Branch(label=end_label))
            ctx.emit_inst(Label_(label=when_false))
        elif isinstance(child, WhenOtherStatement):
            for grandchild in child.children:
                ctx.lower_statement(grandchild, layout, region_reg)

    ctx.emit_inst(Label_(label=end_label))


def lower_continue(
    ctx: EmitContext,
    stmt: ContinueStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """CONTINUE — no-op, emit nothing."""
    pass


def lower_exit(
    ctx: EmitContext,
    stmt: ExitStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """EXIT — no-op sentinel, emit nothing."""
    pass


def lower_initialize(
    ctx: EmitContext,
    stmt: InitializeStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """INITIALIZE field1 field2 — reset to type-appropriate defaults."""
    for operand in stmt.operands:
        if not ctx.has_field(operand, layout):
            logger.warning("INITIALIZE target %s not found in layout", operand)
            continue
        ref = ctx.resolve_field_ref(operand, layout, region_reg)
        td = ref.fl.type_descriptor
        if td.category == CobolDataCategory.ALPHANUMERIC:
            default = " " * td.total_digits
        else:
            default = "0"
        ctx.emit_field_encode(region_reg, ref.fl, default, ref.offset_reg)


def lower_set(
    ctx: EmitContext,
    stmt: SetStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """SET target TO value / SET target UP|DOWN BY value."""
    if stmt.set_type == "TO":
        value_str = stmt.values[0] if stmt.values else "0"
        for target_name in stmt.targets:
            if not ctx.has_field(target_name, layout):
                logger.warning("SET target %s not found in layout", target_name)
                continue
            target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
            value_str_reg = ctx.const_to_reg(str(value_str))
            ctx.emit_encode_and_write(
                region_reg, target_ref.fl, value_str_reg, target_ref.offset_reg
            )
    elif stmt.set_type == "BY":
        step_val = stmt.values[0] if stmt.values else "1"
        op = "+" if stmt.by_type == "UP" else "-"
        for target_name in stmt.targets:
            if not ctx.has_field(target_name, layout):
                logger.warning("SET target %s not found in layout", target_name)
                continue
            target_ref = ctx.resolve_field_ref(target_name, layout, region_reg)
            tgt_decoded = ctx.emit_decode_field(
                region_reg, target_ref.fl, target_ref.offset_reg
            )
            step_reg = ctx.const_to_reg(ctx.parse_literal(step_val))
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(
                Binop(
                    result_reg=result_reg,
                    operator=resolve_binop(op),
                    left=Register(str(tgt_decoded)),
                    right=Register(str(step_reg)),
                )
            )
            result_str_reg = ctx.emit_to_string(result_reg)
            ctx.emit_encode_and_write(
                region_reg, target_ref.fl, result_str_reg, target_ref.offset_reg
            )


def lower_display(
    ctx: EmitContext,
    stmt: DisplayStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """DISPLAY field-or-literal."""
    operand = stmt.operand

    if isinstance(operand, str) and ctx.has_field(operand, layout):
        ref = ctx.resolve_field_ref(operand, layout, region_reg)
        decoded_reg = ctx.emit_decode_field(region_reg, ref.fl, ref.offset_reg)
        display_reg = ctx.emit_to_string(decoded_reg)
    else:
        display_reg = ctx.const_to_reg(str(operand))

    ctx.emit_inst(
        CallFunction(
            result_reg=ctx.fresh_reg(),
            func_name=FuncName("print"),
            args=(Register(str(display_reg)),),
        )
    )


def lower_stop_run(
    ctx: EmitContext,
    stmt: StopRunStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """STOP RUN."""
    zero_reg = ctx.fresh_reg()
    ctx.emit_inst(Const(result_reg=zero_reg, value=0))
    ctx.emit_inst(Return_(value_reg=zero_reg))


def lower_goto(
    ctx: EmitContext,
    stmt: GotoStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """GO TO paragraph-name."""
    ctx.emit_inst(Branch(label=CodeLabel(f"para_{stmt.target}")))
