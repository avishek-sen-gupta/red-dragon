"""The lowered IR maps each driver outcome to the FILE STATUS it reports."""

from interpreter.cobol.access_result import AccessCondition
from tests.covers import NotLanguageFeature, covers
from tests.unit.cobol.file_status_of import file_status_of


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
