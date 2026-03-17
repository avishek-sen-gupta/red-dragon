"""Rosetta test: unary operators across all 15 deterministic frontends.

Tests unary negation: x = -7; answer = -x => answer = 7.
All 15 languages support unary minus on integers.
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
# Programs: unary negation in all 15 languages
# x = -7, answer = -x => answer = 7
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
x = -7
answer = -x
""",
    "javascript": """\
let x = -7;
let answer = -x;
""",
    "typescript": """\
let x: number = -7;
let answer: number = -x;
""",
    "java": """\
class M {
    static int x = -7;
    static int answer = -x;
}
""",
    "ruby": """\
x = -7
answer = -x
""",
    "go": """\
package main

func main() {
    x := -7
    answer := -x
    _ = answer
}
""",
    "php": """\
<?php
$x = -7;
$answer = -$x;
?>
""",
    "csharp": """\
int x = -7;
int answer = -x;
""",
    "c": """\
int x = -7;
int answer = -x;
""",
    "cpp": """\
int x = -7;
int answer = -x;
""",
    "rust": """\
let x: i32 = -7;
let answer = -x;
""",
    "kotlin": """\
val x = -7
val answer = -x
""",
    "scala": """\
object M {
    val x = -7
    val answer = -x
}
""",
    "lua": """\
x = -7
answer = -x
""",
    "pascal": """\
program M;
var x, answer: integer;
begin
    x := -7;
    answer := -x;
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {Opcode.UNOP}

MIN_INSTRUCTIONS = 3


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestUnaryOperatorsLowering:
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

    def test_negation_operator_in_unops(self, language_ir):
        """IR must contain unary negation operator."""
        lang, ir = language_ir
        operators = {inst.operands[0] for inst in find_all(ir, Opcode.UNOP)}
        assert (
            "-" in operators
        ), f"[{lang}] expected '-' (negation) in UNOP operators, got {operators}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestUnaryOperatorsCrossLanguage:
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

UNARY_EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 7  # -(-7) = 7


class TestUnaryOperatorsExecution:
    @pytest.fixture(
        params=sorted(UNARY_EXECUTABLE_LANGUAGES),
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
