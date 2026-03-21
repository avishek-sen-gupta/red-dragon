"""Unit tests for per-language symbol extraction (Phase 2)."""

from __future__ import annotations

from interpreter.frontend import get_frontend
from interpreter.constants import Language
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.parser import TreeSitterParserFactory


def _extract(language: Language, source: str) -> SymbolTable:
    frontend = get_frontend(language)
    parser = TreeSitterParserFactory().get_parser(language)
    tree = parser.parse(source.encode())
    return frontend._extract_symbols(tree.root_node)


class TestCSharpSymbolExtraction:
    def test_extracts_class_with_fields(self):
        st = _extract(Language.CSHARP, "class Circle { public int Radius; }")
        assert "Circle" in st.classes
        assert "Radius" in st.classes["Circle"].fields
        assert st.classes["Circle"].fields["Radius"].type_hint == "int"

    def test_extracts_methods(self):
        st = _extract(Language.CSHARP, "class C { public int Area() { return 0; } }")
        assert "Area" in st.classes["C"].methods

    def test_extracts_static_constants(self):
        st = _extract(Language.CSHARP, "class C { public static int Count = 0; }")
        assert "Count" in st.classes["C"].constants

    def test_extracts_parents(self):
        st = _extract(
            Language.CSHARP, "class Shape {} class Circle : Shape { public int R; }"
        )
        assert "Shape" in st.classes["Circle"].parents

    def test_filters_static_from_fields(self):
        st = _extract(
            Language.CSHARP, "class C { public int R; public static int N = 0; }"
        )
        assert "R" in st.classes["C"].fields
        assert "N" not in st.classes["C"].fields

    def test_multiple_classes(self):
        st = _extract(
            Language.CSHARP, "class A { public int X; } class B { public string Y; }"
        )
        assert "A" in st.classes
        assert "B" in st.classes

    def test_constructor_not_in_methods(self):
        st = _extract(
            Language.CSHARP, "class C { public C() {} public int Area() { return 0; } }"
        )
        assert "Area" in st.classes["C"].methods
        assert "C" not in st.classes["C"].methods

    def test_method_has_params(self):
        st = _extract(
            Language.CSHARP, "class C { public int Add(int a, int b) { return 0; } }"
        )
        assert "Add" in st.classes["C"].methods
        assert "a" in st.classes["C"].methods["Add"].params
        assert "b" in st.classes["C"].methods["Add"].params

    def test_field_has_initializer_flag(self):
        st = _extract(Language.CSHARP, "class C { public int X = 5; }")
        assert st.classes["C"].fields["X"].has_initializer is True

    def test_field_without_initializer(self):
        st = _extract(Language.CSHARP, "class C { public int X; }")
        assert st.classes["C"].fields["X"].has_initializer is False


class TestJavaSymbolExtraction:
    def test_extracts_class_with_fields(self):
        st = _extract(Language.JAVA, "class Circle { int radius; String name; }")
        assert "radius" in st.classes["Circle"].fields
        assert "name" in st.classes["Circle"].fields

    def test_extracts_methods(self):
        st = _extract(Language.JAVA, "class C { int area() { return 0; } }")
        assert "area" in st.classes["C"].methods

    def test_extracts_static_constants(self):
        st = _extract(Language.JAVA, "class C { static int COUNT = 0; }")
        assert "COUNT" in st.classes["C"].constants

    def test_extracts_parents(self):
        st = _extract(
            Language.JAVA, "class Shape {} class Circle extends Shape { int r; }"
        )
        assert "Shape" in st.classes["Circle"].parents

    def test_filters_static_from_fields(self):
        st = _extract(Language.JAVA, "class C { int r; static int N = 0; }")
        assert "r" in st.classes["C"].fields
        assert "N" not in st.classes["C"].fields

    def test_multiple_classes(self):
        st = _extract(Language.JAVA, "class A { int x; } class B { String y; }")
        assert "A" in st.classes
        assert "B" in st.classes

    def test_method_has_params(self):
        st = _extract(Language.JAVA, "class C { int add(int a, int b) { return 0; } }")
        assert "add" in st.classes["C"].methods
        assert "a" in st.classes["C"].methods["add"].params
        assert "b" in st.classes["C"].methods["add"].params

    def test_field_type_hint(self):
        st = _extract(Language.JAVA, "class C { int radius; }")
        assert st.classes["C"].fields["radius"].type_hint == "int"

    def test_field_has_initializer_flag(self):
        st = _extract(Language.JAVA, "class C { int x = 5; }")
        assert st.classes["C"].fields["x"].has_initializer is True

    def test_field_without_initializer(self):
        st = _extract(Language.JAVA, "class C { int x; }")
        assert st.classes["C"].fields["x"].has_initializer is False


