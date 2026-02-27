"""Rosetta test: iterative fibonacci across all 15 deterministic frontends."""

import pytest

from interpreter.frontends import SUPPORTED_DETERMINISTIC_LANGUAGES
from interpreter.ir import Opcode

from tests.unit.rosetta.conftest import (
    parse_for_language,
    opcodes,
    find_all,
    assert_clean_lowering,
    assert_cross_language_consistency,
    execute_for_language,
    extract_answer,
    STANDARD_EXECUTABLE_LANGUAGES,
)

# ---------------------------------------------------------------------------
# Programs: iterative fibonacci in all 15 languages
# Each computes fibonacci(10) and stores the result.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def fibonacci(n):
    a = 0
    b = 1
    i = 0
    while i < n:
        temp = a + b
        a = b
        b = temp
        i = i + 1
    return a

answer = fibonacci(10)
""",
    "javascript": """\
function fibonacci(n) {
    let a = 0;
    let b = 1;
    let i = 0;
    while (i < n) {
        let temp = a + b;
        a = b;
        b = temp;
        i = i + 1;
    }
    return a;
}

let answer = fibonacci(10);
""",
    "typescript": """\
function fibonacci(n: number): number {
    let a: number = 0;
    let b: number = 1;
    let i: number = 0;
    while (i < n) {
        let temp: number = a + b;
        a = b;
        b = temp;
        i = i + 1;
    }
    return a;
}

let answer: number = fibonacci(10);
""",
    "java": """\
class M {
    static int fibonacci(int n) {
        int a = 0;
        int b = 1;
        int i = 0;
        while (i < n) {
            int temp = a + b;
            a = b;
            b = temp;
            i = i + 1;
        }
        return a;
    }

    static int answer = fibonacci(10);
}
""",
    "ruby": """\
def fibonacci(n)
    a = 0
    b = 1
    i = 0
    while i < n
        temp = a + b
        a = b
        b = temp
        i = i + 1
    end
    return a
end

answer = fibonacci(10)
""",
    "go": """\
package main

func fibonacci(n int) int {
    a := 0
    b := 1
    i := 0
    for i < n {
        temp := a + b
        a = b
        b = temp
        i = i + 1
    }
    return a
}

func main() {
    answer := fibonacci(10)
    _ = answer
}
""",
    "php": """\
<?php
function fibonacci($n) {
    $a = 0;
    $b = 1;
    $i = 0;
    while ($i < $n) {
        $temp = $a + $b;
        $a = $b;
        $b = $temp;
        $i = $i + 1;
    }
    return $a;
}

$answer = fibonacci(10);
?>
""",
    "csharp": """\
class M {
    static int fibonacci(int n) {
        int a = 0;
        int b = 1;
        int i = 0;
        while (i < n) {
            int temp = a + b;
            a = b;
            b = temp;
            i = i + 1;
        }
        return a;
    }

    static int answer = fibonacci(10);
}
""",
    "c": """\
int fibonacci(int n) {
    int a = 0;
    int b = 1;
    int i = 0;
    while (i < n) {
        int temp = a + b;
        a = b;
        b = temp;
        i = i + 1;
    }
    return a;
}

int answer = fibonacci(10);
""",
    "cpp": """\
int fibonacci(int n) {
    int a = 0;
    int b = 1;
    int i = 0;
    while (i < n) {
        int temp = a + b;
        a = b;
        b = temp;
        i = i + 1;
    }
    return a;
}

int answer = fibonacci(10);
""",
    "rust": """\
fn fibonacci(n: i32) -> i32 {
    let mut a: i32 = 0;
    let mut b: i32 = 1;
    let mut i: i32 = 0;
    while i < n {
        let temp: i32 = a + b;
        a = b;
        b = temp;
        i = i + 1;
    }
    return a;
}

let answer = fibonacci(10);
""",
    "kotlin": """\
fun fibonacci(n: Int): Int {
    var a: Int = 0
    var b: Int = 1
    var i: Int = 0
    while (i < n) {
        var temp: Int = a + b
        a = b
        b = temp
        i = i + 1
    }
    return a
}

val answer = fibonacci(10)
""",
    "scala": """\
object M {
    def fibonacci(n: Int): Int = {
        var a: Int = 0
        var b: Int = 1
        var i: Int = 0
        while (i < n) {
            var temp: Int = a + b
            a = b
            b = temp
            i = i + 1
        }
        return a
    }

    val answer = fibonacci(10)
}
""",
    "lua": """\
function fibonacci(n)
    local a = 0
    local b = 1
    local i = 0
    while i < n do
        local temp = a + b
        a = b
        b = temp
        i = i + 1
    end
    return a
end

answer = fibonacci(10)
""",
    "pascal": """\
program M;

function fibonacci(n: integer): integer;
var
    a: integer;
    b: integer;
    temp: integer;
    i: integer;
begin
    a := 0;
    b := 1;
    i := 0;
    while i < n do
    begin
        temp := a + b;
        a := b;
        b := temp;
        i := i + 1;
    end;
    fibonacci := a;
end;

var answer: integer;
begin
    answer := fibonacci(10);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.BRANCH_IF,
    Opcode.BINOP,
    Opcode.STORE_VAR,
    Opcode.LOAD_VAR,
}

MIN_INSTRUCTIONS = 10


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestFibonacciIterLowering:
    @pytest.fixture(params=sorted(PROGRAMS.keys()), ids=lambda lang: lang)
    def language_ir(self, request):
        lang = request.param
        ir = parse_for_language(lang, PROGRAMS[lang])
        return lang, ir

    def test_clean_lowering(self, language_ir):
        lang, ir = language_ir
        assert_clean_lowering(
            ir,
            min_instructions=MIN_INSTRUCTIONS,
            required_opcodes=REQUIRED_OPCODES,
            language=lang,
        )

    def test_add_operator_present(self, language_ir):
        lang, ir = language_ir
        binops = find_all(ir, Opcode.BINOP)
        operators = {str(inst.operands[0]) for inst in binops if inst.operands}
        assert (
            "+" in operators
        ), f"[{lang}] expected '+' in BINOP operators: {operators}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestFibonacciIterCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, PROGRAMS[lang]) for lang in PROGRAMS}

    def test_all_languages_covered(self):
        assert set(PROGRAMS.keys()) == set(SUPPORTED_DETERMINISTIC_LANGUAGES)

    def test_cross_language_consistency(self, all_results):
        assert_cross_language_consistency(
            all_results, required_opcodes=REQUIRED_OPCODES
        )


# ---------------------------------------------------------------------------
# VM execution tests (parametrized over executable languages)
# ---------------------------------------------------------------------------

EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 55  # fib(10)


class TestFibonacciExecution:
    @pytest.fixture(
        params=sorted(EXECUTABLE_LANGUAGES), ids=lambda lang: lang, scope="class"
    )
    def execution_result(self, request):
        lang = request.param
        vm, stats = execute_for_language(lang, PROGRAMS[lang])
        return lang, vm, stats

    def test_correct_result(self, execution_result):
        lang, vm, _stats = execution_result
        answer = extract_answer(vm, lang)
        assert (
            answer == EXPECTED_ANSWER
        ), f"[{lang}] expected answer={EXPECTED_ANSWER}, got {answer}"

    def test_zero_llm_calls(self, execution_result):
        lang, _vm, stats = execution_result
        assert (
            stats.llm_calls == 0
        ), f"[{lang}] expected 0 LLM calls, got {stats.llm_calls}"
