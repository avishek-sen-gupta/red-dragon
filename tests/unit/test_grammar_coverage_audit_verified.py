# pyright: standard
"""Tests for verified-features integration in the grammar coverage audit.

Verifies that features implemented via internal dispatch (not top-level
dispatch tables) are classified as `verified` rather than `true_gaps` when
their language has a verified_features registry.
"""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.frontends.go.verified_features import GO_VERIFIED_FEATURES
from interpreter.frontends.kotlin.verified_features import KOTLIN_VERIFIED_FEATURES
from interpreter.frontends.rust.verified_features import RUST_VERIFIED_FEATURES
from scripts.grammar_coverage_audit import audit_language


@pytest.mark.parametrize(
    "language,feature_label",
    [
        pytest.param(Language.GO, f.label, id=f"go/{f.label}")
        for f in GO_VERIFIED_FEATURES
    ]
    + [
        pytest.param(Language.KOTLIN, f.label, id=f"kotlin/{f.label}")
        for f in KOTLIN_VERIFIED_FEATURES
    ]
    + [
        pytest.param(Language.RUST, f.label, id=f"rust/{f.label}")
        for f in RUST_VERIFIED_FEATURES
    ],
)
def test_verified_feature_not_in_true_gaps(
    language: Language, feature_label: str
) -> None:
    """A verified feature label must not appear in true_gaps."""
    result = audit_language(language)
    assert feature_label not in result.true_gaps, (
        f"{language}/{feature_label} is in true_gaps — "
        "add it to the verified_features registry for this language"
    )


@pytest.mark.parametrize(
    "language,feature_label",
    [
        pytest.param(Language.GO, f.label, id=f"go/{f.label}")
        for f in GO_VERIFIED_FEATURES
    ]
    + [
        pytest.param(Language.KOTLIN, f.label, id=f"kotlin/{f.label}")
        for f in KOTLIN_VERIFIED_FEATURES
    ]
    + [
        pytest.param(Language.RUST, f.label, id=f"rust/{f.label}")
        for f in RUST_VERIFIED_FEATURES
    ],
)
def test_verified_feature_in_verified_list(
    language: Language, feature_label: str
) -> None:
    """A verified feature label must appear in the verified list."""
    result = audit_language(language)
    assert feature_label in result.verified, (
        f"{language}/{feature_label} is not in verified — "
        "check that the label matches the grammar node type string exactly"
    )
