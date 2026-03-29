"""Unit tests for per-language symbol extraction (Phase 2)."""

from __future__ import annotations

from interpreter.class_name import ClassName
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
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
        assert ClassName("Circle") in st.classes
        assert FieldName("Radius") in st.classes[ClassName("Circle")].fields
        assert (
            st.classes[ClassName("Circle")].fields[FieldName("Radius")].type_hint
            == "int"
        )

    def test_extracts_methods(self):
        st = _extract(Language.CSHARP, "class C { public int Area() { return 0; } }")
        assert FuncName("Area") in st.classes[ClassName("C")].methods

    def test_extracts_static_constants(self):
        st = _extract(Language.CSHARP, "class C { public static int Count = 0; }")
        assert "Count" in st.classes[ClassName("C")].constants

    def test_extracts_parents(self):
        st = _extract(
            Language.CSHARP, "class Shape {} class Circle : Shape { public int R; }"
        )
        assert ClassName("Shape") in st.classes[ClassName("Circle")].parents

    def test_filters_static_from_fields(self):
        st = _extract(
            Language.CSHARP, "class C { public int R; public static int N = 0; }"
        )
        assert FieldName("R") in st.classes[ClassName("C")].fields
        assert FieldName("N") not in st.classes[ClassName("C")].fields

    def test_multiple_classes(self):
        st = _extract(
            Language.CSHARP, "class A { public int X; } class B { public string Y; }"
        )
        assert ClassName("A") in st.classes
        assert ClassName("B") in st.classes

    def test_constructor_not_in_methods(self):
        st = _extract(
            Language.CSHARP, "class C { public C() {} public int Area() { return 0; } }"
        )
        assert FuncName("Area") in st.classes[ClassName("C")].methods
        assert FuncName("C") not in st.classes[ClassName("C")].methods

    def test_method_has_params(self):
        st = _extract(
            Language.CSHARP, "class C { public int Add(int a, int b) { return 0; } }"
        )
        assert FuncName("Add") in st.classes[ClassName("C")].methods
        assert "a" in st.classes[ClassName("C")].methods[FuncName("Add")].params
        assert "b" in st.classes[ClassName("C")].methods[FuncName("Add")].params

    def test_field_has_initializer_flag(self):
        st = _extract(Language.CSHARP, "class C { public int X = 5; }")
        assert st.classes[ClassName("C")].fields[FieldName("X")].has_initializer is True

    def test_field_without_initializer(self):
        st = _extract(Language.CSHARP, "class C { public int X; }")
        assert (
            st.classes[ClassName("C")].fields[FieldName("X")].has_initializer is False
        )


class TestJavaSymbolExtraction:
    def test_extracts_class_with_fields(self):
        st = _extract(Language.JAVA, "class Circle { int radius; String name; }")
        assert FieldName("radius") in st.classes[ClassName("Circle")].fields
        assert FieldName("name") in st.classes[ClassName("Circle")].fields

    def test_extracts_methods(self):
        st = _extract(Language.JAVA, "class C { int area() { return 0; } }")
        assert FuncName("area") in st.classes[ClassName("C")].methods

    def test_extracts_static_constants(self):
        st = _extract(Language.JAVA, "class C { static int COUNT = 0; }")
        assert "COUNT" in st.classes[ClassName("C")].constants

    def test_extracts_parents(self):
        st = _extract(
            Language.JAVA, "class Shape {} class Circle extends Shape { int r; }"
        )
        assert ClassName("Shape") in st.classes[ClassName("Circle")].parents

    def test_filters_static_from_fields(self):
        st = _extract(Language.JAVA, "class C { int r; static int N = 0; }")
        assert FieldName("r") in st.classes[ClassName("C")].fields
        assert FieldName("N") not in st.classes[ClassName("C")].fields

    def test_multiple_classes(self):
        st = _extract(Language.JAVA, "class A { int x; } class B { String y; }")
        assert ClassName("A") in st.classes
        assert ClassName("B") in st.classes

    def test_method_has_params(self):
        st = _extract(Language.JAVA, "class C { int add(int a, int b) { return 0; } }")
        assert FuncName("add") in st.classes[ClassName("C")].methods
        assert "a" in st.classes[ClassName("C")].methods[FuncName("add")].params
        assert "b" in st.classes[ClassName("C")].methods[FuncName("add")].params

    def test_field_type_hint(self):
        st = _extract(Language.JAVA, "class C { int radius; }")
        assert st.classes[ClassName("C")].fields[FieldName("radius")].type_hint == "int"

    def test_field_has_initializer_flag(self):
        st = _extract(Language.JAVA, "class C { int x = 5; }")
        assert st.classes[ClassName("C")].fields[FieldName("x")].has_initializer is True

    def test_field_without_initializer(self):
        st = _extract(Language.JAVA, "class C { int x; }")
        assert (
            st.classes[ClassName("C")].fields[FieldName("x")].has_initializer is False
        )


