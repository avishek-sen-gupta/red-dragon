# pyright: standard
"""Registry of COBOL features that are implemented and verified by tests.

Each entry maps a feature label to a VerifiedFeature record documenting:
  - what the feature is
  - which test class(es) prove it works

This module is consumed by:
  - tests/unit/test_cobol_verified_features.py → parametrized coverage guard

Adding a feature here without a real test class will fail the enforcement
test immediately.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerifiedFeature:
    """One implemented COBOL feature with its coverage evidence."""

    label: str
    description: str
    # Each entry is (test_module_dotted_path, TestClassName).
    test_refs: tuple[tuple[str, str], ...]


# ---------------------------------------------------------------------------
# Procedure Division — Arithmetic
# ---------------------------------------------------------------------------

_ARITHMETIC_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="ADD",
        description="ADD ... TO / ADD ... GIVING",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestProcedureDivisionLowering"),
            ("tests.integration.test_cobol_programs", "TestAddSubtract"),
            ("tests.integration.test_cobol_programs", "TestArithmeticGiving"),
            ("tests.integration.test_cobol_e2e_features", "TestAllArithmeticForms"),
        ),
    ),
    VerifiedFeature(
        label="SUBTRACT",
        description="SUBTRACT ... FROM / SUBTRACT ... GIVING",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestProcedureDivisionLowering"),
            ("tests.integration.test_cobol_programs", "TestAddSubtract"),
            ("tests.integration.test_cobol_programs", "TestArithmeticGiving"),
            ("tests.integration.test_cobol_e2e_features", "TestAllArithmeticForms"),
        ),
    ),
    VerifiedFeature(
        label="MULTIPLY",
        description="MULTIPLY ... BY",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.integration.test_cobol_programs", "TestMultiplyDivide"),
            ("tests.integration.test_cobol_e2e_features", "TestAllArithmeticForms"),
        ),
    ),
    VerifiedFeature(
        label="DIVIDE",
        description="DIVIDE ... INTO / DIVIDE ... BY ... GIVING",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.integration.test_cobol_programs", "TestMultiplyDivide"),
            ("tests.integration.test_cobol_e2e_features", "TestAllArithmeticForms"),
        ),
    ),
    VerifiedFeature(
        label="COMPUTE",
        description="COMPUTE with arithmetic expressions and precedence",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestComputeLowering"),
            ("tests.integration.test_cobol_programs", "TestComputeExpression"),
            ("tests.integration.test_cobol_e2e_features", "TestAllArithmeticForms"),
        ),
    ),
)

# ---------------------------------------------------------------------------
# Procedure Division — Control Flow
# ---------------------------------------------------------------------------

_CONTROL_FLOW_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="IF",
        description="IF / ELSE / END-IF conditional branching",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestProcedureDivisionLowering"),
            ("tests.unit.test_cobol_e2e", "TestIfElseExecution"),
            ("tests.integration.test_cobol_programs", "TestIfElseBranch"),
            ("tests.integration.test_cobol_e2e_features", "TestControlFlowComposition"),
        ),
    ),
    VerifiedFeature(
        label="EVALUATE",
        description="EVALUATE TRUE/identifier WHEN ... END-EVALUATE",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.integration.test_cobol_programs", "TestEvaluateWhen"),
            ("tests.integration.test_cobol_e2e_features", "TestControlFlowComposition"),
        ),
    ),
    VerifiedFeature(
        label="PERFORM",
        description="PERFORM TIMES/UNTIL/VARYING, inline and out-of-line, THRU",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestPerformSpecs"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestPerformLoopLowering"),
            ("tests.unit.test_cobol_frontend", "TestSectionPerform"),
            ("tests.unit.test_cobol_e2e", "TestPerformTimesExecution"),
            ("tests.unit.test_cobol_e2e", "TestPerformUntilExecution"),
            ("tests.unit.test_cobol_e2e", "TestPerformVaryingExecution"),
            ("tests.integration.test_cobol_programs", "TestPerformTimes"),
            ("tests.integration.test_cobol_programs", "TestPerformUntil"),
            ("tests.integration.test_cobol_programs", "TestPerformVarying"),
            ("tests.integration.test_cobol_programs", "TestNestedPerform"),
            (
                "tests.integration.test_cobol_e2e_features",
                "TestPerformAndParagraphs",
            ),
        ),
    ),
    VerifiedFeature(
        label="GO_TO",
        description="GO TO paragraph-name unconditional transfer",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestProcedureDivisionLowering"),
            ("tests.unit.test_cobol_e2e", "TestGotoInsidePerform"),
            ("tests.integration.test_cobol_programs", "TestGotoSkipsParagraph"),
            ("tests.integration.test_cobol_programs", "TestGotoExitsPerform"),
            ("tests.integration.test_cobol_e2e_features", "TestControlFlowComposition"),
        ),
    ),
    VerifiedFeature(
        label="STOP",
        description="STOP RUN program termination",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestProcedureDivisionLowering"),
        ),
    ),
    VerifiedFeature(
        label="CONTINUE",
        description="CONTINUE no-op placeholder",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestTier1Lowering"),
        ),
    ),
    VerifiedFeature(
        label="EXIT",
        description="EXIT paragraph/section terminator",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestTier1Lowering"),
        ),
    ),
    VerifiedFeature(
        label="ALTER",
        description="ALTER paragraph-name TO PROCEED TO paragraph-name",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.integration.test_cobol_programs", "TestAlterGoto"),
        ),
    ),
)

# ---------------------------------------------------------------------------
# Procedure Division — Data Manipulation
# ---------------------------------------------------------------------------

_DATA_MANIPULATION_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="MOVE",
        description="MOVE literal/field TO field(s)",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestProcedureDivisionLowering"),
            ("tests.unit.test_cobol_e2e", "TestNumericValueVerification"),
            ("tests.integration.test_cobol_programs", "TestMoveLiteral"),
            ("tests.integration.test_cobol_programs", "TestStringMove"),
        ),
    ),
    VerifiedFeature(
        label="INITIALIZE",
        description="INITIALIZE field(s) to default values",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestTier1Lowering"),
            ("tests.integration.test_cobol_programs", "TestInitialize"),
        ),
    ),
    VerifiedFeature(
        label="SET",
        description="SET field TO/UP BY/DOWN BY value",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestTier1Lowering"),
            ("tests.integration.test_cobol_programs", "TestSetStatement"),
        ),
    ),
    VerifiedFeature(
        label="DISPLAY",
        description="DISPLAY literal/field(s)",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestProcedureDivisionLowering"),
        ),
    ),
)

# ---------------------------------------------------------------------------
# Procedure Division — String / Table Operations
# ---------------------------------------------------------------------------

_STRING_TABLE_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="STRING",
        description="STRING ... DELIMITED BY ... INTO target",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestTier2Lowering"),
            ("tests.integration.test_cobol_programs", "TestStringStatement"),
            ("tests.integration.test_cobol_programs", "TestStringMove"),
            ("tests.integration.test_cobol_e2e_features", "TestStringOperations"),
        ),
    ),
    VerifiedFeature(
        label="UNSTRING",
        description="UNSTRING source DELIMITED BY ... INTO fields",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestTier2Lowering"),
            ("tests.integration.test_cobol_programs", "TestUnstringStatement"),
            ("tests.integration.test_cobol_e2e_features", "TestStringOperations"),
        ),
    ),
    VerifiedFeature(
        label="INSPECT",
        description="INSPECT TALLYING / INSPECT REPLACING",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestTier2Lowering"),
            ("tests.integration.test_cobol_programs", "TestInspectTallying"),
            ("tests.integration.test_cobol_programs", "TestInspectReplacing"),
            ("tests.integration.test_cobol_e2e_features", "TestStringOperations"),
        ),
    ),
    VerifiedFeature(
        label="SEARCH",
        description="SEARCH table with WHEN conditions and AT END",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestSearchLowering"),
            ("tests.integration.test_cobol_programs", "TestSearchStatement"),
        ),
    ),
)

# ---------------------------------------------------------------------------
# Procedure Division — Inter-Program Communication
# ---------------------------------------------------------------------------

_INTERPROGRAM_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="CALL",
        description="CALL subprogram USING / GIVING",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.integration.test_cobol_programs", "TestCallStatement"),
        ),
    ),
    VerifiedFeature(
        label="CANCEL",
        description="CANCEL subprogram-name",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.integration.test_cobol_programs", "TestCancelSmoke"),
        ),
    ),
    VerifiedFeature(
        label="ENTRY",
        description="ENTRY alternate entry point",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.integration.test_cobol_programs", "TestEntryPoint"),
        ),
    ),
)

# ---------------------------------------------------------------------------
# Procedure Division — I/O Stubs
# ---------------------------------------------------------------------------

_IO_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="ACCEPT",
        description="ACCEPT field FROM device (stubbed I/O)",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.unit.test_cobol_io_provider", "TestNullIOProvider"),
            ("tests.unit.test_cobol_io_provider", "TestStubIOProvider"),
            ("tests.unit.test_cobol_io_integration", "TestExecutorIOProviderDispatch"),
            ("tests.integration.test_cobol_programs", "TestAcceptStatement"),
        ),
    ),
    VerifiedFeature(
        label="OPEN",
        description="OPEN INPUT/OUTPUT/I-O/EXTEND file (stubbed I/O)",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.unit.test_cobol_io_provider", "TestNullIOProvider"),
            ("tests.unit.test_cobol_io_provider", "TestStubIOProvider"),
            ("tests.unit.test_cobol_io_integration", "TestExecutorIOProviderDispatch"),
            ("tests.integration.test_cobol_programs", "TestOpenCloseStatement"),
        ),
    ),
    VerifiedFeature(
        label="CLOSE",
        description="CLOSE file (stubbed I/O)",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.unit.test_cobol_io_provider", "TestNullIOProvider"),
            ("tests.unit.test_cobol_io_provider", "TestStubIOProvider"),
            ("tests.unit.test_cobol_io_integration", "TestExecutorIOProviderDispatch"),
            ("tests.integration.test_cobol_programs", "TestOpenCloseStatement"),
        ),
    ),
    VerifiedFeature(
        label="READ",
        description="READ file INTO field (stubbed I/O)",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.unit.test_cobol_io_provider", "TestNullIOProvider"),
            ("tests.unit.test_cobol_io_provider", "TestStubIOProvider"),
            ("tests.unit.test_cobol_io_integration", "TestExecutorIOProviderDispatch"),
            ("tests.integration.test_cobol_programs", "TestReadStatement"),
        ),
    ),
    VerifiedFeature(
        label="WRITE",
        description="WRITE record FROM field (stubbed I/O)",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.unit.test_cobol_io_provider", "TestNullIOProvider"),
            ("tests.unit.test_cobol_io_provider", "TestStubIOProvider"),
            ("tests.unit.test_cobol_io_integration", "TestExecutorIOProviderDispatch"),
            ("tests.integration.test_cobol_programs", "TestWriteStatement"),
        ),
    ),
    VerifiedFeature(
        label="REWRITE",
        description="REWRITE record FROM field (stubbed I/O)",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.unit.test_cobol_io_provider", "TestNullIOProvider"),
            ("tests.unit.test_cobol_io_provider", "TestStubIOProvider"),
            ("tests.integration.test_cobol_programs", "TestRewriteStatement"),
        ),
    ),
    VerifiedFeature(
        label="START",
        description="START file KEY condition (stubbed I/O)",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.unit.test_cobol_io_provider", "TestNullIOProvider"),
            ("tests.unit.test_cobol_io_provider", "TestStubIOProvider"),
            ("tests.integration.test_cobol_programs", "TestStartStatement"),
        ),
    ),
    VerifiedFeature(
        label="DELETE",
        description="DELETE file record (stubbed I/O)",
        test_refs=(
            ("tests.unit.test_cobol_statements", "TestParseStatementDispatch"),
            ("tests.unit.test_cobol_statements", "TestRoundTrip"),
            ("tests.unit.test_cobol_frontend", "TestCallAlterEntryCancelLowering"),
            ("tests.unit.test_cobol_io_provider", "TestNullIOProvider"),
            ("tests.unit.test_cobol_io_provider", "TestStubIOProvider"),
            ("tests.integration.test_cobol_programs", "TestDeleteStatement"),
        ),
    ),
)

# ---------------------------------------------------------------------------
# Data Division Features
# ---------------------------------------------------------------------------

_DATA_DIVISION_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="CLAUSE_PIC",
        description="PIC/PICTURE clause for field format definition",
        test_refs=(
            ("tests.unit.test_cobol_types", "TestCobolTypeDescriptor"),
            ("tests.unit.test_cobol_frontend", "TestDataDivisionLowering"),
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_VALUE",
        description="VALUE clause for initial field values",
        test_refs=(
            ("tests.unit.test_cobol_frontend", "TestDataDivisionLowering"),
            ("tests.unit.test_cobol_e2e", "TestNumericValueVerification"),
            ("tests.integration.test_cobol_programs", "TestInitialValues"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_VALUE_MULTI",
        description="VALUE clause with multiple discrete values (level-88)",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
            ("tests.integration.test_cobol_programs", "TestLevel88MixedValues"),
            ("tests.integration.test_cobol_e2e_features", "TestLevel88ConditionNames"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_OCCURS_FIXED",
        description="OCCURS n TIMES fixed-length table",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
            ("tests.integration.test_cobol_programs", "TestElementaryOccursMove"),
            ("tests.integration.test_cobol_programs", "TestOccursFieldSubscript"),
            ("tests.integration.test_cobol_programs", "TestOccursLoop"),
            ("tests.integration.test_cobol_e2e_features", "TestOccursWithSubscripts"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_OCCURS_DEPENDING",
        description="OCCURS ... DEPENDING ON variable-length table",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_REDEFINES",
        description="REDEFINES clause for overlapping storage",
        test_refs=(("tests.integration.test_cobol_programs", "TestRedefines"),),
    ),
    VerifiedFeature(
        label="CLAUSE_FILLER",
        description="FILLER unnamed placeholder fields",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
            ("tests.integration.test_cobol_programs", "TestFillerDisambiguation"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_SIGN",
        description="SIGN IS LEADING/TRAILING SEPARATE CHARACTER",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
            ("tests.integration.test_cobol_programs", "TestSignSeparate"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_JUSTIFIED",
        description="JUSTIFIED RIGHT clause",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
            ("tests.integration.test_cobol_programs", "TestJustifiedRight"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_SYNCHRONIZED",
        description="SYNCHRONIZED/SYNC clause for word-boundary alignment",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_BLANK_WHEN_ZERO",
        description="BLANK WHEN ZERO clause for numeric display fields",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
            ("tests.integration.test_cobol_programs", "TestBlankWhenZero"),
            (
                "tests.integration.test_cobol_e2e_features",
                "TestBlankWhenZeroComposition",
            ),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_USAGE_COMP",
        description="USAGE COMP/BINARY native binary storage",
        test_refs=(
            ("tests.unit.test_cobol_types", "TestCobolTypeDescriptor"),
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
            ("tests.integration.test_cobol_programs", "TestUsageComp"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_USAGE_COMP1",
        description="USAGE COMP-1 single-precision float",
        test_refs=(
            ("tests.unit.test_cobol_types", "TestCobolTypeDescriptor"),
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
            ("tests.integration.test_cobol_programs", "TestUsageComp1"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_USAGE_COMP2",
        description="USAGE COMP-2 double-precision float",
        test_refs=(
            ("tests.unit.test_cobol_types", "TestCobolTypeDescriptor"),
            ("tests.integration.test_cobol_programs", "TestUsageComp2"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_USAGE_COMP3",
        description="USAGE COMP-3 packed-decimal encoding",
        test_refs=(
            ("tests.unit.test_cobol_types", "TestCobolTypeDescriptor"),
            ("tests.integration.test_cobol_programs", "TestUsageComp3"),
        ),
    ),
    VerifiedFeature(
        label="CLAUSE_USAGE_COMP5",
        description="USAGE COMP-5 native binary (same as COMP)",
        test_refs=(("tests.unit.test_cobol_types", "TestCobolTypeDescriptor"),),
    ),
    VerifiedFeature(
        label="CLAUSE_USAGE_DISPLAY",
        description="USAGE DISPLAY default zoned-decimal storage",
        test_refs=(
            ("tests.unit.test_cobol_types", "TestCobolTypeDescriptor"),
            ("tests.integration.test_cobol_programs", "TestUsageDisplay"),
        ),
    ),
    VerifiedFeature(
        label="ENTRY_CONDITION_88",
        description="Level-88 condition names with VALUE/THRU",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
            ("tests.integration.test_cobol_programs", "TestLevel88ConditionName"),
            ("tests.integration.test_cobol_programs", "TestLevel88ThruRange"),
            ("tests.integration.test_cobol_programs", "TestLevel88MixedValues"),
            ("tests.integration.test_cobol_programs", "TestLevel88InEvaluate"),
            ("tests.integration.test_cobol_programs", "TestLevel88InPerformUntil"),
            ("tests.integration.test_cobol_e2e_features", "TestLevel88ConditionNames"),
        ),
    ),
    VerifiedFeature(
        label="ENTRY_GROUP",
        description="Group-level fields containing subordinate entries",
        test_refs=(
            ("tests.unit.test_cobol_frontend", "TestDataDivisionLowering"),
            ("tests.integration.test_cobol_programs", "TestRedefines"),
        ),
    ),
    VerifiedFeature(
        label="ENTRY_RENAME_66",
        description="Level-66 RENAMES clause for field aliasing",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
            ("tests.integration.test_cobol_programs", "TestRenameAlias"),
        ),
    ),
    VerifiedFeature(
        label="SECTION_WORKING_STORAGE",
        description="WORKING-STORAGE SECTION data area",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionClassify"),
            ("tests.unit.test_cobol_frontend", "TestDataDivisionLowering"),
        ),
    ),
)

# ---------------------------------------------------------------------------
# Cross-Cutting / Infrastructure
# ---------------------------------------------------------------------------

_INFRASTRUCTURE_FEATURES: tuple[VerifiedFeature, ...] = (
    VerifiedFeature(
        label="expression_parser",
        description="Tokenizer and precedence parser for COMPUTE expressions",
        test_refs=(
            ("tests.unit.test_cobol_expression", "TestTokenizer"),
            ("tests.unit.test_cobol_expression", "TestParserAtoms"),
            ("tests.unit.test_cobol_expression", "TestParserPrecedence"),
        ),
    ),
    VerifiedFeature(
        label="proleap_bridge",
        description="ProLeap Java subprocess bridge for COBOL parsing",
        test_refs=(("tests.unit.test_cobol_parser", "TestProLeapCobolParser"),),
    ),
    VerifiedFeature(
        label="io_provider",
        description="Injectable I/O provider (null + stub) for file operations",
        test_refs=(
            ("tests.unit.test_cobol_io_provider", "TestNullIOProvider"),
            ("tests.unit.test_cobol_io_provider", "TestStubIOProvider"),
            ("tests.unit.test_cobol_io_provider", "TestStubFile"),
            ("tests.unit.test_cobol_io_integration", "TestExecutorIOProviderDispatch"),
        ),
    ),
    VerifiedFeature(
        label="audit_infrastructure",
        description="Self-auditing coverage constants and classification",
        test_refs=(
            ("tests.unit.test_audit_cobol_frontend", "TestProLeapConstants"),
            ("tests.unit.test_audit_cobol_frontend", "TestClassifyType"),
            ("tests.unit.test_audit_cobol_frontend", "TestPass1Bridge"),
            ("tests.unit.test_audit_cobol_frontend", "TestPass2Dispatch"),
            ("tests.unit.test_audit_cobol_frontend", "TestLoweredTypes"),
            ("tests.unit.test_audit_cobol_frontend", "TestRunAudit"),
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionConstants"),
            ("tests.unit.test_audit_cobol_frontend", "TestDataDivisionAudit"),
        ),
    ),
    VerifiedFeature(
        label="multi_file_imports",
        description="COPY/CALL extraction and cross-module resolution",
        test_refs=(
            ("tests.unit.project.test_cobol_imports", "TestCobolCopyExtraction"),
            ("tests.unit.project.test_cobol_imports", "TestCobolCallExtraction"),
            ("tests.unit.project.test_cobol_imports", "TestCobolResolver"),
        ),
    ),
    VerifiedFeature(
        label="bare_statements",
        description="Statements outside paragraphs (division/section level)",
        test_refs=(
            ("tests.unit.test_cobol_frontend", "TestBareStatements"),
            ("tests.integration.test_cobol_programs", "TestBareStatements"),
        ),
    ),
    VerifiedFeature(
        label="data_layout",
        description="Field offset/length computation and byte region allocation",
        test_refs=(
            ("tests.unit.test_cobol_frontend", "TestDataLayout"),
            ("tests.integration.test_cobol_programs", "TestDataLayout"),
        ),
    ),
    VerifiedFeature(
        label="numeric_execution",
        description="End-to-end numeric value encoding, arithmetic, and accumulation",
        test_refs=(
            ("tests.unit.test_cobol_e2e", "TestNumericValueVerification"),
            ("tests.unit.test_cobol_e2e", "TestNestedPerformNumericValues"),
            ("tests.unit.test_cobol_e2e", "TestSectionFallThrough"),
        ),
    ),
    VerifiedFeature(
        label="frontend_idempotency",
        description="Lowering the same source twice produces identical IR",
        test_refs=(("tests.unit.test_cobol_e2e", "TestCobolFrontendIdempotency"),),
    ),
)

# ---------------------------------------------------------------------------
# Combined registry
# ---------------------------------------------------------------------------

COBOL_VERIFIED_FEATURES: tuple[VerifiedFeature, ...] = (
    *_ARITHMETIC_FEATURES,
    *_CONTROL_FLOW_FEATURES,
    *_DATA_MANIPULATION_FEATURES,
    *_STRING_TABLE_FEATURES,
    *_INTERPROGRAM_FEATURES,
    *_IO_FEATURES,
    *_DATA_DIVISION_FEATURES,
    *_INFRASTRUCTURE_FEATURES,
)
