# pyright: standard
"""SectionedLayout — per-section DataLayout grouping for COBOL DATA DIVISION."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import islice

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_memory.region_id import RegionId
from interpreter.cobol.data_layout import (
    DataItemMatch,
    DataLayout,
    FieldLayout,
    build_data_layout,
    build_index_layout,
    laid_end_to_end,
    record_length,
)
from interpreter.cobol.external_area import ExternalArea
from interpreter.cobol.external_binding import ExternalBinding
from interpreter.cobol.external_layout import partition_external
from interpreter.cobol.linkage_binding import LinkageBinding
from interpreter.cobol.linkage_record import LinkageRecord
from interpreter.cobol.undeclared_data_name import UndeclaredDataName
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
    external: DataLayout = field(default_factory=DataLayout)
    external_areas: tuple[ExternalArea, ...] = ()
    external_owners: Mapping[tuple[str, int, int], ExternalArea] = field(
        default_factory=dict
    )


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
    external: DataLayout = field(default_factory=DataLayout)
    external_bindings: tuple[ExternalBinding, ...] = ()
    external_owners: Mapping[tuple[str, int, int], ExternalArea] = field(
        default_factory=dict
    )

    def external_binding(self, fl: FieldLayout) -> ExternalBinding:
        """The binding of the EXTERNAL area whose description declares ``fl``."""
        area = self.external_owners[_field_identity(fl)]
        return next(
            binding for binding in self.external_bindings if binding.area == area
        )

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
        """Return (FieldLayout, region_register, RegionId) — see :meth:`resolve_match`."""
        match, reg, region = self.resolve_match(name, qualifiers)
        return match.storage, reg, region

    def resolve_match(
        self, name: str, qualifiers: tuple[str, ...] = ()
    ) -> tuple[DataItemMatch, Register, RegionId]:
        """Return the data item ``name`` qualified by ``qualifiers`` denotes, with
        its region register and RegionId.

        Precedence: LOCAL-STORAGE > WORKING-STORAGE > LINKAGE > FILE >
        SPECIAL-REGISTERS > INDEXES; the first section holding a match wins, and
        this is the sole place that precedence lives."""
        found = tuple(
            islice(
                (
                    (match, reg, region)
                    for layout, reg, region in self._sections()
                    for match in layout.qualified_matches(name, qualifiers)
                ),
                1,
            )
        )
        if not found:
            raise UndeclaredDataName(name)
        match, reg, region = found[0]
        if region is RegionId.LOCAL_STORAGE and self.working_storage[
            0
        ].qualified_matches(name, qualifiers):
            logger.warning(
                "Field %r found in both LOCAL-STORAGE and WORKING-STORAGE — LOCAL-STORAGE wins (collision)",
                name,
            )
        if region is RegionId.LINKAGE:
            return match, self.linkage_binding(match.storage).region_reg, region
        if region is RegionId.EXTERNAL:
            return match, self.external_binding(match.storage).region_reg, region
        return match, reg, region

    def layout_of(self, region: RegionId) -> DataLayout:
        """The DataLayout of the section ``region`` holds."""
        return next(layout for layout, _, owner in self._sections() if owner is region)

    def _sections(self) -> tuple[tuple[DataLayout, Register, RegionId], ...]:
        return (
            (*self.local_storage, RegionId.LOCAL_STORAGE),
            (*self.working_storage, RegionId.WORKING_STORAGE),
            (self.external, NO_REGISTER, RegionId.EXTERNAL),
            (*self.linkage, RegionId.LINKAGE),
            (*self.file, RegionId.FILE),
            (*self.special_registers, RegionId.SPECIAL_REGISTERS),
            (*self.indexes, RegionId.INDEXES),
        )

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
            or self.external.exists(name)
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
            (self.external, NO_REGISTER),
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
        if not item.redefines and not item.renames_from.name
    )
    named = [param.name.upper() for param in asg.procedure_using] or [
        record.name for record in records
    ]
    by_name = {record.name: record for record in records}
    shared = partition_external(asg)
    return SectionedLayout(
        working_storage=build_data_layout(list(shared.working_storage)),
        linkage=build_data_layout(linkage_fields),
        local_storage=build_data_layout(asg.local_storage_fields),
        file=build_data_layout(list(shared.file)),
        indexes=build_index_layout(
            asg.data_fields,
            asg.local_storage_fields,
            asg.linkage_fields,
            asg.file_fields,
        ),
        linkage_parameters=tuple(by_name[name] for name in named if name in by_name),
        linkage_unbound=tuple(r for r in records if r.name not in named),
        linkage_owners=_linkage_owners(linkage_fields),
        external=build_data_layout(
            [record for group in shared.groups for record in group]
        ),
        external_areas=shared.areas,
        external_owners={
            _field_identity(fl): area
            for area, group in zip(shared.areas, shared.groups, strict=True)
            for fl in build_data_layout(list(group)).all_fields()
        },
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
        if not item.renames_from.name
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
