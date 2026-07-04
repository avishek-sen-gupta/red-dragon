# pyright: standard
"""RedDragon-owned fake dialect + parser for the frontend's own seam tests.

These prove the GENERIC extension_strategies/dialect_parsers machinery works
without depending on Cicada or Squall — RedDragon must never import either.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FakeExtensionStatement:
    """A minimal opaque coprocessor-extension statement, for testing only."""

    text: str

    def to_dict(self) -> dict:
        return {"type": "FAKE_EXTENSION", "fake_text": self.text}


class FakeDialectParser:
    def applies(self, data: dict) -> bool:
        return data.get("type") == "FAKE_EXTENSION"

    def parse(self, data: dict) -> Any:
        return FakeExtensionStatement(text=data.get("fake_text", ""))
