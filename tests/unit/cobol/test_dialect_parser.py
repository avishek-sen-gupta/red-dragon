import pytest

from interpreter.cobol.dialect_parser import DialectParser, NullDialectParser


def test_null_dialect_parser_never_applies():
    parser = NullDialectParser()
    assert parser.applies({"type": "ANYTHING"}) is False
    assert parser.applies({}) is False


def test_null_dialect_parser_parse_raises_if_ever_called():
    parser = NullDialectParser()
    with pytest.raises(AssertionError):
        parser.parse({"type": "ANYTHING"})


def test_null_dialect_parser_satisfies_protocol():
    assert isinstance(NullDialectParser(), DialectParser)


def test_conforming_class_satisfies_protocol():
    class _Conforming:
        def applies(self, data: dict) -> bool:
            return data.get("type") == "FAKE"

        def parse(self, data: dict):
            return data

    assert isinstance(_Conforming(), DialectParser)


def test_missing_parse_is_not_instance():
    class _MissingParse:
        def applies(self, data: dict) -> bool:
            return True

    assert not isinstance(_MissingParse(), DialectParser)
