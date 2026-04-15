# pyright: standard
"""@covers decorator for annotating test methods with the language features they verify.

Usage::

    from tests.covers import covers
    from interpreter.frontends.java.features import JavaFeature

    class TestJavaInterface:
        @covers(JavaFeature.INTERFACE)
        def test_interface_method_lowering(self):
            ...

The decorator is a no-op at runtime — it attaches metadata to the function for
the feature coverage audit script (scripts/feature_coverage_audit.py).
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import TypeVar

_F = TypeVar("_F", bound=Callable[..., object])


def covers(*features: Enum) -> Callable[[_F], _F]:
    """Annotate a test method with the language feature(s) it primarily verifies.

    Each test method should cover exactly one primary feature.  If a test
    conflates multiple primary features, split it into separate methods.
    """

    def _decorator(func: _F) -> _F:
        func._covers = frozenset(features)  # type: ignore[attr-defined]
        return func

    return _decorator
