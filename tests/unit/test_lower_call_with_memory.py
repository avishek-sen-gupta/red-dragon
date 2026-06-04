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
from interpreter.cobol.features import CobolFeature
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
    """params_reg == results_reg for CALL USING (fresh params region, not WS)."""
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


@covers(CobolFeature.CALL_USING)
def test_lower_call_using_copy_in_before_call():
    """CALL with USING: ALLOC_REGION + LOAD_REGION+WRITE_REGION (copy-in) appear before CALL_WITH_MEMORY."""
    ctx, materialised = _materialised_with_ws("WS-INPUT")
    stmt = CallStatement(
        program="DOUBLIT",
        using=[CallUsingParam(name="WS-INPUT", param_type="REFERENCE")],
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    call_idx = next(i for i, op in enumerate(opcodes) if op == Opcode.CALL_WITH_MEMORY)
    pre_call = opcodes[:call_idx]
    assert (
        Opcode.ALLOC_REGION in pre_call
    ), "ALLOC_REGION must appear before CALL_WITH_MEMORY"
    assert (
        Opcode.LOAD_REGION in pre_call
    ), "LOAD_REGION (copy-in) must precede CALL_WITH_MEMORY"
    assert (
        Opcode.WRITE_REGION in pre_call
    ), "WRITE_REGION (copy-in) must precede CALL_WITH_MEMORY"


@covers(CobolFeature.USING_BY_REFERENCE)
def test_lower_call_by_reference_copy_back_after_call():
    """BY REFERENCE: LOAD_REGION+WRITE_REGION copy-back appear after CALL_WITH_MEMORY."""
    ctx, materialised = _materialised_with_ws("WS-INPUT")
    stmt = CallStatement(
        program="DOUBLIT",
        using=[CallUsingParam(name="WS-INPUT", param_type="REFERENCE")],
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    call_idx = next(i for i, op in enumerate(opcodes) if op == Opcode.CALL_WITH_MEMORY)
    post_call = opcodes[call_idx + 1 :]
    assert (
        Opcode.LOAD_REGION in post_call
    ), "LOAD_REGION (copy-back) must follow CALL_WITH_MEMORY for BY REFERENCE"
    assert (
        Opcode.WRITE_REGION in post_call
    ), "WRITE_REGION (copy-back) must follow CALL_WITH_MEMORY for BY REFERENCE"


@covers(CobolFeature.USING_BY_VALUE)
def test_lower_call_by_value_no_copy_back():
    """BY VALUE: callee gets a copy; no LOAD_REGION or WRITE_REGION after CALL_WITH_MEMORY."""
    ctx, materialised = _materialised_with_ws("WS-INPUT")
    stmt = CallStatement(
        program="SUBPROG",
        using=[CallUsingParam(name="WS-INPUT", param_type="VALUE")],
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    call_idx = next(i for i, op in enumerate(opcodes) if op == Opcode.CALL_WITH_MEMORY)
    post_call = opcodes[call_idx + 1 :]
    assert (
        Opcode.LOAD_REGION not in post_call
    ), "BY VALUE must not emit copy-back LoadRegion"
    assert (
        Opcode.WRITE_REGION not in post_call
    ), "BY VALUE must not emit copy-back WriteRegion"


@covers(CobolFeature.USING_BY_CONTENT)
def test_lower_call_by_content_no_copy_back():
    """BY CONTENT: identical to BY VALUE at the IR level; no copy-back after CALL_WITH_MEMORY."""
    ctx, materialised = _materialised_with_ws("WS-INPUT")
    stmt = CallStatement(
        program="SUBPROG",
        using=[CallUsingParam(name="WS-INPUT", param_type="CONTENT")],
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    call_idx = next(i for i, op in enumerate(opcodes) if op == Opcode.CALL_WITH_MEMORY)
    post_call = opcodes[call_idx + 1 :]
    assert (
        Opcode.LOAD_REGION not in post_call
    ), "BY CONTENT must not emit copy-back LoadRegion"
    assert (
        Opcode.WRITE_REGION not in post_call
    ), "BY CONTENT must not emit copy-back WriteRegion"
