"""Tests for class name dereference in new_object and Type[] metatype seeding."""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.frontends.javascript import JavaScriptFrontend
from interpreter.frontends.typescript import TypeScriptFrontend
from interpreter.parser import TreeSitterParserFactory
from interpreter.run import run
from interpreter.types.type_expr import ParameterizedType, ScalarType, metatype
from interpreter.types.typed_value import unwrap_locals
from interpreter.vm.vm_types import Pointer


def _run_js(source: str, max_steps: int = 200):
    vm = run(source, language=Language.JAVASCRIPT, max_steps=max_steps)
    return vm


def _parse_js_with_types(source: str):
    frontend = JavaScriptFrontend(TreeSitterParserFactory(), "javascript")
    ir = frontend.lower(source.encode("utf-8"))
    return ir, frontend.type_env_builder


def _parse_ts_with_types(source: str):
    frontend = TypeScriptFrontend(TreeSitterParserFactory(), "typescript")
    ir = frontend.lower(source.encode("utf-8"))
    return ir, frontend.type_env_builder


class TestNewObjectDereference:
    """new_object should dereference variables to find the canonical class name."""

    def test_anon_class_heap_type_hint(self):
        """Heap object created via `new Foo()` where Foo holds an anonymous class
        should have the canonical class name as type_hint, not the variable name."""
        vm = _run_js("""
            const Foo = class { constructor() {} };
            let obj = new Foo();
            """)
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        obj_ptr = locals_[VarName("obj")]
        assert isinstance(obj_ptr, Pointer)
        type_hint = vm.heap[obj_ptr.base].type_hint
        assert (
            str(type_hint) != "Foo"
        ), "type_hint should be the canonical class name, not the variable alias"
        assert "__anon_class_" in str(
            type_hint
        ), f"expected canonical anonymous class name, got: {type_hint}"

    def test_named_class_heap_type_hint(self):
        """Regular class declaration should still use its own name as type_hint."""
        vm = _run_js("""
            class Bar { constructor() {} }
            let obj = new Bar();
            """)
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        obj_ptr = locals_[VarName("obj")]
        assert isinstance(obj_ptr, Pointer)
        assert vm.heap[obj_ptr.base].type_hint == "Bar"

    def test_reassigned_class_ref(self):
        """const B = A where A is a named class — new B() should resolve to A."""
        vm = _run_js("""
            class Original { constructor(x) { this.x = x; } }
            const Alias = Original;
            let obj = new Alias(42);
            let result = obj.x;
            """)
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_[VarName("result")] == 42


class TestClassMetatypeSeeding:
    """Class declarations and expressions should seed Type[ClassName] metatype."""

    def test_js_class_declaration_seeds_metatype(self):
        _, teb = _parse_js_with_types("class Foo { constructor() {} }")
        assert teb.var_types["Foo"] == ParameterizedType("Type", (ScalarType("Foo"),))

    def test_js_anon_class_expression_seeds_register_metatype(self):
        _, teb = _parse_js_with_types("const Foo = class { constructor() {} };")
        # The register holding the class ref should have Type[__anon_class_*]
        metatype_regs = [
            (reg, t)
            for reg, t in teb.register_types.items()
            if isinstance(t, ParameterizedType) and t.constructor == "Type"
        ]
        assert (
            len(metatype_regs) >= 1
        ), f"Expected Type[] register, got: {teb.register_types}"

    def test_ts_class_declaration_seeds_metatype(self):
        _, teb = _parse_ts_with_types(
            "class Greeter { greet(): string { return 'hi'; } }"
        )
        assert teb.var_types["Greeter"] == ParameterizedType(
            "Type", (ScalarType("Greeter"),)
        )

    def test_ts_interface_seeds_metatype(self):
        _, teb = _parse_ts_with_types("interface Shape { area(): number; }")
        assert teb.var_types["Shape"] == ParameterizedType(
            "Type", (ScalarType("Shape"),)
        )

    def test_metatype_convenience_constructor(self):
        result = metatype(ScalarType("Foo"))
        assert result == ParameterizedType("Type", (ScalarType("Foo"),))
        assert str(result) == "Type[Foo]"
