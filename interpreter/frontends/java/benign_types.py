# pyright: standard
"""Registry of intentionally-unhandled Java grammar node types.

Each entry maps a tree-sitter node type string to a BenignType record that
documents WHY it is absent from the dispatch tables and WHICH test class(es)
prove the gap is intentional.

This module is the single source of truth consumed by:
  - JavaFrontend._build_constants()  → known_benign_types field
  - tests/unit/test_java_benign_types.py → parametrized coverage test
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BenignType:
    """One intentionally-unhandled node type with its coverage evidence."""

    node_type: str
    reason: str
    # Each entry is (test_module_dotted_path, TestClassName).
    test_refs: tuple[tuple[str, str], ...]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

JAVA_BENIGN_TYPES: tuple[BenignType, ...] = (
    # ── Primitive / void type keywords ───────────────────────────────────
    # Resolved via the text-based type map in JavaFrontend._build_type_map();
    # the keyword node is never dispatched — only its text is read.
    BenignType(
        node_type="boolean_type",
        reason="Resolved by text-based type map; node text read by parent lowerer",
        test_refs=(
            (
                "tests.integration.test_java_frontend_execution",
                "TestJavaBooleanTypeExecution",
            ),
        ),
    ),
    BenignType(
        node_type="integral_type",
        reason="Resolved by text-based type map; node text read by parent lowerer",
        test_refs=(("tests.unit.test_java_frontend", "TestJavaVariables"),),
    ),
    BenignType(
        node_type="floating_point_type",
        reason="Resolved by text-based type map; node text read by parent lowerer",
        test_refs=(("tests.unit.test_java_frontend", "TestJavaExpressions"),),
    ),
    BenignType(
        node_type="void_type",
        reason="Resolved by text-based type map; node text read by parent lowerer",
        test_refs=(("tests.unit.test_java_frontend", "TestJavaFunctions"),),
    ),
    # ── Compound type wrappers ────────────────────────────────────────────
    # Parent lowerers extract the inner type text directly; the wrapper node
    # itself is never dispatched.
    BenignType(
        node_type="generic_type",
        reason="Parent lowerer reads inner type text; wrapper not dispatched",
        test_refs=(("tests.unit.test_java_frontend", "TestJavaGenericTypeSeeding"),),
    ),
    BenignType(
        node_type="array_type",
        reason="Parent lowerer reads inner type text; wrapper not dispatched",
        test_refs=(("tests.unit.test_java_frontend", "TestJavaArrayCreation"),),
    ),
    BenignType(
        node_type="annotated_type",
        reason="Annotation wrapper stripped by parent; inner type text used directly",
        test_refs=(
            ("tests.unit.test_java_frontend", "TestJavaAnnotatedType"),
            (
                "tests.integration.test_java_frontend_execution",
                "TestJavaAnnotatedTypeExecution",
            ),
        ),
    ),
    BenignType(
        node_type="scoped_type_identifier",
        reason="Fully-qualified type name read as plain text by parent lowerer",
        test_refs=(
            (
                "tests.integration.test_java_frontend_execution",
                "TestJavaScopedTypeIdentifierExecution",
            ),
        ),
    ),
    # ── Class-body structural nodes ───────────────────────────────────────
    # Skipped via _CLASS_BODY_SKIP_TYPES in declarations.lower_class_def;
    # they carry no executable semantics.
    BenignType(
        node_type="modifiers",
        reason="Skipped by _CLASS_BODY_SKIP_TYPES; carries no executable semantics",
        test_refs=(("tests.unit.test_java_frontend", "TestJavaModifiersUnit"),),
    ),
    BenignType(
        node_type="marker_annotation",
        reason="Skipped by _CLASS_BODY_SKIP_TYPES; carries no executable semantics",
        test_refs=(
            ("tests.unit.test_java_frontend", "TestJavaMarkerAnnotation"),
            (
                "tests.integration.test_java_frontend_execution",
                "TestJavaMarkerAnnotationExecution",
            ),
        ),
    ),
    BenignType(
        node_type="annotation",
        reason="Skipped by _CLASS_BODY_SKIP_TYPES; carries no executable semantics",
        test_refs=(("tests.unit.test_java_frontend", "TestJavaAnnotation"),),
    ),
    # ── Parameter containers ──────────────────────────────────────────────
    # Lowered by lower_java_params() and _lower_lambda_params(); the container
    # node is iterated over, never dispatched.
    BenignType(
        node_type="formal_parameters",
        reason="Iterated by lower_java_params(); container node not dispatched",
        test_refs=(
            ("tests.unit.test_java_frontend", "TestJavaFormalParametersUnit"),
            (
                "tests.integration.test_java_frontend_execution",
                "TestJavaFormalParametersExecution",
            ),
        ),
    ),
    BenignType(
        node_type="inferred_parameters",
        reason="Iterated by _lower_lambda_params(); container node not dispatched",
        test_refs=(
            ("tests.unit.test_java_frontend", "TestJavaInferredParametersUnit"),
        ),
    ),
)

# Derived frozenset used by JavaFrontend._build_constants()
JAVA_KNOWN_BENIGN_NODE_TYPES: frozenset[str] = frozenset(
    b.node_type for b in JAVA_BENIGN_TYPES
)
