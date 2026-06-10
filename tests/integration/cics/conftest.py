"""Gate for the AWS CardDemo end-to-end CICS tests.

These exercise the *real* unmodified CardDemo COBOL through the full toolchain
(``CARDDEMO_HOME`` + ``BMS_TOOLS_HOME`` + a built ProLeap JAR) — the only tests
that drive the bridge + CSD + PIC + VSAM path end-to-end. Modules opt in with
``pytestmark = pytest.mark.carddemo_e2e``. Policy:

  * **CI** (``CI`` env var set, as GitHub Actions does): SKIP — the heavy
    toolchain (CardDemo checkout, bms-tools, JAR) is not provisioned there.
  * **Local** (not CI): MANDATORY — RUN when the toolchain is set up, else
    **FAIL** with setup guidance. A missing JAR/env can therefore never let the
    CardDemo e2e *silently skip* on a dev machine (which is exactly what once
    hid a REWRITE regression that only this suite catches).
"""

from __future__ import annotations

import os

import pytest

from tests.integration.cics.bms_tools_helpers import BMS_TOOLS_AVAILABLE
from tests.integration.cobol_helpers import JAR_AVAILABLE

_IN_CI = bool(os.environ.get("CI"))
_TOOLCHAIN_OK = (
    bool(os.environ.get("CARDDEMO_HOME")) and JAR_AVAILABLE and BMS_TOOLS_AVAILABLE
)
_SETUP_MSG = (
    "CardDemo e2e is MANDATORY locally but the toolchain is not set up. "
    "Set CARDDEMO_HOME (the CardDemo `app` dir) and BMS_TOOLS_HOME, and build the "
    "ProLeap JAR (cd proleap-bridge && mvn -DskipTests package). "
    "(These tests run locally and are skipped only in CI.)"
)


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip ``carddemo_e2e`` tests in CI; require the toolchain locally."""
    if item.get_closest_marker("carddemo_e2e") is None:
        return
    if _IN_CI:
        pytest.skip("CardDemo e2e skipped in CI (heavy toolchain not provisioned)")
    if not _TOOLCHAIN_OK:
        pytest.fail(_SETUP_MSG, pytrace=False)
