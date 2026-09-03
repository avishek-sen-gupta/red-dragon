"""Instruction identity — a stable coordinate independent of position."""

from interpreter.instructions import NO_INSTRUCTION_ID, Const
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_instruction_id_defaults_to_absent():
    inst = Const.int_(Register("%0"), 1)
    assert inst.id == NO_INSTRUCTION_ID


# No hash assertion here: SourceLocation is an unhashable pydantic
# BaseModel and is a compared field on every instruction, so
# hash(instruction) raises TypeError on main today, independent of
# this change. Instruction identity deliberately never relies on
# hashing an instruction — sidecars key on inst.id instead.
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_instruction_id_does_not_affect_equality():
    a = Const.int_(Register("%0"), 1)
    b = Const.int_(Register("%0"), 1)
    from dataclasses import replace

    assert a == b
    assert replace(a, id=7) == replace(b, id=9)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_emit_context_assigns_sequential_ids():
    from interpreter.cobol.emit_context import EmitContext

    ctx = EmitContext(dispatch_fn=lambda ctx, stmt, layout: None)
    a = ctx.emit_inst(Const.int_(Register("%0"), 1))
    b = ctx.emit_inst(Const.int_(Register("%1"), 2))
    assert a.id != NO_INSTRUCTION_ID
    assert b.id == a.id + 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_map_registers_preserves_id():
    from dataclasses import replace

    inst = replace(Const.int_(Register("%0"), 1), id=42)
    assert inst.map_registers(lambda r: r).id == 42
