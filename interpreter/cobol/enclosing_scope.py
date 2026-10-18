"""A containing program's storage as the programs it contains see it: its whole
WORKING-STORAGE and FILE SECTION, for the file connectors it owns, and the global
part of each, for name resolution."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from cobol_memory.region_id import RegionId
from interpreter.cobol.data_layout import DataItemMatch, DataLayout
from interpreter.register import Register


@dataclass(frozen=True)
class EnclosingLayout:
    program: str
    working_storage: DataLayout
    file: DataLayout
    global_working_storage: DataLayout
    global_file: DataLayout


@dataclass(frozen=True)
class InheritedScope:
    """An enclosing program's layout bound to the regions it lives in at run time."""

    layout: EnclosingLayout
    working_storage_reg: Register
    file_reg: Register

    def global_matches(
        self, name: str, qualifiers: tuple[str, ...]
    ) -> Iterator[tuple[DataItemMatch, Register, RegionId]]:
        return _matches(
            (
                (self.layout.global_working_storage, self.working_storage_reg),
                (self.layout.global_file, self.file_reg),
            ),
            name,
            qualifiers,
        )

    def owned_matches(
        self, name: str, qualifiers: tuple[str, ...]
    ) -> Iterator[tuple[DataItemMatch, Register, RegionId]]:
        """Any item of the program, global or not: what its own file connectors name."""
        return _matches(
            (
                (self.layout.working_storage, self.working_storage_reg),
                (self.layout.file, self.file_reg),
            ),
            name,
            qualifiers,
        )

    def has_global(self, name: str) -> bool:
        return self.layout.global_working_storage.exists(
            name
        ) or self.layout.global_file.exists(name)


def _matches(
    sections: tuple[tuple[DataLayout, Register], tuple[DataLayout, Register]],
    name: str,
    qualifiers: tuple[str, ...],
) -> Iterator[tuple[DataItemMatch, Register, RegionId]]:
    working_storage, file = sections
    return (
        (match, reg, region)
        for (layout, reg), region in (
            (working_storage, RegionId.WORKING_STORAGE),
            (file, RegionId.FILE),
        )
        for match in layout.qualified_matches(name, qualifiers)
    )
