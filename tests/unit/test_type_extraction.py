"""Unit tests for interpreter.frontends.type_extraction — normalize_type_hint."""

from interpreter.frontends.type_extraction import normalize_type_hint

JAVA_TYPE_MAP = {
    "int": "Int",
    "long": "Int",
    "short": "Int",
    "byte": "Int",
    "char": "Int",
    "Integer": "Int",
    "Long": "Int",
    "Short": "Int",
    "Byte": "Int",
    "Character": "Int",
    "double": "Float",
    "float": "Float",
    "Double": "Float",
    "Float": "Float",
    "boolean": "Bool",
    "Boolean": "Bool",
    "String": "String",
    "void": "Any",
}

GO_TYPE_MAP = {
    "int": "Int",
    "int8": "Int",
    "int16": "Int",
    "int32": "Int",
    "int64": "Int",
    "uint": "Int",
    "uint8": "Int",
    "uint16": "Int",
    "uint32": "Int",
    "uint64": "Int",
    "uintptr": "Int",
    "rune": "Int",
    "byte": "Int",
    "float32": "Float",
    "float64": "Float",
    "bool": "Bool",
    "string": "String",
}

RUST_TYPE_MAP = {
    "i8": "Int",
    "i16": "Int",
    "i32": "Int",
    "i64": "Int",
    "i128": "Int",
    "isize": "Int",
    "u8": "Int",
    "u16": "Int",
    "u32": "Int",
    "u64": "Int",
    "u128": "Int",
    "usize": "Int",
    "f32": "Float",
    "f64": "Float",
    "bool": "Bool",
    "String": "String",
    "str": "String",
    "&str": "String",
}

C_TYPE_MAP = {
    "int": "Int",
    "long": "Int",
    "short": "Int",
    "char": "Int",
    "unsigned": "Int",
    "signed": "Int",
    "size_t": "Int",
    "float": "Float",
    "double": "Float",
    "bool": "Bool",
    "_Bool": "Bool",
    "void": "Any",
}

CPP_TYPE_MAP = {
    **C_TYPE_MAP,
    "bool": "Bool",
    "void": "Any",
    "string": "String",
    "std::string": "String",
}

CSHARP_TYPE_MAP = {
    "int": "Int",
    "long": "Int",
    "short": "Int",
    "byte": "Int",
    "sbyte": "Int",
    "uint": "Int",
    "ulong": "Int",
    "ushort": "Int",
    "char": "Int",
    "Int32": "Int",
    "Int64": "Int",
    "float": "Float",
    "double": "Float",
    "decimal": "Float",
    "Single": "Float",
    "Double": "Float",
    "Decimal": "Float",
    "bool": "Bool",
    "Boolean": "Bool",
    "string": "String",
    "String": "String",
    "void": "Any",
    "object": "Object",
    "Object": "Object",
}

KOTLIN_TYPE_MAP = {
    "Int": "Int",
    "Long": "Int",
    "Short": "Int",
    "Byte": "Int",
    "Char": "Int",
    "Float": "Float",
    "Double": "Float",
    "Boolean": "Bool",
    "String": "String",
    "Unit": "Any",
    "Any": "Any",
}

SCALA_TYPE_MAP = {
    "Int": "Int",
    "Long": "Int",
    "Short": "Int",
    "Byte": "Int",
    "Char": "Int",
    "Float": "Float",
    "Double": "Float",
    "Boolean": "Bool",
    "String": "String",
    "Unit": "Any",
    "Any": "Any",
}

PASCAL_TYPE_MAP = {
    "integer": "Int",
    "longint": "Int",
    "shortint": "Int",
    "byte": "Int",
    "word": "Int",
    "cardinal": "Int",
    "real": "Float",
    "single": "Float",
    "double": "Float",
    "extended": "Float",
    "boolean": "Bool",
    "char": "String",
    "string": "String",
}

TYPESCRIPT_TYPE_MAP = {
    "number": "Float",
    "string": "String",
    "boolean": "Bool",
    "void": "Any",
    "any": "Any",
    "undefined": "Any",
    "null": "Any",
    "never": "Any",
    "object": "Object",
}

PYTHON_TYPE_MAP = {
    "int": "Int",
    "float": "Float",
    "bool": "Bool",
    "str": "String",
    "bytes": "String",
    "list": "Array",
    "dict": "Object",
    "object": "Object",
    "None": "Any",
}

PHP_TYPE_MAP = {
    "int": "Int",
    "integer": "Int",
    "float": "Float",
    "double": "Float",
    "bool": "Bool",
    "boolean": "Bool",
    "string": "String",
    "array": "Array",
    "object": "Object",
    "void": "Any",
    "mixed": "Any",
    "null": "Any",
}


class TestNormalizeTypeHintJava:
    def test_int(self):
        assert normalize_type_hint("int", JAVA_TYPE_MAP) == "Int"

    def test_double(self):
        assert normalize_type_hint("double", JAVA_TYPE_MAP) == "Float"

    def test_string(self):
        assert normalize_type_hint("String", JAVA_TYPE_MAP) == "String"

    def test_boolean(self):
        assert normalize_type_hint("boolean", JAVA_TYPE_MAP) == "Bool"

    def test_unknown_class_passthrough(self):
        assert normalize_type_hint("UnknownClass", JAVA_TYPE_MAP) == "UnknownClass"

    def test_long(self):
        assert normalize_type_hint("long", JAVA_TYPE_MAP) == "Int"

    def test_float(self):
        assert normalize_type_hint("float", JAVA_TYPE_MAP) == "Float"

    def test_void(self):
        assert normalize_type_hint("void", JAVA_TYPE_MAP) == "Any"


