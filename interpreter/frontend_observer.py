# pyright: standard
"""Observer protocol for frontend parse/lower timing."""

from __future__ import annotations

from typing import Protocol


class FrontendObserver(Protocol):
    """Timing observer that frontends call during lower()."""

    def on_parse(self, duration: float) -> None: ...

    def on_lower(self, duration: float) -> None: ...


class NullFrontendObserver:
    """No-op observer for callers that don't need timing."""

    def on_parse(self, duration: float) -> None:
        pass

    def on_lower(self, duration: float) -> None:
        pass
