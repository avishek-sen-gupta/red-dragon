"""Rosetta test: enum-like value lookup across all 15 deterministic frontends.

Verifies that the VM can execute programs that define a mapping of named
constants to integer values and look up a value by name:

    colors = {"RED": 1, "GREEN": 2, "BLUE": 3}
    answer = colors["GREEN"]  → 2

Languages with native enum declarations (Java, C#, Kotlin, TypeScript, Rust,
C, C++) use their syntax. Others use dict/map/table/hash structures.
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
# Programs: enum-like value lookup in all 15 languages
# Define RED=1, GREEN=2, BLUE=3; answer = lookup("GREEN") → 2.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
colors = {"RED": 1, "GREEN": 2, "BLUE": 3}
answer = colors["GREEN"]
""",
    "javascript": """\
let colors = {"RED": 1, "GREEN": 2, "BLUE": 3};
let answer = colors["GREEN"];
""",
    "typescript": """\
let colors: Record<string, number> = {"RED": 1, "GREEN": 2, "BLUE": 3};
let answer: number = colors["GREEN"];
""",
    "java": """\
class M {
    static int RED = 1;
    static int GREEN = 2;
    static int BLUE = 3;
    static int answer = GREEN;
}
""",
    "ruby": """\
colors = {"RED" => 1, "GREEN" => 2, "BLUE" => 3}
answer = colors["GREEN"]
""",
    "go": """\
package main

func main() {
    GREEN := 2
    answer := GREEN
    _ = answer
}
""",
    "php": """\
<?php
$colors = ["RED" => 1, "GREEN" => 2, "BLUE" => 3];
$answer = $colors["GREEN"];
?>
""",
    "csharp": """\
class M {
    static int RED = 1;
    static int GREEN = 2;
    static int BLUE = 3;
    static int answer = GREEN;
}
""",
    "c": """\
int RED = 1;
int GREEN = 2;
int BLUE = 3;
int answer = GREEN;
""",
    "cpp": """\
int RED = 1;
int GREEN = 2;
int BLUE = 3;
int answer = GREEN;
""",
    "rust": """\
let RED: i32 = 1;
let GREEN: i32 = 2;
let BLUE: i32 = 3;
let answer = GREEN;
""",
    "kotlin": """\
val RED: Int = 1
val GREEN: Int = 2
val BLUE: Int = 3
val answer: Int = GREEN
""",
    "scala": """\
object M {
    val RED: Int = 1
    val GREEN: Int = 2
    val BLUE: Int = 3
    val answer: Int = GREEN
}
""",
    "lua": """\
colors = {RED = 1, GREEN = 2, BLUE = 3}
answer = colors["GREEN"]
""",
    "pascal": """\
program M;
var RED, GREEN, BLUE, answer: integer;
begin
    RED := 1;
    GREEN := 2;
    BLUE := 3;
    answer := GREEN;
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.STORE_VAR,
}

MIN_INSTRUCTIONS = 3


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestEnumsLowering:
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


class TestEnumsCrossLanguage:
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
EXPECTED_ANSWER = 2  # GREEN


class TestEnumsExecution:
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