class TestCppSymbolExtraction:
    def test_extracts_class_with_fields(self):
        st = _extract(Language.CPP, "class Circle { int radius; };")
        assert ClassName("Circle") in st.classes
        assert FieldName("radius") in st.classes[ClassName("Circle")].fields

    def test_extracts_methods(self):
        st = _extract(Language.CPP, "class C { int area() { return 0; } };")
        assert FuncName("area") in st.classes[ClassName("C")].methods

    def test_extracts_parents(self):
        st = _extract(
            Language.CPP, "class Shape {}; class Circle : public Shape { int r; };"
        )
        assert ClassName("Shape") in st.classes[ClassName("Circle")].parents

    def test_filters_static_from_fields(self):
        st = _extract(Language.CPP, "class C { int r; static int n; };")
        assert FieldName("r") in st.classes[ClassName("C")].fields
        assert FieldName("n") not in st.classes[ClassName("C")].fields

    def test_static_field_in_constants(self):
        st = _extract(Language.CPP, "class C { int r; static int n; };")
        assert "n" in st.classes[ClassName("C")].constants

    def test_multiple_parents(self):
        st = _extract(
            Language.CPP,
            "class A {}; class B {}; class C : public A, private B { int x; };",
        )
        assert ClassName("A") in st.classes[ClassName("C")].parents
        assert ClassName("B") in st.classes[ClassName("C")].parents

    def test_method_has_params(self):
        st = _extract(Language.CPP, "class C { int add(int a, int b) { return 0; } };")
        assert FuncName("add") in st.classes[ClassName("C")].methods
        assert "a" in st.classes[ClassName("C")].methods[FuncName("add")].params
        assert "b" in st.classes[ClassName("C")].methods[FuncName("add")].params

    def test_field_type_hint(self):
        st = _extract(Language.CPP, "class C { int radius; };")
        assert st.classes[ClassName("C")].fields[FieldName("radius")].type_hint == "int"


class TestPythonSymbolExtraction:
    def test_extracts_class_with_fields(self):
        st = _extract(
            Language.PYTHON,
            "class Circle:\n    def __init__(self, radius):\n        self.radius = radius\n",
        )
        assert ClassName("Circle") in st.classes
        assert FieldName("radius") in st.classes[ClassName("Circle")].fields

    def test_extracts_methods(self):
        st = _extract(
            Language.PYTHON, "class C:\n    def area(self):\n        return 0\n"
        )
        assert FuncName("area") in st.classes[ClassName("C")].methods

    def test_extracts_class_constants(self):
        st = _extract(Language.PYTHON, "class C:\n    COUNT = 0\n    PI = 3.14\n")
        assert "COUNT" in st.classes[ClassName("C")].constants
        assert "PI" in st.classes[ClassName("C")].constants

    def test_extracts_match_args(self):
        st = _extract(
            Language.PYTHON,
            'class Point:\n    __match_args__ = ("x", "y")\n    def __init__(self, x, y):\n        self.x = x\n        self.y = y\n',
        )
        assert st.classes[ClassName("Point")].match_args == ("x", "y")

    def test_extracts_parents(self):
        st = _extract(
            Language.PYTHON,
            "class Shape:\n    pass\nclass Circle(Shape):\n    pass\n",
        )
        assert ClassName("Shape") in st.classes[ClassName("Circle")].parents

    def test_match_args_not_in_constants(self):
        st = _extract(
            Language.PYTHON,
            'class Point:\n    __match_args__ = ("x", "y")\n    COUNT = 0\n',
        )
        assert "__match_args__" not in st.classes[ClassName("Point")].constants
        assert "COUNT" in st.classes[ClassName("Point")].constants

    def test_multiple_classes(self):
        st = _extract(
            Language.PYTHON,
            "class A:\n    pass\nclass B:\n    pass\n",
        )
        assert ClassName("A") in st.classes
        assert ClassName("B") in st.classes

    def test_methods_include_init(self):
        src = "class C:\n    def __init__(self):\n        self.x = 0\n    def foo(self):\n        return 1\n"
        st = _extract(Language.PYTHON, src)
        assert FuncName("__init__") in st.classes[ClassName("C")].methods
        assert FuncName("foo") in st.classes[ClassName("C")].methods

    def test_fields_not_in_constants(self):
        src = "class C:\n    COUNT = 0\n    def __init__(self):\n        self.x = 1\n"
        st = _extract(Language.PYTHON, src)
        assert FieldName("x") in st.classes[ClassName("C")].fields
        assert "x" not in st.classes[ClassName("C")].constants


