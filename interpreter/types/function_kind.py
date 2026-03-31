# pyright: standard
"""FunctionKind — classifies functions as unbound, instance, or static."""

from __future__ import annotations

from enum import Enum


class FunctionKind(Enum):
    """Distinguishes top-level functions from class methods.

    UNBOUND  — free/top-level function, not inside any class.
    INSTANCE — instance method with an implicit 'this'/'$this' parameter.
    STATIC   — static/class method inside a class, no 'this' parameter.
    """

    UNBOUND = "unbound"
    INSTANCE = "instance"
    STATIC = "static"
