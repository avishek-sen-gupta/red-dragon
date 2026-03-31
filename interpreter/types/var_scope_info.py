# pyright: standard
"""VarScopeInfo — metadata for mangled block-scoped variable names."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VarScopeInfo:
    """Records the original name and scope depth of a mangled variable.

    When a block-scoped frontend encounters a declaration that shadows
    an outer variable, it generates a mangled name (e.g., ``x$1``) and
    records this metadata so consumers can recover the original name.
    """

    original_name: str
    scope_depth: int
