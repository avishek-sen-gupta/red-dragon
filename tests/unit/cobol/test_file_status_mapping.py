"""The lowered IR maps each driver outcome to the FILE STATUS it reports."""

from interpreter.cobol.access_result import AccessCondition
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import NotLanguageFeature, covers
from tests.unit.cobol.file_status_of import file_status_of, file_status_of_outcome


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_condition_to_file_status():
    assert {c: file_status_of(c) for c in AccessCondition} == {
        AccessCondition.OK: "00",
        AccessCondition.DUPLICATES_FOLLOW: "02",
        AccessCondition.END_OF_FILE: "10",
        AccessCondition.DUPLICATE_KEY: "22",
        AccessCondition.NOT_FOUND: "23",
        AccessCondition.FILE_NOT_FOUND: "35",
        AccessCondition.NOT_OPEN: "47",
        AccessCondition.ATTRIBUTE_CONFLICT: "39",
        AccessCondition.BOUNDARY_VIOLATION: "44",
        AccessCondition.OPEN_MODE_NOT_SUPPORTED: "37",
        AccessCondition.WRITE_NOT_PERMITTED: "48",
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_symbolic_outcome_reports_a_symbolic_status():
    lookup = (
        "__list_get(['00', '02', '10', '23', '22', '35', '39', '44', '37', '47',"
        " '48'], sym_outcome)"
    )
    assert file_status_of_outcome(SymbolicValue(name="sym_outcome")) == SymbolicValue(
        name="sym_0", type_hint=lookup, constraints=[lookup]
    )
