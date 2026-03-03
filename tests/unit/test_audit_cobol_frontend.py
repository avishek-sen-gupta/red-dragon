"""Unit tests for the COBOL frontend audit script."""

from __future__ import annotations

import pytest

from scripts.audit_cobol_frontend import (
    BRIDGE_SERIALIZED_TYPES,
    DD_BRIDGE_EXTRACTED,
    DD_FRONTEND_HANDLED,
    DD_PYTHON_MODELLED,
    CobolAuditResult,
    DataDivisionAuditResult,
    DataDivisionFeature,
    DataDivisionStatus,
    PROLEAP_STATEMENT_TYPES,
    StatusCategory,
    _BRIDGE_TO_DISPATCH,
    _LOWERED_TYPES,
    _classify_dd_feature,
    _classify_type,
    _run_pass1_bridge,
    _run_pass2_dispatch,
    run_audit,
    run_data_division_audit,
)
from interpreter.cobol.cobol_statements import _DISPATCH_TABLE


class TestProLeapConstants:
    """Verify the hard-coded ProLeap type set is consistent."""

    def test_proleap_has_51_types(self):
        assert len(PROLEAP_STATEMENT_TYPES) == 51

    def test_bridge_serialized_subset_of_proleap(self):
        assert BRIDGE_SERIALIZED_TYPES.issubset(PROLEAP_STATEMENT_TYPES)

    def test_bridge_to_dispatch_covers_all_serialized(self):
        assert set(_BRIDGE_TO_DISPATCH.keys()) == set(BRIDGE_SERIALIZED_TYPES)


class TestClassifyType:
    """Test the per-type classification logic."""

    def test_handled_type(self):
        assert _classify_type("MOVE") == StatusCategory.HANDLED
        assert _classify_type("ADD") == StatusCategory.HANDLED
        assert _classify_type("IF") == StatusCategory.HANDLED

    def test_bridge_unknown_type(self):
        assert _classify_type("SORT") == StatusCategory.BRIDGE_UNKNOWN
        assert _classify_type("MERGE") == StatusCategory.BRIDGE_UNKNOWN

    def test_io_types_handled_stub(self):
        assert _classify_type("ACCEPT") == StatusCategory.HANDLED_STUB
        assert _classify_type("READ") == StatusCategory.HANDLED_STUB
        assert _classify_type("WRITE") == StatusCategory.HANDLED_STUB
        assert _classify_type("OPEN") == StatusCategory.HANDLED_STUB
        assert _classify_type("CLOSE") == StatusCategory.HANDLED_STUB
        assert _classify_type("REWRITE") == StatusCategory.HANDLED_STUB
        assert _classify_type("START") == StatusCategory.HANDLED_STUB
        assert _classify_type("DELETE") == StatusCategory.HANDLED_STUB

    def test_call_is_handled(self):
        assert _classify_type("CALL") == StatusCategory.HANDLED

    def test_compute_is_handled(self):
        assert _classify_type("COMPUTE") == StatusCategory.HANDLED

    def test_all_proleap_types_classifiable(self):
        valid_statuses = {
            StatusCategory.HANDLED,
            StatusCategory.HANDLED_STUB,
            StatusCategory.BRIDGE_ONLY,
            StatusCategory.BRIDGE_UNKNOWN,
            StatusCategory.DISPATCH_MISSING,
            StatusCategory.NOT_LOWERED,
        }
        for t in PROLEAP_STATEMENT_TYPES:
            assert _classify_type(t) in valid_statuses, f"Unclassifiable type: {t}"


class TestPass1Bridge:
    """Test bridge serialisation pass."""

    def test_pass1_partitions_all_types(self):
        sorted_types = sorted(PROLEAP_STATEMENT_TYPES)
        serialized, unknown = _run_pass1_bridge(sorted_types)
        assert set(serialized) | set(unknown) == PROLEAP_STATEMENT_TYPES
        assert set(serialized) & set(unknown) == set()

    def test_pass1_serialized_count(self):
        sorted_types = sorted(PROLEAP_STATEMENT_TYPES)
        serialized, unknown = _run_pass1_bridge(sorted_types)
        assert len(serialized) == len(BRIDGE_SERIALIZED_TYPES)
        assert len(unknown) == len(PROLEAP_STATEMENT_TYPES) - len(
            BRIDGE_SERIALIZED_TYPES
        )


class TestPass2Dispatch:
    """Test Python dispatch table pass."""

    def test_pass2_compute_is_handled(self):
        bridge_serialized = sorted(BRIDGE_SERIALIZED_TYPES)
        handled, missing = _run_pass2_dispatch(bridge_serialized)
        assert "COMPUTE" in handled
        assert "COMPUTE" not in missing

    def test_pass2_handled_types_exist_in_dispatch_table(self):
        bridge_serialized = sorted(BRIDGE_SERIALIZED_TYPES)
        handled, _ = _run_pass2_dispatch(bridge_serialized)
        dispatch_keys = set(_DISPATCH_TABLE.keys())
        for t in handled:
            assert t in dispatch_keys, f"{t} not in dispatch table"

    def test_pass2_handled_plus_missing_equals_bridge_serialized(self):
        bridge_serialized = sorted(BRIDGE_SERIALIZED_TYPES)
        handled, missing = _run_pass2_dispatch(bridge_serialized)
        # handled uses dispatch keys, missing uses bridge keys — count should match
        assert len(handled) + len(missing) == len(BRIDGE_SERIALIZED_TYPES)


