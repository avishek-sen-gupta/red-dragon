import pytest

from cobol_asg.asg_types import CobolField
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.lower_program_init import (
    lower_program_init,
    lower_ws_from_singleton,
)
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.frontend import make_cobol_parser
from interpreter.instructions import (
    Branch,
    Const,
    Label_,
    LoadField,
    LoadVar,
    NewObject,
    StoreField,
    StoreVar,
    Symbolic,
)
from interpreter.ir import CodeLabel, Opcode
from interpreter.project.cobol_compile import compile_cobol
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
def test_lower_program_init_publishes_every_singleton_field():
    """Naming the fields, not counting them: a count says nothing about which."""
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    published = [
        str(i.field_name) for i in ctx.instructions if isinstance(i, StoreField)
    ]
    # return_code_handle joins them because the special registers are allocated
    # once, with WORKING-STORAGE, rather than per call (red-dragon-ltq6).
    # initial_state is cleared by the block that lays down WORKING-STORAGE, which
    # CANCEL makes the next entry perform again.
    assert published == [
        "ws_handle",
        "initial_state",
        "return_code_handle",
        "run",
    ]


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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_program_init_registers_the_program_and_its_entry_function():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "subprog", _ws_layout_5bytes())
    program_object = next(i for i in ctx.instructions if isinstance(i, NewObject))
    entry_ref = next(
        i
        for i in ctx.instructions
        if isinstance(i, Const) and i.value == "func_init_params_subprog_0"
    )
    registered = {
        str(i.name): i.value_reg
        for i in ctx.instructions
        if isinstance(i, StoreVar) and str(i.name).startswith(("__prog_", "__entry_"))
    }
    assert registered == {
        "__prog_SUBPROG": program_object.result_reg,
        "__entry_SUBPROG": entry_ref.result_reg,
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_entry_function_declares_the_call_arguments_parameter():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    lower_program_init(ctx, "SUBPROG", _ws_layout_5bytes())
    start = next(
        n
        for n, i in enumerate(ctx.instructions)
        if isinstance(i, Label_) and str(i.label) == "func_init_params_subprog_0"
    )
    match ctx.instructions[start + 1 : start + 3]:
        case [Symbolic(hint=hint), Branch(label=label)]:
            assert (hint, str(label)) == ("param:__call_arguments", "func_subprog_0")
        case unexpected:
            pytest.fail(f"expected the declaration, then the branch: {unexpected}")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linked_entry_function_is_registered_with_its_parameter():
    source = (
        b"       IDENTIFICATION DIVISION.\n"
        b"       PROGRAM-ID. CALLER.\n"
        b"       PROCEDURE DIVISION.\n"
        b"           GOBACK.\n"
    )
    linked = compile_cobol(source, parser=make_cobol_parser())
    assert linked.merged_registry.func_params[
        CodeLabel("__main__.func_init_params_caller_0")
    ] == ["__call_arguments"]
