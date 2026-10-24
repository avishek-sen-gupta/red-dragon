# pyright: standard
"""A unit diagnostic an MNOTE raised as a comment, with its text."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommentMnote:
    text: str
