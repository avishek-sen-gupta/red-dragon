# pyright: standard
"""@covers and @no_covers decorators for annotating test methods.

Usage::

    from tests.covers import covers
    from interpreter.frontends.java.features import JavaFeature

    class TestJavaInterface:
        @covers(JavaFeature.INTERFACE)
        def test_interface_method_lowering(self):
            ...

    # For tests that verify infrastructure rather than a language feature:
    class TestTypeGraph:
        @no_covers("tests TypeGraph internal structure, not a language feature")
        def test_type_graph_lookup(self):
            ...

Both decorators are no-ops at runtime. @covers attaches feature metadata for the
coverage audit script (scripts/feature_coverage_audit.py). @no_covers signals an
intentional exemption from the @covers requirement.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import TypeVar

_F = TypeVar("_F", bound=Callable[..., object])


class FeatureStatus(Enum):
    """Implementation status of a covered feature."""

    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


def covers(
    *features: Enum, status: FeatureStatus = FeatureStatus.IMPLEMENTED
) -> Callable[[_F], _F]:
    """Annotate a test method with the language feature(s) it primarily verifies.

    Each test method should cover exactly one primary feature.  If a test
    conflates multiple primary features, split it into separate methods.

    Use ``status=FeatureStatus.UNSUPPORTED`` (paired with ``@pytest.mark.xfail``)
    to document known gaps where the feature is not yet implemented.
    Use ``status=FeatureStatus.PARTIAL`` for features that are partially implemented.
    """

    def _decorator(func: _F) -> _F:
        func._covers = frozenset(features)  # type: ignore[attr-defined]
        func._covers_status = status  # type: ignore[attr-defined]
        return func

    return _decorator


def no_covers(reason: str) -> Callable[[_F], _F]:
    """Explicitly exempt a test method from the @covers requirement.

    Use only for tests that verify infrastructure, utilities, or cross-cutting
    concerns that don't map to a specific language feature enum member.

    The reason string is mandatory — it documents why the exemption is justified
    and makes intentional exemptions easy to audit (grep for no_covers).
    """

    def _decorator(func: _F) -> _F:
        func._no_covers = reason  # type: ignore[attr-defined]
        return func

    return _decorator
