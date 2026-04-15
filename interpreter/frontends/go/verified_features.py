# pyright: standard
"""Registry of Go features that are fully implemented and verified by tests.

Each entry maps a feature label to a VerifiedFeature record documenting:
  - what the feature is
  - where in the frontend it is implemented
  - which test class(es) prove it works end-to-end

This module is consumed by:
  - scripts/grammar_coverage_audit.py  → "Verified features" section
  - tests/unit/test_go_verified_features.py → parametrized coverage guard

Adding a feature here without a real test class will fail the enforcement
test immediately.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifiedFeature:
    """One implemented Go feature with its coverage evidence."""

    label: str
    description: str
    implementation_note: str
    # Each entry is (test_module_dotted_path, TestClassName).
    test_refs: tuple[tuple[str, str], ...]


GO_VERIFIED_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="iota",
        description="iota identifier in const blocks, with auto-increment counter",
        implementation_note=(
            "Lowered by lower_go_iota in expressions.py; "
            "iota node handled inline in lower_const_spec with a running counter, "
            "not registered in the top-level dispatch table"
        ),
        test_refs=(
            ("tests.unit.test_go_frontend", "TestGoIota"),
            ("tests.integration.test_go_frontend_execution", "TestGoIotaExecution"),
        ),
    ),
    VerifiedFeature(
        label="generic_type",
        description="Go 1.18+ generic type references (e.g. Foo[int])",
        implementation_note=(
            "Lowered by lower_generic_type in expressions.py; "
            "generic_type nodes appear in composite literals and var declarations, "
            "handled via _parse_go_type dispatch"
        ),
        test_refs=(("tests.unit.test_go_frontend", "TestGoGenericType"),),
    ),
    VerifiedFeature(
        label="map_type",
        description="map[K]V type expressions desugared to Map[K, V] constructor",
        implementation_note=(
            "Handled inline in _parse_go_type in expressions.py (line ~68); "
            "map_type node matched by string comparison, not in top-level dispatch table"
        ),
        test_refs=(("tests.unit.test_go_frontend", "TestGoMakeDesugaring"),),
    ),
)
