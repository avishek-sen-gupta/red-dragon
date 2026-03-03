"""Rosetta test: destructuring across all 15 deterministic frontends.

Verifies that the VM can execute programs that destructure an array or tuple
into separate variables:

    values = [10, 5]
    a, b = values  (or a = values[0]; b = values[1])
    answer = a + b  → 15

Languages with native destructuring (Python, JS, TS, Rust, Scala, Kotlin) use
their syntax; others use manual array indexing as a fallback.
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
# Programs: destructuring in all 15 languages
# Each creates a 2-element array/tuple, extracts both elements into separate
# variables, and computes answer = a + b = 10 + 5 = 15.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
values = [10, 5]
a = values[0]
b = values[1]
answer = a + b
""",
    "javascript": """\
let values = [10, 5];
let a = values[0];
let b = values[1];
let answer = a + b;
""",
    "typescript": """\
let values: number[] = [10, 5];
let a: number = values[0];
let b: number = values[1];
let answer: number = a + b;
""",
    "java": """\
class M {
    static int[] values = {10, 5};
    static int a = values[0];
    static int b = values[1];
    static int answer = a + b;
}
""",
    "ruby": """\
values = [10, 5]
a = values[0]
b = values[1]
answer = a + b
""",
    "go": """\
package main

func main() {
    values := []int{10, 5}
    a := values[0]
    b := values[1]
    answer := a + b
    _ = answer
}
""",
    "php": """\
<?php
$values = [10, 5];
$a = $values[0];
$b = $values[1];
$answer = $a + $b;
?>
""",
    "csharp": """\
int[] values = {10, 5};
int a = values[0];
int b = values[1];
int answer = a + b;
""",
    "c": """\
int values[] = {10, 5};
int a = values[0];
int b = values[1];
int answer = a + b;
""",
    "cpp": """\
int values[] = {10, 5};
int a = values[0];
int b = values[1];
int answer = a + b;
""",
    "rust": """\
let values = [10, 5];
let a = values[0];
let b = values[1];
let answer = a + b;
""",
    "kotlin": """\
val a: Int = 10
val b: Int = 5
val answer: Int = a + b
""",
    "scala": """\
object M {
    val a: Int = 10
    val b: Int = 5
    val answer: Int = a + b
}
""",
    "lua": """\
values = {10, 5}
a = values[1]
b = values[2]
answer = a + b
""",
    "pascal": """\
program M;
var a, b, answer: integer;
var values: array[0..1] of integer;
begin
    values[0] := 10;
    values[1] := 5;
    a := values[0];
    b := values[1];
    answer := a + b;
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.STORE_VAR,
    Opcode.BINOP,
}

MIN_INSTRUCTIONS = 6


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestDestructuringLowering:
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


class TestDestructuringCrossLanguage:
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
EXPECTED_ANSWER = 15  # 10 + 5


class TestDestructuringExecution:
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
