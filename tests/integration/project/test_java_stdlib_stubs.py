"""Integration tests for Java stdlib stubs (ArrayList, HashMap, Math, String, System).

Ported from experiments/java_stdlib/tests/ into the main test suite.
These exercise the hand-written IR stubs for common Java standard library classes,
verifying that they produce concrete values (not symbolics) when linked and executed.
"""

import math
from pathlib import Path

import pytest

from interpreter.class_name import ClassName
from interpreter.constants import Language
from interpreter.field_name import FieldName
from interpreter.frontends import get_deterministic_frontend
from interpreter.func_name import FuncName
from interpreter.project.compiler import compile_module
from interpreter.project.entry_point import EntryPoint
from interpreter.project.linker import link_modules
from interpreter.project.types import ExportTable, ModuleUnit
from interpreter.run import run_linked
from interpreter.types.typed_value import unwrap, unwrap_locals
from interpreter.var_name import VarName
from interpreter.vm.vm_types import VMState

from experiments.java_stdlib.registry import STDLIB_REGISTRY
from experiments.java_stdlib.stubs.java_io_print_stream import PRINT_STREAM_MODULE
from experiments.java_stdlib.stubs.java_lang_math import MATH_MODULE
from experiments.java_stdlib.stubs.java_lang_string import STRING_MODULE
from experiments.java_stdlib.stubs.java_lang_system import SYSTEM_MODULE
from experiments.java_stdlib.stubs.java_util_array_list import ARRAY_LIST_MODULE
from experiments.java_stdlib.stubs.java_util_hash_map import HASH_MAP_MODULE

# ── Helpers ───────────────────────────────────────────────────────


def _run_with_stdlib(
    java_source: str,
    stdlib_modules: dict[Path, ModuleUnit],
    max_steps: int = 500,
) -> VMState:
    """Compile java_source, link with stdlib_modules, execute, return VMState."""
    frontend = get_deterministic_frontend(Language.JAVA)
    user_ir = frontend.lower(java_source.encode())
    user_path = Path("Main.java")
    user_module = ModuleUnit(
        path=user_path,
        language=Language.JAVA,
        ir=tuple(user_ir),
        exports=ExportTable(),
        imports=(),
    )
    all_modules = {**stdlib_modules, user_path: user_module}
    linked = link_modules(
        modules=all_modules,
        import_graph={p: [] for p in all_modules},
        project_root=Path("."),
        topo_order=list(stdlib_modules.keys()) + [user_path],
        language=Language.JAVA,
    )
    return run_linked(
        linked,
        entry_point=EntryPoint.top_level(),
        max_steps=max_steps,
    )


def _run_class_with_stdlib(
    java_source: str,
    stdlib_modules: dict[Path, ModuleUnit],
    max_steps: int = 500,
) -> VMState:
    """Compile a full Java class, link with stdlib_modules, execute main()."""
    user_path = Path("Main.java")
    user_module = compile_module(user_path, Language.JAVA, source=java_source.encode())
    all_modules = {**stdlib_modules, user_path: user_module}
    linked = link_modules(
        modules=all_modules,
        import_graph={p: [] for p in all_modules},
        project_root=Path("."),
        topo_order=list(stdlib_modules.keys()) + [user_path],
        language=Language.JAVA,
    )
    return run_linked(
        linked,
        entry_point=EntryPoint.function(lambda ref: ref.name == FuncName("main")),
        max_steps=max_steps,
    )


def _locals(vm: VMState) -> dict:
    return unwrap_locals(vm.call_stack[0].local_vars)


_ALL = STDLIB_REGISTRY
_FIELD_VALUE = FieldName("value")

# ── Registry ──────────────────────────────────────────────────────


class TestStdlibRegistry:
    def test_array_list_present(self):
        assert Path("java/util/ArrayList.java") in STDLIB_REGISTRY

    def test_hash_map_present(self):
        assert Path("java/util/HashMap.java") in STDLIB_REGISTRY

    def test_math_present(self):
        assert Path("java/lang/Math.java") in STDLIB_REGISTRY

    def test_list_interface_aliases_array_list(self):
        assert (
            STDLIB_REGISTRY[Path("java/util/List.java")]
            is STDLIB_REGISTRY[Path("java/util/ArrayList.java")]
        )

    def test_map_interface_aliases_hash_map(self):
        assert (
            STDLIB_REGISTRY[Path("java/util/Map.java")]
            is STDLIB_REGISTRY[Path("java/util/HashMap.java")]
        )

    def test_collection_interface_aliases_array_list(self):
        assert (
            STDLIB_REGISTRY[Path("java/util/Collection.java")]
            is STDLIB_REGISTRY[Path("java/util/ArrayList.java")]
        )


# ── Math ──────────────────────────────────────────────────────────

_MATH = {Path("java/lang/Math.java"): MATH_MODULE}