class TestJavaScriptSymbolExtraction:
    def test_extracts_class_with_fields(self):
        src = "class Circle { constructor() { this.radius = 0; } }"
        st = _extract(Language.JAVASCRIPT, src)
        assert ClassName("Circle") in st.classes
        assert FieldName("radius") in st.classes[ClassName("Circle")].fields

    def test_extracts_methods(self):
        src = "class C { area() { return 0; } }"
        st = _extract(Language.JAVASCRIPT, src)
        assert FuncName("area") in st.classes[ClassName("C")].methods

    def test_extracts_parents(self):
        src = "class Shape {} class Circle extends Shape { area() {} }"
        st = _extract(Language.JAVASCRIPT, src)
        assert ClassName("Shape") in st.classes[ClassName("Circle")].parents

    def test_extracts_field_definition(self):
        src = "class C { count = 0; }"
        st = _extract(Language.JAVASCRIPT, src)
        assert FieldName("count") in st.classes[ClassName("C")].fields

    def test_multiple_classes(self):
        src = "class A {} class B {}"
        st = _extract(Language.JAVASCRIPT, src)
        assert ClassName("A") in st.classes
        assert ClassName("B") in st.classes


class TestTypeScriptSymbolExtraction:
    def test_extracts_class_with_fields(self):
        src = "class Circle { constructor() { this.radius = 0; } }"
        st = _extract(Language.TYPESCRIPT, src)
        assert ClassName("Circle") in st.classes
        assert FieldName("radius") in st.classes[ClassName("Circle")].fields

    def test_extracts_methods(self):
        src = "class C { area(): number { return 0; } }"
        st = _extract(Language.TYPESCRIPT, src)
        assert FuncName("area") in st.classes[ClassName("C")].methods

    def test_extracts_method_params(self):
        src = "class C { push(item: number): void {} add(a: number, b: number): number { return 0; } }"
        st = _extract(Language.TYPESCRIPT, src)
        assert st.classes[ClassName("C")].methods[FuncName("push")].params == ("item",)
        assert st.classes[ClassName("C")].methods[FuncName("add")].params == ("a", "b")

    def test_extracts_parents(self):
        src = "class Shape {} class Circle extends Shape {}"
        st = _extract(Language.TYPESCRIPT, src)
        assert ClassName("Shape") in st.classes[ClassName("Circle")].parents


class TestRubySymbolExtraction:
    def test_extracts_class_with_fields(self):
        src = "class Circle\n  def initialize(r)\n    @radius = r\n  end\nend\n"
        st = _extract(Language.RUBY, src)
        assert ClassName("Circle") in st.classes
        assert FieldName("radius") in st.classes[ClassName("Circle")].fields

    def test_extracts_methods(self):
        src = "class C\n  def area\n    0\n  end\nend\n"
        st = _extract(Language.RUBY, src)
        assert FuncName("area") in st.classes[ClassName("C")].methods

    def test_extracts_parents(self):
        src = "class Shape\nend\nclass Circle < Shape\nend\n"
        st = _extract(Language.RUBY, src)
        assert ClassName("Shape") in st.classes[ClassName("Circle")].parents

    def test_multiple_classes(self):
        src = "class A\nend\nclass B\nend\n"
        st = _extract(Language.RUBY, src)
        assert ClassName("A") in st.classes
        assert ClassName("B") in st.classes


