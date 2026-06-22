# pyright: standard
"""SectionedLayout — per-section DataLayout grouping for COBOL DATA DIVISION."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.data_layout import DataLayout, FieldLayout, build_data_layout
from interpreter.register import NO_REGISTER, Register

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SectionedLayout:
    """DataLayouts for all three DATA DIVISION sections — pure data, no registers."""

    working_storage: DataLayout
    linkage: DataLayout
    local_storage: DataLayout
    file: DataLayout = field(default_factory=DataLayout)


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

    def resolve(
        self, name: str, qualifiers: tuple[str, ...] = ()
    ) -> tuple[FieldLayout, Register]:
        """Return (FieldLayout, region_register). Precedence: LOCAL-STORAGE > WORKING-STORAGE > LINKAGE.

        ``qualifiers`` (``OF``/``IN`` ancestor group names) disambiguate a
        duplicated elementary name within the owning group (CardDemo CSUTLDTC's
        two Vstring groups share leaf names). red-dragon-p7qe."""
        ls_layout, ls_reg = self.local_storage
        ls_fl = ls_layout.lookup_as_storage(name, qualifiers)
        if ls_fl is not None:
            ws_layout, _ = self.working_storage
            if ws_layout.lookup_as_storage(name, qualifiers) is not None:
                logger.warning(
                    "Field %r found in both LOCAL-STORAGE and WORKING-STORAGE — LOCAL-STORAGE wins (collision)",
                    name,
                )
            return ls_fl, ls_reg

        ws_layout, ws_reg = self.working_storage
        ws_fl = ws_layout.lookup_as_storage(name, qualifiers)
        if ws_fl is not None:
            return ws_fl, ws_reg

        lk_layout, lk_reg = self.linkage
        lk_fl = lk_layout.lookup_as_storage(name, qualifiers)
        if lk_fl is not None:
            return lk_fl, lk_reg

        file_layout, file_reg = self.file
        file_fl = file_layout.lookup_as_storage(name, qualifiers)
        if file_fl is not None:
            return file_fl, file_reg

        sr_layout, sr_reg = self.special_registers
        sr_fl = sr_layout.lookup_as_storage(name, qualifiers)
        if sr_fl is not None:
            return sr_fl, sr_reg

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
            if layout.lookup_as_storage(name) is not None:
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
            if layout.lookup_as_storage(name) is not None:
                return layout.all_enclosing_occurs_strides(name)
        return []

    def has_field(self, name: str) -> bool:
        ls_layout, _ = self.local_storage
        ws_layout, _ = self.working_storage
        lk_layout, _ = self.linkage
        file_layout, _ = self.file
        sr_layout, _ = self.special_registers
        return (
            ls_layout.lookup_as_storage(name) is not None
            or ws_layout.lookup_as_storage(name) is not None
            or lk_layout.lookup_as_storage(name) is not None
            or file_layout.lookup_as_storage(name) is not None
            or sr_layout.lookup_as_storage(name) is not None
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
    return SectionedLayout(
        working_storage=build_data_layout(asg.data_fields),
        linkage=build_data_layout(asg.linkage_fields),
        local_storage=build_data_layout(asg.local_storage_fields),
        file=build_data_layout(asg.file_fields),
    )
