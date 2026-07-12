# pyright: standard
from interpreter.constants import FoundationTypeName
from interpreter.types.type_expr import NULL, scalar
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_null_foundation_name_exists():
    assert str(FoundationTypeName.NULL) == "Null"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_null_scalar_is_canonical():
    assert NULL == scalar(FoundationTypeName.NULL)
