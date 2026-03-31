"""Test that CALL_CTOR resolves to the class constructor even when
entering a function directly (skipping module-level declarations).

This is the core reproduction for red-dragon-djll: when entry_point='main'
is used, the module-level DECL_VAR that stores the ClassRef never runs,
so the constructor lookup in _handle_call_ctor fails to find the class
in the scope chain and falls through to symbolic.
"""

from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.refs.class_ref import ClassRef
from interpreter.run import run
from interpreter.var_name import VarName
from interpreter.vm.vm import Pointer


class TestCallCtorDispatch:
    """CALL_CTOR should resolve constructors via the registry, not just scope."""

    def test_java_constructor_creates_heap_object_when_entering_main_directly(self):
        """When entry_point='main', new Dog('Buddy') should produce a Pointer,
        not a SymbolicValue."""
        source = """
public class Dog {
    String name;
    Dog(String n) {
        this.name = n;
    }
    public static void main(String[] args) {
        Dog d = new Dog("Buddy");
    }
}
"""
        vm = run(source, language=Language.JAVA, entry_point="main", max_steps=50)
        d_val = vm.current_frame.local_vars[VarName("d")]
        assert isinstance(
            d_val.value, Pointer
        ), f"Expected Dog d to be a Pointer (heap object), got {type(d_val.value).__name__}: {d_val.value}"

    def test_java_constructor_runs_init_body(self):
        """The constructor body should execute: this.name = n should store 'Buddy'
        in the heap object's 'name' field."""
        source = """
public class Dog {
    String name;
    Dog(String n) {
        this.name = n;
    }
    public static void main(String[] args) {
        Dog d = new Dog("Buddy");
    }
}
"""
        vm = run(source, language=Language.JAVA, entry_point="main", max_steps=50)
        d_val = vm.current_frame.local_vars[VarName("d")]
        assert isinstance(
            d_val.value, Pointer
        ), f"Expected Pointer, got {type(d_val.value).__name__}: {d_val.value}"
        heap_obj = vm.heap_get(d_val.value.base)
        name_val = heap_obj.fields[FieldName("name")]
        raw_name = name_val.value if hasattr(name_val, "value") else name_val
        assert raw_name == "Buddy", f"Expected heap_obj.name == 'Buddy', got {raw_name}"

    def test_java_inner_class_constructor_resolves(self):
        """Inner classes defined in the same file should also resolve
        even when jumping to main directly."""
        source = """
public class App {
    public static class Point {
        int x;
        int y;
        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }
    }
    public static void main(String[] args) {
        Point p = new Point(10, 20);
    }
}
"""
        vm = run(source, language=Language.JAVA, entry_point="main", max_steps=50)
        p_val = vm.current_frame.local_vars[VarName("p")]
        assert isinstance(
            p_val.value, Pointer
        ), f"Expected Point p to be a Pointer, got {type(p_val.value).__name__}: {p_val.value}"

    def test_constructor_without_entry_point_works(self):
        """When NOT using entry_point (running from module top), constructors
        should already work because module-level code sets up ClassRefs."""
        source = """
public class Cat {
    String name;
    Cat(String n) {
        this.name = n;
    }
}
"""
        vm = run(source, language=Language.JAVA, max_steps=50)
        # Module-level code should have declared 'Cat' as a ClassRef
        cat_val = vm.current_frame.local_vars[VarName("Cat")]
        assert isinstance(
            cat_val.value, ClassRef
        ), f"Expected ClassRef, got {type(cat_val.value).__name__}"


