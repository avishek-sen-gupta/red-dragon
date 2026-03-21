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


class TestJavaScriptSymbolExtraction:
    def test_extracts_class_with_fields(self):
        src = "class Circle { constructor() { this.radius = 0; } }"
        st = _extract(Language.JAVASCRIPT, src)
        assert "Circle" in st.classes
        assert "radius" in st.classes["Circle"].fields

    def test_extracts_methods(self):
        src = "class C { area() { return 0; } }"
        st = _extract(Language.JAVASCRIPT, src)
        assert "area" in st.classes["C"].methods

    def test_extracts_parents(self):
        src = "class Shape {} class Circle extends Shape { area() {} }"
        st = _extract(Language.JAVASCRIPT, src)
        assert "Shape" in st.classes["Circle"].parents

    def test_extracts_field_definition(self):
        src = "class C { count = 0; }"
        st = _extract(Language.JAVASCRIPT, src)
        assert "count" in st.classes["C"].fields

    def test_multiple_classes(self):
        src = "class A {} class B {}"
        st = _extract(Language.JAVASCRIPT, src)
        assert "A" in st.classes
        assert "B" in st.classes


class TestTypeScriptSymbolExtraction:
    def test_extracts_class_with_fields(self):
        src = "class Circle { constructor() { this.radius = 0; } }"
        st = _extract(Language.TYPESCRIPT, src)
        assert "Circle" in st.classes
        assert "radius" in st.classes["Circle"].fields

    def test_extracts_methods(self):
        src = "class C { area(): number { return 0; } }"
        st = _extract(Language.TYPESCRIPT, src)
        assert "area" in st.classes["C"].methods

    def test_extracts_parents(self):
        src = "class Shape {} class Circle extends Shape {}"
        st = _extract(Language.TYPESCRIPT, src)
        assert "Shape" in st.classes["Circle"].parents


class TestRubySymbolExtraction:
    def test_extracts_class_with_fields(self):
        src = "class Circle\n  def initialize(r)\n    @radius = r\n  end\nend\n"
        st = _extract(Language.RUBY, src)
        assert "Circle" in st.classes
        assert "radius" in st.classes["Circle"].fields

    def test_extracts_methods(self):
        src = "class C\n  def area\n    0\n  end\nend\n"
        st = _extract(Language.RUBY, src)
        assert "area" in st.classes["C"].methods

    def test_extracts_parents(self):
        src = "class Shape\nend\nclass Circle < Shape\nend\n"
        st = _extract(Language.RUBY, src)
        assert "Shape" in st.classes["Circle"].parents

    def test_multiple_classes(self):
        src = "class A\nend\nclass B\nend\n"
        st = _extract(Language.RUBY, src)
        assert "A" in st.classes
        assert "B" in st.classes


class TestGoSymbolExtraction:
    def test_extracts_struct_with_fields(self):
        src = "package main\ntype Circle struct { Radius int }"
        st = _extract(Language.GO, src)
        assert "Circle" in st.classes
        assert "Radius" in st.classes["Circle"].fields

    def test_extracts_top_level_function(self):
        src = "package main\nfunc Area() int { return 0 }"
        st = _extract(Language.GO, src)
        assert "Area" in st.functions

    def test_extracts_method_for_struct(self):
        src = (
            "package main\ntype C struct { X int }\nfunc (c C) Area() int { return 0 }"
        )
        st = _extract(Language.GO, src)
        assert "Area" in st.classes["C"].methods

    def test_multiple_structs(self):
        src = "package main\ntype A struct { X int }\ntype B struct { Y int }"
        st = _extract(Language.GO, src)
        assert "A" in st.classes
        assert "B" in st.classes


class TestPHPSymbolExtraction:
    def test_extracts_class_with_fields(self):
        src = "<?php\nclass Circle {\n  public $radius;\n}"
        st = _extract(Language.PHP, src)
        assert "Circle" in st.classes
        assert "radius" in st.classes["Circle"].fields

    def test_extracts_methods(self):
        src = "<?php\nclass C {\n  public function area() { return 0; }\n}"
        st = _extract(Language.PHP, src)
        assert "area" in st.classes["C"].methods

    def test_extracts_parents(self):
        src = "<?php\nclass Shape {}\nclass Circle extends Shape {}"
        st = _extract(Language.PHP, src)
        assert "Shape" in st.classes["Circle"].parents

    def test_multiple_classes(self):
        src = "<?php\nclass A {}\nclass B {}"
        st = _extract(Language.PHP, src)
        assert "A" in st.classes
        assert "B" in st.classes


