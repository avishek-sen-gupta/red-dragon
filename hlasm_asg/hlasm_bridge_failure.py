# pyright: standard
"""Raised when the bridge fails for a reason other than assembly errors."""

from __future__ import annotations


class HlasmBridgeFailure(Exception):
    def __init__(self, returncode: int, stderr: str):
        super().__init__(f"hlasm_ast_bridge exited {returncode}: {stderr}")
        self.returncode = returncode
        self.stderr = stderr
