"""TDD tests for GOBACK and EXIT PROGRAM lowering."""

from __future__ import annotations

from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.cobol_statements import GobackStatement, ExitProgramStatement
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_arithmetic import lower_goback, lower_exit_program
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.sectioned_layout import build_sectioned_layout
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.ir import Opcode
from interpreter.cobol.features import CobolFeature
from tests.covers import covers


def _empty_materialised():
    asg = CobolASG(data_fields=[])
    sl = build_sectioned_layout(asg)
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(ctx, sl)
    return ctx, materialised


@covers(CobolFeature.GOBACK)
def test_lower_goback_emits_return():
    """GOBACK must emit Return_ so the subprogram returns control to its caller."""
    ctx, materialised = _empty_materialised()
    lower_goback(ctx, GobackStatement(), materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.RETURN in opcodes, f"Expected RETURN in {opcodes}"


@covers(CobolFeature.EXIT_PROGRAM)
def test_lower_exit_program_emits_return():
    """EXIT PROGRAM must emit Return_ so the subprogram returns control to its caller."""
    ctx, materialised = _empty_materialised()
    lower_exit_program(ctx, ExitProgramStatement(), materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.RETURN in opcodes, f"Expected RETURN in {opcodes}"


@covers(CobolFeature.GOBACK)
def test_lower_goback_emits_exactly_one_return():
    """GOBACK should emit exactly one Return_, mirroring lower_stop_run."""
    ctx, materialised = _empty_materialised()
    lower_goback(ctx, GobackStatement(), materialised)
    returns = [i for i in ctx.instructions if i.opcode == Opcode.RETURN]
    assert len(returns) == 1, f"Expected exactly 1 RETURN, got {len(returns)}"
