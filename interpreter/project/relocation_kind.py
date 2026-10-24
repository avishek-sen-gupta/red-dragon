# pyright: standard
"""What a relocation puts in its field: an address (A, V), a PR offset (Q), a class length (J) or the PR total (CXD)."""

from enum import StrEnum


class RelocationKind(StrEnum):
    ADDRESS = "ADDRESS"
    PR_OFFSET = "PR_OFFSET"
    CLASS_LENGTH = "CLASS_LENGTH"
    PR_TOTAL = "PR_TOTAL"