class TestEntryPointFullChain:
    """Full end-to-end: construct objects, mutate fields, call methods,
    verify concrete values — across Java, Python, and Kotlin."""

    def _unwrap(self, tv):
        """Extract raw value from TypedValue."""
        return tv.value if hasattr(tv, "value") else tv

    def test_java_multi_object_construction_and_method_dispatch(self):
        """Construct two Dog objects with different args, call methods on each,
        verify concrete return values."""
        source = """
public class Dog {
    String name;
    int age;
    Dog(String n, int a) {
        this.name = n;
        this.age = a;
    }
    public String getName() {
        return this.name;
    }
    public int getAge() {
        return this.age;
    }
    public static void main(String[] args) {
        Dog d1 = new Dog("Buddy", 3);
        Dog d2 = new Dog("Rex", 5);
        String n1 = d1.getName();
        String n2 = d2.getName();
        int a1 = d1.getAge();
        int a2 = d2.getAge();
    }
}
"""
        vm = run(source, language=Language.JAVA, entry_point="main", max_steps=200)

        # Both dogs are heap-allocated Pointers
        d1 = vm.current_frame.local_vars[VarName("d1")]
        d2 = vm.current_frame.local_vars[VarName("d2")]
        assert isinstance(d1.value, Pointer)
        assert isinstance(d2.value, Pointer)
        assert d1.value.base != d2.value.base  # distinct heap addresses

        # Constructor bodies executed — fields written to heap
        heap1 = vm.heap_get(d1.value.base)
        heap2 = vm.heap_get(d2.value.base)
        assert self._unwrap(heap1.fields[FieldName("name")]) == "Buddy"
        assert self._unwrap(heap1.fields[FieldName("age")]) == 3
        assert self._unwrap(heap2.fields[FieldName("name")]) == "Rex"
        assert self._unwrap(heap2.fields[FieldName("age")]) == 5

        # Method dispatch returned concrete values
        assert self._unwrap(vm.current_frame.local_vars[VarName("n1")]) == "Buddy"
        assert self._unwrap(vm.current_frame.local_vars[VarName("n2")]) == "Rex"
        assert self._unwrap(vm.current_frame.local_vars[VarName("a1")]) == 3
        assert self._unwrap(vm.current_frame.local_vars[VarName("a2")]) == 5

    def test_python_constructor_and_method_via_entry_point(self):
        """Python class with entry_point='main' — construct, call method,
        verify concrete return value."""
        source = """
class Dog:
    def __init__(self, name, age):
        self.name = name
        self.age = age
    def get_name(self):
        return self.name

def main():
    d = Dog("Buddy", 3)
    n = d.get_name()
"""
        vm = run(source, language=Language.PYTHON, entry_point="main", max_steps=100)

        d = vm.current_frame.local_vars[VarName("d")]
        assert isinstance(d.value, Pointer)

        heap = vm.heap_get(d.value.base)
        assert self._unwrap(heap.fields[FieldName("name")]) == "Buddy"
        assert self._unwrap(heap.fields[FieldName("age")]) == 3

        n = vm.current_frame.local_vars[VarName("n")]
        assert self._unwrap(n) == "Buddy"

    def test_kotlin_constructor_and_method_via_entry_point(self):
        """Kotlin data-like class with entry_point='main' — construct,
        call method, verify concrete return value."""
        source = """
class Dog(val name: String, val age: Int) {
    fun getName(): String {
        return this.name
    }
}
fun main() {
    val d = Dog("Buddy", 3)
    val n = d.getName()
}
"""
        vm = run(source, language=Language.KOTLIN, entry_point="main", max_steps=100)

        d = vm.current_frame.local_vars[VarName("d")]
        assert isinstance(d.value, Pointer)

        heap = vm.heap_get(d.value.base)
        assert self._unwrap(heap.fields[FieldName("name")]) == "Buddy"
        assert self._unwrap(heap.fields[FieldName("age")]) == 3

        n = vm.current_frame.local_vars[VarName("n")]
        assert self._unwrap(n) == "Buddy"

    def test_java_sequential_construction_and_field_mutation(self):
        """Construct, mutate a field via setter, verify mutation persists."""
        source = """
public class Counter {
    int count;
    Counter(int initial) {
        this.count = initial;
    }
    public void increment() {
        this.count = this.count + 1;
    }
    public int getCount() {
        return this.count;
    }
    public static void main(String[] args) {
        Counter c = new Counter(10);
        c.increment();
        c.increment();
        int result = c.getCount();
    }
}
"""
        vm = run(source, language=Language.JAVA, entry_point="main", max_steps=200)

        c = vm.current_frame.local_vars[VarName("c")]
        assert isinstance(c.value, Pointer)

        # After two increments from 10, count should be 12
        result = vm.current_frame.local_vars[VarName("result")]
        assert self._unwrap(result) == 12

    def test_csharp_constructor_and_method_via_entry_point(self):
        """C# class with entry_point='Main'."""
        source = """
class Dog {
    string name;
    int age;
    Dog(string n, int a) { this.name = n; this.age = a; }
    public string getName() { return this.name; }
    public static void Main(string[] args) {
        Dog d = new Dog("Buddy", 3);
        string n = d.getName();
    }
}
"""
        vm = run(source, language=Language.CSHARP, entry_point="Main", max_steps=150)

        d = vm.current_frame.local_vars[VarName("d")]
        assert isinstance(d.value, Pointer)

        heap = vm.heap_get(d.value.base)
        assert self._unwrap(heap.fields[FieldName("name")]) == "Buddy"
        assert self._unwrap(heap.fields[FieldName("age")]) == 3

        n = vm.current_frame.local_vars[VarName("n")]
        assert self._unwrap(n) == "Buddy"

    def test_scala_constructor_and_method_via_entry_point(self):
        """Scala class with entry_point='main'."""
        source = """
class Dog(val name: String, val age: Int) {
    def getName(): String = this.name
}
object Main {
    def main(args: Array[String]): Unit = {
        val d = new Dog("Buddy", 3)
        val n = d.getName()
    }
}
"""
        vm = run(source, language=Language.SCALA, entry_point="main", max_steps=150)

        d = vm.current_frame.local_vars[VarName("d")]
        assert isinstance(d.value, Pointer)

        heap = vm.heap_get(d.value.base)
        assert self._unwrap(heap.fields[FieldName("name")]) == "Buddy"
        assert self._unwrap(heap.fields[FieldName("age")]) == 3

        n = vm.current_frame.local_vars[VarName("n")]
        assert self._unwrap(n) == "Buddy"

    def test_typescript_constructor_and_method_via_entry_point(self):
        """TypeScript class with entry_point='main'."""
        source = """
class Dog {
    name: string;
    age: number;
    constructor(n: string, a: number) {
        this.name = n;
        this.age = a;
    }
    getName(): string {
        return this.name;
    }
}
function main() {
    let d = new Dog("Buddy", 3);
    let n = d.getName();
}
"""
        vm = run(
            source, language=Language.TYPESCRIPT, entry_point="main", max_steps=150
        )

        d = vm.current_frame.local_vars[VarName("d")]
        assert isinstance(d.value, Pointer)

        heap = vm.heap_get(d.value.base)
        assert self._unwrap(heap.fields[FieldName("name")]) == "Buddy"
        assert self._unwrap(heap.fields[FieldName("age")]) == 3

        n = vm.current_frame.local_vars[VarName("n")]
        assert self._unwrap(n) == "Buddy"

    def test_javascript_constructor_and_method_via_entry_point(self):
        """JavaScript class with entry_point='main'."""
        source = """
class Dog {
    constructor(n, a) {
        this.name = n;
        this.age = a;
    }
    getName() {
        return this.name;
    }
}
function main() {
    let d = new Dog("Buddy", 3);
    let n = d.getName();
}
"""
        vm = run(
            source, language=Language.JAVASCRIPT, entry_point="main", max_steps=150
        )

        d = vm.current_frame.local_vars[VarName("d")]
        assert isinstance(d.value, Pointer)

        heap = vm.heap_get(d.value.base)
        assert self._unwrap(heap.fields[FieldName("name")]) == "Buddy"
        assert self._unwrap(heap.fields[FieldName("age")]) == 3

        n = vm.current_frame.local_vars[VarName("n")]
        assert self._unwrap(n) == "Buddy"

    def test_ruby_constructor_and_method_via_entry_point(self):
        """Ruby class with entry_point='main'."""
        source = """
class Dog
    def initialize(name, age)
        @name = name
        @age = age
    end
    def get_name
        return @name
    end
end
def main
    d = Dog.new("Buddy", 3)
    n = d.get_name
end
"""
        vm = run(source, language=Language.RUBY, entry_point="main", max_steps=150)

        d = vm.current_frame.local_vars[VarName("d")]
        assert isinstance(d.value, Pointer)

        n = vm.current_frame.local_vars[VarName("n")]
        assert self._unwrap(n) == "Buddy"

    def test_php_constructor_and_method_via_entry_point(self):
        """PHP class with entry_point='main'."""
        source = """<?php
class Dog {
    public $name;
    public $age;
    function __construct($n, $a) {
        $this->name = $n;
        $this->age = $a;
    }
    function getName() {
        return $this->name;
    }
}
function main() {
    $d = new Dog("Buddy", 3);
    $n = $d->getName();
}
"""
        vm = run(source, language=Language.PHP, entry_point="main", max_steps=150)

        d = vm.current_frame.local_vars[VarName("$d")]
        assert isinstance(d.value, Pointer)

        n = vm.current_frame.local_vars[VarName("$n")]
        assert self._unwrap(n) == "Buddy"

    def test_java_inner_class_full_chain(self):
        """Inner class constructor + field access + method call."""
        source = """
public class Geometry {
    public static class Point {
        int x;
        int y;
        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }
        public int sum() {
            return this.x + this.y;
        }
    }
    public static void main(String[] args) {
        Point p = new Point(10, 20);
        int s = p.sum();
    }
}
"""
        vm = run(source, language=Language.JAVA, entry_point="main", max_steps=100)

        p = vm.current_frame.local_vars[VarName("p")]
        assert isinstance(p.value, Pointer)

        heap = vm.heap_get(p.value.base)
        assert self._unwrap(heap.fields[FieldName("x")]) == 10
        assert self._unwrap(heap.fields[FieldName("y")]) == 20

        s = vm.current_frame.local_vars[VarName("s")]
        assert self._unwrap(s) == 30
