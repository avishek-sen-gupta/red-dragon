"""Rosetta test: nested functions across all 15 deterministic frontends.

Verifies that the VM can execute programs with an inner helper function
called from an outer function:

    def inner(x): return x * 2
    def outer(x): return inner(x) + 5
    answer = outer(5)  → inner(5) + 5 = 10 + 5 = 15

Languages with true nested function support (Python, JS, TS, Ruby, Lua, Rust,
Go, Kotlin, Scala, PHP) define inner inside outer. Languages without nesting
(C, C++, Java, C#, Pascal) define inner and outer as sibling functions.
"""

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
# Programs: nested/inner functions in all 15 languages
# inner(x) returns x * 2, outer(x) returns inner(x) + 5.
# answer = outer(5) → 10 + 5 = 15.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def outer(x):
    def inner(y):
        return y * 2
    return inner(x) + 5

answer = outer(5)
""",
    "javascript": """\
function outer(x) {
    function inner(y) {
        return y * 2;
    }
    return inner(x) + 5;
}

let answer = outer(5);
""",
    "typescript": """\
function outer(x: number): number {
    function inner(y: number): number {
        return y * 2;
    }
    return inner(x) + 5;
}

let answer: number = outer(5);
""",
    "java": """\
class M {
    static int inner(int y) {
        return y * 2;
    }

    static int outer(int x) {
        return inner(x) + 5;
    }

    static int answer = outer(5);
}
""",
    "ruby": """\
def inner(y)
    return y * 2
end

def outer(x)
    return inner(x) + 5
end

answer = outer(5)
""",
    "go": """\
package main

func inner(y int) int {
    return y * 2
}

func outer(x int) int {
    return inner(x) + 5
}

func main() {
    answer := outer(5)
    _ = answer
}
""",
    "php": """\
<?php
function inner($y) {
    return $y * 2;
}

function outer($x) {
    return inner($x) + 5;
}

$answer = outer(5);
?>
""",
    "csharp": """\
class M {
    static int inner(int y) {
        return y * 2;
    }

    static int outer(int x) {
        return inner(x) + 5;
    }

    static int answer = outer(5);
}
""",
    "c": """\
int inner(int y) {
    return y * 2;
}

int outer(int x) {
    return inner(x) + 5;
}

int answer = outer(5);
""",
    "cpp": """\
int inner(int y) {
    return y * 2;
}

int outer(int x) {
    return inner(x) + 5;
}

int answer = outer(5);
""",
    "rust": """\
fn inner(y: i32) -> i32 {
    return y * 2;
}

fn outer(x: i32) -> i32 {
    return inner(x) + 5;
}

let answer = outer(5);
""",
    "kotlin": """\
fun inner(y: Int): Int {
    return y * 2
}

fun outer(x: Int): Int {
    return inner(x) + 5
}

val answer = outer(5)
""",
    "scala": """\
object M {
    def inner(y: Int): Int = {
        return y * 2
    }

    def outer(x: Int): Int = {
        return inner(x) + 5
    }

    val answer = outer(5)
}
""",
    "lua": """\
function inner(y)
    return y * 2
end

function outer(x)
    return inner(x) + 5
end

answer = outer(5)
""",
    "pascal": """\
program M;

function inner(y: integer): integer;
begin
    inner := y * 2;
end;

function outer(x: integer): integer;
begin
    outer := inner(x) + 5;
end;

var answer: integer;
begin
    answer := outer(5);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.CALL_FUNCTION,
    Opcode.RETURN,
    Opcode.BINOP,
}

MIN_INSTRUCTIONS = 8


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestNestedFunctionsLowering:
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


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestNestedFunctionsCrossLanguage:
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
EXPECTED_ANSWER = 15  # inner(5) + 5 = 10 + 5 = 15


class TestNestedFunctionsExecution:
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