class TestGoSymbolExtraction:
    def test_extracts_struct_with_fields(self):
        src = "package main\ntype Circle struct { Radius int }"
        st = _extract(Language.GO, src)
        assert ClassName("Circle") in st.classes
        assert FieldName("Radius") in st.classes[ClassName("Circle")].fields

    def test_extracts_top_level_function(self):
        src = "package main\nfunc Area() int { return 0 }"
        st = _extract(Language.GO, src)
        assert FuncName("Area") in st.functions

    def test_extracts_method_for_struct(self):
        src = (
            "package main\ntype C struct { X int }\nfunc (c C) Area() int { return 0 }"
        )
        st = _extract(Language.GO, src)
        assert FuncName("Area") in st.classes[ClassName("C")].methods

    def test_multiple_structs(self):
        src = "package main\ntype A struct { X int }\ntype B struct { Y int }"
        st = _extract(Language.GO, src)
        assert ClassName("A") in st.classes
        assert ClassName("B") in st.classes


class TestPHPSymbolExtraction:
    def test_extracts_class_with_fields(self):
        src = "<?php\nclass Circle {\n  public $radius;\n}"
        st = _extract(Language.PHP, src)
        assert ClassName("Circle") in st.classes
        assert FieldName("radius") in st.classes[ClassName("Circle")].fields

    def test_extracts_methods(self):
        src = "<?php\nclass C {\n  public function area() { return 0; }\n}"
        st = _extract(Language.PHP, src)
        assert FuncName("area") in st.classes[ClassName("C")].methods

    def test_extracts_parents(self):
        src = "<?php\nclass Shape {}\nclass Circle extends Shape {}"
        st = _extract(Language.PHP, src)
        assert ClassName("Shape") in st.classes[ClassName("Circle")].parents

    def test_multiple_classes(self):
        src = "<?php\nclass A {}\nclass B {}"
        st = _extract(Language.PHP, src)
        assert ClassName("A") in st.classes
        assert ClassName("B") in st.classes

    def test_static_property_goes_to_constants_not_fields(self):
        """Static properties should be in constants, not fields."""
        src = "<?php\nclass Product {\n  public $name;\n  public static $tax_rate = 0.1;\n}"
        st = _extract(Language.PHP, src)
        assert FieldName("name") in st.classes[ClassName("Product")].fields
        assert FieldName("tax_rate") not in st.classes[ClassName("Product")].fields
        assert "tax_rate" in st.classes[ClassName("Product")].constants

    def test_instance_and_static_separated(self):
        """Multiple properties — instance in fields, static in constants."""
        src = "<?php\nclass Counter {\n  public $count;\n  public static $total = 0;\n  public static $max = 100;\n}"
        st = _extract(Language.PHP, src)
        assert FieldName("count") in st.classes[ClassName("Counter")].fields
        assert "total" in st.classes[ClassName("Counter")].constants
        assert "max" in st.classes[ClassName("Counter")].constants
        assert FieldName("total") not in st.classes[ClassName("Counter")].fields
        assert FieldName("max") not in st.classes[ClassName("Counter")].fields


class TestKotlinSymbolExtraction:
    def test_extracts_class_with_primary_ctor_fields(self):
        src = "class Circle(val radius: Int)"
        st = _extract(Language.KOTLIN, src)
        assert ClassName("Circle") in st.classes
        assert FieldName("radius") in st.classes[ClassName("Circle")].fields

    def test_extracts_methods(self):
        src = "class C {\n  fun area(): Int { return 0 }\n}"
        st = _extract(Language.KOTLIN, src)
        assert FuncName("area") in st.classes[ClassName("C")].methods

    def test_extracts_parents(self):
        src = "open class Shape\nclass Circle : Shape()"
        st = _extract(Language.KOTLIN, src)
        assert ClassName("Shape") in st.classes[ClassName("Circle")].parents

    def test_extracts_property_field(self):
        src = "class C {\n  val x: Int = 0\n}"
        st = _extract(Language.KOTLIN, src)
        assert FieldName("x") in st.classes[ClassName("C")].fields

    def test_multiple_classes(self):
        src = "class A\nclass B"
        st = _extract(Language.KOTLIN, src)
        assert ClassName("A") in st.classes
        assert ClassName("B") in st.classes


