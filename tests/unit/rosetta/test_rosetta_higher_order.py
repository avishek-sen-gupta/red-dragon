"""Rosetta test: Higher-order functions across all 15 deterministic frontends.

Every program passes a function (or lambda/closure) as an argument to ``apply``,
which calls it on a value.  The pattern is ``apply(double, 5) => 10``.
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
# Programs: Higher-order functions in all 15 languages.
# Each computes apply(double, 5) => 10 by passing a function as an argument.
# Languages use the most natural mechanism: function references, lambdas, or
# anonymous functions.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def apply(f, x):
    return f(x)

def double_val(x):
    return x * 2

answer = apply(double_val, 5)
""",
    "javascript": """\
function apply(f, x) {
    return f(x);
}

function double_val(x) {
    return x * 2;
}

let answer = apply(double_val, 5);
""",
    "typescript": """\
function apply(f: Function, x: number): number {
    return f(x);
}

function double_val(x: number): number {
    return x * 2;
}

let answer: number = apply(double_val, 5);
""",
    "java": """\
import java.util.function.Function;

class M {
    static int doubleVal(int x) {
        return x * 2;
    }

    static int apply(Function<Integer, Integer> f, int x) {
        return f.apply(x);
    }

    static int answer = apply(x -> x * 2, 5);
}
""",
    "ruby": """\
def double_val(x)
    return x * 2
end

def apply(f, x)
    return f(x)
end

answer = apply(double_val, 5)
""",
    "go": """\
package main

func doubleVal(x int) int {
    return x * 2
}

func apply(f func(int) int, x int) int {
    return f(x)
}

func main() {
    answer := apply(doubleVal, 5)
    _ = answer
}
""",
    "php": """\
<?php
function apply_fn($f, $x) {
    return $f($x);
}

$answer = apply_fn(function($x) { return $x * 2; }, 5);
?>
""",
    "csharp": """\
using System;

class M {
    static int DoubleVal(int x) {
        return x * 2;
    }

    static int Apply(Func<int, int> f, int x) {
        return f(x);
    }

    static int answer = Apply(x => x * 2, 5);
}
""",
    "c": """\
int double_val(int x) {
    return x * 2;
}

int apply(int (*f)(int), int x) {
    return f(x);
}

int answer = apply(double_val, 5);
""",
    "cpp": """\
int double_val(int x) {
    return x * 2;
}

int apply(int (*f)(int), int x) {
    return f(x);
}

int answer = apply(double_val, 5);
""",
    "rust": """\
fn double_val(x: i32) -> i32 {
    return x * 2;
}

fn apply(f: fn(i32) -> i32, x: i32) -> i32 {
    return f(x);
}

let answer = apply(double_val, 5);
""",
    "kotlin": """\
fun doubleVal(x: Int): Int {
    return x * 2
}

fun apply(f: (Int) -> Int, x: Int): Int {
    return f(x)
}

val answer = apply(::doubleVal, 5)
""",
    "scala": """\
object M {
    def doubleVal(x: Int): Int = {
        return x * 2
    }

    def apply(f: Int => Int, x: Int): Int = {
        return f(x)
    }

    val answer = apply(doubleVal, 5)
}
""",
    "lua": """\
function double_val(x)
    return x * 2
end

function apply(f, x)
    return f(x)
end

answer = apply(double_val, 5)
""",
    "pascal": """\
program M;

type
    TIntFunc = function(x: integer): integer;

function double_val(x: integer): integer;
begin
    double_val := x * 2;
end;

function apply(f: TIntFunc; x: integer): integer;
begin
    apply := f(x);
end;

var answer: integer;
begin
    answer := apply(double_val, 5);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.CALL_FUNCTION,
    Opcode.BINOP,
}

MIN_INSTRUCTIONS = 8


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestHigherOrderLowering:
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

    def test_call_function_present(self, language_ir):
        lang, ir = language_ir
        calls = find_all(ir, Opcode.CALL_FUNCTION)
        assert (
            len(calls) >= 1
        ), f"[{lang}] expected at least 1 CALL_FUNCTION instruction, got {len(calls)}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestHigherOrderCrossLanguage:
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

HIGHER_ORDER_EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 10  # double(5) = 10


class TestHigherOrderExecution:
    @pytest.fixture(
        params=sorted(HIGHER_ORDER_EXECUTABLE_LANGUAGES),
        ids=lambda lang: lang,
        scope="class",
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
