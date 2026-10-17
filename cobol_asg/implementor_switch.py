"""A SPECIAL-NAMES implementor switch clause: names for a switch and its two statuses."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ImplementorSwitch:
    """environment-name IS mnemonic-name ON STATUS IS on-condition OFF STATUS IS
    off-condition; a name not written is empty."""

    environment_name: str
    mnemonic_name: str
    on_condition: str
    off_condition: str

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> ImplementorSwitch:
        return cls(
            environment_name=data["environment_name"],
            mnemonic_name=data["mnemonic_name"],
            on_condition=data["on_condition"],
            off_condition=data["off_condition"],
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "environment_name": self.environment_name,
            "mnemonic_name": self.mnemonic_name,
            "on_condition": self.on_condition,
            "off_condition": self.off_condition,
        }
