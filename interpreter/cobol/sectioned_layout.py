# pyright: standard
"""SectionedLayout — per-section DataLayout grouping for COBOL DATA DIVISION."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_memory.region_id import RegionId
from interpreter.cobol.data_layout import (
    DataLayout,
    FieldLayout,
    OccursTable,
    build_data_layout,
    build_index_layout,
    laid_end_to_end,
    record_length,
)
from interpreter.cobol.linkage_binding import LinkageBinding
from interpreter.cobol.linkage_record import LinkageRecord
from interpreter.register import NO_REGISTER, Register

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SectionedLayout:
    """DataLayouts for all three DATA DIVISION sections — pure data, no registers."""

    working_storage: DataLayout
    linkage: DataLayout
    local_storage: DataLayout
    file: DataLayout = field(default_factory=DataLayout)
    indexes: DataLayout = field(default_factory=DataLayout)
    linkage_parameters: tuple[LinkageRecord, ...] = ()
    linkage_unbound: tuple[LinkageRecord, ...] = ()
    linkage_owners: Mapping[tuple[str, int, int], str] = field(default_factory=dict)


@dataclass(frozen=True)
class MaterialisedSectionedLayout:
    """SectionedLayout with region registers bound — owns field resolution."""

    working_storage: tuple[DataLayout, Register]
    linkage: tuple[DataLayout, Register]
    local_storage: tuple[DataLayout, Register]
    file: tuple[DataLayout, Register] = field(
        default_factory=lambda: (DataLayout(), NO_REGISTER)
    )
    special_registers: tuple[DataLayout, Register] = field(
        default_factory=lambda: (DataLayout(), NO_REGISTER)
    )
    indexes: tuple[DataLayout, Register] = field(
        default_factory=lambda: (DataLayout(), NO_REGISTER)
    )
    linkage_bindings: tuple[LinkageBinding, ...] = ()
    linkage_owners: Mapping[tuple[str, int, int], str] = field(default_factory=dict)

    def linkage_binding(self, fl: FieldLayout) -> LinkageBinding:
        """The binding of the LINKAGE 01 that declares ``fl`` -- for a field under
        a REDEFINES 01, the 01 it redefines, however far it runs past it."""
        owner = self.linkage_owners[_field_identity(fl)]
        return next(
            binding for binding in self.linkage_bindings if binding.name == owner
        )

    def resolve(
        self, name: str, qualifiers: tuple[str, ...] = ()
    ) -> tuple[FieldLayout, Register]:
        """Return (FieldLayout, region_register). Precedence: LOCAL-STORAGE > WORKING-STORAGE > LINKAGE.

        ``qualifiers`` (``OF``/``IN`` ancestor group names) disambiguate a
        duplicated elementary name within the owning group (CardDemo CSUTLDTC's
        two Vstring groups share leaf names). red-dragon-p7qe."""
        fl, reg, _region = self.resolve_with_region(name, qualifiers)
        return fl, reg

    def resolve_with_region(
        self, name: str, qualifiers: tuple[str, ...] = ()
    ) -> tuple[FieldLayout, Register, RegionId]:
        """Return (FieldLayout, region_register, RegionId).

        Precedence: LOCAL-STORAGE > WORKING-STORAGE > LINKAGE > FILE >
        SPECIAL-REGISTERS > INDEXES. See resolve()'s docstring for the
        ``qualifiers`` semantics; this is the sole place that precedence
        logic lives — resolve() delegates here."""
        ls_layout, ls_reg = self.local_storage
        ls_fl = ls_layout.lookup_as_storage(name, qualifiers)
        if ls_fl is not None:
            ws_layout, _ = self.working_storage
            if ws_layout.lookup_as_storage(name, qualifiers) is not None:
                logger.warning(
                    "Field %r found in both LOCAL-STORAGE and WORKING-STORAGE — LOCAL-STORAGE wins (collision)",
                    name,
                )
            return ls_fl, ls_reg, RegionId.LOCAL_STORAGE

        ws_layout, ws_reg = self.working_storage
        ws_fl = ws_layout.lookup_as_storage(name, qualifiers)
        if ws_fl is not None:
            return ws_fl, ws_reg, RegionId.WORKING_STORAGE

        lk_layout, _ = self.linkage
        lk_fl = lk_layout.lookup_as_storage(name, qualifiers)
        if lk_fl is not None:
            return lk_fl, self.linkage_binding(lk_fl).region_reg, RegionId.LINKAGE

        file_layout, file_reg = self.file
        file_fl = file_layout.lookup_as_storage(name, qualifiers)
        if file_fl is not None:
            return file_fl, file_reg, RegionId.FILE

        sr_layout, sr_reg = self.special_registers
        sr_fl = sr_layout.lookup_as_storage(name, qualifiers)
        if sr_fl is not None:
            return sr_fl, sr_reg, RegionId.SPECIAL_REGISTERS

        ix_layout, ix_reg = self.indexes
        ix_fl = ix_layout.lookup_as_storage(name, qualifiers)
        if ix_fl is not None:
            return ix_fl, ix_reg, RegionId.INDEXES

        raise KeyError(f"Field {name!r} not found in any DATA DIVISION section")

    def subscript_stride(self, name: str) -> int:
        """Return the subscript stride (enclosing OCCURS element_size) for a
        leaf field, searched across sections with resolve()'s precedence.

        A leaf nested inside an OCCURS group strides by the group's element_size,
        not by the leaf's own byte_length. Returns 0 if not under an OCCURS table.
        """
        for layout, _reg in (
            self.local_storage,
            self.working_storage,
            self.linkage,
            self.file,
        ):
            if layout.exists(name):
                return layout.enclosing_occurs_element_size(name)
        return 0

    def subscript_strides(self, name: str) -> list[int]:
        """Return all OCCURS element_sizes from outermost to innermost for ``name``.

        len() equals the number of subscript dimensions the field supports.
        """
        for layout, _reg in (
            self.local_storage,
            self.working_storage,
            self.linkage,
            self.file,
        ):
            if layout.exists(name):
                return layout.all_enclosing_occurs_strides(name)
        return []

    def occurs_tables(self, name: str) -> list[OccursTable]:
        """Return the OCCURS constructs enclosing ``name``, outermost first.

        Positionally aligned with :meth:`subscript_strides` (same sections,
        same precedence, same walk), so subscript *k* belongs to table *k*.
        Used to bound a computed-subscript access to a declared table rather
        than to the whole region.
        """
        for layout, _reg in (
            self.local_storage,
            self.working_storage,
            self.linkage,
            self.file,
        ):
            if layout.exists(name):
                return layout.all_enclosing_occurs_tables(name)
        return []

    def enclosing_record_extent(self, name: str) -> tuple[int, int] | None:
        """Return ``(offset, byte_length)`` of the 01/77 record holding ``name``.

        Searches all six sections, not the four that carry OCCURS tables: this
        is the last-resort bound for an access nothing else can bound, so it
        must not come up empty for a field that resolved successfully.
        """
        for layout, _reg in (
            self.local_storage,
            self.working_storage,
            self.linkage,
            self.file,
            self.special_registers,
            self.indexes,
        ):
            found = layout.enclosing_record_extent(name)
            if found is not None:
                return found
        return None

    def has_field(self, name: str) -> bool:
        ls_layout, _ = self.local_storage
        ws_layout, _ = self.working_storage
        lk_layout, _ = self.linkage
        file_layout, _ = self.file
        sr_layout, _ = self.special_registers
        ix_layout, _ = self.indexes
        return (
            ls_layout.exists(name)
            or ws_layout.exists(name)
            or lk_layout.exists(name)
            or file_layout.exists(name)
            or sr_layout.exists(name)
            or ix_layout.exists(name)
        )

    def group_leaf_names(self, group_name: str) -> list[str]:
        """Return the leaf field names of a group, searched across sections.

        Order is the layout's depth-first order. Returns [] if no such group.
        Precedence mirrors resolve(): LOCAL-STORAGE > WORKING-STORAGE > LINKAGE > FILE.
        """
        for layout, _reg in (
            self.local_storage,
            self.working_storage,
            self.linkage,
            self.file,
        ):
            try:
                grp = layout.lookup_group(group_name)
            except KeyError:
                continue
            return [leaf.name for leaf in grp.all_leaves()]
        return []


def build_sectioned_layout(asg: CobolASG) -> SectionedLayout:
    """Build SectionedLayout from a CobolASG — one DataLayout per section."""
    linkage_fields = laid_end_to_end(_in_using_order(asg))
    records = tuple(
        LinkageRecord(item.name.upper(), item.offset, record_length(item))
        for item in linkage_fields
        if not item.redefines and not item.renames_from
    )
    named = [param.name.upper() for param in asg.procedure_using] or [
        record.name for record in records
    ]
    by_name = {record.name: record for record in records}
    return SectionedLayout(
        working_storage=build_data_layout(asg.data_fields),
        linkage=build_data_layout(linkage_fields),
        local_storage=build_data_layout(asg.local_storage_fields),
        file=build_data_layout(asg.file_fields),
        indexes=build_index_layout(
            asg.data_fields,
            asg.local_storage_fields,
            asg.linkage_fields,
            asg.file_fields,
        ),
        linkage_parameters=tuple(by_name[name] for name in named if name in by_name),
        linkage_unbound=tuple(r for r in records if r.name not in named),
        linkage_owners=_linkage_owners(linkage_fields),
    )


def _linkage_owners(
    linkage_fields: Sequence[CobolField],
) -> Mapping[tuple[str, int, int], str]:
    """Each LINKAGE field, leaf or group, mapped to the 01 whose argument it lives
    in. A REDEFINES 01 is laid out at the 01 it redefines and belongs to it."""
    by_name = {item.name.upper(): item for item in linkage_fields}
    return {
        _field_identity(fl): owner.name.upper()
        for item in linkage_fields
        if not item.renames_from
        for owner in (by_name.get(item.redefines.upper(), item),)
        for fl in build_data_layout(
            [replace(item, redefines="", offset=owner.offset)]
        ).all_fields()
    }


def _field_identity(fl: FieldLayout) -> tuple[str, int, int]:
    return fl.name.upper(), fl.offset, fl.byte_length


def _in_using_order(asg: CobolASG) -> list[CobolField]:
    """LINKAGE in PROCEDURE DIVISION USING order, since a caller's arguments
    arrive packed by position; items USING does not name follow, in declaration
    order. A USING name with no declaration (a missing copybook) has nothing to
    lay out."""
    declared = {item.name.upper(): item for item in asg.linkage_fields}
    listed = [param.name.upper() for param in asg.procedure_using]
    return [declared[name] for name in listed if name in declared] + [
        item for item in asg.linkage_fields if item.name.upper() not in listed
    ]
