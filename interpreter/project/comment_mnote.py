# pyright: standard
"""A unit diagnostic an MNOTE raised as a comment."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommentMnote:
    pass
