"""Integration tests for TypeScript frontend execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_ts(source: str, max_steps: int = 200):
    vm = run(source, language=Language.TYPESCRIPT, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestTSTypeAssertionExecution:
    def test_type_assertion_passes_value_through(self):
        """<number>x should pass the value of x through."""
        locals_ = _run_ts("let x = 42;\nlet y = <number>x;")
        assert locals_["y"] == 42

    def test_type_assertion_string(self):
        """<string>val should pass string value through."""
        locals_ = _run_ts('let s = "hello";\nlet t = <string>s;')
        assert locals_["t"] == "hello"


class TestTSFunctionSignatureExecution:
    """Overload signatures should not block execution of the implementation."""

    def test_overload_implementation_executes(self):
        locals_ = _run_ts("""
            function add(a: number, b: number): number;
            function add(a: string, b: string): string;
            function add(a: any, b: any): any { return a + b; }
            let result = add(3, 4);
            """)
        assert locals_["result"] == 7


class TestTSAmbientDeclarationExecution:
    """Ambient declarations should not block subsequent code."""

    def test_declare_const_does_not_block(self):
        locals_ = _run_ts("""
            declare const DEBUG: boolean;
            let x = 42;
            """)
        assert locals_["x"] == 42

    def test_declare_function_does_not_block(self):
        locals_ = _run_ts("""
            declare function externalLog(msg: string): void;
            let y = "hello";
            """)
        assert locals_["y"] == "hello"


class TestTSInstantiationExpressionExecution:
    """instantiation_expression should pass through the function reference."""

    def test_instantiated_function_is_callable(self):
        locals_ = _run_ts("""
            function identity(x: any): any { return x; }
            const strId = identity<string>;
            let result = strId("hello");
            """)
        assert locals_["result"] == "hello"

    def test_instantiated_function_with_number(self):
        locals_ = _run_ts("""
            function double(x: any): any { return x * 2; }
            const numDouble = double<number>;
            let result = numDouble(21);
            """)
        assert locals_["result"] == 42


class TestTSInterfacePropertySignatureExecution:
    """Interface property_signature should seed types without blocking execution."""

    def test_code_after_interface_with_properties_executes(self):
        locals_ = _run_ts("""
            interface Config {
                name: string;
                level: number;
                compute(): number;
            }
            let x = 99;
            """)
        assert locals_["x"] == 99
