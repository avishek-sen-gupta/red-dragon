"""DATA DIVISION lowering — allocate region and initialize field values."""

from __future__ import annotations

import logging

from cobol_memory.region_id import RegionId
from interpreter.cobol.data_layout import DataLayout
from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.field_resolution import whole_field_extent
from interpreter.cobol.linkage_binding import LinkageBinding
from interpreter.cobol.linkage_record import LinkageRecord
from interpreter.cobol.sectioned_layout import (
    MaterialisedSectionedLayout,
    SectionedLayout,
)
from interpreter.cobol.special_registers import (
    RETURN_CODE_HANDLE,
    SPECIAL_REGISTERS_LAYOUT,
)
from interpreter.field_name import FieldName
from interpreter.instructions import (
    AllocRegion,
    Binop,
    Branch,
    BranchIf,
    Const,
    Label_,
    LoadField,
    LoadIndex,
    LoadVar,
    StoreVar,
)
from interpreter.operator_kind import resolve_binop
from interpreter.register import NO_REGISTER, Register
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)


def lower_data_division(
    ctx: EmitContext, layout: DataLayout, region: RegionId
) -> Register:
    """Emit ALLOC_REGION + initial VALUE encodings. Returns region register.

    ``region`` says which DATA DIVISION section this layout is, and is required:
    this one function initialises WORKING-STORAGE, LOCAL-STORAGE, FILE, INDEXES
    and SPECIAL-REGISTERS, so there is no defensible default. Extents in
    different regions never alias, so a wrong region here would silently erase
    every dependency edge on the fields it initialises.
    """
    size_reg = ctx.fresh_reg()
    ctx.emit_inst(
        Const.int_(size_reg, layout.total_bytes),
        span=None,  # region-level: no single declaration
    )
    region_reg = ctx.fresh_reg()
    ctx.emit_inst(
        AllocRegion(result_reg=region_reg, size_reg=size_reg),
        span=None,  # region-level: no single declaration
    )

    fields_with_values = [fl for fl in layout.all_leaves() if fl.value]
    for fl in fields_with_values:
        # A VALUE clause initialises the whole declared field at its own
        # offset — no subscript is in play — so the whole-field extent is
        # exactly right here.
        ctx.emit_field_encode(
            region_reg,
            fl,
            fl.value,
            extent=whole_field_extent(fl, region),
            span=fl.span,
        )

    logger.debug(
        "Data Division: allocated %d bytes, initialized %d fields",
        layout.total_bytes,
        len(fields_with_values),
    )
    return region_reg


def lower_sectioned_data_division(
    ctx: EmitContext,
    layout: SectionedLayout,
    program_id: str,
) -> MaterialisedSectionedLayout:
    """Bind WS to the persistent singleton region; allocate fresh LS per call.

    The WS region handle must already be stored in __ws_region by the caller
    (currently the inline shim in CobolFrontend; Task 5 will replace this
    with the program init block that loads it from the singleton HeapObject).
    Each LINKAGE 01 is bound to its argument in __call_arguments, which
    _handle_call_with_memory injects. LOCAL-STORAGE is freshly allocated on
    every call.
    """
    ws_reg = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=ws_reg, name=VarName("__ws_region")))

    bindings = bind_linkage(ctx, layout.linkage_parameters, layout.linkage_unbound)

    if layout.local_storage.total_bytes > 0:
        ls_reg = lower_data_division(ctx, layout.local_storage, RegionId.LOCAL_STORAGE)
    else:
        ls_reg = NO_REGISTER

    if layout.file.total_bytes > 0:
        file_reg = lower_data_division(ctx, layout.file, RegionId.FILE)
    else:
        file_reg = NO_REGISTER

    # INDEXED BY items belong to no record, so they get their own region rather
    # than being appended to one: LINKAGE in particular is the CALLER's argument
    # storage, sized by the caller and not by total_bytes, so an index placed
    # there would write past the arguments and corrupt them.
    if layout.indexes.total_bytes > 0:
        index_reg = lower_data_division(ctx, layout.indexes, RegionId.INDEXES)
    else:
        index_reg = NO_REGISTER

    # The special registers are allocated ONCE, in the init block beside
    # WORKING-STORAGE, and merely rebound here — so this loads the handle rather
    # than allocating. Allocating per entry would zero RETURN-CODE on every call,
    # which contradicts both halves of its semantics: a subprogram is left in its
    # last-used state, and a callee's value has to outlive its own exit long
    # enough for the caller to copy it up (red-dragon-ltq6).
    singleton_reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadVar(result_reg=singleton_reg, name=VarName(f"__prog_{program_id.upper()}"))
    )
    sr_reg = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(
            result_reg=sr_reg, obj_reg=singleton_reg, field_name=RETURN_CODE_HANDLE
        )
    )

    logger.debug(
        "Sectioned data division: WS=%s LK=%d bound LS=%s FILE=%s SR=%s IX=%s",
        ws_reg,
        len(bindings),
        ls_reg,
        file_reg,
        sr_reg,
        index_reg,
    )

    return MaterialisedSectionedLayout(
        working_storage=(layout.working_storage, ws_reg),
        linkage=(layout.linkage, NO_REGISTER),
        local_storage=(layout.local_storage, ls_reg),
        file=(layout.file, file_reg),
        special_registers=(SPECIAL_REGISTERS_LAYOUT, sr_reg),
        indexes=(layout.indexes, index_reg),
        linkage_bindings=bindings,
        linkage_owners=layout.linkage_owners,
    )


