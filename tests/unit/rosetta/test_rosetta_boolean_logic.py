"""Rosetta test: Boolean logic across all 15 deterministic frontends."""

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
# Programs: Boolean logic in all 15 languages
# Each computes answer = (true AND (NOT false)) OR false and stores the result.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
a = True
b = False
answer = (a and (not b)) or False
""",
    "javascript": """\
let a = true;
let b = false;
let answer = (a && (!b)) || false;
""",
    "typescript": """\
let a: boolean = true;
let b: boolean = false;
let answer: boolean = (a && (!b)) || false;
""",
    "java": """\
class M { static boolean a = true; static boolean b = false; static boolean answer = (a && (!b)) || false; }
""",
    "ruby": """\
a = true
b = false
answer = (a && (!b)) || false
""",
    "go": """\
package main
func main() {
  a := true
  b := false
  answer := (a && (!b)) || false
  _ = answer
}
""",
    "php": """\
<?php $a = true; $b = false; $answer = ($a && (!$b)) || false; ?>
""",
    "csharp": """\
bool a = true;
bool b = false;
bool answer = (a && (!b)) || false;
""",
    "c": """\
int a = 1;
int b = 0;
int answer = (a && (!b)) || 0;
""",
    "cpp": """\
bool a = true;
bool b = false;
bool answer = (a && (!b)) || false;
""",
    "rust": """\
let a = true;
let b = false;
let answer = (a && (!b)) || false;
""",
    "kotlin": """\
val a = true
val b = false
val answer = (a && (!b)) || false
""",
    "scala": """\
object M { val a = true; val b = false; val answer = (a && (!b)) || false }
""",
    "lua": """\
a = true
b = false
answer = (a and (not b)) or false
""",
    "pascal": """\
program M;
var a, b, answer: boolean;
begin
  a := true;
  b := false;
  answer := (a and (not b)) or false;
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {Opcode.BINOP}

MIN_INSTRUCTIONS = 5

LOGICAL_OPERATORS: set[str] = {"and", "or", "&&", "||"}


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestBooleanLogicLowering:
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

    def test_logical_operator_present(self, language_ir):
        lang, ir = language_ir
        binops = find_all(ir, Opcode.BINOP)
        operators = {str(inst.operands[0]) for inst in binops if inst.operands}
        has_logical = bool(operators & LOGICAL_OPERATORS)
        assert (
            has_logical
        ), f"[{lang}] expected logical operator in BINOP operators: {operators}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestBooleanLogicCrossLanguage:
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

BOOLEAN_LOGIC_EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = True


class TestBooleanLogicExecution:
    @pytest.fixture(
        params=sorted(BOOLEAN_LOGIC_EXECUTABLE_LANGUAGES),
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
