"""Gating + path constants for the external bms-tools pipeline.

Mirrors tests/integration/cobol_helpers.py (JAR_PATH/JAR_AVAILABLE). The pipeline
is an EXTERNAL, locally-built toolchain; everything that needs it skips when
BMS_TOOLS_HOME is unset or the hlasm_export binary is absent.
"""

from __future__ import annotations

import os
from pathlib import Path

BMS_TOOLS_HOME: str | None = os.environ.get("BMS_TOOLS_HOME") or (
    os.path.expanduser("~/code/bms-tools")
    if os.path.isdir(os.path.expanduser("~/code/bms-tools"))
    else None
)

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
