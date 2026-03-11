"""Rosetta test: Higher-order functions (interprocedural call chains) across all 15 deterministic frontends."""

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
# Programs: Higher-order function / interprocedural call chain in all 15 languages
# Each computes apply(double, 5) => 10.
# Languages without first-class function support in the VM use a chained call
# pattern: apply(x) internally calls double_val(x).
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def apply(f, x):
    return f(x)

def double(x):
    return x * 2

answer = apply(double, 5)
""",
    "javascript": """\
function apply(f, x) {
    return f(x);
}

function double(x) {
    return x * 2;
}

let answer = apply(double, 5);
""",
    "typescript": """\
function apply(f: Function, x: number): number {
    return f(x);
}

function double(x: number): number {
    return x * 2;
}

let answer: number = apply(double, 5);
""",
    "java": """\
class M {
    static int double_val(int x) {
        return x * 2;
    }

    static int apply(int x) {
        return double_val(x);
    }

    static int answer = apply(5);
}
""",
    "ruby": """\
def double_val(x)
    return x * 2
end

def apply(x)
    return double_val(x)
end

answer = apply(5)
""",
    "go": """\
package main

func double_val(x int) int {
    return x * 2
}

func apply(x int) int {
    return double_val(x)
}

func main() {
    answer := apply(5)
    _ = answer
}
""",
    "php": """\
<?php
function double_val($x) {
    return $x * 2;
}

function apply_fn($x) {
    return double_val($x);
}

$answer = apply_fn(5);
?>
""",
    "csharp": """\
class M {
    static int double_val(int x) {
        return x * 2;
    }

    static int apply(int x) {
        return double_val(x);
    }

    static int answer = apply(5);
}
""",
    "c": """\
int double_val(int x) {
    return x * 2;
}

int apply(int x) {
    return double_val(x);
}

int answer = apply(5);
""",
    "cpp": """\
int double_val(int x) {
    return x * 2;
}

int apply(int x) {
    return double_val(x);
}

int answer = apply(5);
""",
    "rust": """\
fn double_val(x: i32) -> i32 {
    return x * 2;
}

fn apply(x: i32) -> i32 {
    return double_val(x);
}

let answer = apply(5);
""",
    "kotlin": """\
fun doubleVal(x: Int): Int {
    return x * 2
}

fun apply(x: Int): Int {
    return doubleVal(x)
}

val answer = apply(5)
""",
    "scala": """\
object M {
    def doubleVal(x: Int): Int = {
        return x * 2
    }

    def apply(x: Int): Int = {
        return doubleVal(x)
    }

    val answer = apply(5)
}
""",
    "lua": """\
function double_val(x)
    return x * 2
end

function apply(x)
    return double_val(x)
end

answer = apply(5)
""",
    "pascal": """\
program M;

function double_val(x: integer): integer;
begin
    double_val := x * 2;
end;

function apply(x: integer): integer;
begin
    apply := double_val(x);
end;

var answer: integer;
begin
    answer := apply(5);
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
