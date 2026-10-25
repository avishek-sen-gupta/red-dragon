# pyright: standard
"""What a relocation puts in its field: an address (A, V), a PR offset (Q, QD) or one in long-displacement format (QY), a class length (J) or the PR total (CXD)."""

from enum import StrEnum


class RelocationKind(StrEnum):
    ADDRESS = "ADDRESS"
    PR_OFFSET = "PR_OFFSET"
    PR_LONG_OFFSET = "PR_LONG_OFFSET"
    CLASS_LENGTH = "CLASS_LENGTH"
    PR_TOTAL = "PR_TOTAL"
