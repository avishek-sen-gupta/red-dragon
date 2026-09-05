"""AbstractLocation — the alias relation, extracted from Definition.__eq__."""

from cobol_memory.abstract_location import AbstractLocation
from interpreter.register import Register
from interpreter.var_name import VarName
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_register_aliases_only_itself():
    a, b = Register("%0"), Register("%0")
    c = Register("%1")
    assert a.may_alias(b) and a.must_cover(b)
    assert not a.may_alias(c) and not a.must_cover(c)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_varname_does_not_alias_register_of_same_text():
    assert not VarName("x").may_alias(Register("x"))
    assert not Register("x").may_alias(VarName("x"))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_alias_key_buckets_by_identity_for_names():
    assert Register("%0").alias_key() == Register("%0").alias_key()
    assert Register("%0").alias_key() != Register("%1").alias_key()
    assert VarName("x").alias_key() != Register("x").alias_key()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_register_and_varname_satisfy_the_protocol():
    assert isinstance(Register("%0"), AbstractLocation)
    assert isinstance(VarName("x"), AbstractLocation)
