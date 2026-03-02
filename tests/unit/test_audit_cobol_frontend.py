"""Unit tests for the COBOL frontend audit script."""

from __future__ import annotations

import pytest

from scripts.audit_cobol_frontend import (
    BRIDGE_SERIALIZED_TYPES,
    PROLEAP_STATEMENT_TYPES,
    CobolAuditResult,
    StatusCategory,
    _BRIDGE_TO_DISPATCH,
    _LOWERED_TYPES,
    _classify_type,
    _run_pass1_bridge,
    _run_pass2_dispatch,
    run_audit,
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
        assert _classify_type("ACCEPT") == StatusCategory.BRIDGE_UNKNOWN
        assert _classify_type("READ") == StatusCategory.BRIDGE_UNKNOWN

    def test_call_is_handled(self):
        assert _classify_type("CALL") == StatusCategory.HANDLED

    def test_compute_is_handled(self):
        assert _classify_type("COMPUTE") == StatusCategory.HANDLED

    def test_all_proleap_types_classifiable(self):
        valid_statuses = {
            StatusCategory.HANDLED,
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
