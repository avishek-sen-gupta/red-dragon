from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.field_name import FieldName
from interpreter.func_name import FuncName
from interpreter.types.typed_value import unwrap
from interpreter.var_name import VarName
from experiments.java_stdlib.stubs.java_lang_string import STRING_MODULE
from experiments.java_stdlib.tests.conftest import run_with_stdlib, locals_of

_STDLIB = {Path("java/lang/String.java"): STRING_MODULE}
_VALUE = FieldName("value")


class TestStringModuleExports:
    def test_exports_to_upper_case(self):
        assert FuncName("toUpperCase") in STRING_MODULE.exports.functions

    def test_exports_to_lower_case(self):
        assert FuncName("toLowerCase") in STRING_MODULE.exports.functions

    def test_exports_length(self):
        assert FuncName("length") in STRING_MODULE.exports.functions

    def test_exports_trim(self):
        assert FuncName("trim") in STRING_MODULE.exports.functions

    def test_exports_contains(self):
        assert FuncName("contains") in STRING_MODULE.exports.functions

    def test_exports_init(self):
        assert FuncName("__init__") in STRING_MODULE.exports.functions

    def test_exports_string_class(self):
        assert ClassName("String") in STRING_MODULE.exports.classes


# TODO: symbolic input behavior not tested
class TestStringExecution:
    def test_length(self):
        vm = run_with_stdlib(
            'String s = new String("hello"); int n = s.length();',
            _STDLIB,
        )
        assert locals_of(vm)[VarName("n")] == 5

    def test_to_upper_case(self):
        vm = run_with_stdlib(
            'String s = new String("hello"); String u = s.toUpperCase();',
            _STDLIB,
        )
        ptr = locals_of(vm)[VarName("u")]
        result_obj = vm.heap_get(ptr.base)
        assert unwrap(result_obj.fields[_VALUE]) == "HELLO"

    def test_to_lower_case(self):
        vm = run_with_stdlib(
            'String s = new String("WORLD"); String l = s.toLowerCase();',
            _STDLIB,
        )
        ptr = locals_of(vm)[VarName("l")]
        result_obj = vm.heap_get(ptr.base)
        assert unwrap(result_obj.fields[_VALUE]) == "world"

    def test_trim(self):
        vm = run_with_stdlib(
            'String s = new String("  hi  "); String t = s.trim();',
            _STDLIB,
        )
        ptr = locals_of(vm)[VarName("t")]
        result_obj = vm.heap_get(ptr.base)
        assert unwrap(result_obj.fields[_VALUE]) == "hi"

    def test_contains_true(self):
        vm = run_with_stdlib(
            'String s = new String("hello world"); String sub = new String("world"); boolean b = s.contains(sub);',
            _STDLIB,
        )
        assert locals_of(vm)[VarName("b")]

    def test_contains_false(self):
        vm = run_with_stdlib(
            'String s = new String("hello"); String sub = new String("xyz"); boolean b = s.contains(sub);',
            _STDLIB,
        )
        assert not locals_of(vm)[VarName("b")]