class TestMathModuleExports:
    def test_exports_sqrt(self):
        assert FuncName("sqrt") in MATH_MODULE.exports.functions

    def test_exports_abs(self):
        assert FuncName("abs") in MATH_MODULE.exports.functions

    def test_exports_pow(self):
        assert FuncName("pow") in MATH_MODULE.exports.functions

    def test_exports_min(self):
        assert FuncName("min") in MATH_MODULE.exports.functions

    def test_exports_max(self):
        assert FuncName("max") in MATH_MODULE.exports.functions

    def test_exports_math_class(self):
        assert ClassName("Math") in MATH_MODULE.exports.classes


class TestMathExecution:
    def test_sqrt_nine(self):
        vm = _run_with_stdlib("double x = Math.sqrt(9.0);", _MATH)
        assert _locals(vm)[VarName("x")] == 3.0

    def test_abs_negative(self):
        vm = _run_with_stdlib("double x = Math.abs(-5.0);", _MATH)
        assert _locals(vm)[VarName("x")] == 5.0

    def test_pow_two_cubed(self):
        vm = _run_with_stdlib("double x = Math.pow(2.0, 3.0);", _MATH)
        assert _locals(vm)[VarName("x")] == 8.0

    def test_min_picks_smaller(self):
        vm = _run_with_stdlib("double x = Math.min(3.0, 7.0);", _MATH)
        assert _locals(vm)[VarName("x")] == 3.0

    def test_max_picks_larger(self):
        vm = _run_with_stdlib("double x = Math.max(3.0, 7.0);", _MATH)
        assert _locals(vm)[VarName("x")] == 7.0

    def test_sqrt_two(self):
        vm = _run_with_stdlib("double x = Math.sqrt(2.0);", _MATH)
        assert abs(_locals(vm)[VarName("x")] - math.sqrt(2)) < 1e-9

    def test_pow_fractional_result(self):
        vm = _run_with_stdlib("double x = Math.pow(4.0, 0.5);", _MATH)
        assert _locals(vm)[VarName("x")] == 2.0


# ── ArrayList ─────────────────────────────────────────────────────

