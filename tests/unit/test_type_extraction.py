"""Unit tests for interpreter.frontends.type_extraction — normalize_type_hint."""

from interpreter.constants import Language
from interpreter.frontends.type_extraction import normalize_type_hint


class TestNormalizeTypeHintJava:
    def test_int(self):
        assert normalize_type_hint("int", Language.JAVA) == "Int"

    def test_double(self):
        assert normalize_type_hint("double", Language.JAVA) == "Float"

    def test_string(self):
        assert normalize_type_hint("String", Language.JAVA) == "String"

    def test_boolean(self):
        assert normalize_type_hint("boolean", Language.JAVA) == "Bool"

    def test_unknown_class_passthrough(self):
        assert normalize_type_hint("UnknownClass", Language.JAVA) == "UnknownClass"

    def test_long(self):
        assert normalize_type_hint("long", Language.JAVA) == "Int"

    def test_float(self):
        assert normalize_type_hint("float", Language.JAVA) == "Float"

    def test_void(self):
        assert normalize_type_hint("void", Language.JAVA) == "Any"


class TestNormalizeTypeHintGo:
    def test_int64(self):
        assert normalize_type_hint("int64", Language.GO) == "Int"

    def test_float32(self):
        assert normalize_type_hint("float32", Language.GO) == "Float"

    def test_string(self):
        assert normalize_type_hint("string", Language.GO) == "String"

    def test_bool(self):
        assert normalize_type_hint("bool", Language.GO) == "Bool"

    def test_int(self):
        assert normalize_type_hint("int", Language.GO) == "Int"


class TestNormalizeTypeHintRust:
    def test_i32(self):
        assert normalize_type_hint("i32", Language.RUST) == "Int"

    def test_f64(self):
        assert normalize_type_hint("f64", Language.RUST) == "Float"

    def test_bool(self):
        assert normalize_type_hint("bool", Language.RUST) == "Bool"

    def test_string(self):
        assert normalize_type_hint("String", Language.RUST) == "String"

    def test_str(self):
        assert normalize_type_hint("str", Language.RUST) == "String"


class TestNormalizeTypeHintC:
    def test_int(self):
        assert normalize_type_hint("int", Language.C) == "Int"

    def test_bool(self):
        assert normalize_type_hint("bool", Language.C) == "Bool"

    def test_float(self):
        assert normalize_type_hint("float", Language.C) == "Float"

    def test_double(self):
        assert normalize_type_hint("double", Language.C) == "Float"


class TestNormalizeTypeHintCpp:
    def test_int(self):
        assert normalize_type_hint("int", Language.CPP) == "Int"

    def test_bool(self):
        assert normalize_type_hint("bool", Language.CPP) == "Bool"

    def test_string(self):
        assert normalize_type_hint("string", Language.CPP) == "String"


class TestNormalizeTypeHintCSharp:
    def test_int(self):
        assert normalize_type_hint("int", Language.CSHARP) == "Int"

    def test_double(self):
        assert normalize_type_hint("double", Language.CSHARP) == "Float"

    def test_string(self):
        assert normalize_type_hint("string", Language.CSHARP) == "String"

    def test_bool(self):
        assert normalize_type_hint("bool", Language.CSHARP) == "Bool"


class TestNormalizeTypeHintKotlin:
    def test_int(self):
        assert normalize_type_hint("Int", Language.KOTLIN) == "Int"

    def test_double(self):
        assert normalize_type_hint("Double", Language.KOTLIN) == "Float"

    def test_string(self):
        assert normalize_type_hint("String", Language.KOTLIN) == "String"

    def test_boolean(self):
        assert normalize_type_hint("Boolean", Language.KOTLIN) == "Bool"


class TestNormalizeTypeHintScala:
    def test_int(self):
        assert normalize_type_hint("Int", Language.SCALA) == "Int"

    def test_double(self):
        assert normalize_type_hint("Double", Language.SCALA) == "Float"

    def test_string(self):
        assert normalize_type_hint("String", Language.SCALA) == "String"


class TestNormalizeTypeHintPascal:
    def test_integer(self):
        assert normalize_type_hint("integer", Language.PASCAL) == "Int"

    def test_real(self):
        assert normalize_type_hint("real", Language.PASCAL) == "Float"

    def test_boolean(self):
        assert normalize_type_hint("boolean", Language.PASCAL) == "Bool"

    def test_string(self):
        assert normalize_type_hint("string", Language.PASCAL) == "String"


class TestNormalizeTypeHintTypeScript:
    def test_number(self):
        assert normalize_type_hint("number", Language.TYPESCRIPT) == "Float"

    def test_string(self):
        assert normalize_type_hint("string", Language.TYPESCRIPT) == "String"

    def test_boolean(self):
        assert normalize_type_hint("boolean", Language.TYPESCRIPT) == "Bool"


class TestNormalizeTypeHintPython:
    def test_int(self):
        assert normalize_type_hint("int", Language.PYTHON) == "Int"

    def test_str(self):
        assert normalize_type_hint("str", Language.PYTHON) == "String"

    def test_float(self):
        assert normalize_type_hint("float", Language.PYTHON) == "Float"

    def test_bool(self):
        assert normalize_type_hint("bool", Language.PYTHON) == "Bool"

    def test_list(self):
        assert normalize_type_hint("list", Language.PYTHON) == "Array"


class TestNormalizeTypeHintPHP:
    def test_int(self):
        assert normalize_type_hint("int", Language.PHP) == "Int"

    def test_float(self):
        assert normalize_type_hint("float", Language.PHP) == "Float"

    def test_string(self):
        assert normalize_type_hint("string", Language.PHP) == "String"

    def test_bool(self):
        assert normalize_type_hint("bool", Language.PHP) == "Bool"

    def test_array(self):
        assert normalize_type_hint("array", Language.PHP) == "Array"


class TestNormalizeTypeHintEdgeCases:
    def test_empty_string_returns_empty(self):
        assert normalize_type_hint("", Language.JAVA) == ""

    def test_unknown_language_returns_raw(self):
        assert normalize_type_hint("int", Language.RUBY) == "int"

    def test_custom_class_passthrough(self):
        assert normalize_type_hint("MyCustomType", Language.GO) == "MyCustomType"
