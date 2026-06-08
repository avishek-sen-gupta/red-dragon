"""Gating constants for the bms-tools pipeline (mirror cobol_helpers JAR gating)."""

from __future__ import annotations

from tests.covers import covers, NotLanguageFeature


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_helpers_expose_gating_constants() -> None:
    from tests.integration.cics import bms_tools_helpers as h

    assert hasattr(h, "BMS_TOOLS_HOME")
    assert hasattr(h, "HLASM_EXPORT_BIN")
    assert hasattr(h, "BMS_COPYBOOK_GEN_SRC")
    assert isinstance(h.BMS_TOOLS_AVAILABLE, bool)
    import os

    assert h.BMS_TOOLS_AVAILABLE == (
        h.HLASM_EXPORT_BIN is not None and os.path.isfile(h.HLASM_EXPORT_BIN)
    )
