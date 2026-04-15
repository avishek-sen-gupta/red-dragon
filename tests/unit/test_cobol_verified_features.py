# pyright: standard
"""Enforcement test: every COBOL VerifiedFeature must reference real test classes."""

from __future__ import annotations

import importlib

import pytest

from interpreter.cobol.verified_features import COBOL_VERIFIED_FEATURES


@pytest.mark.parametrize(
    "feature",
    COBOL_VERIFIED_FEATURES,
    ids=[f.label for f in COBOL_VERIFIED_FEATURES],
)
def test_verified_feature_test_refs_resolve(feature):
    """Each test_ref (module, class) pair must be importable."""
    assert feature.test_refs, f"{feature.label} has no test_refs"
    for module_path, class_name in feature.test_refs:
        mod = importlib.import_module(module_path)
        assert hasattr(
            mod, class_name
        ), f"{feature.label}: {module_path} has no class {class_name}"
