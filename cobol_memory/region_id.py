# pyright: standard
"""RegionId — the DATA DIVISION section buffers a COBOL field can live in.

lower_data_division emits one AllocRegion per non-empty section, so a field
address is (region, byte offset). Two fields can alias only within the same
region; across regions there is no overlap, because they are separate byte
buffers. LINKAGE is the exception in scope 2, where CALL USING deliberately
binds a callee's linkage region onto caller storage.
"""

from __future__ import annotations

from enum import Enum


class RegionId(Enum):
    WORKING_STORAGE = "working_storage"
    LINKAGE = "linkage"
    LOCAL_STORAGE = "local_storage"
    FILE = "file"
    SPECIAL_REGISTERS = "special_registers"
    INDEXES = "indexes"