def bind_linkage(
    ctx: EmitContext,
    parameters: tuple[LinkageRecord, ...],
    unbound: tuple[LinkageRecord, ...],
) -> tuple[LinkageBinding, ...]:
    """Each parameter bound to the argument at its position; the 01s no USING
    position names, to zero-filled storage of their own."""
    return (
        *(
            _bind_parameter(ctx, record, position)
            for position, record in enumerate(parameters)
        ),
        *(_placeholder(ctx, record) for record in unbound),
    )


def _bind_parameter(
    ctx: EmitContext, record: LinkageRecord, position: int
) -> LinkageBinding:
    """The argument at ``position``, or zero-filled storage when the caller
    supplied fewer arguments or supplied this one OMITTED."""
    present, bind, absent, done = (
        ctx.fresh_label(f"lk_{tag}") for tag in ("present", "bind", "absent", "done")
    )
    args = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=args, name=VarName("__call_arguments")), span=None)
    count = _field(ctx, args, "count")
    index = ctx.const_to_reg(position, span=None)
    supplied = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=supplied, operator=resolve_binop("<"), left=index, right=count
        ),
        span=None,
    )
    ctx.emit_inst(
        BranchIf(cond_reg=supplied, branch_targets=(present, absent)), span=None
    )
    ctx.emit_inst(Label_(label=present), span=None)
    element = ctx.fresh_reg()
    ctx.emit_inst(
        LoadIndex(result_reg=element, arr_reg=args, index_reg=index), span=None
    )
    omitted = _field(ctx, element, "omitted")
    ctx.emit_inst(BranchIf(cond_reg=omitted, branch_targets=(absent, bind)), span=None)
    ctx.emit_inst(Label_(label=bind), span=None)
    _store_binding(
        ctx, record, _field(ctx, element, "region"), _field(ctx, element, "offset")
    )
    ctx.emit_inst(Branch(label=done), span=None)
    ctx.emit_inst(Label_(label=absent), span=None)
    _store_zeroed(ctx, record)
    ctx.emit_inst(Label_(label=done), span=None)
    return _loaded(ctx, record)


def _placeholder(ctx: EmitContext, record: LinkageRecord) -> LinkageBinding:
    _store_zeroed(ctx, record)
    return _loaded(ctx, record)


def _field(ctx: EmitContext, obj: Register, name: str) -> Register:
    value = ctx.fresh_reg()
    ctx.emit_inst(
        LoadField(result_reg=value, obj_reg=obj, field_name=FieldName(name)), span=None
    )
    return value


def _store_binding(
    ctx: EmitContext, record: LinkageRecord, region: Register, offset: Register
) -> None:
    delta = ctx.fresh_reg()
    ctx.emit_inst(
        Binop(
            result_reg=delta,
            operator=resolve_binop("-"),
            left=offset,
            right=ctx.const_to_reg(record.start, span=None),
        ),
        span=None,
    )
    ctx.emit_inst(StoreVar(name=_region_var(record), value_reg=region), span=None)
    ctx.emit_inst(StoreVar(name=_delta_var(record), value_reg=delta), span=None)


def _store_zeroed(ctx: EmitContext, record: LinkageRecord) -> None:
    region = ctx.fresh_reg()
    ctx.emit_inst(
        AllocRegion(
            result_reg=region, size_reg=ctx.const_to_reg(record.length, span=None)
        ),
        span=None,
    )
    _store_binding(ctx, record, region, ctx.const_to_reg(0, span=None))


def _loaded(ctx: EmitContext, record: LinkageRecord) -> LinkageBinding:
    region = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=region, name=_region_var(record)), span=None)
    delta = ctx.fresh_reg()
    ctx.emit_inst(LoadVar(result_reg=delta, name=_delta_var(record)), span=None)
    return LinkageBinding(record.name, record.start, record.length, region, delta)


def _region_var(record: LinkageRecord) -> VarName:
    return VarName(f"__linkage_{record.name}_region")


def _delta_var(record: LinkageRecord) -> VarName:
    return VarName(f"__linkage_{record.name}_delta")
