# pyright: standard
"""Raised when the bridge named by HLASM_AST_BRIDGE, or the built default, is not an executable."""

from __future__ import annotations


class HlasmBridgeNotFound(Exception):
    def __init__(self, name: str):
        super().__init__(f"hlasm_ast_bridge not found: {name}")
        self.name = name
