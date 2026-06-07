"""BMS map loader — loads BMS mapset definitions for SEND MAP / RECEIVE MAP."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BmsField:
    offset: int
    length: int
    attr: int = 0x00  # BMS attribute byte (default: unprotected, alphanumeric)
    # Symbolic-map COBOL subfield names (from the generated symbolic copybook).
    # When unset, derived by suffix convention (see BmsMap.symbolic_names).
    input_name: str | None = None  # <base>I
    output_name: str | None = None  # <base>O
    length_name: str | None = None  # <base>L


@dataclass
class BmsMap:
    name: str
    fields: dict[str, BmsField] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fields": {
                fname: {"offset": f.offset, "length": f.length, "attr": f.attr}
                for fname, f in self.fields.items()
            },
        }

    def symbolic_names(self, base: str) -> tuple[str, str, str]:
        """Return (input, output, length) symbolic-map COBOL subfield names.

        Explicit names on the BmsField win; otherwise names are derived by
        appending the conventional I/O/L suffixes to the base field name.
        Assumption: COBOL names cap at 30 chars; for long bases the host map
        generator truncates per its own rules — we simply append the suffix
        here and rely on explicit overrides for the truncated cases.
        """
        f = self.fields[base]
        inp = f.input_name or (base + "I")
        out = f.output_name or (base + "O")
        length = f.length_name or (base + "L")
        return inp, out, length

    def extract_fields(self, region: bytes) -> dict[str, bytes]:
        """Extract named field values from a map region (byte slice)."""
        result: dict[str, bytes] = {}
        for fname, fdef in self.fields.items():
            start = fdef.offset
            end = start + fdef.length
            result[fname] = region[start:end] if end <= len(region) else b""
        return result

    def write_fields(self, region: bytearray, values: dict[str, bytes]) -> None:
        """Write named field values into a map region (bytearray, mutated in-place)."""
        for fname, fval in values.items():
            fdef = self.fields.get(fname)
            if fdef is None:
                continue
            start = fdef.offset
            end = start + fdef.length
            padded = fval[: fdef.length].ljust(fdef.length, b" ")
            region[start:end] = padded[: fdef.length]


class BmsLoader:
    """Loads BMS maps from a directory of .bms files or stub registrations."""

    def __init__(self, maps_dir: Path | None) -> None:
        self._maps: dict[str, BmsMap] = {}
        if maps_dir is not None and maps_dir.exists():
            self._load_dir(maps_dir)

    def _load_dir(self, maps_dir: Path) -> None:
        for bms_file in maps_dir.glob("*.bms"):
            try:
                self._parse_bms_file(bms_file)
            except Exception as exc:  # best-effort: log and skip
                logger.warning("BMS: failed to load %s: %s", bms_file, exc)

    def _parse_bms_file(self, path: Path) -> None:
        """Minimal .bms parser — extracts DFHMDI map + DFHMDF field definitions."""
        content = path.read_text(encoding="utf-8", errors="replace").upper()
        current_map: str | None = None
        fields: dict[str, BmsField] = {}
        for m in re.finditer(r"(\w+)\s+DFHMDI\b", content):
            current_map = m.group(1)
            fields = {}
        for m in re.finditer(
            r"(\w+)\s+DFHMDF\s+.*?POS=\((\d+),(\d+)\).*?LENGTH=(\d+)", content
        ):
            fname = m.group(1)
            row, col, length = int(m.group(2)), int(m.group(3)), int(m.group(4))
            offset = (row - 1) * 80 + (col - 1)  # 80-col 3270 screen approximation
            fields[fname] = BmsField(offset=offset, length=length)
        if current_map and fields:
            self._maps[current_map] = BmsMap(name=current_map, fields=fields)
            logger.info("BMS: loaded map %s (%d fields)", current_map, len(fields))

    def register_stub(self, map_name: str, bms_map: BmsMap) -> None:
        """Register a manually constructed stub map (for tests or pre-defined maps)."""
        self._maps[map_name.upper()] = bms_map

    def get(self, map_name: str) -> BmsMap | None:
        return self._maps.get(map_name.upper().strip("'\" "))
