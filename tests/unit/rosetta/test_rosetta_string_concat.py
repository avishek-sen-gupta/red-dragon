"""Rosetta test: String concatenation across deterministic frontends.

C is excluded — it has no string concatenation operator (requires strcat
with mutable buffers, not an expression).
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
# Programs: String concatenation in 14 languages (C excluded — no concat operator)
# Each concatenates "hello" and " world" and stores the result in answer.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
answer = "hello" + " world"
""",
    "javascript": """\
let answer = "hello" + " world";
""",
    "typescript": """\
let answer: string = "hello" + " world";
""",
    "java": """\
class M { static String answer = "hello" + " world"; }
""",
    "ruby": """\
answer = "hello" + " world"
""",
    "go": """\
package main
func main() { answer := "hello" + " world"
_ = answer }
""",
    "php": """\
<?php $answer = "hello" . " world"; ?>
""",
    "csharp": """\
string answer = "hello" + " world";
""",
    "cpp": """\
std::string a = "hello";
std::string b = " world";
std::string answer = a + b;
""",
    "rust": """\
let answer = "hello" + " world";
""",
    "kotlin": """\
val answer = "hello" + " world"
""",
    "scala": """\
object M { val answer = "hello" + " world" }
""",
    "lua": """\
answer = "hello" .. " world"
""",
    "pascal": """\
program M;
var answer: string;
begin
  answer := 'hello' + ' world';
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.CONST,
}

MIN_INSTRUCTIONS = 3


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestStringConcatLowering:
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

    def test_string_literal_present(self, language_ir):
        lang, ir = language_ir
        consts = find_all(ir, Opcode.CONST)
        values = {str(inst.operands[0]) for inst in consts if inst.operands}
        has_hello = any("hello" in v for v in values)
        assert (
            has_hello
        ), f"[{lang}] expected a CONST containing 'hello' in values: {values}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestStringConcatCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, PROGRAMS[lang]) for lang in PROGRAMS}

    def test_all_languages_covered(self):
        # C excluded: no string concat operator (requires strcat, not an expression)
        expected = set(SUPPORTED_DETERMINISTIC_LANGUAGES) - {"c"}
        assert set(PROGRAMS.keys()) == expected

    def test_cross_language_consistency(self, all_results):
        assert_cross_language_consistency(
            all_results,
            required_opcodes=REQUIRED_OPCODES,
            expected_languages=set(PROGRAMS.keys()),
        )


# ---------------------------------------------------------------------------
# VM execution tests (parametrized over executable languages)
# ---------------------------------------------------------------------------

# C excluded from PROGRAMS entirely (no string concat operator)
STRING_CONCAT_EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES - {
    "c"
}
EXPECTED_ANSWER = "hello world"


class TestStringConcatExecution:
    @pytest.fixture(
        params=sorted(STRING_CONCAT_EXECUTABLE_LANGUAGES),
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
        ), f"[{lang}] expected answer={EXPECTED_ANSWER!r}, got {answer!r}"

    def test_zero_llm_calls(self, execution_result):
        lang, _vm, stats = execution_result
        assert (
            stats.llm_calls == 0
        ), f"[{lang}] expected 0 LLM calls, got {stats.llm_calls}"