class TestKotlinSymbolExtraction:
    def test_extracts_class_with_primary_ctor_fields(self):
        src = "class Circle(val radius: Int)"
        st = _extract(Language.KOTLIN, src)
        assert "Circle" in st.classes
        assert "radius" in st.classes["Circle"].fields

    def test_extracts_methods(self):
        src = "class C {\n  fun area(): Int { return 0 }\n}"
        st = _extract(Language.KOTLIN, src)
        assert "area" in st.classes["C"].methods

    def test_extracts_parents(self):
        src = "open class Shape\nclass Circle : Shape()"
        st = _extract(Language.KOTLIN, src)
        assert "Shape" in st.classes["Circle"].parents

    def test_extracts_property_field(self):
        src = "class C {\n  val x: Int = 0\n}"
        st = _extract(Language.KOTLIN, src)
        assert "x" in st.classes["C"].fields

    def test_multiple_classes(self):
        src = "class A\nclass B"
        st = _extract(Language.KOTLIN, src)
        assert "A" in st.classes
        assert "B" in st.classes


class TestScalaSymbolExtraction:
    def test_extracts_class_with_primary_ctor_fields(self):
        src = "class Circle(val radius: Int)"
        st = _extract(Language.SCALA, src)
        assert "Circle" in st.classes
        assert "radius" in st.classes["Circle"].fields

    def test_extracts_methods(self):
        src = "class C {\n  def area(): Int = 0\n}"
        st = _extract(Language.SCALA, src)
        assert "area" in st.classes["C"].methods

    def test_extracts_parents(self):
        src = "class Shape\nclass Circle extends Shape"
        st = _extract(Language.SCALA, src)
        assert "Shape" in st.classes["Circle"].parents

    def test_extracts_val_field(self):
        src = "class C {\n  val x: Int = 0\n}"
        st = _extract(Language.SCALA, src)
        assert "x" in st.classes["C"].fields

    def test_multiple_classes(self):
        src = "class A\nclass B"
        st = _extract(Language.SCALA, src)
        assert "A" in st.classes
        assert "B" in st.classes


class TestRustSymbolExtraction:
    def test_extracts_struct_with_fields(self):
        src = "struct Circle { radius: f64 }"
        st = _extract(Language.RUST, src)
        assert "Circle" in st.classes
        assert "radius" in st.classes["Circle"].fields

    def test_extracts_methods_from_impl(self):
        src = "struct C { x: i32 }\nimpl C { fn area(&self) -> i32 { 0 } }"
        st = _extract(Language.RUST, src)
        assert "area" in st.classes["C"].methods

    def test_extracts_top_level_function(self):
        src = "fn greet(name: &str) -> i32 { 0 }"
        st = _extract(Language.RUST, src)
        assert "greet" in st.functions

    def test_multiple_structs(self):
        src = "struct A { x: i32 }\nstruct B { y: f64 }"
        st = _extract(Language.RUST, src)
        assert "A" in st.classes
        assert "B" in st.classes


class TestLuaSymbolExtraction:
    def test_returns_empty_symbol_table(self):
        src = "local x = 1"
        st = _extract(Language.LUA, src)
        assert st.classes == {}

    def test_function_defined_lua(self):
        src = "function greet() end"
        st = _extract(Language.LUA, src)
        # Lua extraction is minimal — just verify it doesn't crash
        assert isinstance(st.classes, dict)


class TestPascalSymbolExtraction:
    def test_extracts_class_with_fields(self):
        src = (
            "program Test;\n"
            "type\n"
            "  TCircle = class\n"
            "  private\n"
            "    FRadius: Integer;\n"
            "  end;\n"
            "begin end.\n"
        )
        st = _extract(Language.PASCAL, src)
        assert "TCircle" in st.classes
        assert "FRadius" in st.classes["TCircle"].fields

    def test_multiple_classes(self):
        src = (
            "program Test;\n"
            "type\n"
            "  TA = class\n"
            "  private\n"
            "    FX: Integer;\n"
            "  end;\n"
            "  TB = class\n"
            "  private\n"
            "    FY: Integer;\n"
            "  end;\n"
            "begin end.\n"
        )
        st = _extract(Language.PASCAL, src)
        assert "TA" in st.classes
        assert "TB" in st.classes


class TestCSymbolExtraction:
    def test_extracts_struct_with_fields(self):
        src = "struct Circle { int radius; double area; };"
        st = _extract(Language.C, src)
        assert "Circle" in st.classes
        assert "radius" in st.classes["Circle"].fields

    def test_extracts_top_level_function(self):
        src = "int add(int a, int b) { return a + b; }"
        st = _extract(Language.C, src)
        assert "add" in st.functions

    def test_multiple_structs(self):
        src = "struct A { int x; }; struct B { float y; };"
        st = _extract(Language.C, src)
        assert "A" in st.classes
        assert "B" in st.classes
