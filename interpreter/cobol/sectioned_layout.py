# pyright: standard
"""SectionedLayout — per-section DataLayout grouping for COBOL DATA DIVISION."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.data_layout import DataLayout, FieldLayout, build_data_layout
from interpreter.register import Register

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

    def resolve(self, name: str) -> tuple[FieldLayout, Register]:
        """Return (FieldLayout, region_register). Precedence: LOCAL-STORAGE > WORKING-STORAGE > LINKAGE."""
        ls_layout, ls_reg = self.local_storage
        ls_fl = ls_layout.lookup_as_storage(name)
        if ls_fl is not None:
            ws_layout, _ = self.working_storage
            if ws_layout.lookup_as_storage(name) is not None:
                logger.warning(
                    "Field %r found in both LOCAL-STORAGE and WORKING-STORAGE — LOCAL-STORAGE wins (collision)",
                    name,
                )
            return ls_fl, ls_reg

        ws_layout, ws_reg = self.working_storage
        ws_fl = ws_layout.lookup_as_storage(name)
        if ws_fl is not None:
            return ws_fl, ws_reg

        lk_layout, lk_reg = self.linkage
        lk_fl = lk_layout.lookup_as_storage(name)
        if lk_fl is not None:
            return lk_fl, lk_reg

        raise KeyError(f"Field {name!r} not found in any DATA DIVISION section")

    def has_field(self, name: str) -> bool:
        ls_layout, _ = self.local_storage
        ws_layout, _ = self.working_storage
        lk_layout, _ = self.linkage
        return (
            ls_layout.lookup_as_storage(name) is not None
            or ws_layout.lookup_as_storage(name) is not None
            or lk_layout.lookup_as_storage(name) is not None
        )

    def group_leaf_names(self, group_name: str) -> list[str]:
        """Return the leaf field names of a group, searched across sections.

        Order is the layout's depth-first order. Returns [] if no such group.
        Precedence mirrors resolve(): LOCAL-STORAGE > WORKING-STORAGE > LINKAGE.
        """
        for layout, _reg in (
            self.local_storage,
            self.working_storage,
            self.linkage,
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
