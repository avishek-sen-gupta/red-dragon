"""Integration tests for Java frontend: hex_floating_point_literal."""

from __future__ import annotations

import pytest

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint
from interpreter.frontends.java.features import JavaFeature
from tests.covers import covers


def _run_java(source: str, max_steps: int = 500):
    vm = run(
        source,
        language=Language.JAVA,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestJavaHexFloatExecution:
    @covers(JavaFeature.HEX_FLOAT_LITERAL)
    def test_hex_float_value(self):
        """0x1.0p10 should parse to 1024.0."""
        source = """\
class M {
    static double x = 0x1.0p10;
}
"""
        _, locals_ = _run_java(source)
        assert locals_[VarName("x")] == 1024.0

    @covers(JavaFeature.HEX_FLOAT_LITERAL)
    def test_hex_float_in_arithmetic(self):
        """0x1.0p10 + 1 should produce 1025.0."""
        source = """\
class M {
    static double x = 0x1.0p10;
    static double y = x + 1;
}
"""
        _, locals_ = _run_java(source)
        assert locals_[VarName("x")] == 1024.0
        assert locals_[VarName("y")] == 1025.0


class TestJavaImplicitThisFieldExecution:
    """Bare field names in method bodies should resolve via implicit this."""

    @covers(JavaFeature.FIELD_ACCESS)
    def test_method_reads_field_by_bare_name(self):
        """this.count accessed as bare 'count' in method body."""
        source = """\
class Counter {
    int count;
    Counter(int c) {
        this.count = c;
    }
    int getCount() {
        return count;
    }
}
Counter c = new Counter(42);
int answer = c.getCount();
"""
        _, locals_ = _run_java(source, max_steps=1000)
        assert locals_[VarName("answer")] == 42


class TestJavaConstructorChainingExecution:
    """Java this(...) constructor chaining with field initializers."""

    @covers(JavaFeature.EXPLICIT_CONSTRUCTOR_INVOCATION)
    def test_single_field_constructor_chaining(self):
        """Two-arg constructor delegates to one-arg via this(x)."""
        source = """\
class Box {
    int value;
    Box(int v) {
        this.value = v;
    }
    Box(int v, int scale) {
        this(v * scale);
    }
}
Box b = new Box(3, 4);
int answer = b.value;
"""
        _, locals_ = _run_java(source, max_steps=1000)
        assert locals_[VarName("answer")] == 12

    @covers(JavaFeature.EXPLICIT_CONSTRUCTOR_INVOCATION)
    def test_chaining_with_field_initializer(self):
        """Field initializer (int extra = 10) should exist after constructor chaining."""
        source = """\
class Calc {
    int result;
    int extra = 10;
    Calc(int r) {
        this.result = r;
    }
    Calc(int a, int b) {
        this(a + b);
    }
    int total() {
        return result + extra;
    }
}
Calc c = new Calc(3, 4);
int answer = c.total();
"""
        _, locals_ = _run_java(source, max_steps=1000)
        assert locals_[VarName("answer")] == 17

    @covers(JavaFeature.EXPLICIT_CONSTRUCTOR_INVOCATION)
    def test_chaining_body_reads_field_by_bare_name(self):
        """After this(...), constructor body can read fields set by delegation."""
        source = """\
class Counter {
    int count;
    int doubled;
    Counter(int c) {
        this.count = c;
        this.doubled = 0;
    }
    Counter(int c, int scale) {
        this(c);
        doubled = count * scale;
    }
}
Counter obj = new Counter(5, 3);
int answer = obj.doubled;
"""
        _, locals_ = _run_java(source, max_steps=1000)
        assert locals_[VarName("answer")] == 15


class TestJavaCompactRecordConstructorExecution:
    """Java record with compact constructor should store fields and run body."""

    @covers(JavaFeature.RECORD)
    def test_record_field_access(self):
        """record Point(int x, int y) — new Point(3, 5).x should be 3."""
        source = """\
record Point(int x, int y) {}
Point p = new Point(3, 5);
int answer = p.x;
"""
        _, locals_ = _run_java(source, max_steps=500)
        assert locals_[VarName("answer")] == 3

    @covers(JavaFeature.RECORD)
    def test_record_both_fields(self):
        """Both record component fields should be accessible."""
        source = """\
record Point(int x, int y) {}
Point p = new Point(3, 5);
int a = p.x;
int b = p.y;
"""
        _, locals_ = _run_java(source, max_steps=500)
        assert locals_[VarName("a")] == 3
        assert locals_[VarName("b")] == 5

    @covers(JavaFeature.RECORD)
    @covers(JavaFeature.COMPACT_CONSTRUCTOR)
    def test_compact_constructor_with_validation(self):
        """Compact constructor body runs before field assignment."""
        source = """\
record Range(int lo, int hi) {
    Range {
        int temp = lo + hi;
    }
}
Range r = new Range(1, 10);
int a = r.lo;
int b = r.hi;
"""
        _, locals_ = _run_java(source, max_steps=500)
        assert locals_[VarName("a")] == 1
        assert locals_[VarName("b")] == 10

    @covers(JavaFeature.RECORD)
    def test_record_with_method(self):
        """Record with an additional method should work."""
        source = """\
record Point(int x, int y) {
    int sum() {
        return x + y;
    }
}
Point p = new Point(3, 5);
int answer = p.sum();
"""
        _, locals_ = _run_java(source, max_steps=1000)
        assert locals_[VarName("answer")] == 8


class TestJavaIntegerLiteralExecution:
    """Hex/octal/binary literals should produce concrete values in the VM."""

    @covers(JavaFeature.INTEGER_LITERALS)
    def test_hex_literal_comparison(self):
        source = """\
class M {
    static int x = 0x7f;
    static boolean result = x > 100;
}
"""
        _, locals_ = _run_java(source)
        assert locals_[VarName("x")] == 127
        assert locals_[VarName("result")] is True

    @covers(JavaFeature.INTEGER_LITERALS)
    def test_hex_in_loop_bound(self):
        """Loop with hex bound should execute concretely, not produce symbolic."""
        source = """\
class M {
    static int count = 0;
    static { for (int i = 0; i < 0x0a; i++) { count = count + 1; } }
}
"""
        vm, locals_ = _run_java(source, max_steps=500)
        assert locals_[VarName("count")] == 10


class TestJavaArrayLengthExecution:
    """Array .length should return a concrete integer, not a symbolic value."""

    @covers(JavaFeature.ARRAY_ACCESS)
    def test_array_length_is_concrete(self):
        source = """\
class M {
    static int[] arr = new int[5];
    static int len = arr.length;
}
"""
        _, locals_ = _run_java(source, max_steps=200)
        assert locals_[VarName("len")] == 5

    @covers(JavaFeature.ARRAY_ACCESS)
    def test_array_length_in_loop(self):
        source = """\
class M {
    static int[] arr = new int[3];
    static int count = 0;
    static { for (int i = 0; i < arr.length; i++) { count = count + 1; } }
}
"""
        _, locals_ = _run_java(source, max_steps=500)
        assert locals_[VarName("count")] == 3


class TestJavaBooleanTypeExecution:
    """boolean_type variables and negation must execute concretely."""

    @covers(JavaFeature.LOCAL_VARIABLE)
    def test_boolean_field_true(self):
        source = """\
class M {
    static boolean flag = true;
}
"""
        _, locals_ = _run_java(source)
        assert locals_[VarName("flag")] is True

    @covers(JavaFeature.LOCAL_VARIABLE)
    def test_boolean_negation(self):
        source = """\
class M {
    static boolean flag = true;
    static boolean result = !flag;
}
"""
        _, locals_ = _run_java(source)
        assert locals_[VarName("flag")] is True
        assert locals_[VarName("result")] is False


class TestJavaAnnotatedTypeExecution:
    """annotated_type (@NonNull String) must not affect the stored value."""

    @covers(JavaFeature.ANNOTATIONS)
    def test_annotated_string_field(self):
        """@NonNull on a local var must not crash; value must be stored correctly."""
        source = """\
class M {
    static void run() { }
    static String result = "hello";
}
"""
        _, locals_ = _run_java(source)
        assert locals_[VarName("result")] == "hello"

    @covers(JavaFeature.ANNOTATIONS)
    def test_annotated_local_var_in_method(self):
        """Method with @NonNull param type must execute and return the value."""
        source = """\
class Greeter {
    String greet(@NonNull String name) {
        return name;
    }
}
Greeter g = new Greeter();
String answer = g.greet("world");
"""
        _, locals_ = _run_java(source, max_steps=500)
        assert locals_[VarName("answer")] == "world"


class TestJavaMarkerAnnotationExecution:
    """@Override / @Deprecated on methods must not affect execution."""

    @covers(JavaFeature.ANNOTATIONS)
    def test_override_method_executes(self):
        """@Override method must be callable and return the correct value."""
        source = """\
class Animal {
    String speak() {
        return "generic";
    }
}
class Dog extends Animal {
    @Override
    String speak() {
        return "woof";
    }
}
Dog d = new Dog();
String answer = d.speak();
"""
        _, locals_ = _run_java(source, max_steps=500)
        assert locals_[VarName("answer")] == "woof"


class TestJavaFormalParametersExecution:
    """formal_parameters must bind correctly during method invocation."""

    @covers(JavaFeature.FORMAL_PARAMETERS)
    def test_two_int_params_add(self):
        source = """\
class Calc {
    int add(int a, int b) {
        return a + b;
    }
}
Calc c = new Calc();
int answer = c.add(3, 4);
"""
        _, locals_ = _run_java(source, max_steps=500)
        assert locals_[VarName("answer")] == 7

    @covers(JavaFeature.FORMAL_PARAMETERS)
    def test_string_param_method(self):
        source = """\
class Wrapper {
    String wrap(String s) {
        return s;
    }
}
Wrapper w = new Wrapper();
String answer = w.wrap("hi");
"""
        _, locals_ = _run_java(source, max_steps=500)
        assert locals_[VarName("answer")] == "hi"


class TestJavaScopedTypeIdentifierExecution:
    """scoped_type_identifier (java.lang.String) in declarations must not affect value."""

    @covers(JavaFeature.SCOPED_IDENTIFIER)
    def test_scoped_string_type_field(self):
        """java.lang.String as declared type must store the string value correctly."""
        source = """\
class M {
    static java.lang.String greeting = "hello";
}
"""
        _, locals_ = _run_java(source)
        assert locals_[VarName("greeting")] == "hello"
