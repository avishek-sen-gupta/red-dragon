"""Tests for class instantiation across multiple frontends."""

from __future__ import annotations

import pytest

from interpreter.ir import Opcode
from interpreter.run import run


def _run_program(source: str, language: str = "python", max_steps: int = 300) -> dict:
    """Run a program and return the main frame's local_vars."""
    vm = run(source, language=language, max_steps=max_steps)
    return dict(vm.call_stack[0].local_vars)


class TestPythonClassInstantiation:
    def test_constructor_sets_fields(self):
        """Python class constructor should set instance fields."""
        source = """\
class Dog:
    def __init__(self, name):
        self.name = name

d = Dog("Rex")
answer = 42
"""
        vm = run(source, language="python", max_steps=300)
        vars_ = dict(vm.call_stack[0].local_vars)
        assert vars_["answer"] == 42
        assert "d" in vars_
        obj_addr = vars_["d"]
        assert obj_addr in vm.heap
        assert vm.heap[obj_addr].fields.get("name") == "Rex"

    def test_method_call_on_instance(self):
        """Method calls on instances should work."""
        source = """\
class Counter:
    def __init__(self):
        self.val = 0
    def inc(self):
        self.val = self.val + 1
    def get(self):
        return self.val

c = Counter()
c.inc()
c.inc()
c.inc()
answer = c.get()
"""
        vars_ = _run_program(source)
        assert vars_["answer"] == 3


class TestJavaClassInstantiation:
    def test_class_methods_registered(self):
        """Java class methods should be registered in the correct class scope."""
        from interpreter.frontends import get_deterministic_frontend
        from interpreter.cfg import build_cfg
        from interpreter.registry import build_registry

        fe = get_deterministic_frontend("java")
        ir = fe.lower(b"""\
class Dog {
    String name;
    Dog(String n) {
        this.name = n;
    }
}
""")
        cfg = build_cfg(ir)
        reg = build_registry(ir, cfg)
        assert "Dog" in reg.class_methods
        assert "__init__" in reg.class_methods["Dog"]

    def test_constructor_dispatched(self):
        """Java new expression should dispatch the constructor."""
        source = """\
class Dog {
    String name;
    Dog(String n) {
        this.name = n;
    }
}
Dog d = new Dog("Rex");
int answer = 42;
"""
        vm = run(source, language="java", max_steps=300)
        vars_ = dict(vm.call_stack[0].local_vars)
        assert vars_["answer"] == 42
        # d should be a heap address, not symbolic
        assert isinstance(vars_["d"], str)
        assert vars_["d"].startswith("obj_")

    def test_constructor_sets_fields(self):
        """Java constructor should set fields on the allocated object."""
        source = """\
class Dog {
    String name;
    Dog(String n) {
        this.name = n;
    }
}
Dog d = new Dog("Rex");
int answer = 42;
"""
        vm = run(source, language="java", max_steps=300)
        heap = vm.heap
        obj_addr = vm.call_stack[0].local_vars["d"]
        assert obj_addr in heap
        assert heap[obj_addr].fields.get("name") == "Rex"


class TestCSharpClassInstantiation:
    def test_class_methods_registered(self):
        """C# class methods should be registered in the correct class scope."""
        from interpreter.frontends import get_deterministic_frontend
        from interpreter.cfg import build_cfg
        from interpreter.registry import build_registry

        fe = get_deterministic_frontend("csharp")
        ir = fe.lower(b"""\
class Dog {
    string name;
    Dog(string n) {
        this.name = n;
    }
}
""")
        cfg = build_cfg(ir)
        reg = build_registry(ir, cfg)
        assert "Dog" in reg.class_methods
        assert "__init__" in reg.class_methods["Dog"]


class TestScalaClassInstantiation:
    def test_class_methods_registered(self):
        """Scala class methods should be registered in the correct class scope."""
        from interpreter.frontends import get_deterministic_frontend
        from interpreter.cfg import build_cfg
        from interpreter.registry import build_registry

        fe = get_deterministic_frontend("scala")
        ir = fe.lower(b"""\
class Dog(name: String) {
    def getName(): String = name
}
""")
        cfg = build_cfg(ir)
        reg = build_registry(ir, cfg)
        assert "Dog" in reg.class_methods
        assert "getName" in reg.class_methods["Dog"]


class TestJavaScriptClassInstantiation:
    def test_constructor_allocates_and_calls(self):
        """JavaScript new expression should allocate object and call constructor."""
        source = """\
class Dog {
    constructor(name) {
        this.name = name;
    }
}
let d = new Dog("Rex");
let answer = 42;
"""
        vm = run(source, language="javascript", max_steps=300)
        vars_ = dict(vm.call_stack[0].local_vars)
        assert vars_["answer"] == 42
        assert isinstance(vars_["d"], str)
        assert vars_["d"].startswith("obj_")
        # Constructor body must have run: this.name = "Rex"
        heap_obj = vm.heap[vars_["d"]]
        assert heap_obj.fields["name"] == "Rex"
