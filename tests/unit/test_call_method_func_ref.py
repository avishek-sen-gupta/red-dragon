"""Tests for FUNC_REF dispatch via CALL_METHOD and CALL_UNKNOWN.

When a language invokes a method (e.g. `.call()`, `.apply()`) on a variable
holding a FUNC_REF, the VM should dispatch to the underlying user function
rather than falling through to the symbolic resolver.  Likewise, when
CALL_UNKNOWN targets a FUNC_REF (PHP arrow-function call), it should invoke
the function directly.
"""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.frontends import get_deterministic_frontend
from interpreter.ir import Opcode
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_program(source: str, language: Language, max_steps: int = 200) -> dict:
    """Run a program and return the main frame's local_vars."""
    vm = run(source, language=language, max_steps=max_steps)
    return unwrap_locals(vm.call_stack[0].local_vars)


def _has_func_ref(source: str, language: Language) -> bool:
    """Check whether the IR contains a CONST with a func_ label FUNC_REF."""
    fe = get_deterministic_frontend(language.value)
    ir = fe.lower(source.encode())
    return any(
        inst.opcode == Opcode.CONST
        and any(str(op).startswith("func_") for op in inst.operands)
        for inst in ir
    )


class TestCallMethodOnFuncRef:
    def test_java_lambda_apply(self):
        """Java lambda invoked via .apply() should dispatch through FUNC_REF."""
        source = """\
class M {
    static int make_adder(int x) {
        var adder = (int y) -> { return x + y; };
        return adder.apply(5);
    }

    static int answer = make_adder(10);
}
"""
        assert _has_func_ref(
            source, Language.JAVA
        ), "IR should contain a FUNC_REF for the lambda"
        vars_ = _run_program(source, Language.JAVA)
        assert vars_["answer"] == 15

    def test_ruby_lambda_call(self):
        """Ruby lambda invoked via .call() should dispatch through FUNC_REF."""
        source = """\
def make_adder(x)
    adder = -> (y) { return x + y }
    return adder.call(5)
end

answer = make_adder(10)
"""
        assert _has_func_ref(
            source, Language.RUBY
        ), "IR should contain a FUNC_REF for the lambda"
        vars_ = _run_program(source, Language.RUBY)
        assert vars_["answer"] == 15


class TestLambdaFuncRef:
    def test_csharp_lambda_produces_func_ref(self):
        """C# lambda stored in variable should produce a proper FUNC_REF."""
        source = """\
class M {
    static int make_adder(int x) {
        var adder = (int y) => { return x + y; };
        return adder(5);
    }

    static int answer = make_adder(10);
}
"""
        vars_ = _run_program(source, Language.CSHARP)
        assert vars_["answer"] == 15

    def test_csharp_local_function_closure(self):
        """C# local function capturing enclosing variable should produce correct result."""
        source = """\
class M {
    static int make_adder(int x) {
        int adder(int y) {
            return x + y;
        }
        return adder(5);
    }

    static int answer = make_adder(10);
}
"""
        vars_ = _run_program(source, Language.CSHARP)
        assert vars_["answer"] == 15

    def test_python_lambda_produces_func_ref(self):
        """Python lambda should produce a proper FUNC_REF and compute correct closure result."""
        source = """\
make_adder = lambda x: lambda y: x + y
add10 = make_adder(10)
answer = add10(5)
"""
        vars_ = _run_program(source, Language.PYTHON)
        assert vars_["answer"] == 15

    def test_kotlin_lambda_literal_binds_params(self):
        """Kotlin lambda literal should bind params and compute correct closure result."""
        source = """\
fun make_adder(x: Int): Int {
    val adder = { y: Int -> x + y }
    return adder(5)
}

val answer = make_adder(10)
"""
        vars_ = _run_program(source, Language.KOTLIN)
        assert vars_["answer"] == 15

    def test_scala_lambda_expression_binds_params(self):
        """Scala lambda expression should bind params and compute correct closure result."""
        source = """\
object M {
    def make_adder(x: Int): Int = {
        val adder = (y: Int) => x + y
        return adder(5)
    }

    val answer = make_adder(10)
}
"""
        vars_ = _run_program(source, Language.SCALA)
        assert vars_["answer"] == 15


class TestCallUnknownOnFuncRef:
    def test_php_arrow_function_call(self):
        """PHP arrow function invoked via dynamic call should dispatch through FUNC_REF."""
        source = """\
<?php
function make_adder($x) {
    $adder = fn($y) => $x + $y;
    return $adder;
}
$add10 = make_adder(10);
$answer = $add10(5);
?>
"""
        vars_ = _run_program(source, Language.PHP)
        assert vars_["$answer"] == 15