class TestCppSymbolExtraction:
    def test_extracts_class_with_fields(self):
        st = _extract(Language.CPP, "class Circle { int radius; };")
        assert "Circle" in st.classes
        assert "radius" in st.classes["Circle"].fields

    def test_extracts_methods(self):
        st = _extract(Language.CPP, "class C { int area() { return 0; } };")
        assert "area" in st.classes["C"].methods

    def test_extracts_parents(self):
        st = _extract(
            Language.CPP, "class Shape {}; class Circle : public Shape { int r; };"
        )
        assert "Shape" in st.classes["Circle"].parents

    def test_filters_static_from_fields(self):
        st = _extract(Language.CPP, "class C { int r; static int n; };")
        assert "r" in st.classes["C"].fields
        assert "n" not in st.classes["C"].fields

    def test_static_field_in_constants(self):
        st = _extract(Language.CPP, "class C { int r; static int n; };")
        assert "n" in st.classes["C"].constants

    def test_multiple_parents(self):
        st = _extract(
            Language.CPP,
            "class A {}; class B {}; class C : public A, private B { int x; };",
        )
        assert "A" in st.classes["C"].parents
        assert "B" in st.classes["C"].parents

    def test_method_has_params(self):
        st = _extract(Language.CPP, "class C { int add(int a, int b) { return 0; } };")
        assert "add" in st.classes["C"].methods
        assert "a" in st.classes["C"].methods["add"].params
        assert "b" in st.classes["C"].methods["add"].params

    def test_field_type_hint(self):
        st = _extract(Language.CPP, "class C { int radius; };")
        assert st.classes["C"].fields["radius"].type_hint == "int"


class TestPythonSymbolExtraction:
    def test_extracts_class_with_fields(self):
        st = _extract(
            Language.PYTHON,
            "class Circle:\n    def __init__(self, radius):\n        self.radius = radius\n",
        )
        assert "Circle" in st.classes
        assert "radius" in st.classes["Circle"].fields

    def test_extracts_methods(self):
        st = _extract(
            Language.PYTHON, "class C:\n    def area(self):\n        return 0\n"
        )
        assert "area" in st.classes["C"].methods

    def test_extracts_class_constants(self):
        st = _extract(Language.PYTHON, "class C:\n    COUNT = 0\n    PI = 3.14\n")
        assert "COUNT" in st.classes["C"].constants
        assert "PI" in st.classes["C"].constants

    def test_extracts_match_args(self):
        st = _extract(
            Language.PYTHON,
            'class Point:\n    __match_args__ = ("x", "y")\n    def __init__(self, x, y):\n        self.x = x\n        self.y = y\n',
        )
        assert st.classes["Point"].match_args == ("x", "y")

    def test_extracts_parents(self):
        st = _extract(
            Language.PYTHON,
            "class Shape:\n    pass\nclass Circle(Shape):\n    pass\n",
        )
        assert "Shape" in st.classes["Circle"].parents

    def test_match_args_not_in_constants(self):
        st = _extract(
            Language.PYTHON,
            'class Point:\n    __match_args__ = ("x", "y")\n    COUNT = 0\n',
        )
        assert "__match_args__" not in st.classes["Point"].constants
        assert "COUNT" in st.classes["Point"].constants

    def test_multiple_classes(self):
        st = _extract(
            Language.PYTHON,
            "class A:\n    pass\nclass B:\n    pass\n",
        )
        assert "A" in st.classes
        assert "B" in st.classes

    def test_methods_include_init(self):
        src = "class C:\n    def __init__(self):\n        self.x = 0\n    def foo(self):\n        return 1\n"
        st = _extract(Language.PYTHON, src)
        assert "__init__" in st.classes["C"].methods
        assert "foo" in st.classes["C"].methods

    def test_fields_not_in_constants(self):
        src = "class C:\n    COUNT = 0\n    def __init__(self):\n        self.x = 1\n"
        st = _extract(Language.PYTHON, src)
        assert "x" in st.classes["C"].fields
        assert "x" not in st.classes["C"].constants
