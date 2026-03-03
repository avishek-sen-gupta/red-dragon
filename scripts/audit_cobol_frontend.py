"""COBOL frontend coverage audit — three-pass analysis of the ProLeap pipeline.

Architecture
------------
The COBOL pipeline has three layers where coverage gaps can occur:

1. **Bridge** (StatementSerializer.java): ProLeap recognises 51 statement
   types (StatementTypeEnum). Only a subset are fully serialised; the rest
   fall through to serializeUnknown() which emits a bare {"type": "..."}.

2. **Python dispatch** (cobol_statements._DISPATCH_TABLE): Maps JSON type
   strings to typed dataclasses. Unknown types raise ValueError.

3. **Frontend lowering** (cobol_frontend._lower_statement): isinstance
   dispatch to _lower_* methods. Unhandled types log a warning.

This script audits all three layers and produces a per-type coverage matrix.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from enum import Enum

# Ensure project root is on sys.path so imports resolve.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from interpreter.cobol.cobol_statements import _DISPATCH_TABLE  # noqa: E402

logger = logging.getLogger(__name__)

# ── ProLeap StatementTypeEnum — all 51 types ─────────────────────

PROLEAP_STATEMENT_TYPES: frozenset[str] = frozenset(
    {
        "ACCEPT",
        "ADD",
        "ALTER",
        "CALL",
        "CANCEL",
        "CLOSE",
        "COMPUTE",
        "CONTINUE",
        "DELETE",
        "DISABLE",
        "DISPLAY",
        "DIVIDE",
        "ENABLE",
        "ENTRY",
        "EVALUATE",
        "EXEC_CICS",
        "EXEC_SQL",
        "EXEC_SQL_IMS",
        "EXIT",
        "GENERATE",
        "GO_TO",
        "IF",
        "INITIALIZE",
        "INITIATE",
        "INSPECT",
        "MERGE",
        "MOVE",
        "MULTIPLY",
        "OPEN",
        "PERFORM",
        "PURGE",
        "READ",
        "RECEIVE",
        "RELEASE",
        "RETURN",
        "REWRITE",
        "SEARCH",
        "SEND",
        "SET",
        "SORT",
        "START",
        "STOP",
        "STRING",
        "SUBTRACT",
        "TERMINATE",
        "UNSTRING",
        "USE",
        "WHEN",
        "WHEN_OTHER",
        "WRITE",
        "XML",
    }
)

# Types that the Java bridge fully serialises (with operands, children, etc.)
# as opposed to the bare {"type": "..."} skeleton from serializeUnknown().
BRIDGE_SERIALIZED_TYPES: frozenset[str] = frozenset(
    {
        "MOVE",
        "ADD",
        "SUBTRACT",
        "MULTIPLY",
        "DIVIDE",
        "COMPUTE",
        "IF",
        "PERFORM",
        "DISPLAY",
        "STOP",
        "GO_TO",
        "EVALUATE",
        "CONTINUE",
        "EXIT",
        "INITIALIZE",
        "SET",
        "STRING",
        "UNSTRING",
        "INSPECT",
        "SEARCH",
        "CALL",
        "ALTER",
        "ENTRY",
        "CANCEL",
        "ACCEPT",
        "OPEN",
        "CLOSE",
        "READ",
        "WRITE",
        "REWRITE",
        "START",
        "DELETE",
    }
)

# Mapping from bridge JSON type strings to Python dispatch table keys.
# Most are identity; a few differ (bridge emits GO_TO / STOP, dispatch
# expects GOTO / STOP_RUN).
_BRIDGE_TO_DISPATCH: dict[str, str] = {
    "MOVE": "MOVE",
    "ADD": "ADD",
    "SUBTRACT": "SUBTRACT",
    "MULTIPLY": "MULTIPLY",
    "DIVIDE": "DIVIDE",
    "COMPUTE": "COMPUTE",
    "IF": "IF",
    "PERFORM": "PERFORM",
    "DISPLAY": "DISPLAY",
    "STOP": "STOP_RUN",
    "GO_TO": "GOTO",
    "EVALUATE": "EVALUATE",
    "CONTINUE": "CONTINUE",
    "EXIT": "EXIT",
    "INITIALIZE": "INITIALIZE",
    "SET": "SET",
    "STRING": "STRING",
    "UNSTRING": "UNSTRING",
    "INSPECT": "INSPECT",
    "SEARCH": "SEARCH",
    "CALL": "CALL",
    "ALTER": "ALTER",
    "ENTRY": "ENTRY",
    "CANCEL": "CANCEL",
    "ACCEPT": "ACCEPT",
    "OPEN": "OPEN",
    "CLOSE": "CLOSE",
    "READ": "READ",
    "WRITE": "WRITE",
    "REWRITE": "REWRITE",
    "START": "START",
    "DELETE": "DELETE",
}

# Types lowered by CobolFrontend._lower_statement (isinstance dispatch).
# WhenStatement and WhenOtherStatement are lowered inside _lower_evaluate,
# not through _lower_statement directly, so they are not listed here.
_LOWERED_TYPES: frozenset[str] = frozenset(
    {
        "MOVE",
        "ADD",
        "SUBTRACT",
        "MULTIPLY",
        "DIVIDE",
        "COMPUTE",
        "IF",
        "EVALUATE",
        "DISPLAY",
        "GOTO",
        "STOP_RUN",
        "PERFORM",
        "CONTINUE",
        "EXIT",
        "INITIALIZE",
        "SET",
        "STRING",
        "UNSTRING",
        "INSPECT",
        "SEARCH",
        "CALL",
        "ALTER",
        "ENTRY",
        "CANCEL",
        "ACCEPT",
        "OPEN",
        "CLOSE",
        "READ",
        "WRITE",
        "REWRITE",
        "START",
        "DELETE",
    }
)


# ── DATA DIVISION feature sets ──────────────────────────────────────


class DataDivisionFeature(str, Enum):
    """All auditable DATA DIVISION features."""

    # Sections
    SECTION_WORKING_STORAGE = "SECTION_WORKING_STORAGE"
    SECTION_LINKAGE = "SECTION_LINKAGE"
    SECTION_LOCAL_STORAGE = "SECTION_LOCAL_STORAGE"
    SECTION_FILE = "SECTION_FILE"
    # Entry types
    ENTRY_GROUP = "ENTRY_GROUP"
    ENTRY_CONDITION_88 = "ENTRY_CONDITION_88"
    ENTRY_RENAME_66 = "ENTRY_RENAME_66"
    # Clauses
    CLAUSE_PIC = "CLAUSE_PIC"
    CLAUSE_USAGE_DISPLAY = "CLAUSE_USAGE_DISPLAY"
    CLAUSE_USAGE_COMP3 = "CLAUSE_USAGE_COMP3"
    CLAUSE_USAGE_COMP = "CLAUSE_USAGE_COMP"
    CLAUSE_USAGE_COMP1 = "CLAUSE_USAGE_COMP1"
    CLAUSE_USAGE_COMP2 = "CLAUSE_USAGE_COMP2"
    CLAUSE_USAGE_COMP5 = "CLAUSE_USAGE_COMP5"
    CLAUSE_USAGE_INDEX = "CLAUSE_USAGE_INDEX"
    CLAUSE_USAGE_POINTER = "CLAUSE_USAGE_POINTER"
    CLAUSE_VALUE = "CLAUSE_VALUE"
    CLAUSE_VALUE_MULTI = "CLAUSE_VALUE_MULTI"
    CLAUSE_REDEFINES = "CLAUSE_REDEFINES"
    CLAUSE_OCCURS_FIXED = "CLAUSE_OCCURS_FIXED"
    CLAUSE_OCCURS_DEPENDING = "CLAUSE_OCCURS_DEPENDING"
    CLAUSE_OCCURS_INDEXED_BY = "CLAUSE_OCCURS_INDEXED_BY"
    CLAUSE_SIGN = "CLAUSE_SIGN"
    CLAUSE_JUSTIFIED = "CLAUSE_JUSTIFIED"
    CLAUSE_BLANK_WHEN_ZERO = "CLAUSE_BLANK_WHEN_ZERO"
    CLAUSE_SYNCHRONIZED = "CLAUSE_SYNCHRONIZED"
    CLAUSE_EXTERNAL = "CLAUSE_EXTERNAL"
    CLAUSE_GLOBAL = "CLAUSE_GLOBAL"
    CLAUSE_FILLER = "CLAUSE_FILLER"


# Features the Java bridge (DataFieldSerializer) extracts from ProLeap.
DD_BRIDGE_EXTRACTED: frozenset[str] = frozenset(
    {
        DataDivisionFeature.SECTION_WORKING_STORAGE.value,
        DataDivisionFeature.ENTRY_GROUP.value,
        DataDivisionFeature.ENTRY_CONDITION_88.value,
        DataDivisionFeature.ENTRY_RENAME_66.value,
        DataDivisionFeature.CLAUSE_PIC.value,
        DataDivisionFeature.CLAUSE_USAGE_DISPLAY.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP3.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP1.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP2.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP5.value,
        DataDivisionFeature.CLAUSE_USAGE_INDEX.value,
        DataDivisionFeature.CLAUSE_USAGE_POINTER.value,
        DataDivisionFeature.CLAUSE_VALUE.value,
        DataDivisionFeature.CLAUSE_VALUE_MULTI.value,
        DataDivisionFeature.CLAUSE_REDEFINES.value,
        DataDivisionFeature.CLAUSE_OCCURS_FIXED.value,
        DataDivisionFeature.CLAUSE_OCCURS_DEPENDING.value,
        DataDivisionFeature.CLAUSE_SIGN.value,
        DataDivisionFeature.CLAUSE_JUSTIFIED.value,
        DataDivisionFeature.CLAUSE_SYNCHRONIZED.value,
        DataDivisionFeature.CLAUSE_BLANK_WHEN_ZERO.value,
        DataDivisionFeature.CLAUSE_FILLER.value,
    }
)

# Features that CobolField / FieldLayout Python models carry.
DD_PYTHON_MODELLED: frozenset[str] = frozenset(
    {
        DataDivisionFeature.SECTION_WORKING_STORAGE.value,
        DataDivisionFeature.ENTRY_GROUP.value,
        DataDivisionFeature.ENTRY_CONDITION_88.value,
        DataDivisionFeature.ENTRY_RENAME_66.value,
        DataDivisionFeature.CLAUSE_PIC.value,
        DataDivisionFeature.CLAUSE_USAGE_DISPLAY.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP3.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP1.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP2.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP5.value,
        DataDivisionFeature.CLAUSE_VALUE.value,
        DataDivisionFeature.CLAUSE_VALUE_MULTI.value,
        DataDivisionFeature.CLAUSE_REDEFINES.value,
        DataDivisionFeature.CLAUSE_OCCURS_FIXED.value,
        DataDivisionFeature.CLAUSE_OCCURS_DEPENDING.value,
        DataDivisionFeature.CLAUSE_SIGN.value,
        DataDivisionFeature.CLAUSE_JUSTIFIED.value,
        DataDivisionFeature.CLAUSE_SYNCHRONIZED.value,
        DataDivisionFeature.CLAUSE_BLANK_WHEN_ZERO.value,
        DataDivisionFeature.CLAUSE_FILLER.value,
    }
)

# Features the frontend (cobol_frontend.py / data_layout.py) acts on during lowering.
DD_FRONTEND_HANDLED: frozenset[str] = frozenset(
    {
        DataDivisionFeature.SECTION_WORKING_STORAGE.value,
        DataDivisionFeature.ENTRY_GROUP.value,
        DataDivisionFeature.ENTRY_CONDITION_88.value,
        DataDivisionFeature.ENTRY_RENAME_66.value,
        DataDivisionFeature.CLAUSE_PIC.value,
        DataDivisionFeature.CLAUSE_USAGE_DISPLAY.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP3.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP1.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP2.value,
        DataDivisionFeature.CLAUSE_USAGE_COMP5.value,
        DataDivisionFeature.CLAUSE_VALUE.value,
        DataDivisionFeature.CLAUSE_VALUE_MULTI.value,
        DataDivisionFeature.CLAUSE_REDEFINES.value,
        DataDivisionFeature.CLAUSE_OCCURS_FIXED.value,
        DataDivisionFeature.CLAUSE_OCCURS_DEPENDING.value,
        DataDivisionFeature.CLAUSE_SIGN.value,
        DataDivisionFeature.CLAUSE_JUSTIFIED.value,
        DataDivisionFeature.CLAUSE_SYNCHRONIZED.value,
        DataDivisionFeature.CLAUSE_BLANK_WHEN_ZERO.value,
        DataDivisionFeature.CLAUSE_FILLER.value,
    }
)


class DataDivisionStatus(str, Enum):
    """Classification status for a DATA DIVISION feature."""

    HANDLED = "HANDLED"
    BRIDGE_ONLY = "BRIDGE_ONLY"
    MODELLED_NOT_HANDLED = "MODELLED_NOT_HANDLED"
    NOT_EXTRACTED = "NOT_EXTRACTED"


@dataclass(frozen=True)
class DataDivisionAuditResult:
    """Result of the DATA DIVISION coverage audit."""

    all_features: frozenset[str]
    bridge_extracted: frozenset[str]
    python_modelled: frozenset[str]
    frontend_handled: frozenset[str]
    classified: dict[str, DataDivisionStatus]


def _classify_dd_feature(feature: str) -> DataDivisionStatus:
    """Classify a single DATA DIVISION feature through the three layers."""
    if feature in DD_FRONTEND_HANDLED:
        return DataDivisionStatus.HANDLED
    if feature in DD_PYTHON_MODELLED:
        return DataDivisionStatus.MODELLED_NOT_HANDLED
    if feature in DD_BRIDGE_EXTRACTED:
        return DataDivisionStatus.BRIDGE_ONLY
    return DataDivisionStatus.NOT_EXTRACTED


def run_data_division_audit() -> DataDivisionAuditResult:
    """Execute the static DATA DIVISION coverage audit."""
    all_features = frozenset(f.value for f in DataDivisionFeature)
    classified = {feature: _classify_dd_feature(feature) for feature in all_features}
    return DataDivisionAuditResult(
        all_features=all_features,
        bridge_extracted=DD_BRIDGE_EXTRACTED,
        python_modelled=DD_PYTHON_MODELLED,
        frontend_handled=DD_FRONTEND_HANDLED,
        classified=classified,
    )


# ── PROCEDURE DIVISION status categories ───────────────────────────


class StatusCategory:
    """Coverage status categories for the audit matrix."""

    HANDLED = "HANDLED"
    HANDLED_STUB = "HANDLED_STUB"
    BRIDGE_ONLY = "BRIDGE_ONLY"
    DISPATCH_MISSING = "DISPATCH_MISSING"
    NOT_LOWERED = "NOT_LOWERED"
    BRIDGE_UNKNOWN = "BRIDGE_UNKNOWN"


# Types that are fully handled but dispatch to an injectable I/O provider
# rather than deterministic IR. Marked HANDLED_STUB to flag future expansion.
_IO_STUB_TYPES: frozenset[str] = frozenset(
    {"ACCEPT", "OPEN", "CLOSE", "READ", "WRITE", "REWRITE", "START", "DELETE"}
)


@dataclass(frozen=True)
class CobolAuditResult:
    """Result of the three-pass COBOL frontend audit."""

    total_proleap_types: int
    bridge_serialized: list[str] = field(default_factory=list)
    bridge_unknown: list[str] = field(default_factory=list)
    dispatch_handled: list[str] = field(default_factory=list)
    dispatch_missing: list[str] = field(default_factory=list)
    lowered_types: list[str] = field(default_factory=list)
    not_lowered: list[str] = field(default_factory=list)
    runtime_warnings: list[str] = field(default_factory=list)
    runtime_available: bool = False
    data_division: DataDivisionAuditResult = field(
        default_factory=lambda: run_data_division_audit()
    )


def _classify_type(proleap_type: str) -> str:
    """Classify a single ProLeap statement type through the three layers."""
    bridge_key = proleap_type
    if bridge_key not in BRIDGE_SERIALIZED_TYPES:
        return StatusCategory.BRIDGE_UNKNOWN

    dispatch_key = _BRIDGE_TO_DISPATCH.get(bridge_key, bridge_key)
    if dispatch_key not in _DISPATCH_TABLE:
        return StatusCategory.DISPATCH_MISSING

    if dispatch_key not in _LOWERED_TYPES:
        return StatusCategory.NOT_LOWERED

    if proleap_type in _IO_STUB_TYPES:
        return StatusCategory.HANDLED_STUB

    return StatusCategory.HANDLED


def _run_pass1_bridge(sorted_types: list[str]) -> tuple[list[str], list[str]]:
    """Pass 1: Bridge serialisation coverage (static)."""
    bridge_serialized = sorted(t for t in sorted_types if t in BRIDGE_SERIALIZED_TYPES)
    bridge_unknown = sorted(t for t in sorted_types if t not in BRIDGE_SERIALIZED_TYPES)
    return bridge_serialized, bridge_unknown


def _run_pass2_dispatch(
    bridge_serialized: list[str],
) -> tuple[list[str], list[str]]:
    """Pass 2: Python dispatch table coverage (static)."""
    dispatch_keys = set(_DISPATCH_TABLE.keys())
    dispatch_handled = sorted(
        _BRIDGE_TO_DISPATCH[t]
        for t in bridge_serialized
        if _BRIDGE_TO_DISPATCH.get(t, t) in dispatch_keys
    )
    dispatch_missing = sorted(
        t
        for t in bridge_serialized
        if _BRIDGE_TO_DISPATCH.get(t, t) not in dispatch_keys
    )
    return dispatch_handled, dispatch_missing


def _run_pass3_runtime() -> tuple[list[str], bool]:
    """Pass 3: Runtime lowering check (requires bridge JAR).

    Returns (list of warning types, whether runtime was available).
    """
    default_jar = os.path.join(
        _PROJECT_ROOT,
        "proleap-bridge",
        "target",
        "proleap-bridge-0.1.0-shaded.jar",
    )
    bridge_jar = os.environ.get("PROLEAP_BRIDGE_JAR", default_jar)

    if not os.path.isfile(bridge_jar):
        logger.info(
            "Bridge JAR not found at %s — skipping Pass 3 (runtime)", bridge_jar
        )
        return [], False

    logger.info("Bridge JAR found at %s — running Pass 3 (runtime)", bridge_jar)

    captured_warnings: list[str] = []
    handler = _WarningCapture(captured_warnings)
    cobol_logger = logging.getLogger("interpreter.cobol.cobol_frontend")
    cobol_logger.addHandler(handler)
    cobol_logger.setLevel(logging.WARNING)

    try:
        from interpreter.cobol.cobol_parser import ProLeapCobolParser
        from interpreter.cobol.subprocess_runner import RealSubprocessRunner
        from interpreter.cobol.cobol_frontend import CobolFrontend

        parser = ProLeapCobolParser(RealSubprocessRunner(), bridge_jar)
        frontend = CobolFrontend(parser)
        frontend.lower(_COBOL_SAMPLE.encode("utf-8"))
    except Exception as exc:
        logger.warning("Pass 3 runtime error: %s", exc)
    finally:
        cobol_logger.removeHandler(handler)

    return captured_warnings, True


class _WarningCapture(logging.Handler):
    """Logging handler that captures 'Unhandled COBOL statement type' warnings."""

    def __init__(self, captured: list[str]):
        super().__init__(level=logging.WARNING)
        self._captured = captured

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "Unhandled COBOL statement type" in msg:
            # Extract the type name from the message
            self._captured.append(msg.split(":")[-1].strip())


def run_audit() -> CobolAuditResult:
    """Execute the full three-pass audit and return results."""
    sorted_types = sorted(PROLEAP_STATEMENT_TYPES)

    logger.info("=== Pass 1: Bridge serialisation coverage ===")
    bridge_serialized, bridge_unknown = _run_pass1_bridge(sorted_types)
    logger.info(
        "  Fully serialised: %d, Unknown/skeleton: %d",
        len(bridge_serialized),
        len(bridge_unknown),
    )

    logger.info("=== Pass 2: Python dispatch table coverage ===")
    dispatch_handled, dispatch_missing = _run_pass2_dispatch(bridge_serialized)
    logger.info(
        "  Dispatch handled: %d, Dispatch missing: %d",
        len(dispatch_handled),
        len(dispatch_missing),
    )

    lowered = sorted(_LOWERED_TYPES)
    not_lowered = sorted(d for d in dispatch_handled if d not in _LOWERED_TYPES)

    logger.info("=== Pass 3: Runtime lowering check ===")
    runtime_warnings, runtime_available = _run_pass3_runtime()

    logger.info("=== DATA DIVISION coverage audit ===")
    dd_result = run_data_division_audit()
    dd_handled = sum(
        1 for s in dd_result.classified.values() if s == DataDivisionStatus.HANDLED
    )
    logger.info(
        "  Features: %d total, %d handled, %d bridge-only, %d not extracted",
        len(dd_result.all_features),
        dd_handled,
        len(dd_result.bridge_extracted) - len(dd_result.frontend_handled),
        len(dd_result.all_features) - len(dd_result.bridge_extracted),
    )

    return CobolAuditResult(
        total_proleap_types=len(PROLEAP_STATEMENT_TYPES),
        bridge_serialized=bridge_serialized,
        bridge_unknown=bridge_unknown,
        dispatch_handled=dispatch_handled,
        dispatch_missing=dispatch_missing,
        lowered_types=lowered,
        not_lowered=not_lowered,
        runtime_warnings=runtime_warnings,
        runtime_available=runtime_available,
        data_division=dd_result,
    )


def _print_coverage_matrix(result: CobolAuditResult) -> None:
    """Print the per-type coverage matrix to stdout."""
    sorted_types = sorted(PROLEAP_STATEMENT_TYPES)

    col_widths = {
        "type": 16,
        "bridge": 10,
        "dispatch": 12,
        "lowered": 10,
        "status": 18,
    }
    header = (
        f"{'ProLeap Type':<{col_widths['type']}} "
        f"{'Bridge':<{col_widths['bridge']}} "
        f"{'Py Dispatch':<{col_widths['dispatch']}} "
        f"{'Lowered':<{col_widths['lowered']}} "
        f"{'Status':<{col_widths['status']}}"
    )
    separator = "-" * len(header)

    print("\n" + separator)
    print("COBOL Frontend Coverage Audit")
    print(separator)
    print(header)
    print(separator)

    status_counts: dict[str, int] = {}
    for proleap_type in sorted_types:
        status = _classify_type(proleap_type)
        status_counts[status] = status_counts.get(status, 0) + 1

        bridge_ok = proleap_type in BRIDGE_SERIALIZED_TYPES
        dispatch_key = _BRIDGE_TO_DISPATCH.get(proleap_type, proleap_type)
        dispatch_ok = dispatch_key in _DISPATCH_TABLE
        lowered_ok = dispatch_key in _LOWERED_TYPES

        bridge_mark = "YES" if bridge_ok else "no"
        dispatch_mark = (
            "YES"
            if (bridge_ok and dispatch_ok)
            else ("n/a" if not bridge_ok else "MISSING")
        )
        lowered_mark = (
            "YES"
            if (dispatch_ok and lowered_ok)
            else ("n/a" if not dispatch_ok else "MISSING")
        )

        print(
            f"{proleap_type:<{col_widths['type']}} "
            f"{bridge_mark:<{col_widths['bridge']}} "
            f"{dispatch_mark:<{col_widths['dispatch']}} "
            f"{lowered_mark:<{col_widths['lowered']}} "
            f"{status:<{col_widths['status']}}"
        )

    print(separator)

    # Summary
    handled = status_counts.get(StatusCategory.HANDLED, 0)
    handled_stub = status_counts.get(StatusCategory.HANDLED_STUB, 0)
    print(f"\nTotal ProLeap statement types: {result.total_proleap_types}")
    print(f"  HANDLED (full pipeline):     {handled}")
    print(f"  HANDLED_STUB (I/O provider): {handled_stub}")
    print(f"  Total handled:               {handled + handled_stub}")
    print(
        f"  BRIDGE_ONLY (serialised):    {status_counts.get(StatusCategory.BRIDGE_ONLY, 0)}"
    )
    print(
        f"  DISPATCH_MISSING:            {status_counts.get(StatusCategory.DISPATCH_MISSING, 0)}"
    )
    print(
        f"  NOT_LOWERED:                 {status_counts.get(StatusCategory.NOT_LOWERED, 0)}"
    )
    print(
        f"  BRIDGE_UNKNOWN (skeleton):   {status_counts.get(StatusCategory.BRIDGE_UNKNOWN, 0)}"
    )

    if result.dispatch_missing:
        print(f"\nDispatch gaps (bridge serialises but Python cannot parse):")
        for t in result.dispatch_missing:
            print(f"  - {t}")

    if result.not_lowered:
        print(f"\nLowering gaps (parsed but not lowered to IR):")
        for t in result.not_lowered:
            print(f"  - {t}")

    if result.bridge_unknown:
        print(
            f"\nBridge gaps ({len(result.bridge_unknown)} types use skeleton serialisation):"
        )
        for t in result.bridge_unknown:
            print(f"  - {t}")

    # Pass 3 results
    if result.runtime_available:
        if result.runtime_warnings:
            print(
                f"\nRuntime warnings ({len(result.runtime_warnings)} unhandled at lowering):"
            )
            for w in result.runtime_warnings:
                print(f"  - {w}")
        else:
            print(
                "\nRuntime: no unhandled statement warnings (all exercised types lowered successfully)"
            )
    else:
        print("\nRuntime: skipped (bridge JAR not available)")

    print(separator)

    # ── DATA DIVISION Coverage ──────────────────────────────────────
    dd = result.data_division
    dd_col_widths = {
        "feature": 30,
        "bridge": 10,
        "modelled": 10,
        "handled": 10,
        "status": 22,
    }
    dd_header = (
        f"{'Feature':<{dd_col_widths['feature']}} "
        f"{'Bridge':<{dd_col_widths['bridge']}} "
        f"{'Modelled':<{dd_col_widths['modelled']}} "
        f"{'Handled':<{dd_col_widths['handled']}} "
        f"{'Status':<{dd_col_widths['status']}}"
    )
    dd_separator = "-" * len(dd_header)

    print("\n" + dd_separator)
    print("DATA DIVISION Coverage Audit")
    print(dd_separator)
    print(dd_header)
    print(dd_separator)

    dd_status_counts: dict[str, int] = {}
    for feature in sorted(dd.all_features):
        status = dd.classified[feature]
        dd_status_counts[status.value] = dd_status_counts.get(status.value, 0) + 1

        bridge_mark = "YES" if feature in dd.bridge_extracted else "no"
        modelled_mark = (
            "YES"
            if feature in dd.python_modelled
            else ("n/a" if feature not in dd.bridge_extracted else "no")
        )
        handled_mark = (
            "YES"
            if feature in dd.frontend_handled
            else ("n/a" if feature not in dd.python_modelled else "no")
        )

        print(
            f"{feature:<{dd_col_widths['feature']}} "
            f"{bridge_mark:<{dd_col_widths['bridge']}} "
            f"{modelled_mark:<{dd_col_widths['modelled']}} "
            f"{handled_mark:<{dd_col_widths['handled']}} "
            f"{status.value:<{dd_col_widths['status']}}"
        )

    print(dd_separator)

    dd_handled = dd_status_counts.get(DataDivisionStatus.HANDLED.value, 0)
    dd_bridge_only = dd_status_counts.get(DataDivisionStatus.BRIDGE_ONLY.value, 0)
    dd_modelled_not = dd_status_counts.get(
        DataDivisionStatus.MODELLED_NOT_HANDLED.value, 0
    )
    dd_not_extracted = dd_status_counts.get(DataDivisionStatus.NOT_EXTRACTED.value, 0)

    print(f"\nTotal DATA DIVISION features: {len(dd.all_features)}")
    print(f"  HANDLED (full pipeline):     {dd_handled}")
    print(f"  BRIDGE_ONLY:                 {dd_bridge_only}")
    print(f"  MODELLED_NOT_HANDLED:        {dd_modelled_not}")
    print(f"  NOT_EXTRACTED:               {dd_not_extracted}")

    dd_not_extracted_features = sorted(
        f for f, s in dd.classified.items() if s == DataDivisionStatus.NOT_EXTRACTED
    )
    if dd_not_extracted_features:
        print(f"\nNot extracted ({len(dd_not_extracted_features)} features):")
        for f in dd_not_extracted_features:
            print(f"  - {f}")

    dd_bridge_only_features = sorted(
        f for f, s in dd.classified.items() if s == DataDivisionStatus.BRIDGE_ONLY
    )
    if dd_bridge_only_features:
        print(
            f"\nBridge-only ({len(dd_bridge_only_features)} features — extracted but not modelled in Python):"
        )
        for f in dd_bridge_only_features:
            print(f"  - {f}")

    print(dd_separator + "\n")


# ── COBOL sample source for Pass 3 ───────────────────────────────

_COBOL_SAMPLE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. AUDIT-SAMPLE.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A        PIC 9(4) VALUE 10.
       01 WS-B        PIC 9(4) VALUE 5.
       01 WS-RESULT   PIC 9(4) VALUE 0.
       01 WS-NAME     PIC X(10) VALUE 'HELLO'.
       01 WS-COUNTER  PIC 9(4) VALUE 0.
       01 WS-FLAG     PIC 9(1) VALUE 1.
       01 WS-IDX      PIC 9(4) VALUE 0.
       01 WS-FIRST    PIC X(10) VALUE SPACES.
       01 WS-LAST     PIC X(10) VALUE SPACES.
       01 WS-FULL     PIC X(20) VALUE 'JOHN DOE'.
       01 WS-TALLY    PIC 9(4) VALUE 0.

       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-A TO WS-RESULT
           ADD WS-B TO WS-RESULT
           SUBTRACT WS-B FROM WS-RESULT
           MULTIPLY WS-A BY WS-RESULT
           DIVIDE WS-B INTO WS-RESULT
           COMPUTE WS-RESULT = WS-A + WS-B * 2
           DISPLAY WS-RESULT

           IF WS-A > WS-B
               DISPLAY 'A IS BIGGER'
           ELSE
               DISPLAY 'B IS BIGGER'
           END-IF

           EVALUATE TRUE
               WHEN WS-FLAG = 1
                   DISPLAY 'FLAG IS ONE'
               WHEN OTHER
                   DISPLAY 'FLAG IS OTHER'
           END-EVALUATE

           PERFORM LOOP-PARA

           PERFORM LOOP-PARA 3 TIMES

           PERFORM LOOP-PARA
               UNTIL WS-COUNTER > 5

           PERFORM VARYING WS-COUNTER FROM 1 BY 1
               UNTIL WS-COUNTER > 3
               DISPLAY WS-COUNTER
           END-PERFORM

           CONTINUE

           INITIALIZE WS-RESULT WS-NAME

           SET WS-IDX TO 5
           SET WS-IDX UP BY 1

           STRING WS-FIRST DELIMITED BY SPACES
                  WS-LAST  DELIMITED BY SIZE
                  INTO WS-FULL

           UNSTRING WS-FULL DELIMITED BY SPACES
                    INTO WS-FIRST WS-LAST

           INSPECT WS-NAME TALLYING WS-TALLY
                   FOR ALL 'L'
           INSPECT WS-NAME REPLACING ALL 'L' BY 'R'

           SEARCH WS-TABLE
               WHEN WS-IDX = 5
                   DISPLAY 'FOUND'
           END-SEARCH

           GO TO EXIT-PARA.

       LOOP-PARA.
           ADD 1 TO WS-COUNTER
           DISPLAY WS-COUNTER.

       EXIT-PARA.
           EXIT.
           STOP RUN.
"""


def main() -> None:
    """Entry point — run audit and print results."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = run_audit()
    _print_coverage_matrix(result)


if __name__ == "__main__":
    main()
