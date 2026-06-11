"""Gate for the CardDemo end-to-end CICS tests.

These exercise the real unmodified CardDemo COBOL through the full toolchain
(CardDemo submodule + bms-tools submodule + a built ProLeap JAR). Modules opt in
with ``pytestmark = pytest.mark.carddemo_e2e``.

Policy: run everywhere (CI and local) when the toolchain is available, fail with
setup guidance when it is not. No silent skips — a missing tool must never hide
a regression.

Resolution order for CARDDEMO_HOME:
  1. CARDDEMO_HOME env var (explicit override, set by CI workflow)
  2. third-party/carddemo/app submodule (auto-detected from repo root)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.integration.cics.bms_tools_helpers import BMS_TOOLS_AVAILABLE
from tests.integration.cobol_helpers import JAR_AVAILABLE

_REPO_ROOT = Path(__file__).parents[3]
_SUBMODULE_CARDDEMO = _REPO_ROOT / "third-party" / "carddemo" / "app"


def _resolve_carddemo_home() -> str | None:
    if env := os.environ.get("CARDDEMO_HOME"):
        return env
    if _SUBMODULE_CARDDEMO.is_dir():
        return str(_SUBMODULE_CARDDEMO)
    return None


_CARDDEMO_HOME = _resolve_carddemo_home()

if _CARDDEMO_HOME:
    os.environ.setdefault("CARDDEMO_HOME", _CARDDEMO_HOME)

_TOOLCHAIN_OK = bool(_CARDDEMO_HOME) and JAR_AVAILABLE and BMS_TOOLS_AVAILABLE

_SETUP_MSG = (
    "CardDemo e2e toolchain not available. Ensure:\n"
    "  • git submodule update --init third-party/carddemo third-party/bms-tools\n"
    "  • ProLeap JAR built: cd proleap-bridge && mvn -DskipTests package\n"
    "  • hlasm_export built or downloaded into "
    "third-party/bms-tools/che-che4z-lsp-for-hlasm-fork/build/bin/"
)


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("carddemo_e2e") is None:
        return
    if not _TOOLCHAIN_OK:
        pytest.fail(_SETUP_MSG, pytrace=False)