class TestScalaSymbolExtraction:
    def test_extracts_class_with_primary_ctor_fields(self):
        src = "class Circle(val radius: Int)"
        st = _extract(Language.SCALA, src)
        assert ClassName("Circle") in st.classes
        assert FieldName("radius") in st.classes[ClassName("Circle")].fields

    def test_extracts_methods(self):
        src = "class C {\n  def area(): Int = 0\n}"
        st = _extract(Language.SCALA, src)
        assert FuncName("area") in st.classes[ClassName("C")].methods

    def test_extracts_parents(self):
        src = "class Shape\nclass Circle extends Shape"
        st = _extract(Language.SCALA, src)
        assert ClassName("Shape") in st.classes[ClassName("Circle")].parents

    def test_extracts_val_field(self):
        src = "class C {\n  val x: Int = 0\n}"
        st = _extract(Language.SCALA, src)
        assert FieldName("x") in st.classes[ClassName("C")].fields

    def test_multiple_classes(self):
        src = "class A\nclass B"
        st = _extract(Language.SCALA, src)
        assert ClassName("A") in st.classes
        assert ClassName("B") in st.classes


class TestRustSymbolExtraction:
    def test_extracts_struct_with_fields(self):
        src = "struct Circle { radius: f64 }"
        st = _extract(Language.RUST, src)
        assert ClassName("Circle") in st.classes
        assert FieldName("radius") in st.classes[ClassName("Circle")].fields

    def test_extracts_methods_from_impl(self):
        src = "struct C { x: i32 }\nimpl C { fn area(&self) -> i32 { 0 } }"
        st = _extract(Language.RUST, src)
        assert FuncName("area") in st.classes[ClassName("C")].methods

    def test_extracts_top_level_function(self):
        src = "fn greet(name: &str) -> i32 { 0 }"
        st = _extract(Language.RUST, src)
        assert FuncName("greet") in st.functions

    def test_multiple_structs(self):
        src = "struct A { x: i32 }\nstruct B { y: f64 }"
        st = _extract(Language.RUST, src)
        assert ClassName("A") in st.classes
        assert ClassName("B") in st.classes

    def test_impl_methods_not_duplicated_as_functions(self):
        src = "struct C { x: i32 }\nimpl C { fn area(&self) -> i32 { 0 } }\nfn standalone() -> i32 { 42 }"
        st = _extract(Language.RUST, src)
        assert FuncName("area") in st.classes[ClassName("C")].methods
        assert FuncName("area") not in st.functions
        assert FuncName("standalone") in st.functions


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
        assert ClassName("TCircle") in st.classes
        assert FieldName("FRadius") in st.classes[ClassName("TCircle")].fields

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
        assert ClassName("TA") in st.classes
        assert ClassName("TB") in st.classes

    def test_extracts_direct_fields_and_methods(self):
        """Fields and methods directly in declClass (no declSection wrapper)."""
        src = (
            "program M;\n"
            "type\n"
            "  TAnimal = class\n"
            "    Name: string;\n"
            "    Age: Integer;\n"
            "    procedure Speak;\n"
            "  end;\n"
            "begin end.\n"
        )
        st = _extract(Language.PASCAL, src)
        assert FieldName("Name") in st.classes[ClassName("TAnimal")].fields
        assert FieldName("Age") in st.classes[ClassName("TAnimal")].fields
        assert FuncName("Speak") in st.classes[ClassName("TAnimal")].methods


class TestCSymbolExtraction:
    def test_extracts_struct_with_fields(self):
        src = "struct Circle { int radius; double area; };"
        st = _extract(Language.C, src)
        assert ClassName("Circle") in st.classes
        assert FieldName("radius") in st.classes[ClassName("Circle")].fields

    def test_extracts_top_level_function(self):
        src = "int add(int a, int b) { return a + b; }"
        st = _extract(Language.C, src)
        assert FuncName("add") in st.functions

    def test_multiple_structs(self):
        src = "struct A { int x; }; struct B { float y; };"
        st = _extract(Language.C, src)
        assert ClassName("A") in st.classes
        assert ClassName("B") in st.classes
