"""Task 7 TDD tests: lower_call must emit CallWithMemory for region-passing calls."""

from __future__ import annotations

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_statements import CallStatement, CallTarget, CallUsingParam
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.lower_call import lower_call
from interpreter.cobol.lower_data_division import lower_sectioned_data_division
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    build_sectioned_layout,
)
from interpreter.cobol.statement_dispatch import dispatch_statement
from interpreter.ir import Opcode
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
        giving="",
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.CALL_WITH_MEMORY in opcodes, f"Expected CALL_WITH_MEMORY in {opcodes}"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lower_call_giving_result_written_back():
    """GIVING: result written back to caller's WS field via WRITE_REGION."""
    ctx, materialised = _materialised_with_ws("WS-RESULT")
    stmt = CallStatement(
        target=CallTarget.of_literal("SUBPROG"),
        using=[],
        giving="WS-RESULT",
    )
    lower_call(ctx, stmt, materialised)
    opcodes = [i.opcode for i in ctx.instructions]
    assert Opcode.CALL_WITH_MEMORY in opcodes
    assert Opcode.WRITE_REGION in opcodes


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
        giving="",
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
        giving="",
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
            giving="",
        ),
        materialised,
    )
    instructions = list(ctx.instructions)
    (array,) = [i for i in instructions if isinstance(i, NewArray)]
    (call,) = [i for i in instructions if isinstance(i, CallWithMemory)]

    assert (
        call.params_reg,
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
            giving="",
        ),
        materialised,
    )
    emitted = list(ctx.instructions)[before:]
    _ws_layout, ws_reg = materialised.working_storage
    _sr_layout, sr_reg = materialised.special_registers
    copies = {i.result_reg for i in emitted if i.opcode is Opcode.ALLOC_REGION}

    def owner(inst) -> str:
        if inst.opcode is Opcode.ALLOC_REGION:
            return "new"
        if inst.region_reg == ws_reg:
            return "argument"
        if inst.region_reg in copies:
            return "copy"
        return "other"

    return [
        (inst.opcode, owner(inst))
        for inst in emitted
        if inst.opcode in (Opcode.ALLOC_REGION, Opcode.LOAD_REGION, Opcode.WRITE_REGION)
        and not (inst.opcode is not Opcode.ALLOC_REGION and inst.region_reg == sr_reg)
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
                giving="",
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
