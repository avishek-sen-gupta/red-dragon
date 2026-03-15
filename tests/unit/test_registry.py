"""Tests for the function/class registry."""

from __future__ import annotations

from interpreter.cfg import build_cfg
from interpreter.func_ref import FuncRef
from interpreter.ir import IRInstruction, Opcode
from interpreter.registry import build_registry, _scan_classes


class TestScanClassesOverloads:
    """_scan_classes should accumulate all overloads per method name."""

    def test_single_method_returns_single_element_list(self):
        """A class with one method should have a single-element list for that name."""
        instructions = [
            IRInstruction(opcode=Opcode.CONST, operands=["<class:Foo@class_Foo_0>"]),
            IRInstruction(opcode=Opcode.LABEL, label="class_Foo_0"),
            IRInstruction(opcode=Opcode.CONST, operands=["func_greet_0"]),
            IRInstruction(opcode=Opcode.LABEL, label="end_class_Foo_0"),
        ]
        func_st = {"func_greet_0": FuncRef(name="greet", label="func_greet_0")}
        _classes, class_methods, _parents = _scan_classes(instructions, func_st)
        assert class_methods["Foo"]["greet"] == ["func_greet_0"]

    def test_overloaded_methods_accumulate(self):
        """Two methods with the same name should produce a two-element list."""
        instructions = [
            IRInstruction(opcode=Opcode.CONST, operands=["<class:Foo@class_Foo_0>"]),
            IRInstruction(opcode=Opcode.LABEL, label="class_Foo_0"),
            IRInstruction(opcode=Opcode.CONST, operands=["func_greet_0"]),
            IRInstruction(opcode=Opcode.CONST, operands=["func_greet_1"]),
            IRInstruction(opcode=Opcode.LABEL, label="end_class_Foo_0"),
        ]
        func_st = {
            "func_greet_0": FuncRef(name="greet", label="func_greet_0"),
            "func_greet_1": FuncRef(name="greet", label="func_greet_1"),
        }
        _classes, class_methods, _parents = _scan_classes(instructions, func_st)
        assert class_methods["Foo"]["greet"] == ["func_greet_0", "func_greet_1"]

    def test_different_methods_separate_lists(self):
        """Different method names should have independent lists."""
        instructions = [
            IRInstruction(opcode=Opcode.CONST, operands=["<class:Foo@class_Foo_0>"]),
            IRInstruction(opcode=Opcode.LABEL, label="class_Foo_0"),
            IRInstruction(opcode=Opcode.CONST, operands=["func_greet_0"]),
            IRInstruction(opcode=Opcode.CONST, operands=["func_farewell_0"]),
            IRInstruction(opcode=Opcode.LABEL, label="end_class_Foo_0"),
        ]
        func_st = {
            "func_greet_0": FuncRef(name="greet", label="func_greet_0"),
            "func_farewell_0": FuncRef(name="farewell", label="func_farewell_0"),
        }
        _classes, class_methods, _parents = _scan_classes(instructions, func_st)
        assert class_methods["Foo"]["greet"] == ["func_greet_0"]
        assert class_methods["Foo"]["farewell"] == ["func_farewell_0"]

    def test_three_overloads(self):
        """Three overloads of the same method should all be preserved."""
        instructions = [
            IRInstruction(opcode=Opcode.CONST, operands=["<class:Calc@class_Calc_0>"]),
            IRInstruction(opcode=Opcode.LABEL, label="class_Calc_0"),
            IRInstruction(opcode=Opcode.CONST, operands=["func_add_0"]),
            IRInstruction(opcode=Opcode.CONST, operands=["func_add_1"]),
            IRInstruction(opcode=Opcode.CONST, operands=["func_add_2"]),
            IRInstruction(opcode=Opcode.LABEL, label="end_class_Calc_0"),
        ]
        func_st = {
            "func_add_0": FuncRef(name="add", label="func_add_0"),
            "func_add_1": FuncRef(name="add", label="func_add_1"),
            "func_add_2": FuncRef(name="add", label="func_add_2"),
        }
        _classes, class_methods, _parents = _scan_classes(instructions, func_st)
        assert class_methods["Calc"]["add"] == [
            "func_add_0",
            "func_add_1",
            "func_add_2",
        ]


class TestBuildRegistryOverloads:
    """build_registry should produce class_methods with list[str] values."""

    def test_java_overloaded_constructors(self):
        """Java class with overloaded constructors should register both."""
        from interpreter.frontends import get_deterministic_frontend

        fe = get_deterministic_frontend("java")
        ir = fe.lower(b"""\
class Calc {
    int val;
    Calc() {
        this.val = 0;
    }
    Calc(int v) {
        this.val = v;
    }
    int add(int a, int b) {
        return a + b;
    }
    int add(int a, int b, int c) {
        return a + b + c;
    }
}
""")
        cfg = build_cfg(ir)
        reg = build_registry(ir, cfg, fe.func_symbol_table)
        assert "Calc" in reg.class_methods
        # __init__ should have 2 overloads (from two constructors)
        assert len(reg.class_methods["Calc"]["__init__"]) == 2
        # add should have 2 overloads
        assert len(reg.class_methods["Calc"]["add"]) == 2
