"""Gating + path constants for the bms-tools pipeline.

Resolution order for BMS_TOOLS_HOME:
  1. BMS_TOOLS_HOME env var (explicit override)
  2. third-party/bms-tools submodule (relative to repo root)
  3. ~/code/bms-tools (legacy local convention)
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[3]
_SUBMODULE = _REPO_ROOT / "third-party" / "bms-tools"


def _resolve_bms_tools_home() -> str | None:
    if env := os.environ.get("BMS_TOOLS_HOME"):
        return env
    if _SUBMODULE.is_dir():
        return str(_SUBMODULE)
    legacy = Path(os.path.expanduser("~/code/bms-tools"))
    if legacy.is_dir():
        return str(legacy)
    return None


BMS_TOOLS_HOME: str | None = _resolve_bms_tools_home()

HLASM_EXPORT_BIN: str | None = (
    str(
        Path(BMS_TOOLS_HOME)
        / "che-che4z-lsp-for-hlasm-fork"
        / "build"
        / "bin"
        / "hlasm_export"
    )
    if BMS_TOOLS_HOME
    else None
)

BMS_COPYBOOK_GEN_SRC: str | None = (
    str(Path(BMS_TOOLS_HOME) / "python" / "bms_copybook_gen" / "src")
    if BMS_TOOLS_HOME
    else None
)

BMS_TOOLS_AVAILABLE: bool = bool(
    HLASM_EXPORT_BIN is not None and os.path.isfile(HLASM_EXPORT_BIN)
)
