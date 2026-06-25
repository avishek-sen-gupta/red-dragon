from interpreter.cobol.access_result import AccessCondition
from interpreter.cobol.real_file_provider import _file_status  # the mapping fn (Task 4)
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_condition_to_file_status():
    assert _file_status(AccessCondition.OK) == "00"
    assert _file_status(AccessCondition.END_OF_FILE) == "10"
    assert _file_status(AccessCondition.DUPLICATE_KEY) == "22"
    assert _file_status(AccessCondition.NOT_FOUND) == "23"
    assert _file_status(AccessCondition.FILE_NOT_FOUND) == "35"
    assert _file_status(AccessCondition.NOT_OPEN) == "47"
    assert _file_status(AccessCondition.WRITE_NOT_PERMITTED) == "48"
