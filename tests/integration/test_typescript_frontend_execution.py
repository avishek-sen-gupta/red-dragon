"""Integration tests for TypeScript frontend execution."""

from __future__ import annotations

from interpreter.var_name import VarName
from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.project.entry_point import EntryPoint


def _run_ts(source: str, max_steps: int = 200):
    vm = run(
        source,
        language=Language.TYPESCRIPT,
        max_steps=max_steps,
        entry_point=EntryPoint.top_level(),
    )
    return unwrap_locals(vm.call_stack[0].local_vars)


class TestTSTypeAssertionExecution:
    def test_type_assertion_passes_value_through(self):
        """<number>x should pass the value of x through."""
        locals_ = _run_ts("let x = 42;\nlet y = <number>x;")
        assert locals_[VarName("y")] == 42

    def test_type_assertion_string(self):
        """<string>val should pass string value through."""
        locals_ = _run_ts('let s = "hello";\nlet t = <string>s;')
        assert locals_[VarName("t")] == "hello"


class TestTSFunctionSignatureExecution:
    """Overload signatures should not block execution of the implementation."""

    def test_overload_implementation_executes(self):
        locals_ = _run_ts("""
            function add(a: number, b: number): number;
            function add(a: string, b: string): string;
            function add(a: any, b: any): any { return a + b; }
            let result = add(3, 4);
            """)
        assert locals_[VarName("result")] == 7


class TestTSAmbientDeclarationExecution:
    """Ambient declarations should not block subsequent code."""

    def test_declare_const_does_not_block(self):
        locals_ = _run_ts("""
            declare const DEBUG: boolean;
            let x = 42;
            """)
        assert locals_[VarName("x")] == 42

    def test_declare_function_does_not_block(self):
        locals_ = _run_ts("""
            declare function externalLog(msg: string): void;
            let y = "hello";
            """)
        assert locals_[VarName("y")] == "hello"


class TestTSInstantiationExpressionExecution:
    """instantiation_expression should pass through the function reference."""

    def test_instantiated_function_is_callable(self):
        locals_ = _run_ts("""
            function identity(x: any): any { return x; }
            const strId = identity<string>;
            let result = strId("hello");
            """)
        assert locals_[VarName("result")] == "hello"

    def test_instantiated_function_with_number(self):
        locals_ = _run_ts("""
            function double(x: any): any { return x * 2; }
            const numDouble = double<number>;
            let result = numDouble(21);
            """)
        assert locals_[VarName("result")] == 42


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
        assert locals_[VarName("x")] == 99


class TestTSOptionalChainExecution:
    """Optional chaining (?.) short-circuits to None on null, accesses on non-null."""

    def test_optional_chain_on_object(self):
        locals_ = _run_ts('let obj = { name: "Alice" }; let result = obj?.name;')
        assert locals_[VarName("result")] == "Alice"

    def test_optional_chain_on_null_returns_none(self):
        locals_ = _run_ts("""
            let obj: any = null;
            let result = obj?.name;
            """)
        assert locals_[VarName("result")] is None

    def test_optional_chain_nested(self):
        locals_ = _run_ts("""
            let outer = { inner: { value: 42 } };
            let result: number = outer?.inner?.value;
            """)
        assert locals_[VarName("result")] == 42
