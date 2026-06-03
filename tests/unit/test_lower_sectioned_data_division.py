from interpreter.cobol.asg_types import CobolASG, CobolField
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.sectioned_layout import SectionedLayout, build_sectioned_layout
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.cobol.features import CobolFeature
from interpreter.ir import Opcode
from tests.covers import covers, NotLanguageFeature


def _make_field(name: str, pic: str = "X(5)", offset: int = 0) -> CobolField:
    return CobolField(name=name, level=1, pic=pic, usage="DISPLAY", offset=offset)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_sectioned_data_division_returns_materialised():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    asg = CobolASG(data_fields=[_make_field("WS-X")])
    sl = build_sectioned_layout(asg)
    result = lower_sectioned_data_division(ctx, sl)
    assert isinstance(result, MaterialisedSectionedLayout)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_sectioned_emits_alloc_region_for_ws():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    asg = CobolASG(data_fields=[_make_field("WS-X")])
    sl = build_sectioned_layout(asg)
    lower_sectioned_data_division(ctx, sl)
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.ALLOC_REGION in opcodes


@covers(CobolFeature.SECTION_LINKAGE)
def test_lower_sectioned_emits_load_var_for_non_empty_linkage():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    asg = CobolASG(
        data_fields=[_make_field("WS-X")],
        linkage_fields=[_make_field("LK-Y")],
    )
    sl = build_sectioned_layout(asg)
    lower_sectioned_data_division(ctx, sl)
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.LOAD_VAR in opcodes


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_sectioned_no_load_var_when_linkage_empty():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    asg = CobolASG(data_fields=[_make_field("WS-X")])
    sl = build_sectioned_layout(asg)
    lower_sectioned_data_division(ctx, sl)
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.LOAD_VAR not in opcodes


@covers(CobolFeature.SECTION_LOCAL_STORAGE)
def test_lower_sectioned_emits_alloc_region_for_local_storage():
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    asg = CobolASG(
        data_fields=[_make_field("WS-X")],
        local_storage_fields=[_make_field("LS-Z")],
    )
    sl = build_sectioned_layout(asg)
    lower_sectioned_data_division(ctx, sl)
    alloc_count = sum(1 for i in ctx.instructions if i.opcode == Opcode.ALLOC_REGION)
    assert alloc_count == 2  # one for WS, one for LS
