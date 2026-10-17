"""The region registers and RegionIds of a CORRESPONDING statement's sending and receiving groups."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_memory.region_id import RegionId
from interpreter.register import Register


@dataclass(frozen=True)
class CorrespondingRegions:
    source: Register
    source_region: RegionId
    target: Register
    target_region: RegionId
