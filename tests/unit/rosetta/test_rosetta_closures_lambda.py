"""Rosetta test: lambda/arrow-function closure variants for 5 languages.

Companion to test_rosetta_closures.py which exercises the nested
def/function form.  This test covers the lambda/arrow-function
alternative for the 5 languages that support it:

  - Python:     lambda x: lambda y: x + y
  - JavaScript: (x) => { ... }
  - TypeScript:  (x: number): ... => { ... }
  - Kotlin:     { y: Int -> x + y }
  - Scala:      (y: Int) => x + y

All compute make_adder(10)(5) = 15 using closures that capture x.
"""

import pytest

from interpreter.ir import Opcode

from tests.unit.rosetta.conftest import (
    parse_for_language,
    opcodes,
    assert_clean_lowering,
    assert_cross_language_consistency,
    execute_for_language,
    extract_answer,
)

# ---------------------------------------------------------------------------
# Programs: adder-factory using lambda/arrow syntax
# ---------------------------------------------------------------------------

LAMBDA_LANGUAGES: frozenset[str] = frozenset(
    {"python", "javascript", "typescript", "kotlin", "scala"}
)

PROGRAMS: dict[str, str] = {
    "python": """\
make_adder = lambda x: lambda y: x + y

add10 = make_adder(10)
answer = add10(5)
""",
    "javascript": """\
let make_adder = (x) => {
    let adder = (y) => x + y;
    return adder;
};

let add10 = make_adder(10);
let answer = add10(5);
""",
    "typescript": """\
let make_adder = (x: number): ((y: number) => number) => {
    let adder = (y: number): number => x + y;
    return adder;
};

let add10 = make_adder(10);
let answer: number = add10(5);
""",
    "kotlin": """\
fun make_adder(x: Int): Int {
    val adder = { y: Int -> x + y }
    return adder
}

val add10 = make_adder(10)
val answer = add10(5)
""",
    "scala": """\
object M {
    def make_adder(x: Int): Int = {
        val adder = (y: Int) => x + y
        return adder
    }

    val add10 = make_adder(10)
    val answer = add10(5)
}
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.CALL_FUNCTION,
    Opcode.RETURN,
    Opcode.BINOP,
}

MIN_INSTRUCTIONS = 6


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestClosuresLambdaLowering:
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


class TestClosuresLambdaCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, PROGRAMS[lang]) for lang in PROGRAMS}

    def test_all_lambda_languages_covered(self):
        assert set(PROGRAMS.keys()) == LAMBDA_LANGUAGES

    def test_cross_language_consistency(self, all_results):
        # Use a local consistency check (not the global one which expects 15 languages)
        opcode_sets = [opcodes(ir) for ir in all_results.values()]
        intersection = set.intersection(*opcode_sets)
        missing = REQUIRED_OPCODES - intersection
        assert not missing, f"Required opcodes not universal: {missing}"


# ---------------------------------------------------------------------------
# VM execution tests (parametrized over all 5 lambda languages)
# ---------------------------------------------------------------------------

EXPECTED_ANSWER = 15


class TestClosuresLambdaExecution:
    @pytest.fixture(
        params=sorted(LAMBDA_LANGUAGES), ids=lambda lang: lang, scope="class"
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
