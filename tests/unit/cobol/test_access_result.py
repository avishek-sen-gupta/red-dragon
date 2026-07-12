from interpreter.cobol.access_result import AccessCondition, AccessResult
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_access_result_holds_condition_and_bytes():
    r = AccessResult(condition=AccessCondition.OK, data=b"ABC")
    assert r.condition is AccessCondition.OK
    assert r.data == b"ABC"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_access_result_data_defaults_none():
    r = AccessResult(condition=AccessCondition.END_OF_FILE)
    assert r.data is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_conditions_present():
    names = {c.name for c in AccessCondition}
    assert names == {
        "OK",
        "END_OF_FILE",
        "NOT_FOUND",
        "DUPLICATE_KEY",
        "FILE_NOT_FOUND",
        "NOT_OPEN",
        "WRITE_NOT_PERMITTED",
    }
