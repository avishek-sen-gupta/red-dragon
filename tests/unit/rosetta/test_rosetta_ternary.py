"""Rosetta test: Ternary/conditional absolute value across all 15 deterministic frontends."""

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
# Programs: Absolute value of -5 via ternary/conditional in all 15 languages
# Each computes abs(-5) and stores the result in `answer`.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
x = -5
answer = x if x > 0 else -x
""",
    "javascript": """\
let x = -5;
let answer = x > 0 ? x : -x;
""",
    "typescript": """\
let x: number = -5;
let answer: number = x > 0 ? x : -x;
""",
    "java": """\
class M { static int x = -5; static int answer = x > 0 ? x : -x; }
""",
    "ruby": """\
x = -5
answer = x > 0 ? x : -x
""",
    "go": """\
package main
func main() {
  x := -5
  answer := 0
  if x > 0 { answer = x } else { answer = -x }
  _ = answer
}
""",
    "php": """\
<?php $x = -5; $answer = $x > 0 ? $x : -$x; ?>
""",
    "csharp": """\
int x = -5;
int answer = x > 0 ? x : -x;
""",
    "c": """\
int x = -5;
int answer = x > 0 ? x : -x;
""",
    "cpp": """\
int x = -5;
int answer = x > 0 ? x : -x;
""",
    "rust": """\
let x: i32 = -5;
let answer = if x > 0 { x } else { -x };
""",
    "kotlin": """\
val x = -5
val answer = if (x > 0) x else -x
""",
    "scala": """\
object M { val x = -5; val answer = if (x > 0) x else -x }
""",
    "lua": """\
x = -5
if x > 0 then answer = x else answer = -x end
""",
    "pascal": """\
program M;
var x, answer: integer;
begin
  x := -5;
  if x > 0 then answer := x else answer := -x;
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.BRANCH_IF,
}

MIN_INSTRUCTIONS = 5


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestTernaryLowering:
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

    def test_branch_if_present(self, language_ir):
        lang, ir = language_ir
        branch_ifs = find_all(ir, Opcode.BRANCH_IF)
        assert (
            len(branch_ifs) >= 1
        ), f"[{lang}] expected at least one BRANCH_IF instruction, found none"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestTernaryCrossLanguage:
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

TERNARY_EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 5  # abs(-5)


class TestTernaryExecution:
    @pytest.fixture(
        params=sorted(TERNARY_EXECUTABLE_LANGUAGES),
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
