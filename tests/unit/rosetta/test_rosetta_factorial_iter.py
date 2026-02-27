"""Rosetta test: iterative factorial across all 15 deterministic frontends."""

import pytest

from interpreter.frontends import SUPPORTED_DETERMINISTIC_LANGUAGES
from interpreter.ir import Opcode

from tests.unit.rosetta.conftest import (
    parse_for_language,
    opcodes,
    find_all,
    assert_clean_lowering,
    assert_cross_language_consistency,
)

# ---------------------------------------------------------------------------
# Programs: iterative factorial in all 15 languages
# Each computes factorial(5) and stores the result.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def factorial(n):
    result = 1
    i = 2
    while i <= n:
        result = result * i
        i = i + 1
    return result

answer = factorial(5)
""",
    "javascript": """\
function factorial(n) {
    let result = 1;
    let i = 2;
    while (i <= n) {
        result = result * i;
        i = i + 1;
    }
    return result;
}

let answer = factorial(5);
""",
    "typescript": """\
function factorial(n: number): number {
    let result: number = 1;
    let i: number = 2;
    while (i <= n) {
        result = result * i;
        i = i + 1;
    }
    return result;
}

let answer: number = factorial(5);
""",
    "java": """\
class M {
    static int factorial(int n) {
        int result = 1;
        int i = 2;
        while (i <= n) {
            result = result * i;
            i = i + 1;
        }
        return result;
    }

    static int answer = factorial(5);
}
""",
    "ruby": """\
def factorial(n)
    result = 1
    i = 2
    while i <= n
        result = result * i
        i = i + 1
    end
    return result
end

answer = factorial(5)
""",
    "go": """\
package main

func factorial(n int) int {
    result := 1
    i := 2
    for i <= n {
        result = result * i
        i = i + 1
    }
    return result
}

func main() {
    answer := factorial(5)
    _ = answer
}
""",
    "php": """\
<?php
function factorial($n) {
    $result = 1;
    $i = 2;
    while ($i <= $n) {
        $result = $result * $i;
        $i = $i + 1;
    }
    return $result;
}

$answer = factorial(5);
?>
""",
    "csharp": """\
class M {
    static int factorial(int n) {
        int result = 1;
        int i = 2;
        while (i <= n) {
            result = result * i;
            i = i + 1;
        }
        return result;
    }

    static int answer = factorial(5);
}
""",
    "c": """\
int factorial(int n) {
    int result = 1;
    int i = 2;
    while (i <= n) {
        result = result * i;
        i = i + 1;
    }
    return result;
}

int answer = factorial(5);
""",
    "cpp": """\
int factorial(int n) {
    int result = 1;
    int i = 2;
    while (i <= n) {
        result = result * i;
        i = i + 1;
    }
    return result;
}

int answer = factorial(5);
""",
    "rust": """\
fn factorial(n: i32) -> i32 {
    let mut result: i32 = 1;
    let mut i: i32 = 2;
    while i <= n {
        result = result * i;
        i = i + 1;
    }
    return result;
}

let answer = factorial(5);
""",
    "kotlin": """\
fun factorial(n: Int): Int {
    var result: Int = 1
    var i: Int = 2
    while (i <= n) {
        result = result * i
        i = i + 1
    }
    return result
}

val answer = factorial(5)
""",
    "scala": """\
object M {
    def factorial(n: Int): Int = {
        var result: Int = 1
        var i: Int = 2
        while (i <= n) {
            result = result * i
            i = i + 1
        }
        return result
    }

    val answer = factorial(5)
}
""",
    "lua": """\
function factorial(n)
    local result = 1
    local i = 2
    while i <= n do
        result = result * i
        i = i + 1
    end
    return result
end

answer = factorial(5)
""",
    "pascal": """\
program M;

function factorial(n: integer): integer;
var
    result: integer;
    i: integer;
begin
    result := 1;
    i := 2;
    while i <= n do
    begin
        result := result * i;
        i := i + 1;
    end;
    factorial := result;
end;

var answer: integer;
begin
    answer := factorial(5);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.BRANCH_IF,
    Opcode.BINOP,
    Opcode.STORE_VAR,
}

MIN_INSTRUCTIONS = 10


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestFactorialIterLowering:
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

    def test_multiply_operator_present(self, language_ir):
        lang, ir = language_ir
        binops = find_all(ir, Opcode.BINOP)
        operators = {str(inst.operands[0]) for inst in binops if inst.operands}
        assert (
            "*" in operators
        ), f"[{lang}] expected '*' in BINOP operators: {operators}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestFactorialIterCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, PROGRAMS[lang]) for lang in PROGRAMS}

    def test_all_languages_covered(self):
        assert set(PROGRAMS.keys()) == set(SUPPORTED_DETERMINISTIC_LANGUAGES)

    def test_cross_language_consistency(self, all_results):
        assert_cross_language_consistency(
            all_results, required_opcodes=REQUIRED_OPCODES
        )
