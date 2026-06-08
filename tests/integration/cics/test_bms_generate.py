"""Gated: the real bms-tools pipeline generates a symbolic copybook from a .bms."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.covers import covers, NotLanguageFeature
from tests.integration.cics.bms_tools_helpers import (
    BMS_TOOLS_AVAILABLE,
    HLASM_EXPORT_BIN,
    BMS_COPYBOOK_GEN_SRC,
)

_CARDDEMO_HOME = os.environ.get("CARDDEMO_HOME")

pytestmark = pytest.mark.skipif(
    not BMS_TOOLS_AVAILABLE or not _CARDDEMO_HOME,
    reason="needs BMS_TOOLS_HOME (built hlasm_export) and CARDDEMO_HOME",
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_generate_symbolic_copybooks_from_bms_dir(tmp_path: Path) -> None:
    from interpreter.cics.bms.generate import generate_symbolic_copybooks

    bms_dir = Path(_CARDDEMO_HOME) / "bms"
    out_dir = tmp_path / "sym"
    written = generate_symbolic_copybooks(
        bms_dir=bms_dir,
        out_dir=out_dir,
        hlasm_export_bin=HLASM_EXPORT_BIN,
        bms_copybook_gen_src=BMS_COPYBOOK_GEN_SRC,
    )
    assert out_dir in {p.parent for p in written}
    cosgn = out_dir / "COSGN00.cpy"
    assert cosgn.is_file()
    text = cosgn.read_text().upper()
    assert "01  COSGN0AO" in text or "01 COSGN0AO" in text
    assert "USERIDO" in text
