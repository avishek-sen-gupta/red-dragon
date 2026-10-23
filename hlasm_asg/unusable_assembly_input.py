# pyright: standard
"""Raised when an assembly input cannot be handed to HLASM: a clock without its UTC offset, or an overlong SYSPARM."""

from __future__ import annotations


class UnusableAssemblyInput(ValueError):
    pass
