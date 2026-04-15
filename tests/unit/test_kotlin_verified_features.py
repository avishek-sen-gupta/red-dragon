# pyright: standard
"""Enforcement tests for the Kotlin verified-features registry.

For every entry in KOTLIN_VERIFIED_FEATURES, asserts that each referenced
test module is importable and the test class exists within it.

Deleting a test class or misspelling a module path fails these tests
immediately, preventing the registry from silently going stale.
"""

from __future__ import annotations

import importlib

import pytest

from interpreter.frontends.kotlin.verified_features import (
    KOTLIN_VERIFIED_FEATURES,
    VerifiedFeature,
)


def _all_refs() -> list[tuple[VerifiedFeature, str, str]]:
    return [
        (feat, mod, cls)
        for feat in KOTLIN_VERIFIED_FEATURES
        for mod, cls in feat.test_refs
    ]


@pytest.mark.parametrize(
    "feature,module_path,class_name",
    [
        pytest.param(feat, mod, cls, id=f"{feat.label}→{cls}")
        for feat, mod, cls in _all_refs()
    ],
)
def test_verified_feature_test_class_exists(
    feature: VerifiedFeature, module_path: str, class_name: str
) -> None:
    """Each test_ref in the registry must resolve to a real test class."""
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"verified feature '{feature.label}': "
            f"test module '{module_path}' not found — {exc}"
        )

    assert hasattr(module, class_name), (
        f"verified feature '{feature.label}': "
        f"test class '{class_name}' not found in '{module_path}'"
    )
