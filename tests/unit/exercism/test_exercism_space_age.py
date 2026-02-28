"""Exercism test: space-age across all 15 deterministic frontends.

Uses canonical test data from Exercism problem-specifications.
Each language solution is a separate file under
exercises/space_age/solutions/.

Single function per solution: spaceAge / space_age.
Takes a planet name (string) and seconds (int), returns a float
representing the age on that planet.

The error case (invalid planet ``"Sun"``) is auto-filtered by
``load_canonical_cases`` since its ``expected`` is an error object.
Float comparison uses tolerance of 0.01.
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

EXERCISE = "space_age"

SNAKE_CASE_LANGUAGES = frozenset({"python", "ruby", "rust"})


def _function_name(language: str) -> str:
    """Return the space-age function name for *language*."""
    return "space_age" if language in SNAKE_CASE_LANGUAGES else "spaceAge"


SOLUTIONS: dict[str, str] = {
    lang: load_solution(EXERCISE, lang)
    for lang in sorted(STANDARD_EXECUTABLE_LANGUAGES)
}

CANONICAL_CASES: list[dict] = load_canonical_cases(EXERCISE)

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.RETURN,
    Opcode.BRANCH_IF,
    Opcode.BINOP,
}

MIN_INSTRUCTIONS = 15

FLOAT_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Per-language lowering tests
# ---------------------------------------------------------------------------


class TestSpaceAgeLowering:
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


class TestSpaceAgeCrossLanguage:
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
    return [case["input"]["planet"], case["input"]["seconds"]]


def _case_expected(case: dict) -> float:
    return float(case["expected"])


EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES


class TestSpaceAgeExecution:
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
        vm, stats = execute_for_language(lang, source, max_steps=5000)
        expected = _case_expected(case)
        return lang, vm, stats, expected, case["description"]

    def test_correct_result(self, execution_result):
        lang, vm, _stats, expected, desc = execution_result
        answer = extract_answer(vm, lang)
        assert (
            abs(answer - expected) < FLOAT_TOLERANCE
        ), f"[{lang}] {desc}: expected {expected}, got {answer}"

    def test_zero_llm_calls(self, execution_result):
        lang, _vm, stats, _expected, desc = execution_result
        assert (
            stats.llm_calls == 0
        ), f"[{lang}] {desc}: expected 0 LLM calls, got {stats.llm_calls}"
