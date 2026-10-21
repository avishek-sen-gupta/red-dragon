# pyright: standard
"""Raised when the bridge refuses a source because it has assembly errors."""

from __future__ import annotations

from hlasm_asg.program.diagnostic import Diagnostic


class HlasmParseError(Exception):
    def __init__(self, diagnostics: tuple[Diagnostic, ...]):
        super().__init__(
            "; ".join(f"{d.code} line {d.line}: {d.message}" for d in diagnostics)
        )
        self.diagnostics = diagnostics