_ARRAYLIST = {Path("java/util/ArrayList.java"): ARRAY_LIST_MODULE}
_ARRAYLIST_SRC = """
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
        vm = _run_with_stdlib(_ARRAYLIST_SRC, _ARRAYLIST)
        assert _locals(vm)[VarName("first")] == 42

    def test_get_second_element(self):
        vm = _run_with_stdlib(_ARRAYLIST_SRC, _ARRAYLIST)
        assert _locals(vm)[VarName("second")] == 99

    def test_size_after_two_adds(self):
        vm = _run_with_stdlib(_ARRAYLIST_SRC, _ARRAYLIST)
        assert _locals(vm)[VarName("sz")] == 2

    def test_is_empty_on_fresh_list(self):
        vm = _run_with_stdlib(
            "ArrayList list = new ArrayList(); boolean empty = list.isEmpty();",
            _ARRAYLIST,
        )
        assert _locals(vm)[VarName("empty")] == True  # noqa: E712


# ── HashMap ───────────────────────────────────────────────────────

_HASHMAP = {Path("java/util/HashMap.java"): HASH_MAP_MODULE}
_HASHMAP_SRC = """
HashMap map = new HashMap();
map.put("a", 1);
map.put("b", 2);
int val = map.get("a");
int sz = map.size();
boolean has = map.containsKey("b");
boolean missing = map.containsKey("c");
"""


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


class TestHashMapExecution:
    def test_get_value(self):
        vm = _run_with_stdlib(_HASHMAP_SRC, _HASHMAP)
        assert _locals(vm)[VarName("val")] == 1

    def test_size(self):
        vm = _run_with_stdlib(_HASHMAP_SRC, _HASHMAP)
        assert _locals(vm)[VarName("sz")] == 2

    def test_contains_key_present(self):
        vm = _run_with_stdlib(_HASHMAP_SRC, _HASHMAP)
        assert _locals(vm)[VarName("has")] is True

    def test_contains_key_absent(self):
        vm = _run_with_stdlib(_HASHMAP_SRC, _HASHMAP)
        assert _locals(vm)[VarName("missing")] is False


# ── String ────────────────────────────────────────────────────────

_STRING = {Path("java/lang/String.java"): STRING_MODULE}


class TestStringExports:
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


class TestStringExecution:
    def test_length(self):
        vm = _run_with_stdlib(
            'String s = new String("hello"); int n = s.length();',
            _STRING,
        )
        assert _locals(vm)[VarName("n")] == 5

    def test_to_upper_case(self):
        vm = _run_with_stdlib(
            'String s = new String("hello"); String u = s.toUpperCase();',
            _STRING,
        )
        ptr = _locals(vm)[VarName("u")]
        result_obj = vm.heap_get(ptr.base)
        assert unwrap(result_obj.fields[_FIELD_VALUE]) == "HELLO"

    def test_to_lower_case(self):
        vm = _run_with_stdlib(
            'String s = new String("WORLD"); String l = s.toLowerCase();',
            _STRING,
        )
        ptr = _locals(vm)[VarName("l")]
        result_obj = vm.heap_get(ptr.base)
        assert unwrap(result_obj.fields[_FIELD_VALUE]) == "world"

    def test_trim(self):
        vm = _run_with_stdlib(
            'String s = new String("  hi  "); String t = s.trim();',
            _STRING,
        )
        ptr = _locals(vm)[VarName("t")]
        result_obj = vm.heap_get(ptr.base)
        assert unwrap(result_obj.fields[_FIELD_VALUE]) == "hi"

    def test_contains_true(self):
        vm = _run_with_stdlib(
            'String s = new String("hello world"); String sub = new String("world"); boolean b = s.contains(sub);',
            _STRING,
        )
        assert _locals(vm)[VarName("b")]

    def test_contains_false(self):
        vm = _run_with_stdlib(
            'String s = new String("hello"); String sub = new String("xyz"); boolean b = s.contains(sub);',
            _STRING,
        )
        assert not _locals(vm)[VarName("b")]


# ── System / PrintStream ─────────────────────────────────────────

_SYSTEM = {
    Path("java/io/PrintStream.java"): PRINT_STREAM_MODULE,
    Path("java/lang/System.java"): SYSTEM_MODULE,
}


class TestSystemExports:
    def test_system_has_class(self):
        assert ClassName("System") in SYSTEM_MODULE.exports.classes

    def test_print_stream_exports_println(self):
        assert FuncName("println") in PRINT_STREAM_MODULE.exports.functions

    def test_print_stream_exports_print(self):
        assert FuncName("print") in PRINT_STREAM_MODULE.exports.functions

    def test_print_stream_has_class(self):
        assert ClassName("PrintStream") in PRINT_STREAM_MODULE.exports.classes


class TestSystemExecution:
    def test_println_produces_output(self, capsys):
        _run_with_stdlib('System.out.println("hello");', _SYSTEM)
        assert capsys.readouterr().out == "hello\n"


# ── End-to-End (all stubs combined) ──────────────────────────────


class TestEndToEnd:
    def test_arraylist_produces_concrete_not_symbolic(self):
        vm = _run_with_stdlib(
            """
            ArrayList list = new ArrayList();
            list.add(10);
            list.add(20);
            int x = list.get(0);
            int y = list.get(1);
            int total = x + y;
            """,
            _ALL,
            max_steps=1000,
        )
        locs = _locals(vm)
        assert locs[VarName("x")] == 10
        assert locs[VarName("y")] == 20
        assert locs[VarName("total")] == 30

    def test_math_result_flows_into_arithmetic(self):
        vm = _run_with_stdlib(
            "double root = Math.sqrt(16.0); double doubled = root + root;",
            _ALL,
        )
        locs = _locals(vm)
        assert locs[VarName("root")] == 4.0
        assert locs[VarName("doubled")] == 8.0

    def test_hashmap_roundtrip(self):
        vm = _run_with_stdlib(
            """
            HashMap map = new HashMap();
            map.put("score", 42);
            int result = map.get("score");
            """,
            _ALL,
            max_steps=1000,
        )
        assert _locals(vm)[VarName("result")] == 42

    def test_system_out_println(self, capsys):
        _run_with_stdlib('System.out.println("experiment works");', _ALL)
        assert "experiment works" in capsys.readouterr().out


class TestFullClassEndToEnd:
    def test_arraylist_in_main_method(self):
        vm = _run_class_with_stdlib(
            """
            import java.util.ArrayList;
            class Main {
                public static void main() {
                    ArrayList list = new ArrayList();
                    list.add(10);
                    list.add(20);
                    int x = list.get(0);
                    int y = list.get(1);
                    int total = x + y;
                }
            }
            """,
            _ALL,
            max_steps=1000,
        )
        locs = _locals(vm)
        assert locs[VarName("x")] == 10
        assert locs[VarName("y")] == 20
        assert locs[VarName("total")] == 30

    def test_math_in_main_method(self):
        vm = _run_class_with_stdlib(
            """
            class Main {
                public static void main() {
                    double root = Math.sqrt(16.0);
                    double doubled = root + root;
                }
            }
            """,
            _ALL,
        )
        locs = _locals(vm)
        assert locs[VarName("root")] == 4.0
        assert locs[VarName("doubled")] == 8.0

    def test_hashmap_in_main_method(self):
        vm = _run_class_with_stdlib(
            """
            import java.util.HashMap;
            class Main {
                public static void main() {
                    HashMap map = new HashMap();
                    map.put("score", 42);
                    int result = map.get("score");
                }
            }
            """,
            _ALL,
            max_steps=1000,
        )
        assert _locals(vm)[VarName("result")] == 42

    def test_system_out_println_in_main_method(self, capsys):
        _run_class_with_stdlib(
            """
            class Main {
                public static void main() {
                    System.out.println("hello from main");
                }
            }
            """,
            _ALL,
        )
        assert "hello from main" in capsys.readouterr().out
