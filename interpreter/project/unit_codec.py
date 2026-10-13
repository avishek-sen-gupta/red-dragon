"""A ModuleUnit to and from its .unit.json file."""

from __future__ import annotations

import json
from pathlib import Path

from interpreter.project.ir_codec import IrCodec, Wire
from interpreter.project.types import ModuleUnit
from interpreter.project.unit_format_error import UnitFormatError

_FORMAT = 1


class UnitCodec:
    def __init__(self, ir: IrCodec) -> None:
        self._ir = ir

    def write(self, unit: ModuleUnit, path: Path) -> None:
        path.write_text(
            json.dumps({"format": _FORMAT, "unit": self._ir.encode(unit)}),
            encoding="utf-8",
        )

    def read(self, path: Path) -> ModuleUnit:
        try:
            return self._unit(json.loads(path.read_text(encoding="utf-8")))
        except (UnitFormatError, json.JSONDecodeError, KeyError) as exc:
            raise UnitFormatError(f"{path}: {exc}") from exc

    def _unit(self, wire: Wire) -> ModuleUnit:
        match wire:
            case {"format": 1, "unit": body}:
                return self._ir.decode_as(body, ModuleUnit)
            case _:
                raise UnitFormatError(f"not a unit file of format {_FORMAT}")
