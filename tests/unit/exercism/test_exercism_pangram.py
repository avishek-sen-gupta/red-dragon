"""Exercism test: pangram across all 15 deterministic frontends.

Uses canonical test data from Exercism problem-specifications.
Each language solution is a separate file under exercises/pangram/solutions/.

Uses a toLowerChar helper function with 26 if-statements for
case-insensitive comparison, and checks all 26 letters via nested loops.
"""

import pytest

from interpreter.frontends import SUPPORTED_DETERMINISTIC_LANGUAGES
from interpreter.ir import Opcode

from tests.unit.rosetta.conftest import (
    parse_for_language,
    assert_clean_lowering,
    assert_cross_language_consistency,
    execute_for_language,
    extract_answer,
    STANDARD_EXECUTABLE_LANGUAGES,
)

from tests.unit.exercism.conftest import (
    load_solution,
    load_canonical_cases,
    build_program,
)

EXERCISE = "pangram"

SNAKE_CASE_LANGUAGES = frozenset({"python", "ruby", "rust"})


def _function_name(language: str) -> str:
    """Return the pangram function name for *language*."""
    return "is_pangram" if language in SNAKE_CASE_LANGUAGES else "isPangram"


SOLUTIONS: dict[str, str] = {
    lang: load_solution(EXERCISE, lang)
    for lang in sorted(STANDARD_EXECUTABLE_LANGUAGES)
}

CANONICAL_CASES: list[dict] = load_canonical_cases(EXERCISE)

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.RETURN,
    Opcode.BRANCH_IF,
    Opcode.CALL_FUNCTION,
}

MIN_INSTRUCTIONS = 15


# ---------------------------------------------------------------------------
# Per-language lowering tests
# ---------------------------------------------------------------------------


class TestPangramLowering:
    @pytest.fixture(params=sorted(SOLUTIONS.keys()), ids=lambda lang: lang)
    def language_ir(self, request):
        lang = request.param
        ir = parse_for_language(lang, SOLUTIONS[lang])
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


class TestPangramCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, SOLUTIONS[lang]) for lang in SOLUTIONS}

    def test_all_languages_covered(self):
        assert set(SOLUTIONS.keys()) == set(SUPPORTED_DETERMINISTIC_LANGUAGES)

    def test_cross_language_consistency(self, all_results):
        assert_cross_language_consistency(
            all_results, required_opcodes=REQUIRED_OPCODES
        )


# ---------------------------------------------------------------------------
# VM execution tests — parametrized by (language, canonical case)
# ---------------------------------------------------------------------------


def _case_id(case: dict) -> str:
    return case["description"].replace(" ", "_")


def _case_args(case: dict) -> list[object]:
    sentence = case["input"]["sentence"]
    return [sentence, len(sentence)]


def _case_expected(case: dict) -> int:
    return 1 if case["expected"] else 0


EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES


class TestPangramExecution:
    @pytest.fixture(
        params=[
            (lang, case)
            for lang in sorted(EXECUTABLE_LANGUAGES)
            for case in CANONICAL_CASES
        ],
        ids=lambda pair: f"{pair[0]}-{_case_id(pair[1])}",
        scope="class",
    )
    def execution_result(self, request):
        lang, case = request.param
        fn_name = _function_name(lang)
        source = build_program(SOLUTIONS[lang], fn_name, _case_args(case), lang)
        vm, stats = execute_for_language(lang, source, max_steps=100000)
        expected = _case_expected(case)
        return lang, vm, stats, expected, case["description"]

    def test_correct_result(self, execution_result):
        lang, vm, _stats, expected, desc = execution_result
        answer = extract_answer(vm, lang)
        assert answer == expected, f"[{lang}] {desc}: expected {expected}, got {answer}"

    def test_zero_llm_calls(self, execution_result):
        lang, _vm, stats, _expected, desc = execution_result
        assert (
            stats.llm_calls == 0
        ), f"[{lang}] {desc}: expected 0 LLM calls, got {stats.llm_calls}"
