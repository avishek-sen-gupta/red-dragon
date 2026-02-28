"""Rosetta test: interprocedural calls across all 15 deterministic frontends.

Verifies that the VM can execute a program where one user-defined function
calls a completely separate user-defined function:

    double(x)      → x * 2
    double_add(a, b) → double(a) + double(b)
    answer = double_add(3, 4)  → 6 + 8 = 14
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
# Programs: interprocedural calls in all 15 languages
# Each defines double(x) and double_add(a, b), then computes double_add(3, 4).
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def double(x):
    return x * 2

def double_add(a, b):
    return double(a) + double(b)

answer = double_add(3, 4)
""",
    "javascript": """\
function double(x) {
    return x * 2;
}

function double_add(a, b) {
    return double(a) + double(b);
}

let answer = double_add(3, 4);
""",
    "typescript": """\
function double(x: number): number {
    return x * 2;
}

function double_add(a: number, b: number): number {
    return double(a) + double(b);
}

let answer: number = double_add(3, 4);
""",
    "java": """\
class M {
    static int double_fn(int x) {
        return x * 2;
    }

    static int double_add(int x, int y) {
        return double_fn(x) + double_fn(y);
    }

    static int answer = double_add(3, 4);
}
""",
    "ruby": """\
def double(x)
    return x * 2
end

def double_add(a, b)
    return double(a) + double(b)
end

answer = double_add(3, 4)
""",
    "go": """\
package main

func double(x int) int {
    return x * 2
}

func double_add(a int, b int) int {
    return double(a) + double(b)
}

func main() {
    answer := double_add(3, 4)
    _ = answer
}
""",
    "php": """\
<?php
function double_fn($x) {
    return $x * 2;
}

function double_add($a, $b) {
    return double_fn($a) + double_fn($b);
}

$answer = double_add(3, 4);
?>
""",
    "csharp": """\
class M {
    static int double_fn(int x) {
        return x * 2;
    }

    static int double_add(int x, int y) {
        return double_fn(x) + double_fn(y);
    }

    static int answer = double_add(3, 4);
}
""",
    "c": """\
int double_fn(int x) {
    return x * 2;
}

int double_add(int a, int b) {
    return double_fn(a) + double_fn(b);
}

int answer = double_add(3, 4);
""",
    "cpp": """\
int double_fn(int x) {
    return x * 2;
}

int double_add(int a, int b) {
    return double_fn(a) + double_fn(b);
}

int answer = double_add(3, 4);
""",
    "rust": """\
fn double_fn(x: i32) -> i32 {
    return x * 2;
}

fn double_add(a: i32, b: i32) -> i32 {
    return double_fn(a) + double_fn(b);
}

let answer = double_add(3, 4);
""",
    "kotlin": """\
fun double_fn(x: Int): Int {
    return x * 2
}

fun double_add(a: Int, b: Int): Int {
    return double_fn(a) + double_fn(b)
}

val answer = double_add(3, 4)
""",
    "scala": """\
object M {
    def double_fn(x: Int): Int = {
        return x * 2
    }

    def double_add(a: Int, b: Int): Int = {
        return double_fn(a) + double_fn(b)
    }

    val answer = double_add(3, 4)
}
""",
    "lua": """\
function double_fn(x)
    return x * 2
end

function double_add(a, b)
    return double_fn(a) + double_fn(b)
end

answer = double_add(3, 4)
""",
    "pascal": """\
program M;

function double_fn(x: integer): integer;
begin
    double_fn := x * 2;
end;

function double_add(a: integer; b: integer): integer;
begin
    double_add := double_fn(a) + double_fn(b);
end;

var answer: integer;
begin
    answer := double_add(3, 4);
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


class TestInterproceduralLowering:
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

    def test_multiple_call_functions(self, language_ir):
        lang, ir = language_ir
        calls = find_all(ir, Opcode.CALL_FUNCTION)
        assert len(calls) >= 2, (
            f"[{lang}] expected at least 2 CALL_FUNCTION instructions "
            f"(one for double_add at top level, one for double_fn inside "
            f"double_add), got {len(calls)}"
        )


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestInterproceduralCrossLanguage:
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
EXPECTED_ANSWER = 14  # double(3) + double(4) = 6 + 8


class TestInterproceduralExecution:
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