class TestNormalizeTypeHintGo:
    def test_int64(self):
        assert normalize_type_hint("int64", GO_TYPE_MAP) == "Int"

    def test_float32(self):
        assert normalize_type_hint("float32", GO_TYPE_MAP) == "Float"

    def test_string(self):
        assert normalize_type_hint("string", GO_TYPE_MAP) == "String"

    def test_bool(self):
        assert normalize_type_hint("bool", GO_TYPE_MAP) == "Bool"

    def test_int(self):
        assert normalize_type_hint("int", GO_TYPE_MAP) == "Int"


class TestNormalizeTypeHintRust:
    def test_i32(self):
        assert normalize_type_hint("i32", RUST_TYPE_MAP) == "Int"

    def test_f64(self):
        assert normalize_type_hint("f64", RUST_TYPE_MAP) == "Float"

    def test_bool(self):
        assert normalize_type_hint("bool", RUST_TYPE_MAP) == "Bool"

    def test_string(self):
        assert normalize_type_hint("String", RUST_TYPE_MAP) == "String"

    def test_str(self):
        assert normalize_type_hint("str", RUST_TYPE_MAP) == "String"


class TestNormalizeTypeHintC:
    def test_int(self):
        assert normalize_type_hint("int", C_TYPE_MAP) == "Int"

    def test_bool(self):
        assert normalize_type_hint("bool", C_TYPE_MAP) == "Bool"

    def test_float(self):
        assert normalize_type_hint("float", C_TYPE_MAP) == "Float"

    def test_double(self):
        assert normalize_type_hint("double", C_TYPE_MAP) == "Float"


class TestNormalizeTypeHintCpp:
    def test_int(self):
        assert normalize_type_hint("int", CPP_TYPE_MAP) == "Int"

    def test_bool(self):
        assert normalize_type_hint("bool", CPP_TYPE_MAP) == "Bool"

    def test_string(self):
        assert normalize_type_hint("string", CPP_TYPE_MAP) == "String"


class TestNormalizeTypeHintCSharp:
    def test_int(self):
        assert normalize_type_hint("int", CSHARP_TYPE_MAP) == "Int"

    def test_double(self):
        assert normalize_type_hint("double", CSHARP_TYPE_MAP) == "Float"

    def test_string(self):
        assert normalize_type_hint("string", CSHARP_TYPE_MAP) == "String"

    def test_bool(self):
        assert normalize_type_hint("bool", CSHARP_TYPE_MAP) == "Bool"


class TestNormalizeTypeHintKotlin:
    def test_int(self):
        assert normalize_type_hint("Int", KOTLIN_TYPE_MAP) == "Int"

    def test_double(self):
        assert normalize_type_hint("Double", KOTLIN_TYPE_MAP) == "Float"

    def test_string(self):
        assert normalize_type_hint("String", KOTLIN_TYPE_MAP) == "String"

    def test_boolean(self):
        assert normalize_type_hint("Boolean", KOTLIN_TYPE_MAP) == "Bool"


class TestNormalizeTypeHintScala:
    def test_int(self):
        assert normalize_type_hint("Int", SCALA_TYPE_MAP) == "Int"

    def test_double(self):
        assert normalize_type_hint("Double", SCALA_TYPE_MAP) == "Float"

    def test_string(self):
        assert normalize_type_hint("String", SCALA_TYPE_MAP) == "String"


class TestNormalizeTypeHintPascal:
    def test_integer(self):
        assert normalize_type_hint("integer", PASCAL_TYPE_MAP) == "Int"

    def test_real(self):
        assert normalize_type_hint("real", PASCAL_TYPE_MAP) == "Float"

    def test_boolean(self):
        assert normalize_type_hint("boolean", PASCAL_TYPE_MAP) == "Bool"

    def test_string(self):
        assert normalize_type_hint("string", PASCAL_TYPE_MAP) == "String"


class TestNormalizeTypeHintTypeScript:
    def test_number(self):
        assert normalize_type_hint("number", TYPESCRIPT_TYPE_MAP) == "Float"

    def test_string(self):
        assert normalize_type_hint("string", TYPESCRIPT_TYPE_MAP) == "String"

    def test_boolean(self):
        assert normalize_type_hint("boolean", TYPESCRIPT_TYPE_MAP) == "Bool"


class TestNormalizeTypeHintPython:
    def test_int(self):
        assert normalize_type_hint("int", PYTHON_TYPE_MAP) == "Int"

    def test_str(self):
        assert normalize_type_hint("str", PYTHON_TYPE_MAP) == "String"

    def test_float(self):
        assert normalize_type_hint("float", PYTHON_TYPE_MAP) == "Float"

    def test_bool(self):
        assert normalize_type_hint("bool", PYTHON_TYPE_MAP) == "Bool"

    def test_list(self):
        assert normalize_type_hint("list", PYTHON_TYPE_MAP) == "Array"


class TestNormalizeTypeHintPHP:
    def test_int(self):
        assert normalize_type_hint("int", PHP_TYPE_MAP) == "Int"

    def test_float(self):
        assert normalize_type_hint("float", PHP_TYPE_MAP) == "Float"

    def test_string(self):
        assert normalize_type_hint("string", PHP_TYPE_MAP) == "String"

    def test_bool(self):
        assert normalize_type_hint("bool", PHP_TYPE_MAP) == "Bool"

    def test_array(self):
        assert normalize_type_hint("array", PHP_TYPE_MAP) == "Array"


class TestNormalizeTypeHintEdgeCases:
    def test_empty_string_returns_empty(self):
        assert normalize_type_hint("", JAVA_TYPE_MAP) == ""

    def test_empty_map_returns_raw(self):
        assert normalize_type_hint("int", {}) == "int"

    def test_custom_class_passthrough(self):
        assert normalize_type_hint("MyCustomType", GO_TYPE_MAP) == "MyCustomType"
