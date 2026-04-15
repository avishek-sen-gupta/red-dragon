# pyright: standard
"""Registry of Rust features that are fully implemented and verified by tests.

Each entry maps a feature label to a VerifiedFeature record documenting:
  - what the feature is
  - where in the frontend it is implemented
  - which test class(es) prove it works end-to-end

This module is consumed by:
  - scripts/grammar_coverage_audit.py  → "Verified features" section
  - tests/unit/test_rust_verified_features.py → parametrized coverage guard

Adding a feature here without a real test class will fail the enforcement
test immediately.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifiedFeature:
    """One implemented Rust feature with its coverage evidence."""

    label: str
    description: str
    implementation_note: str
    # Each entry is (test_module_dotted_path, TestClassName).
    test_refs: tuple[tuple[str, str], ...]


RUST_VERIFIED_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="reference_pattern",
        description="&val dereference patterns in match arms and if-let",
        implementation_note=(
            "Lowered in patterns.py via parse_rust_pattern internal dispatch; "
            "reference_pattern emits LOAD_DEREF to dereference the scrutinee before binding"
        ),
        test_refs=(
            (
                "tests.integration.test_rust_pattern_matching",
                "TestRustReferencePattern",
            ),
        ),
    ),
    VerifiedFeature(
        label="slice_pattern",
        description="[head, tail @ ..] slice patterns in match arms",
        implementation_note=(
            "Lowered by _parse_slice_pattern in patterns.py; "
            "called from parse_rust_pattern internal dispatch, "
            "not registered in top-level frontend dispatch table"
        ),
        test_refs=(
            (
                "tests.integration.test_rust_pattern_matching",
                "TestRustSlicePattern",
            ),
        ),
    ),
    VerifiedFeature(
        label="let_chain",
        description="if let cond1 && let cond2 chained let bindings (Rust 2024)",
        implementation_note=(
            "Lowered by _lower_if_let_chain_expr in expressions.py; "
            "let_chain node type matched in lower_if_expression before standard dispatch"
        ),
        test_refs=(
            (
                "tests.integration.test_rust_pattern_matching",
                "TestRustLetChain",
            ),
        ),
    ),
)
