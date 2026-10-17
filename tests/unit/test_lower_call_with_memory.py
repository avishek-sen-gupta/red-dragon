"""Task 7 TDD tests: lower_call must emit CallWithMemory for region-passing calls."""

from __future__ import annotations

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_statements import CallStatement, CallTarget, CallUsingParam
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.lower_call import lower_call
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    build_sectioned_layout,
)
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.instructions import (
    AllocRegion,
    CallFunction,
    CallWithMemory,
    Const,
    LoadRegion,
    WriteRegion,
)
from interpreter.register import Register
from interpreter.ir import Opcode
from interpreter.var_name import VarName
from tests.covers import NotLanguageFeature, covers


def _make_field(name: str, pic: str = "X(5)", offset: int = 0) -> CobolField:
    return CobolField(name=name, level=1, pic=pic, usage="DISPLAY", offset=offset)


def _materialised_with_ws(
    field_name: str,
) -> tuple[EmitContext, MaterialisedSectionedLayout]:
    asg = CobolASG(data_fields=[_make_field(field_name)])
    sl = build_sectioned_layout(asg)
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    materialised = lower_sectioned_data_division(ctx, sl, "TESTPGM")
    return ctx, materialised


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_call_emits_call_with_memory():
    ctx, materialised = _materialised_with_ws("WS-PARAM")
    stmt = CallStatement(
        target=CallTarget.of_literal("SUBPROG"),
        using=[CallUsingParam(name="WS-PARAM", param_type="REFERENCE")],
        giving=RefModOperand(name=""),
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.CALL_WITH_MEMORY in opcodes, f"Expected CALL_WITH_MEMORY in {opcodes}"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_call_giving_result_written_back():
    """GIVING: after the copy-up, RETURN-CODE is read back as a field and its value
    written to the caller's WS field -- a MOVE, not a copy of the raw bytes."""
    ctx, materialised = _materialised_with_ws("WS-RESULT")
    stmt = CallStatement(
        target=CallTarget.of_literal("SUBPROG"),
        using=[],
        giving=RefModOperand(name="WS-RESULT"),
    )
    lower_call(ctx, stmt, materialised)
    _sr_layout, sr_reg = materialised.special_registers
    _ws_layout, ws_reg = materialised.working_storage
    assert (
        _post_call_accesses_of_region(ctx, sr_reg),
        _post_call_accesses_of_region(ctx, ws_reg),
    ) == ([Opcode.WRITE_REGION, Opcode.LOAD_REGION], [Opcode.WRITE_REGION])


def _post_call_accesses_of_region(ctx, region_reg):
    """Region reads/writes emitted after CALL_WITH_MEMORY that touch one region.

    Scoped to a region on purpose. Every CALL now also reads and writes the
    SPECIAL_REGISTERS region -- seeding the call's result register with the
    caller's RETURN-CODE and storing the callee's back into it (red-dragon-ltq6)
    -- so "no copy-back" has to mean "nothing written back into the ARGUMENT's
    storage", not "no region traffic at all".
    """
    instructions = list(ctx.instructions)
    call_idx = next(
        i
        for i, inst in enumerate(instructions)
        if inst.opcode == Opcode.CALL_WITH_MEMORY
    )
    return [
        inst.opcode
        for inst in instructions[call_idx + 1 :]
        if inst.opcode in (Opcode.LOAD_REGION, Opcode.WRITE_REGION)
        and inst.region_reg == region_reg
    ]


@covers(CobolFeature.USING_BY_VALUE)
def test_lower_call_by_value_no_copy_back():
    """BY VALUE: callee gets a copy; no LOAD_REGION or WRITE_REGION after CALL_WITH_MEMORY."""
    ctx, materialised = _materialised_with_ws("WS-INPUT")
    stmt = CallStatement(
        target=CallTarget.of_literal("SUBPROG"),
        using=[CallUsingParam(name="WS-INPUT", param_type="VALUE")],
        giving=RefModOperand(name=""),
    )
    lower_call(ctx, stmt, materialised)
    _ws_layout, ws_reg = materialised.working_storage
    assert (
        _post_call_accesses_of_region(ctx, ws_reg) == []
    ), "BY VALUE must not copy anything back into the argument's own storage"


@covers(CobolFeature.USING_BY_CONTENT)
def test_lower_call_by_content_no_copy_back():
    """BY CONTENT: identical to BY VALUE at the IR level; no copy-back after CALL_WITH_MEMORY."""
    ctx, materialised = _materialised_with_ws("WS-INPUT")
    stmt = CallStatement(
        target=CallTarget.of_literal("SUBPROG"),
        using=[CallUsingParam(name="WS-INPUT", param_type="CONTENT")],
        giving=RefModOperand(name=""),
    )
    lower_call(ctx, stmt, materialised)
    _ws_layout, ws_reg = materialised.working_storage
    assert (
        _post_call_accesses_of_region(ctx, ws_reg) == []
    ), "BY CONTENT must not copy anything back into the argument's own storage"


def _materialised_with_sections() -> tuple[EmitContext, MaterialisedSectionedLayout]:
    asg = CobolASG(
        data_fields=[_make_field("WS-DECOY", "X(8)")],
        linkage_fields=[_make_field("LK-ARG", "X(8)")],
        local_storage_fields=[_make_field("LS-ARG", "X(8)")],
    )
    ctx = EmitContext(dispatch_fn=dispatch_statement)
    return ctx, lower_sectioned_data_division(
        ctx, build_sectioned_layout(asg), "SECPGM"
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_call_passes_an_argument_array_with_its_count():
    """CALL USING hands the callee an array: a count, and one element per argument."""
    from interpreter.instructions import (
        CallWithMemory,
        NewArray,
        StoreField,
        StoreIndex,
    )

    ctx, materialised = _materialised_with_ws("WS-PARAM")
    lower_call(
        ctx,
        CallStatement(
            target=CallTarget.of_literal("SUBPROG"),
            using=[
                CallUsingParam(name="WS-PARAM", param_type="REFERENCE"),
                CallUsingParam(name="", param_type="REFERENCE", omitted=True),
            ],
            giving=RefModOperand(name=""),
        ),
        materialised,
    )
    instructions = list(ctx.instructions)
    (array,) = [i for i in instructions if isinstance(i, NewArray)]
    (call,) = [i for i in instructions if isinstance(i, CallWithMemory)]

    assert (
        call.memory,
        [
            i.field_name.value
            for i in instructions
            if isinstance(i, StoreField) and i.obj_reg == array.result_reg
        ],
        sum(
            1
            for i in instructions
            if isinstance(i, StoreIndex) and i.arr_reg == array.result_reg
        ),
    ) == (array.result_reg, ["count"], 2)


def _call_region_traffic(param_type: str) -> list[tuple[Opcode, str]]:
    """Region allocation and access lower_call itself emits for one argument,
    each tagged with whose region it touches."""
    ctx, materialised = _materialised_with_ws("WS-INPUT")
    before = len(ctx.instructions)
    lower_call(
        ctx,
        CallStatement(
            target=CallTarget.of_literal("DOUBLIT"),
            using=[CallUsingParam(name="WS-INPUT", param_type=param_type)],
            giving=RefModOperand(name=""),
        ),
        materialised,
    )
    emitted = list(ctx.instructions)[before:]
    _ws_layout, ws_reg = materialised.working_storage
    _sr_layout, sr_reg = materialised.special_registers
    copies = {i.result_reg for i in emitted if isinstance(i, AllocRegion)}

    def owner(inst: AllocRegion | LoadRegion | WriteRegion) -> str:
        match inst:
            case AllocRegion():
                return "new"
            case _ if inst.region_reg == ws_reg:
                return "argument"
            case _ if inst.region_reg in copies:
                return "copy"
            case _:
                return "other"

    return [
        (inst.opcode, owner(inst))
        for inst in emitted
        if isinstance(inst, AllocRegion)
        or (isinstance(inst, (LoadRegion, WriteRegion)) and inst.region_reg != sr_reg)
    ]


@covers(CobolFeature.USING_BY_REFERENCE, CobolFeature.USING_BY_CONTENT)
def test_by_reference_copies_nothing_and_by_content_copies_once():
    """BY REFERENCE passes the argument's own bytes and copies nothing, either
    way; BY CONTENT copies the argument into one fresh region before the call and
    writes nothing back."""
    assert (_call_region_traffic("REFERENCE"), _call_region_traffic("CONTENT")) == (
        [],
        [
            (Opcode.ALLOC_REGION, "new"),
            (Opcode.LOAD_REGION, "argument"),
            (Opcode.WRITE_REGION, "copy"),
        ],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_by_reference_argument_passes_its_own_sections_region():
    """An argument declared outside WORKING-STORAGE is passed in its own region:
    a LINKAGE item passed on is its 01's bound region, a LOCAL-STORAGE item the
    LOCAL-STORAGE region -- never WORKING-STORAGE at the same offset."""
    from interpreter.instructions import StoreField

    def passed_region(name: str) -> tuple[bool, bool]:
        ctx, materialised = _materialised_with_sections()
        _fl, owning_reg = materialised.resolve(name)
        _ws_layout, ws_reg = materialised.working_storage
        lower_call(
            ctx,
            CallStatement(
                target=CallTarget.of_literal("SUBPROG"),
                using=[CallUsingParam(name=name, param_type="REFERENCE")],
                giving=RefModOperand(name=""),
            ),
            materialised,
        )
        (region,) = [
            i.value_reg
            for i in ctx.instructions
            if isinstance(i, StoreField) and i.field_name.value == "region"
        ]
        return region == owning_reg, region == ws_reg

    assert (passed_region("LK-ARG"), passed_region("LS-ARG")) == (
        (True, False),
        (True, False),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_literal_call_looks_up_the_callee_entry_var():
    ctx, materialised = _materialised_with_ws("WS-PARAM")
    stmt = CallStatement(
        target=CallTarget.of_literal("subprog"),
        using=[CallUsingParam(name="WS-PARAM", param_type="REFERENCE")],
        giving=RefModOperand(name=""),
    )
    lower_call(ctx, stmt, materialised)
    (call,) = [i for i in ctx.instructions if isinstance(i, CallWithMemory)]
    assert (call.location, call.operands) == (
        VarName("__entry_SUBPROG"),
        ["__entry_SUBPROG", str(call.memory)],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_data_name_call_computes_the_entry_var_in_ir():
    ctx, materialised = _materialised_with_ws("WS-PROG")
    stmt = CallStatement(
        target=CallTarget.of_identifier(RefModOperand(name="WS-PROG")),
        using=[],
        giving=RefModOperand(name=""),
    )
    lower_call(ctx, stmt, materialised)
    calls = {i.result_reg: i for i in ctx.instructions if isinstance(i, CallFunction)}
    consts = {i.result_reg: i for i in ctx.instructions if isinstance(i, Const)}
    (call,) = [i for i in ctx.instructions if isinstance(i, CallWithMemory)]
    concat = calls[Register(str(call.location))]
    prefix_reg, upper_reg = (Register(str(a)) for a in concat.args)
    prefix, upper = consts[prefix_reg], calls[upper_reg]
    trim = calls[Register(str(upper.args[0]))]
    assert (
        str(concat.func_name),
        prefix.value,
        str(upper.func_name),
        str(trim.func_name),
    ) == ("__string_concat_pair", "__entry_", "__upper_case", "__cobol_trim")
