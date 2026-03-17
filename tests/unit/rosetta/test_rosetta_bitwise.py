"""Rosetta test: bitwise operations across all 15 deterministic frontends.

All 15 languages use native bitwise operators: &/^ (most), and/xor (Kotlin,
Pascal), ~ for XOR (Lua).
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
# Programs: bitwise (a AND b) XOR 5 in all 15 languages
# a=12, b=10 => a&b=8, 8^5=13. Expected: answer=13.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
a = 12
b = 10
c = a & b
answer = c ^ 5
""",
    "javascript": """\
let a = 12;
let b = 10;
let c = a & b;
let answer = c ^ 5;
""",
    "typescript": """\
let a: number = 12;
let b: number = 10;
let c: number = a & b;
let answer: number = c ^ 5;
""",
    "java": """\
class M {
    static int a = 12;
    static int b = 10;
    static int c = a & b;
    static int answer = c ^ 5;
}
""",
    "ruby": """\
a = 12
b = 10
c = a & b
answer = c ^ 5
""",
    "go": """\
package main

func main() {
    a := 12
    b := 10
    c := a & b
    answer := c ^ 5
    _ = answer
}
""",
    "php": """\
<?php
$a = 12;
$b = 10;
$c = $a & $b;
$answer = $c ^ 5;
?>
""",
    "csharp": """\
int a = 12;
int b = 10;
int c = a & b;
int answer = c ^ 5;
""",
    "c": """\
int a = 12;
int b = 10;
int c = a & b;
int answer = c ^ 5;
""",
    "cpp": """\
int a = 12;
int b = 10;
int c = a & b;
int answer = c ^ 5;
""",
    "rust": """\
let a: i32 = 12;
let b: i32 = 10;
let c = a & b;
let answer = c ^ 5;
""",
    "kotlin": """\
val a = 12
val b = 10
val c = a and b
val answer = c xor 5
""",
    "scala": """\
object M {
    val a = 12
    val b = 10
    val c = a & b
    val answer = c ^ 5
}
""",
    "lua": """\
a = 12
b = 10
c = a & b
answer = c ~ 5
""",
    "pascal": """\
program M;
var a, b, c, answer: integer;
begin
    a := 12;
    b := 10;
    c := a and b;
    answer := c xor 5;
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {Opcode.BINOP}

MIN_INSTRUCTIONS = 5


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestBitwiseLowering:
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

    def test_bitwise_operators_in_binops(self, language_ir):
        """IR must contain bitwise AND and a XOR-family operator."""
        lang, ir = language_ir
        operators = {inst.operands[0] for inst in find_all(ir, Opcode.BINOP)}
        assert (
            "&" in operators
        ), f"[{lang}] expected '&' (bitwise AND) in BINOP operators, got {operators}"
        # Lua uses '~' for XOR, other languages use '^'
        has_xor = operators & {"^", "~"}
        assert (
            has_xor
        ), f"[{lang}] expected XOR operator ('^' or '~') in BINOP operators, got {operators}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestBitwiseCrossLanguage:
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

BITWISE_EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 13  # (12 & 10) ^ 5 = 8 ^ 5 = 13


class TestBitwiseExecution:
    @pytest.fixture(
        params=sorted(BITWISE_EXECUTABLE_LANGUAGES),
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
