"""AddressingMode — what a pointer looks like under one LP setting."""

from __future__ import annotations

from typing import Protocol

from cobol_asg.cobol_types import CobolTypeDescriptor


class AddressingMode(Protocol):
    @property
    def pointer_type(self) -> CobolTypeDescriptor: ...
