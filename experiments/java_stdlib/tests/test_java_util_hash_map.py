from pathlib import Path

from interpreter.class_name import ClassName
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from experiments.java_stdlib.stubs.java_util_hash_map import HASH_MAP_MODULE
from experiments.java_stdlib.tests.conftest import run_with_stdlib, locals_of


class TestHashMapExports:
    def test_exports_init(self):
        assert FuncName("__init__") in HASH_MAP_MODULE.exports.functions

    def test_exports_put(self):
        assert FuncName("put") in HASH_MAP_MODULE.exports.functions

    def test_exports_get(self):
        assert FuncName("get") in HASH_MAP_MODULE.exports.functions

    def test_exports_contains_key(self):
        assert FuncName("containsKey") in HASH_MAP_MODULE.exports.functions

    def test_exports_size(self):
        assert FuncName("size") in HASH_MAP_MODULE.exports.functions

    def test_exports_class(self):
        assert ClassName("HashMap") in HASH_MAP_MODULE.exports.classes


_STDLIB = {Path("java/util/HashMap.java"): HASH_MAP_MODULE}
_SRC = """
HashMap map = new HashMap();
map.put("a", 1);
map.put("b", 2);
int val = map.get("a");
int sz = map.size();
boolean has = map.containsKey("b");
boolean missing = map.containsKey("c");
"""


class TestHashMapExecution:
    def test_get_value(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("val")] == 1

    def test_size(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("sz")] == 2

    def test_contains_key_present(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("has")] is True

    def test_contains_key_absent(self):
        vm = run_with_stdlib(_SRC, _STDLIB)
        assert locals_of(vm)[VarName("missing")] is False
