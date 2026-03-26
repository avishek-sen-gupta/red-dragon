"""Integration tests for default parameter resolution — end-to-end VM execution."""

from __future__ import annotations

from interpreter.constants import Language
from interpreter.run import run
from interpreter.types.typed_value import unwrap_locals
from interpreter.var_name import VarName


def _run(source: str, language: Language, max_steps: int = 500) -> tuple:
    """Run a program and return (vm, unwrapped local vars)."""
    vm = run(source, language=language, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


def _run_python(source: str, max_steps: int = 500) -> tuple:
    return _run(source, Language.PYTHON, max_steps)


class TestPythonDefaultParamExecution:
    """End-to-end default parameter tests via VM execution."""

    def test_string_default_used_when_no_arg(self):
        _, vars_ = _run_python("""\
def two_fer(name="you"):
    return "One for " + name + ", one for me."

answer = two_fer()""")
        assert vars_[VarName("answer")] == "One for you, one for me."

    def test_string_default_overridden_by_arg(self):
        _, vars_ = _run_python("""\
def two_fer(name="you"):
    return "One for " + name + ", one for me."

answer = two_fer("Alice")""")
        assert vars_[VarName("answer")] == "One for Alice, one for me."

    def test_integer_default(self):
        _, vars_ = _run_python("""\
def add_one(x=42):
    return x + 1

answer = add_one()""")
        assert vars_[VarName("answer")] == 43

    def test_integer_default_overridden(self):
        _, vars_ = _run_python("""\
def add_one(x=42):
    return x + 1

answer = add_one(10)""")
        assert vars_[VarName("answer")] == 11

    def test_mixed_required_and_default(self):
        _, vars_ = _run_python("""\
def greet(greeting, name="world"):
    return greeting + " " + name

answer = greet("hello")""")
        assert vars_[VarName("answer")] == "hello world"

    def test_mixed_required_and_default_both_provided(self):
        _, vars_ = _run_python("""\
def greet(greeting, name="world"):
    return greeting + " " + name

answer = greet("hi", "Alice")""")
        assert vars_[VarName("answer")] == "hi Alice"

    def test_multiple_defaults(self):
        _, vars_ = _run_python("""\
def pair(a="x", b="y"):
    return a + b

answer = pair()""")
        assert vars_[VarName("answer")] == "xy"

    def test_multiple_defaults_first_overridden(self):
        _, vars_ = _run_python("""\
def pair(a="x", b="y"):
    return a + b

answer = pair("A")""")
        assert vars_[VarName("answer")] == "Ay"

    def test_lambda_default_param(self):
        _, vars_ = _run_python("""\
f = lambda x="hi": x
answer = f()""")
        assert vars_[VarName("answer")] == "hi"

    def test_function_without_defaults_unchanged(self):
        _, vars_ = _run_python("""\
def add(a, b):
    return a + b

answer = add(3, 4)""")
        assert vars_[VarName("answer")] == 7


class TestJavaScriptDefaultParamExecution:
    """End-to-end default parameter tests for JavaScript."""

    def test_string_default_used_when_no_arg(self):
        _, vars_ = _run(
            'function greet(name = "you") { return "hello " + name; }\n'
            "let answer = greet();",
            Language.JAVASCRIPT,
        )
        assert vars_[VarName("answer")] == "hello you"

    def test_string_default_overridden(self):
        _, vars_ = _run(
            'function greet(name = "you") { return "hello " + name; }\n'
            'let answer = greet("Alice");',
            Language.JAVASCRIPT,
        )
        assert vars_[VarName("answer")] == "hello Alice"

    def test_mixed_required_and_default(self):
        _, vars_ = _run(
            'function greet(greeting, name = "world") {\n'
            '    return greeting + " " + name;\n'
            "}\n"
            'let answer = greet("hi");',
            Language.JAVASCRIPT,
        )
        assert vars_[VarName("answer")] == "hi world"


class TestTypeScriptDefaultParamExecution:
    """End-to-end default parameter tests for TypeScript."""

    def test_string_default_used_when_no_arg(self):
        _, vars_ = _run(
            'function greet(name: string = "you"): string {\n'
            '    return "hello " + name;\n'
            "}\n"
            "let answer: string = greet();",
            Language.TYPESCRIPT,
        )
        assert vars_[VarName("answer")] == "hello you"

    def test_string_default_overridden(self):
        _, vars_ = _run(
            'function greet(name: string = "you"): string {\n'
            '    return "hello " + name;\n'
            "}\n"
            'let answer: string = greet("Alice");',
            Language.TYPESCRIPT,
        )
        assert vars_[VarName("answer")] == "hello Alice"

    def test_mixed_required_and_default(self):
        _, vars_ = _run(
            'function greet(greeting: string, name: string = "world"): string {\n'
            '    return greeting + " " + name;\n'
            "}\n"
            'let answer: string = greet("hi");',
            Language.TYPESCRIPT,
        )
        assert vars_[VarName("answer")] == "hi world"


class TestRubyDefaultParamExecution:
    """End-to-end default parameter tests for Ruby."""

    def test_string_default_used_when_no_arg(self):
        _, vars_ = _run(
            'def greet(name = "you")\n'
            '    return "hello " + name\n'
            "end\n"
            "answer = greet()",
            Language.RUBY,
        )
        assert vars_[VarName("answer")] == "hello you"

    def test_string_default_overridden(self):
        _, vars_ = _run(
            'def greet(name = "you")\n'
            '    return "hello " + name\n'
            "end\n"
            'answer = greet("Alice")',
            Language.RUBY,
        )
        assert vars_[VarName("answer")] == "hello Alice"

    def test_mixed_required_and_default(self):
        _, vars_ = _run(
            'def greet(greeting, name = "world")\n'
            '    return greeting + " " + name\n'
            "end\n"
            'answer = greet("hi")',
            Language.RUBY,
        )
        assert vars_[VarName("answer")] == "hi world"


class TestCppDefaultParamExecution:
    """End-to-end default parameter tests for C++."""

    def test_string_default_used_when_no_arg(self):
        _, vars_ = _run(
            'string greet(string name = "you") {\n'
            '    return "hello " + name;\n'
            "}\n"
            "string answer = greet();",
            Language.CPP,
        )
        assert vars_[VarName("answer")] == "hello you"

    def test_string_default_overridden(self):
        _, vars_ = _run(
            'string greet(string name = "you") {\n'
            '    return "hello " + name;\n'
            "}\n"
            'string answer = greet("Alice");',
            Language.CPP,
        )
        assert vars_[VarName("answer")] == "hello Alice"

    def test_mixed_required_and_default(self):
        _, vars_ = _run(
            'string greet(string greeting, string name = "world") {\n'
            '    return greeting + " " + name;\n'
            "}\n"
            'string answer = greet("hi");',
            Language.CPP,
        )
        assert vars_[VarName("answer")] == "hi world"


class TestScalaDefaultParamExecution:
    """End-to-end default parameter tests for Scala."""

    def test_string_default_used_when_no_arg(self):
        _, vars_ = _run(
            "object M {\n"
            '    def greet(name: String = "you"): String = {\n'
            '        return "hello " + name\n'
            "    }\n"
            "    val answer = greet()\n"
            "}",
            Language.SCALA,
        )
        assert vars_[VarName("answer")] == "hello you"

    def test_string_default_overridden(self):
        _, vars_ = _run(
            "object M {\n"
            '    def greet(name: String = "you"): String = {\n'
            '        return "hello " + name\n'
            "    }\n"
            '    val answer = greet("Alice")\n'
            "}",
            Language.SCALA,
        )
        assert vars_[VarName("answer")] == "hello Alice"

    def test_mixed_required_and_default(self):
        _, vars_ = _run(
            "object M {\n"
            '    def greet(greeting: String, name: String = "world"): String = {\n'
            '        return greeting + " " + name\n'
            "    }\n"
            '    val answer = greet("hi")\n'
            "}",
            Language.SCALA,
        )
        assert vars_[VarName("answer")] == "hi world"


class TestPhpDefaultParamExecution:
    """End-to-end default parameter tests for PHP."""

    def test_string_default_used_when_no_arg(self):
        _, vars_ = _run(
            "<?php\n"
            'function greet($name = "you") {\n'
            '    return "hello " . $name;\n'
            "}\n"
            "$answer = greet();\n"
            "?>",
            Language.PHP,
        )
        assert vars_[VarName("$answer")] == "hello you"

    def test_string_default_overridden(self):
        _, vars_ = _run(
            "<?php\n"
            'function greet($name = "you") {\n'
            '    return "hello " . $name;\n'
            "}\n"
            '$answer = greet("Alice");\n'
            "?>",
            Language.PHP,
        )
        assert vars_[VarName("$answer")] == "hello Alice"

    def test_mixed_required_and_default(self):
        _, vars_ = _run(
            "<?php\n"
            'function greet($greeting, $name = "world") {\n'
            '    return $greeting . " " . $name;\n'
            "}\n"
            '$answer = greet("hi");\n'
            "?>",
            Language.PHP,
        )
        assert vars_[VarName("$answer")] == "hi world"


class TestCsharpDefaultParamExecution:
    """End-to-end default parameter tests for C#."""

    def test_string_default_used_when_no_arg(self):
        _, vars_ = _run(
            "class M {\n"
            '    static string greet(string name = "you") {\n'
            '        return "hello " + name;\n'
            "    }\n"
            "    static string answer = greet();\n"
            "}",
            Language.CSHARP,
        )
        assert vars_[VarName("answer")] == "hello you"

    def test_string_default_overridden(self):
        _, vars_ = _run(
            "class M {\n"
            '    static string greet(string name = "you") {\n'
            '        return "hello " + name;\n'
            "    }\n"
            '    static string answer = greet("Alice");\n'
            "}",
            Language.CSHARP,
        )
        assert vars_[VarName("answer")] == "hello Alice"

    def test_mixed_required_and_default(self):
        _, vars_ = _run(
            "class M {\n"
            '    static string greet(string greeting, string name = "world") {\n'
            '        return greeting + " " + name;\n'
            "    }\n"
            '    static string answer = greet("hi");\n'
            "}",
            Language.CSHARP,
        )
        assert vars_[VarName("answer")] == "hi world"


class TestKotlinDefaultParamExecution:
    """End-to-end default parameter tests for Kotlin."""

    def test_string_default_used_when_no_arg(self):
        _, vars_ = _run(
            'fun greet(name: String = "you"): String {\n'
            '    return "hello " + name\n'
            "}\n"
            "val answer = greet()",
            Language.KOTLIN,
        )
        assert vars_[VarName("answer")] == "hello you"

    def test_string_default_overridden(self):
        _, vars_ = _run(
            'fun greet(name: String = "you"): String {\n'
            '    return "hello " + name\n'
            "}\n"
            'val answer = greet("Alice")',
            Language.KOTLIN,
        )
        assert vars_[VarName("answer")] == "hello Alice"

    def test_mixed_required_and_default(self):
        _, vars_ = _run(
            'fun greet(greeting: String, name: String = "world"): String {\n'
            '    return greeting + " " + name\n'
            "}\n"
            'val answer = greet("hi")',
            Language.KOTLIN,
        )
        assert vars_[VarName("answer")] == "hi world"


class TestPascalDefaultParamExecution:
    """End-to-end default parameter tests for Pascal."""

    def test_string_default_used_when_no_arg(self):
        _, vars_ = _run(
            "program M;\n"
            "function greet(name: string = 'you'): string;\n"
            "begin\n"
            "    greet := 'hello ' + name;\n"
            "end;\n"
            "var answer: string;\n"
            "begin\n"
            "    answer := greet();\n"
            "end.",
            Language.PASCAL,
            max_steps=1000,
        )
        assert vars_[VarName("answer")] == "hello you"

    def test_string_default_overridden(self):
        _, vars_ = _run(
            "program M;\n"
            "function greet(name: string = 'you'): string;\n"
            "begin\n"
            "    greet := 'hello ' + name;\n"
            "end;\n"
            "var answer: string;\n"
            "begin\n"
            "    answer := greet('Alice');\n"
            "end.",
            Language.PASCAL,
            max_steps=1000,
        )
        assert vars_[VarName("answer")] == "hello Alice"

    def test_mixed_required_and_default(self):
        _, vars_ = _run(
            "program M;\n"
            "function greet(greeting: string; name: string = 'world'): string;\n"
            "begin\n"
            "    greet := greeting + ' ' + name;\n"
            "end;\n"
            "var answer: string;\n"
            "begin\n"
            "    answer := greet('hi');\n"
            "end.",
            Language.PASCAL,
            max_steps=1000,
        )
        assert vars_[VarName("answer")] == "hi world"
