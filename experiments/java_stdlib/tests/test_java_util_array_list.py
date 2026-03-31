from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from experiments.java_stdlib.stubs.java_util_array_list import ARRAY_LIST_MODULE
from experiments.java_stdlib.tests.conftest import run_with_stdlib, locals_of

_STDLIB = {Path("java/util/ArrayList.java"): ARRAY_LIST_MODULE}
_SRC = """
ArrayList list = new ArrayList();
list.add(42);
list.add(99);
int first = list.get(0);
int second = list.get(1);
int sz = list.size();
"""


class TestArrayListExports:
    def test_exports_init(self):
        assert FuncName("__init__") in ARRAY_LIST_MODULE.exports.functions

    def test_exports_add(self):
        assert FuncName("add") in ARRAY_LIST_MODULE.exports.functions

    def test_exports_get(self):
        assert FuncName("get") in ARRAY_LIST_MODULE.exports.functions

    def test_exports_size(self):
        assert FuncName("size") in ARRAY_LIST_MODULE.exports.functions

    def test_exports_is_empty(self):
        assert FuncName("isEmpty") in ARRAY_LIST_MODULE.exports.functions

    def test_exports_class(self):
        assert ClassName("ArrayList") in ARRAY_LIST_MODULE.exports.classes


class TestArrayListExecution:
    def test_get_first_element(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("first")] == 42

    def test_get_second_element(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("second")] == 99

    def test_size_after_two_adds(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("sz")] == 2

    def test_is_empty_on_fresh_list(self):
        vm = run_with_stdlib(
            "ArrayList list = new ArrayList(); boolean empty = list.isEmpty();",
            _STDLIB,
        )
        assert locals_of(vm)[VarName("empty")] == True  # noqa: E712
