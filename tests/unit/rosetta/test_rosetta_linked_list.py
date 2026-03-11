"""Rosetta test: recursive linked list sum across all 15 deterministic frontends.

Simulates walking a linked list of 3 nodes (values 1, 2, 3) by computing
sum_list(3) = 3 + sum_list(2) = 3 + 2 + sum_list(1) = 3 + 2 + 1 = 6.

The recursive function exercises CALL_FUNCTION (self-calls) and BRANCH_IF
(base case check), mirroring the control flow of traversing a linked list.
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
# Programs: recursive linked list sum in all 15 languages
# Each computes sum_list(3) = 3 + 2 + 1 = 6 and stores the result.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def sum_list(n):
    if n <= 0:
        return 0
    return n + sum_list(n - 1)

answer = sum_list(3)
""",
    "javascript": """\
function sum_list(n) {
    if (n <= 0) {
        return 0;
    }
    return n + sum_list(n - 1);
}

let answer = sum_list(3);
""",
    "typescript": """\
function sum_list(n: number): number {
    if (n <= 0) {
        return 0;
    }
    return n + sum_list(n - 1);
}

let answer: number = sum_list(3);
""",
    "java": """\
class M {
    static int sum_list(int n) {
        if (n <= 0) {
            return 0;
        }
        return n + sum_list(n - 1);
    }

    static int answer = sum_list(3);
}
""",
    "ruby": """\
def sum_list(n)
    if n <= 0
        return 0
    end
    return n + sum_list(n - 1)
end

answer = sum_list(3)
""",
    "go": """\
package main

func sum_list(n int) int {
    if n <= 0 {
        return 0
    }
    return n + sum_list(n - 1)
}

func main() {
    answer := sum_list(3)
    _ = answer
}
""",
    "php": """\
<?php
function sum_list($n) {
    if ($n <= 0) {
        return 0;
    }
    return $n + sum_list($n - 1);
}

$answer = sum_list(3);
?>
""",
    "csharp": """\
class M {
    static int sum_list(int n) {
        if (n <= 0) {
            return 0;
        }
        return n + sum_list(n - 1);
    }

    static int answer = sum_list(3);
}
""",
    "c": """\
int sum_list(int n) {
    if (n <= 0) {
        return 0;
    }
    return n + sum_list(n - 1);
}

int answer = sum_list(3);
""",
    "cpp": """\
int sum_list(int n) {
    if (n <= 0) {
        return 0;
    }
    return n + sum_list(n - 1);
}

int answer = sum_list(3);
""",
    "rust": """\
fn sum_list(n: i32) -> i32 {
    if n <= 0 {
        return 0;
    }
    return n + sum_list(n - 1);
}

let answer = sum_list(3);
""",
    "kotlin": """\
fun sum_list(n: Int): Int {
    if (n <= 0) {
        return 0
    }
    return n + sum_list(n - 1)
}

val answer = sum_list(3)
""",
    "scala": """\
object M {
    def sum_list(n: Int): Int = {
        if (n <= 0) {
            return 0
        }
        return n + sum_list(n - 1)
    }

    val answer = sum_list(3)
}
""",
    "lua": """\
function sum_list(n)
    if n <= 0 then
        return 0
    end
    return n + sum_list(n - 1)
end

answer = sum_list(3)
""",
    "pascal": """\
program M;

function sum_list(n: integer): integer;
begin
    if n <= 0 then
        sum_list := 0
    else
        sum_list := n + sum_list(n - 1);
end;

var answer: integer;
begin
    answer := sum_list(3);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.CALL_FUNCTION,
    Opcode.BRANCH_IF,
}

MIN_INSTRUCTIONS = 8


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestLinkedListLowering:
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

    def test_call_function_present(self, language_ir):
        """Verify CALL_FUNCTION instructions exist for the recursive calls."""
        lang, ir = language_ir
        calls = find_all(ir, Opcode.CALL_FUNCTION)
        assert (
            len(calls) >= 2
        ), f"[{lang}] expected at least 2 CALL_FUNCTION (call site + recursion), got {len(calls)}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestLinkedListCrossLanguage:
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

EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 6  # sum_list(3) = 3 + 2 + 1 = 6


class TestLinkedListExecution:
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
