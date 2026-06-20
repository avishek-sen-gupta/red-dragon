# pyright: standard
"""COBOL special registers — compiler-provided pseudo-fields, not DATA DIVISION.

RETURN-CODE is an implicit ``PIC S9(4) COMP`` register (binary halfword, 2 bytes,
big-endian two's complement) that a program sets to communicate a completion code
to its caller. It is not declared in the DATA DIVISION, so it gets its OWN dedicated
region — isolated from WORKING-STORAGE and the FD/file region — and a stable handle
on the program's singleton HeapObject (field ``return_code_handle``) so the value is
recoverable from the returned VMState (see ``return_code_readback``).

This module is import-clean of the VM layer so the lowering pipeline can pull in the
layout/handle constants without dragging ``interpreter.vm`` into the COBOL/project
import chain (the read-back helper, which needs VMState, lives separately).

Only RETURN-CODE is wired today (red-dragon-o8uq). SORT-RETURN and TALLY remain in
the lower_arithmetic skip-list and can later be added as further elementary fields
of this same layout.
"""

from __future__ import annotations

from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.data_layout import build_data_layout
from interpreter.field_name import FieldName

RETURN_CODE_NAME = "RETURN-CODE"

# Stable identity: the SR region's address is stored on the program singleton under
# this field name, mirroring how WORKING-STORAGE is stored under ``ws_handle``.
RETURN_CODE_HANDLE = FieldName("return_code_handle")

# One elementary field, implicit PIC S9(4) COMP, offset 0, in its own region.
# No VALUE clause: ALLOC_REGION zero-fills the region, and a 2-byte big-endian zero
# already encodes RETURN-CODE's initial value 0 — so emitting an encode would only
# add instruction noise (the binary-encode helper expands to BINOPs).
SPECIAL_REGISTERS_LAYOUT = build_data_layout(
    [
        CobolField(
            name=RETURN_CODE_NAME,
            level=1,
            pic="S9(4)",
            usage="COMP",
            offset=0,
        )
    ]
)
