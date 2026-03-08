"""Integration tests for simulating classes in C using structs with function pointers.

The classic C pattern: store function pointers inside structs to simulate
methods, vtables, and polymorphism.  Each test verifies the full pipeline:
C source → tree-sitter parse → IR lowering → VM execution.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run


def _run_c(source: str, max_steps: int = 800) -> dict:
    """Run a C program and return the top-level frame's local_vars."""
    vm = run(source, language=Language.C, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


class TestStructAsClass:
    def test_single_method(self):
        """Struct with one function pointer field acting as a method."""
        source = """\
struct Shape { int width; int height; };

int rect_area(struct Shape *self) {
    return self->width * self->height;
}

struct Shape s;
s.width = 6;
s.height = 7;
s.area = &rect_area;
int result = (*s.area)(&s);
"""
        vars_ = _run_c(source)
        assert vars_["result"] == 42

    def test_multiple_methods(self):
        """Struct with several function pointer fields simulating a full class."""
        source = """\
struct Counter { int count; };

void counter_increment(struct Counter *self) {
    self->count = self->count + 1;
}

void counter_add(struct Counter *self, int n) {
    self->count = self->count + n;
}

int counter_get(struct Counter *self) {
    return self->count;
}

struct Counter c;
c.count = 0;
c.increment = &counter_increment;
c.add = &counter_add;
c.get = &counter_get;

(*c.increment)(&c);
(*c.increment)(&c);
(*c.add)(&c, 10);
int result = (*c.get)(&c);
"""
        vars_ = _run_c(source)
        assert vars_["result"] == 12

    def test_constructor_pattern(self):
        """A function that initialises a struct and attaches method pointers."""
        source = """\
struct Vec2 { int x; int y; };

int vec2_dot(struct Vec2 *self, struct Vec2 *other) {
    return self->x * other->x + self->y * other->y;
}

int vec2_magnitude_sq(struct Vec2 *self) {
    return self->x * self->x + self->y * self->y;
}

void vec2_init(struct Vec2 *v, int x, int y) {
    v->x = x;
    v->y = y;
    v->dot = &vec2_dot;
    v->magnitude_sq = &vec2_magnitude_sq;
}

struct Vec2 a;
vec2_init(&a, 3, 4);
int mag = (*a.magnitude_sq)(&a);

struct Vec2 b;
vec2_init(&b, 1, 2);
int d = (*a.dot)(&a, &b);
"""
        vars_ = _run_c(source)
        assert vars_["mag"] == 25
        assert vars_["d"] == 11


class TestStructPolymorphism:
    def test_method_swap(self):
        """Reassigning a function pointer field changes which function is called."""
        source = """\
struct Animal { int legs; };

int dog_speak(struct Animal *self) {
    return 1;
}

int cat_speak(struct Animal *self) {
    return 2;
}

struct Animal a;
a.legs = 4;
a.speak = &dog_speak;
int r1 = (*a.speak)(&a);

a.speak = &cat_speak;
int r2 = (*a.speak)(&a);
"""
        vars_ = _run_c(source)
        assert vars_["r1"] == 1
        assert vars_["r2"] == 2

    def test_dispatch_via_shared_interface(self):
        """Two structs with the same function pointer field, each bound to
        a different implementation — dispatched through a common helper."""
        source = """\
struct Shape { int param; };

int circle_area(struct Shape *self) {
    return 3 * self->param * self->param;
}

int square_area(struct Shape *self) {
    return self->param * self->param;
}

int compute_area(struct Shape *s) {
    return (*s->area)(s);
}

struct Shape circle;
circle.param = 5;
circle.area = &circle_area;

struct Shape square;
square.param = 4;
square.area = &square_area;

int ca = compute_area(&circle);
int sa = compute_area(&square);
"""
        vars_ = _run_c(source)
        assert vars_["ca"] == 75
        assert vars_["sa"] == 16
