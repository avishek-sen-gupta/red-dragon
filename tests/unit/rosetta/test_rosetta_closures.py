"""Rosetta test: adder-factory arithmetic across all 15 deterministic frontends.

Two tiers of programs compute the same result (answer = 15):

  Tier 1 — Genuine closures (Python, JavaScript, TypeScript, Lua, Go,
      Kotlin, Scala):
      make_adder(x) returns a nested function adder(y) that captures x
      from the enclosing scope.  answer = make_adder(10)(5)

  Tier 2 — Function-call fallback (Java, Ruby, PHP, C#, C, C++, Rust,
      Pascal):
      A plain two-argument function apply_adder(x, y) with no closure
      semantics.  answer = apply_adder(10, 5)

Why some languages with nested function syntax remain in Tier 2:
  - Rust: nested `fn` items are static and do not capture enclosing variables.
  - Ruby: `def` inside another `def` does not capture outer locals.
  - PHP: nested `function` does not capture without an explicit `use` clause.

The test verifies that every frontend lowers to valid IR and that the VM
produces the correct arithmetic result (15) for all 15 languages.
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
# Language tier classification
# ---------------------------------------------------------------------------

CLOSURE_LANGUAGES: frozenset[str] = frozenset(
    {"python", "javascript", "typescript", "lua", "go", "kotlin", "scala"}
)
FALLBACK_LANGUAGES: frozenset[str] = frozenset(
    {
        "java",
        "ruby",
        "php",
        "csharp",
        "c",
        "cpp",
        "rust",
        "pascal",
    }
)

# ---------------------------------------------------------------------------
# Programs: adder-factory arithmetic in all 15 languages
#
# Tier 1 (CLOSURE_LANGUAGES — 7 languages): make_adder(x) returns
#   adder(y) → x + y, invoked as make_adder(10)(5) = 15.
# Tier 2 (FALLBACK_LANGUAGES — 8 languages): apply_adder(x, y) → x + y,
#   invoked as apply_adder(10, 5) = 15.  No closure semantics.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def make_adder(x):
    def adder(y):
        return x + y
    return adder

add10 = make_adder(10)
answer = add10(5)
""",
    "javascript": """\
function make_adder(x) {
    function adder(y) {
        return x + y;
    }
    return adder;
}

let add10 = make_adder(10);
let answer = add10(5);
""",
    "typescript": """\
function make_adder(x: number): (y: number) => number {
    function adder(y: number): number {
        return x + y;
    }
    return adder;
}

let add10 = make_adder(10);
let answer: number = add10(5);
""",
    "java": """\
class M {
    static int make_adder_result;

    static int apply_adder(int x, int y) {
        return x + y;
    }

    static int answer = apply_adder(10, 5);
}
""",
    "ruby": """\
def make_adder(x)
    def adder(x, y)
        return x + y
    end
    return adder(x, 5)
end

answer = make_adder(10)
""",
    "go": """\
package main

func make_adder(x int) int {
    adder := func(y int) int {
        return x + y
    }
    return adder
}

func main() {
    add10 := make_adder(10)
    answer := add10(5)
    _ = answer
}
""",
    "php": """\
<?php
function make_adder($x) {
    function adder($x, $y) {
        return $x + $y;
    }
    return adder($x, 5);
}

$answer = make_adder(10);
?>
""",
    "csharp": """\
class M {
    static int apply_adder(int x, int y) {
        return x + y;
    }

    static int answer = apply_adder(10, 5);
}
""",
    "c": """\
int apply_adder(int x, int y) {
    return x + y;
}

int answer = apply_adder(10, 5);
""",
    "cpp": """\
int apply_adder(int x, int y) {
    return x + y;
}

int answer = apply_adder(10, 5);
""",
    "rust": """\
fn apply_adder(x: i32, y: i32) -> i32 {
    return x + y;
}

let answer = apply_adder(10, 5);
""",
    "kotlin": """\
fun make_adder(x: Int): Int {
    fun adder(y: Int): Int {
        return x + y
    }
    return adder
}

val add10 = make_adder(10)
val answer = add10(5)
""",
    "scala": """\
object M {
    def make_adder(x: Int): Int = {
        def adder(y: Int): Int = {
            return x + y
        }
        return adder
    }

    val add10 = make_adder(10)
    val answer = add10(5)
}
""",
    "lua": """\
function make_adder(x)
    function adder(y)
        return x + y
    end
    return adder
end

add10 = make_adder(10)
answer = add10(5)
""",
    "pascal": """\
program M;

function apply_adder(x: integer; y: integer): integer;
begin
    apply_adder := x + y;
end;

var answer: integer;
begin
    answer := apply_adder(10, 5);
end.
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


class TestClosuresLowering:
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


class TestClosuresCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, PROGRAMS[lang]) for lang in PROGRAMS}

    def test_all_languages_covered(self):
        assert set(PROGRAMS.keys()) == set(SUPPORTED_DETERMINISTIC_LANGUAGES)

    def test_tier_constants_cover_all_programs(self):
        """CLOSURE_LANGUAGES | FALLBACK_LANGUAGES must equal the full program set."""
        assert CLOSURE_LANGUAGES | FALLBACK_LANGUAGES == set(PROGRAMS.keys())

    def test_cross_language_consistency(self, all_results):
        assert_cross_language_consistency(
            all_results, required_opcodes=REQUIRED_OPCODES
        )


# ---------------------------------------------------------------------------
# VM execution tests (parametrized over executable languages)
# ---------------------------------------------------------------------------

EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 15  # make_adder(10)(5) or apply_adder(10, 5)


class TestClosuresExecution:
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
