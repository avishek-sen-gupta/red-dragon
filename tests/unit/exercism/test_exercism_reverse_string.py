"""Exercism test: reverse-string across all 15 deterministic frontends.

Uses canonical test data from Exercism problem-specifications.
Each language solution is a separate file under exercises/reverse_string/solutions/.
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

EXERCISE = "reverse_string"

SNAKE_CASE_LANGUAGES = frozenset({"python", "ruby", "rust"})


def _function_name(language: str) -> str:
    """Return the reverse-string function name for *language*."""
    return "reverse_string" if language in SNAKE_CASE_LANGUAGES else "reverseString"


SOLUTIONS: dict[str, str] = {
    lang: load_solution(EXERCISE, lang)
    for lang in sorted(STANDARD_EXECUTABLE_LANGUAGES)
}

CANONICAL_CASES: list[dict] = [
    case
    for case in load_canonical_cases(EXERCISE)
    if "unicode" not in case.get("scenarios", []) and "'" not in case["input"]["value"]
]

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.RETURN,
    Opcode.BINOP,
    Opcode.BRANCH_IF,
}

MIN_INSTRUCTIONS = 10


# ---------------------------------------------------------------------------
# Per-language lowering tests
# ---------------------------------------------------------------------------


class TestReverseStringLowering:
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


class TestReverseStringCrossLanguage:
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
    value = case["input"]["value"]
    return [value, len(value)]


def _case_expected(case: dict) -> str:
    return case["expected"]


EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES


class TestReverseStringExecution:
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
            answer == expected
        ), f"[{lang}] {desc}: expected {expected!r}, got {answer!r}"

    def test_zero_llm_calls(self, execution_result):
        lang, _vm, stats, _expected, desc = execution_result
        assert (
            stats.llm_calls == 0
        ), f"[{lang}] {desc}: expected 0 LLM calls, got {stats.llm_calls}"


# ---------------------------------------------------------------------------
# Known limitation: Pascal apostrophe escaping
# ---------------------------------------------------------------------------

_APOSTROPHE_CASE: dict = next(
    case
    for case in load_canonical_cases(EXERCISE)
    if "'" in case["input"]["value"] and "unicode" not in case.get("scenarios", [])
)


class TestPascalApostropheLimitation:
    """Document that Pascal's '' escape does not round-trip through _parse_const.

    Pascal string literals escape apostrophes by doubling them: 'I''m hungry!'
    The VM's _parse_const strips the outer quotes (raw[1:-1]) but does not
    un-escape inner doubled quotes, so the stored string contains '' instead
    of ' and has the wrong length.  This causes reverse-string to produce
    incorrect output for inputs containing apostrophes.

    All other 14 languages handle this case correctly because they use
    double-quoted strings where apostrophes need no escaping.
    """

    @pytest.mark.xfail(
        reason=(
            "_parse_const does not un-escape Pascal '' → ' inside "
            "single-quoted string literals (ADR-024)"
        ),
        strict=True,
    )
    def test_pascal_apostrophe_reverse(self):
        """Reversing "I'm hungry!" should yield "!yrgnuh m'I" in Pascal."""
        fn_name = _function_name("pascal")
        source = build_program(
            SOLUTIONS["pascal"], fn_name, _case_args(_APOSTROPHE_CASE), "pascal"
        )
        vm, _stats = execute_for_language("pascal", source, max_steps=5000)
        answer = extract_answer(vm, "pascal")
        assert answer == _APOSTROPHE_CASE["expected"]

    def test_non_pascal_languages_handle_apostrophe(self):
        """All non-Pascal languages correctly reverse strings with apostrophes."""
        non_pascal = sorted(lang for lang in EXECUTABLE_LANGUAGES if lang != "pascal")
        for lang in non_pascal:
            fn_name = _function_name(lang)
            source = build_program(
                SOLUTIONS[lang], fn_name, _case_args(_APOSTROPHE_CASE), lang
            )
            vm, _stats = execute_for_language(lang, source, max_steps=5000)
            answer = extract_answer(vm, lang)
            assert (
                answer == _APOSTROPHE_CASE["expected"]
            ), f"[{lang}] expected {_APOSTROPHE_CASE['expected']!r}, got {answer!r}"
