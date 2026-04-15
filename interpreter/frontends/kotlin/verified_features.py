# pyright: standard
"""Registry of Kotlin features that are fully implemented and verified by tests.

Each entry maps a feature label to a VerifiedFeature record documenting:
  - what the feature is
  - where in the frontend it is implemented
  - which test class(es) prove it works end-to-end

This module is consumed by:
  - scripts/grammar_coverage_audit.py  → "Verified features" section
  - tests/unit/test_kotlin_verified_features.py → parametrized coverage guard

Adding a feature here without a real test class will fail the enforcement
test immediately.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifiedFeature:
    """One implemented Kotlin feature with its coverage evidence."""

    label: str
    description: str
    implementation_note: str
    # Each entry is (test_module_dotted_path, TestClassName).
    test_refs: tuple[tuple[str, str], ...]


KOTLIN_VERIFIED_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="secondary_constructor",
        description="secondary constructor declarations with optional delegation",
        implementation_note=(
            "Lowered by lower_secondary_constructor in declarations.py; "
            "called from lower_class_def body walk, not in top-level dispatch table"
        ),
        test_refs=(
            ("tests.unit.test_kotlin_frontend", "TestKotlinSecondaryConstructor"),
            (
                "tests.integration.test_kotlin_frontend_execution",
                "TestKotlinSecondaryConstructorExecution",
            ),
        ),
    ),
    VerifiedFeature(
        label="constructor_delegation_call",
        description="this()/super() delegation calls within secondary constructors",
        implementation_note=(
            "Lowered by _emit_constructor_delegation in declarations.py; "
            "invoked from lower_secondary_constructor, not in top-level dispatch table"
        ),
        test_refs=(
            ("tests.unit.test_kotlin_frontend", "TestKotlinSecondaryConstructor"),
            (
                "tests.integration.test_kotlin_frontend_execution",
                "TestKotlinSecondaryConstructorExecution",
            ),
        ),
    ),
)
