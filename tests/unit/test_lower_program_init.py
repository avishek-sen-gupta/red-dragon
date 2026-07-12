from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_program_init import (
    lower_program_init,
    lower_ws_from_singleton,
)
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.instructions import LoadField, LoadVar, StoreVar
from interpreter.ir import Opcode
from tests.covers import NotLanguageFeature, covers


def _ws_layout_5bytes():
    field = CobolField(name="WS-X", level=1, pic="X(5)", usage="DISPLAY", offset=0)
    return build_data_layout([field])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_new_object():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.NEW_OBJECT in opcodes


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_alloc_region_for_ws():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.ALLOC_REGION in opcodes


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_three_store_fields():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    count = sum(1 for i in ctx.instructions if i.opcode == Opcode.STORE_FIELD)
    assert count == 3  # ws_handle, run, __init_params__


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_store_var_singleton():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    store_var_insts = [i for i in ctx.instructions if isinstance(i, StoreVar)]
    names = [str(i.name) for i in store_var_insts]
    assert "__prog_SUBPROG" in names


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_branch_to_after_label():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    after_label = lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    branch_insts = [i for i in ctx.instructions if i.opcode == Opcode.BRANCH]
    branch_labels = [str(i.label) for i in branch_insts]
    assert str(after_label) in branch_labels


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_emits_func_init_params_label():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    labels = [str(i.label) for i in ctx.instructions if i.opcode == Opcode.LABEL]
    assert "func_init_params_subprog_0" in labels


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_returns_after_label():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    after_label = lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    assert str(after_label) == "__after_subprog_0"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_ws_from_singleton_emits_load_var_singleton():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_ws_from_singleton(ctx, "SUBPROG")
    load_var_insts = [i for i in ctx.instructions if isinstance(i, LoadVar)]
    names = [str(i.name) for i in load_var_insts]
    assert "__prog_SUBPROG" in names


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_ws_from_singleton_emits_load_field_ws_handle():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_ws_from_singleton(ctx, "SUBPROG")
    load_field_insts = [i for i in ctx.instructions if isinstance(i, LoadField)]
    field_names = [str(i.field_name) for i in load_field_insts]
    assert "ws_handle" in field_names


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_ws_from_singleton_emits_store_var_ws_region():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_ws_from_singleton(ctx, "SUBPROG")
    store_var_insts = [i for i in ctx.instructions if isinstance(i, StoreVar)]
    names = [str(i.name) for i in store_var_insts]
    assert "__ws_region" in names
