"""Rosetta test: genuine nested functions across 10 languages.

Verifies that languages whose frontends genuinely lower inner functions
nested inside outer functions emit a ``func_inner`` (or ``func___anon``)
label nested inside the ``func_outer`` body, with ``CALL_FUNCTION inner``
inside the outer function.

10 of the 15 deterministic frontends support nested function definitions:
  Python, JavaScript, TypeScript, Rust, Lua, Ruby, Go, Kotlin, Scala, PHP

Excluded (5): C, C++, Java, C#, Pascal — no nested function syntax.

Program:
    def outer(x):
        def inner(y):
            return y * 2
        return inner(x) + 5
    answer = outer(3)  → inner(3) + 5 → 6 + 5 = 11
"""

import pytest

from interpreter.ir import IRInstruction, Opcode

from tests.unit.rosetta.conftest import (
    parse_for_language,
    find_all,
    assert_clean_lowering,
    execute_for_language,
    extract_answer,
)

# ---------------------------------------------------------------------------
# Programs: nested functions in 10 languages
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def outer(x):
    def inner(y):
        return y * 2
    return inner(x) + 5

answer = outer(3)
""",
    "javascript": """\
function outer(x) {
    function inner(y) {
        return y * 2;
    }
    return inner(x) + 5;
}

let answer = outer(3);
""",
    "typescript": """\
function outer(x: number): number {
    function inner(y: number): number {
        return y * 2;
    }
    return inner(x) + 5;
}

let answer: number = outer(3);
""",
    "rust": """\
fn outer(x: i32) -> i32 {
    fn inner(y: i32) -> i32 {
        return y * 2;
    }
    return inner(x) + 5;
}

let answer = outer(3);
""",
    "lua": """\
function outer(x)
    function inner(y)
        return y * 2
    end
    return inner(x) + 5
end

answer = outer(3)
""",
    "ruby": """\
def outer(x)
    def inner(y)
        return y * 2
    end
    return inner(x) + 5
end

answer = outer(3)
""",
    "go": """\
package main

func outer(x int) int {
    inner := func(y int) int {
        return y * 2
    }
    return inner(x) + 5
}

func main() {
    answer := outer(3)
    _ = answer
}
""",
    "kotlin": """\
fun outer(x: Int): Int {
    fun inner(y: Int): Int {
        return y * 2
    }
    return inner(x) + 5
}

val answer = outer(3)
""",
    "scala": """\
object M {
    def outer(x: Int): Int = {
        def inner(y: Int): Int = {
            return y * 2
        }
        return inner(x) + 5
    }

    val answer = outer(3)
}
""",
    "php": """\
<?php
function outer($x) {
    function inner($y) {
        return $y * 2;
    }
    return inner($x) + 5;
}

$answer = outer(3);
?>
""",
}

NESTED_FUNCTION_LANGUAGES: frozenset[str] = frozenset(PROGRAMS.keys())

REQUIRED_OPCODES: set[Opcode] = {Opcode.CALL_FUNCTION, Opcode.RETURN, Opcode.BINOP}

MIN_INSTRUCTIONS = 10

EXPECTED_ANSWER = 11


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_nested_inner_label(ir: list[IRInstruction]) -> bool:
    """Return True if the IR contains a label for an inner/anonymous function."""
    return any(
        inst.opcode == Opcode.LABEL
        and inst.label is not None
        and ("func_inner" in inst.label or "func___anon" in inst.label)
        for inst in ir
    )


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized over 10 languages)
# ---------------------------------------------------------------------------


class TestNestedFunctionsLowering:
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

    def test_inner_function_nested_in_ir(self, language_ir):
        lang, ir = language_ir
        assert _has_nested_inner_label(ir), (
            f"[{lang}] expected a 'func_inner' or 'func___anon' label in IR "
            f"(proving inner function was lowered as a nested definition), "
            f"got labels: {[inst.label for inst in ir if inst.opcode == Opcode.LABEL]}"
        )


# ---------------------------------------------------------------------------
# Cross-language consistency tests (10 languages only)
# ---------------------------------------------------------------------------


class TestNestedFunctionsCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, PROGRAMS[lang]) for lang in PROGRAMS}

    def test_all_nested_function_languages_covered(self):
        expected = {
            "python",
            "javascript",
            "typescript",
            "rust",
            "lua",
            "ruby",
            "go",
            "kotlin",
            "scala",
            "php",
        }
        assert set(PROGRAMS.keys()) == expected

    def test_cross_language_nested_label(self, all_results):
        for lang, ir in all_results.items():
            assert _has_nested_inner_label(ir), (
                f"[{lang}] expected a nested inner function label in IR, "
                f"got labels: {[inst.label for inst in ir if inst.opcode == Opcode.LABEL]}"
            )


# ---------------------------------------------------------------------------
# VM execution tests (parametrized over 10 languages)
# ---------------------------------------------------------------------------


class TestNestedFunctionsExecution:
    @pytest.fixture(
        params=sorted(NESTED_FUNCTION_LANGUAGES),
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
