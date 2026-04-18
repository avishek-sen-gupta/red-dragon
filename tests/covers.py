# pyright: standard
"""@covers decorator for annotating test methods with the language feature they verify.

Usage::

    from tests.covers import covers, FeatureStatus, NotLanguageFeature
    from interpreter.frontends.java.features import JavaFeature

    class TestJavaInterface:
        @covers(JavaFeature.INTERFACE)
        def test_interface_method_lowering(self):
            ...

    # For tests that verify infrastructure rather than a language feature:
    class TestTypeGraph:
        @covers(NotLanguageFeature.INFRASTRUCTURE)
        def test_type_graph_lookup(self):
            ...

    # For known gaps not yet implemented:
    class TestJSWith:
        @pytest.mark.xfail(reason="not implemented (issue-xyz)")
        @covers(JavaScriptFeature.WITH_STATEMENT, status=FeatureStatus.UNSUPPORTED)
        def test_with_scope(self):
            ...

@covers is a no-op at runtime. It attaches feature metadata for the coverage audit
script (scripts/feature_coverage_audit.py). NotLanguageFeature members are silently
ignored by the audit — they only satisfy the covers-guard hook.
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


class NotLanguageFeature(Enum):
    """Sentinel for tests that verify infrastructure or cross-cutting concerns.

    Use instead of a language-specific feature enum when the test does not
    exercise a language feature directly (e.g. coverage tooling, type graph
    internals, audit scripts).
    """

    INFRASTRUCTURE = (
        "tests infrastructure or cross-cutting concerns, not a language feature"
    )


def covers(
    *features: Enum, status: FeatureStatus = FeatureStatus.IMPLEMENTED
) -> Callable[[_F], _F]:
    """Annotate a test method with the language feature(s) it primarily verifies.

    Pass a language-specific ``XxxFeature`` member, or ``NotLanguageFeature.INFRASTRUCTURE``
    for tests that don't map to a specific language feature.

    Use ``status=FeatureStatus.UNSUPPORTED`` (paired with ``@pytest.mark.xfail``)
    to document known gaps where the feature is not yet implemented.
    Use ``status=FeatureStatus.PARTIAL`` for features that are partially implemented.
    """

    def _decorator(func: _F) -> _F:
        func._covers = frozenset(features)  # type: ignore[attr-defined]
        func._covers_status = status  # type: ignore[attr-defined]
        return func

    return _decorator
