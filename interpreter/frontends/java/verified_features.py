# pyright: standard
"""Registry of Java features that are fully implemented and verified by tests.

Each entry maps a feature label to a VerifiedFeature record documenting:
  - what the feature is
  - where in the frontend it is implemented
  - which test class(es) prove it works end-to-end

This module is consumed by:
  - scripts/grammar_coverage_audit.py  → "Verified features" section
  - tests/unit/test_java_verified_features.py → parametrized coverage guard

Adding a feature here without a real test class will fail the enforcement
test immediately.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifiedFeature:
    """One implemented Java feature with its coverage evidence."""

    label: str
    description: str
    implementation_note: str
    # Each entry is (test_module_dotted_path, TestClassName).
    test_refs: tuple[tuple[str, str], ...]


JAVA_VERIFIED_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="error_handling_flow",
        description="try/catch/finally, checked exceptions",
        implementation_note=(
            "Lowered by java_cf.lower_try via TRY_STATEMENT and "
            "TRY_WITH_RESOURCES_STATEMENT in _build_stmt_dispatch"
        ),
        test_refs=(
            ("tests.unit.test_java_frontend", "TestNonTrivialJava"),
            ("tests.unit.test_java_frontend", "TestJavaSpecial"),
        ),
    ),
    VerifiedFeature(
        label="interface_dispatch",
        description="interface keyword, implements, virtual dispatch",
        implementation_note=(
            "Lowered by java_decl.lower_interface_decl via "
            "INTERFACE_DECLARATION in _build_stmt_dispatch"
        ),
        test_refs=(
            ("tests.unit.test_java_frontend", "TestJavaInterfaceLowering"),
            (
                "tests.integration.test_java_frontend_execution",
                "TestJavaMarkerAnnotationExecution",
            ),
        ),
    ),
    VerifiedFeature(
        label="static_methods",
        description="static keyword on class methods, static field access",
        implementation_note=(
            "Static modifier handled in lower_method_decl_stmt and "
            "lower_class_def; static initializer via lower_class_def body walk"
        ),
        test_refs=(
            ("tests.unit.test_java_frontend", "TestJavaStaticInitializer"),
            ("tests.integration.test_static_method_dispatch", "TestJavaStaticMethod"),
        ),
    ),
    VerifiedFeature(
        label="multi_module",
        description="class imports across files, static method cross-references",
        implementation_note=(
            "Multi-file linking via interpreter/project/ compiler + linker; "
            "IMPORT_DECLARATION is a no-op (metadata only)"
        ),
        test_refs=(
            (
                "tests.integration.project.test_java_multi_module",
                "TestJavaMultiModuleLinking",
            ),
            (
                "tests.integration.project.test_all_languages_execution",
                "TestJavaMultiFile",
            ),
        ),
    ),
    VerifiedFeature(
        label="sealed_record_patterns",
        description="sealed classes, record patterns, instanceof type patterns (Java 17+)",
        implementation_note=(
            "Lowered by lower_record_decl (RECORD_DECLARATION) and "
            "lower_instanceof (INSTANCEOF_EXPRESSION with pattern); "
            "switch type patterns via lower_java_switch"
        ),
        test_refs=(
            ("tests.unit.test_java_frontend", "TestJavaTypePattern"),
            ("tests.unit.test_java_frontend", "TestJavaRecordPatternInstanceof"),
            (
                "tests.integration.test_java_pattern_matching",
                "TestJavaInstanceofTypePattern",
            ),
            (
                "tests.integration.test_java_pattern_matching",
                "TestJavaSwitchTypePattern",
            ),
        ),
    ),
)
