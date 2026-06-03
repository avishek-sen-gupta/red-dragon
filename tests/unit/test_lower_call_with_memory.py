"""Task 7 TDD tests: lower_call must emit CallWithMemory for region-passing calls."""

from __future__ import annotations

from interpreter.cobol.asg_types import CobolASG, CobolField
from interpreter.cobol.cobol_statements import CallStatement, CallUsingParam
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_call import lower_call
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    build_sectioned_layout,
)
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.ir import Opcode
from interpreter.register import NO_REGISTER, Register
from tests.covers import covers, NotLanguageFeature


def _make_field(name: str, pic: str = "X(5)", offset: int = 0) -> CobolField:
    return CobolField(name=name, level=1, pic=pic, usage="DISPLAY", offset=offset)


def _materialised_with_ws(
    field_name: str,
) -> tuple[EmitContext, MaterialisedSectionedLayout]:
    asg = CobolASG(data_fields=[_make_field(field_name)])
    sl = build_sectioned_layout(asg)
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(ctx, sl)
    return ctx, materialised


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_call_emits_call_with_memory():
    ctx, materialised = _materialised_with_ws("WS-PARAM")
    stmt = CallStatement(
        program="SUBPROG",
        using=[CallUsingParam(name="WS-PARAM", param_type="REFERENCE")],
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.CALL_WITH_MEMORY in opcodes, f"Expected CALL_WITH_MEMORY in {opcodes}"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_call_by_reference_params_eq_results():
    """BY REFERENCE: params_reg == results_reg (same caller WS region)."""
    from interpreter.instructions import CallWithMemory

    ctx, materialised = _materialised_with_ws("WS-PARAM")
    stmt = CallStatement(
        program="SUBPROG",
        using=[CallUsingParam(name="WS-PARAM", param_type="REFERENCE")],
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    call_insts = [i for i in ctx.instructions if i.opcode == Opcode.CALL_WITH_MEMORY]
    assert len(call_insts) == 1
    cwm = call_insts[0]
    assert isinstance(cwm, CallWithMemory)
    assert cwm.params_reg == cwm.results_reg


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_call_giving_result_written_back():
    """GIVING: result written back to caller's WS field via WRITE_REGION."""
    ctx, materialised = _materialised_with_ws("WS-RESULT")
    stmt = CallStatement(
        program="SUBPROG",
        using=[],
        giving="WS-RESULT",
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.CALL_WITH_MEMORY in opcodes
    assert Opcode.WRITE_REGION in opcodes