class TestLoweredTypes:
    """Test lowered type consistency."""

    def test_lowered_types_subset_of_dispatch(self):
        dispatch_keys = set(_DISPATCH_TABLE.keys())
        assert _LOWERED_TYPES.issubset(dispatch_keys)

    def test_when_types_not_in_lowered(self):
        # WHEN/WHEN_OTHER are lowered inside _lower_evaluate, not _lower_statement
        assert "WHEN" not in _LOWERED_TYPES
        assert "WHEN_OTHER" not in _LOWERED_TYPES


class TestRunAudit:
    """Integration-level test of the full audit (Pass 1+2, no JAR)."""

    def test_run_audit_returns_result(self):
        result = run_audit()
        assert isinstance(result, CobolAuditResult)
        assert result.total_proleap_types == 51
        assert len(result.bridge_serialized) == len(BRIDGE_SERIALIZED_TYPES)
        assert len(result.bridge_unknown) == len(PROLEAP_STATEMENT_TYPES) - len(
            BRIDGE_SERIALIZED_TYPES
        )

    def test_run_audit_no_dispatch_missing(self):
        result = run_audit()
        assert len(result.dispatch_missing) == 0

    def test_run_audit_includes_data_division(self):
        result = run_audit()
        assert result.data_division is not None
        assert isinstance(result.data_division, DataDivisionAuditResult)


# ── DATA DIVISION audit tests ──────────────────────────────────────


class TestDataDivisionConstants:
    """Verify DATA DIVISION static sets are consistent with the enum."""

    def test_all_enum_members_accounted_for(self):
        all_features = frozenset(f.value for f in DataDivisionFeature)
        classified = (
            DD_BRIDGE_EXTRACTED
            | DD_PYTHON_MODELLED
            | DD_FRONTEND_HANDLED
            | (all_features - DD_BRIDGE_EXTRACTED)
        )
        assert classified == all_features

    def test_bridge_extracted_subset_of_all(self):
        all_features = frozenset(f.value for f in DataDivisionFeature)
        assert DD_BRIDGE_EXTRACTED.issubset(all_features)

    def test_python_modelled_subset_of_bridge_extracted(self):
        assert DD_PYTHON_MODELLED.issubset(DD_BRIDGE_EXTRACTED)

    def test_frontend_handled_subset_of_python_modelled(self):
        assert DD_FRONTEND_HANDLED.issubset(DD_PYTHON_MODELLED)

    def test_no_empty_sets(self):
        assert len(DD_BRIDGE_EXTRACTED) > 0
        assert len(DD_PYTHON_MODELLED) > 0
        assert len(DD_FRONTEND_HANDLED) > 0


class TestDataDivisionClassify:
    """Spot-check classification of specific DATA DIVISION features."""

    def test_pic_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.CLAUSE_PIC.value)
            == DataDivisionStatus.HANDLED
        )

    def test_occurs_fixed_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.CLAUSE_OCCURS_FIXED.value)
            == DataDivisionStatus.HANDLED
        )

    def test_working_storage_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.SECTION_WORKING_STORAGE.value)
            == DataDivisionStatus.HANDLED
        )

    def test_comp_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.CLAUSE_USAGE_COMP.value)
            == DataDivisionStatus.HANDLED
        )

    def test_comp1_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.CLAUSE_USAGE_COMP1.value)
            == DataDivisionStatus.HANDLED
        )

    def test_sign_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.CLAUSE_SIGN.value)
            == DataDivisionStatus.HANDLED
        )

    def test_justified_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.CLAUSE_JUSTIFIED.value)
            == DataDivisionStatus.HANDLED
        )

    def test_synchronized_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.CLAUSE_SYNCHRONIZED.value)
            == DataDivisionStatus.HANDLED
        )

    def test_occurs_depending_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.CLAUSE_OCCURS_DEPENDING.value)
            == DataDivisionStatus.HANDLED
        )

    def test_rename_66_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.ENTRY_RENAME_66.value)
            == DataDivisionStatus.HANDLED
        )

    def test_linkage_is_not_extracted(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.SECTION_LINKAGE.value)
            == DataDivisionStatus.NOT_EXTRACTED
        )

    def test_condition_88_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.ENTRY_CONDITION_88.value)
            == DataDivisionStatus.HANDLED
        )

    def test_filler_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.CLAUSE_FILLER.value)
            == DataDivisionStatus.HANDLED
        )

    def test_value_multi_is_handled(self):
        assert (
            _classify_dd_feature(DataDivisionFeature.CLAUSE_VALUE_MULTI.value)
            == DataDivisionStatus.HANDLED
        )


class TestDataDivisionAudit:
    """Test run_data_division_audit returns correct structure and counts."""

    def test_returns_audit_result(self):
        result = run_data_division_audit()
        assert isinstance(result, DataDivisionAuditResult)

    def test_all_features_classified(self):
        result = run_data_division_audit()
        all_features = frozenset(f.value for f in DataDivisionFeature)
        assert frozenset(result.classified.keys()) == all_features

    def test_counts_match_sets(self):
        result = run_data_division_audit()
        assert result.bridge_extracted == DD_BRIDGE_EXTRACTED
        assert result.python_modelled == DD_PYTHON_MODELLED
        assert result.frontend_handled == DD_FRONTEND_HANDLED

    def test_every_feature_has_valid_status(self):
        result = run_data_division_audit()
        valid_statuses = {
            DataDivisionStatus.HANDLED,
            DataDivisionStatus.BRIDGE_ONLY,
            DataDivisionStatus.MODELLED_NOT_HANDLED,
            DataDivisionStatus.NOT_EXTRACTED,
        }
        for feature, status in result.classified.items():
            assert status in valid_statuses, f"Invalid status for {feature}: {status}"

    def test_handled_count(self):
        result = run_data_division_audit()
        handled_count = sum(
            1 for s in result.classified.values() if s == DataDivisionStatus.HANDLED
        )
        assert handled_count == len(DD_FRONTEND_HANDLED)
