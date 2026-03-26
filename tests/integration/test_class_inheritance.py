"""Integration tests for class inheritance — full pipeline execution.

Verifies that inherited methods dispatch correctly through the parent
chain across languages with class inheritance support.
"""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals


def _run(source: str, language: Language, max_steps: int = 500) -> dict:
    vm = run(source, language=language, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestJavaInheritance:
    def test_inherited_method(self):
        """Calling a method defined in the parent class on a child instance."""
        source = """\
class Animal {
    int legs;
    Animal(int l) {
        this.legs = l;
    }
    int getLegs() {
        return this.legs;
    }
}

class Dog extends Animal {
    Dog() {
        this.legs = 4;
    }
    int speak() {
        return 1;
    }
}

Dog d = new Dog();
int legs = d.getLegs();
int voice = d.speak();
"""
        vars_ = _run(source, Language.JAVA)
        assert vars_[VarName("legs")] == 4
        assert vars_[VarName("voice")] == 1

    def test_method_override(self):
        """A child class overrides a parent method — child version is called."""
        source = """\
class Base {
    int value() { return 1; }
}

class Derived extends Base {
    int value() { return 2; }
}

Derived d = new Derived();
int result = d.value();
"""
        vars_ = _run(source, Language.JAVA)
        assert vars_[VarName("result")] == 2

    def test_multi_level_inheritance(self):
        """C extends B extends A — methods inherited through the full chain."""
        source = """\
class A {
    int fromA() { return 10; }
}

class B extends A {
    int fromB() { return 20; }
}

class C extends B {
    int fromC() { return 30; }
}

C c = new C();
int a = c.fromA();
int b = c.fromB();
int cc = c.fromC();
"""
        vars_ = _run(source, Language.JAVA)
        assert vars_[VarName("a")] == 10
        assert vars_[VarName("b")] == 20
        assert vars_[VarName("cc")] == 30

    def test_polymorphic_dispatch(self):
        """Overridden method dispatches based on actual type, not declared type."""
        source = """\
class Shape {
    int area() { return 0; }
}

class Circle extends Shape {
    int radius;
    Circle(int r) { this.radius = r; }
    int area() { return 3 * this.radius * this.radius; }
}

class Square extends Shape {
    int side;
    Square(int s) { this.side = s; }
    int area() { return this.side * this.side; }
}

Shape s1 = new Circle(5);
int a1 = s1.area();

Shape s2 = new Square(4);
int a2 = s2.area();
"""
        vars_ = _run(source, Language.JAVA)
        assert vars_[VarName("a1")] == 75
        assert vars_[VarName("a2")] == 16

    def test_inherited_field_access_via_method(self):
        """A parent method reads a field set by the child constructor."""
        source = """\
class Vehicle {
    int speed;
    int getSpeed() { return this.speed; }
}

class Car extends Vehicle {
    Car(int s) { this.speed = s; }
}

Car c = new Car(120);
int s = c.getSpeed();
"""
        vars_ = _run(source, Language.JAVA)
        assert vars_[VarName("s")] == 120
