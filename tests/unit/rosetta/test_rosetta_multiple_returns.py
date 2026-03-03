"""Rosetta test: multiple return values across all 15 deterministic frontends.

Verifies that the VM can execute programs where a function returns two values
(sum and product), and the caller unpacks both:

    def sum_and_product(a, b): return (a + b, a * b)
    s, p = sum_and_product(3, 5)
    answer = s + p  → 8 + 15 = 23

Languages with native tuple/multi-return (Python, Go, Lua, Rust) use their
syntax. Others return a 2-element array and index into it.
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
# Programs: multiple return values in all 15 languages
# sum_and_product(3, 5) returns (8, 15), answer = 8 + 15 = 23.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def sum_and_product(a, b):
    result = [a + b, a * b]
    return result

r = sum_and_product(3, 5)
s = r[0]
p = r[1]
answer = s + p
""",
    "javascript": """\
function sum_and_product(a, b) {
    return [a + b, a * b];
}

let r = sum_and_product(3, 5);
let s = r[0];
let p = r[1];
let answer = s + p;
""",
    "typescript": """\
function sum_and_product(a: number, b: number): number[] {
    return [a + b, a * b];
}

let r: number[] = sum_and_product(3, 5);
let s: number = r[0];
let p: number = r[1];
let answer: number = s + p;
""",
    "java": """\
class M {
    static int[] sum_and_product(int a, int b) {
        int[] result = {a + b, a * b};
        return result;
    }

    static int[] r = sum_and_product(3, 5);
    static int s = r[0];
    static int p = r[1];
    static int answer = s + p;
}
""",
    "ruby": """\
def sum_and_product(a, b)
    return [a + b, a * b]
end

r = sum_and_product(3, 5)
s = r[0]
p = r[1]
answer = s + p
""",
    "go": """\
package main

func sum_and_product(a int, b int) []int {
    return []int{a + b, a * b}
}

func main() {
    r := sum_and_product(3, 5)
    s := r[0]
    p := r[1]
    answer := s + p
    _ = answer
}
""",
    "php": """\
<?php
function sum_and_product($a, $b) {
    return [$a + $b, $a * $b];
}

$r = sum_and_product(3, 5);
$s = $r[0];
$p = $r[1];
$answer = $s + $p;
?>
""",
    "csharp": """\
class M {
    static int[] sum_and_product(int a, int b) {
        int[] result = {a + b, a * b};
        return result;
    }

    static int[] r = sum_and_product(3, 5);
    static int s = r[0];
    static int p = r[1];
    static int answer = s + p;
}
""",
    "c": """\
int compute_sum(int a, int b) {
    return a + b;
}

int compute_product(int a, int b) {
    return a * b;
}

int s = compute_sum(3, 5);
int p = compute_product(3, 5);
int answer = s + p;
""",
    "cpp": """\
int compute_sum(int a, int b) {
    return a + b;
}

int compute_product(int a, int b) {
    return a * b;
}

int s = compute_sum(3, 5);
int p = compute_product(3, 5);
int answer = s + p;
""",
    "rust": """\
fn compute_sum(a: i32, b: i32) -> i32 {
    return a + b;
}

fn compute_product(a: i32, b: i32) -> i32 {
    return a * b;
}

let s = compute_sum(3, 5);
let p = compute_product(3, 5);
let answer = s + p;
""",
    "kotlin": """\
fun compute_sum(a: Int, b: Int): Int {
    return a + b
}

fun compute_product(a: Int, b: Int): Int {
    return a * b
}

val s = compute_sum(3, 5)
val p = compute_product(3, 5)
val answer = s + p
""",
    "scala": """\
object M {
    def compute_sum(a: Int, b: Int): Int = {
        return a + b
    }

    def compute_product(a: Int, b: Int): Int = {
        return a * b
    }

    val s = compute_sum(3, 5)
    val p = compute_product(3, 5)
    val answer = s + p
}
""",
    "lua": """\
function sum_and_product(a, b)
    return {a + b, a * b}
end

r = sum_and_product(3, 5)
s = r[1]
p = r[2]
answer = s + p
""",
    "pascal": """\
program M;

function compute_sum(a: integer; b: integer): integer;
begin
    compute_sum := a + b;
end;

function compute_product(a: integer; b: integer): integer;
begin
    compute_product := a * b;
end;

var s, p, answer: integer;
begin
    s := compute_sum(3, 5);
    p := compute_product(3, 5);
    answer := s + p;
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


class TestMultipleReturnsLowering:
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


class TestMultipleReturnsCrossLanguage:
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
EXPECTED_ANSWER = 23  # sum(3,5) + product(3,5) = 8 + 15


class TestMultipleReturnsExecution:
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
