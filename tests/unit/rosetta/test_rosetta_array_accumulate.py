"""Rosetta test: array accumulation across all 15 deterministic frontends.

Sum elements of an array [1,2,3,4,5] using a while loop. Expected: answer = 15.
Tests NEW_ARRAY, LOAD_INDEX, and loop-based accumulation.

Scala arr(i) emits CALL_FUNCTION (syntax is ambiguous with function calls);
the VM resolves it to native indexing at runtime. So Scala is excluded from
the LOAD_INDEX IR check but included in execution verification.
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
# Programs: sum array [1,2,3,4,5] in all 15 languages
# Expected: answer = 15
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
arr = [1, 2, 3, 4, 5]
answer = 0
i = 0
while i < 5:
    answer = answer + arr[i]
    i = i + 1
""",
    "javascript": """\
let arr = [1, 2, 3, 4, 5];
let answer = 0;
let i = 0;
while (i < 5) {
    answer = answer + arr[i];
    i = i + 1;
}
""",
    "typescript": """\
let arr: number[] = [1, 2, 3, 4, 5];
let answer: number = 0;
let i: number = 0;
while (i < 5) {
    answer = answer + arr[i];
    i = i + 1;
}
""",
    "java": """\
class M {
    static int[] arr = {1, 2, 3, 4, 5};
    static int answer = 0;
    static {
        int i = 0;
        while (i < 5) {
            answer = answer + arr[i];
            i = i + 1;
        }
    }
}
""",
    "ruby": """\
arr = [1, 2, 3, 4, 5]
answer = 0
i = 0
while i < 5
    answer = answer + arr[i]
    i = i + 1
end
""",
    "go": """\
package main

func main() {
    arr := [5]int{1, 2, 3, 4, 5}
    answer := 0
    i := 0
    for i < 5 {
        answer = answer + arr[i]
        i = i + 1
    }
    _ = answer
}
""",
    "php": """\
<?php
$arr = [1, 2, 3, 4, 5];
$answer = 0;
$i = 0;
while ($i < 5) {
    $answer = $answer + $arr[$i];
    $i = $i + 1;
}
?>
""",
    "csharp": """\
int[] arr = {1, 2, 3, 4, 5};
int answer = 0;
int i = 0;
while (i < 5) {
    answer = answer + arr[i];
    i = i + 1;
}
""",
    "c": """\
int arr[] = {1, 2, 3, 4, 5};
int answer = 0;
int i = 0;
while (i < 5) {
    answer = answer + arr[i];
    i = i + 1;
}
""",
    "cpp": """\
int arr[] = {1, 2, 3, 4, 5};
int answer = 0;
int i = 0;
while (i < 5) {
    answer = answer + arr[i];
    i = i + 1;
}
""",
    "rust": """\
let arr = [1, 2, 3, 4, 5];
let mut answer = 0;
let mut i = 0;
while i < 5 {
    answer = answer + arr[i];
    i = i + 1;
}
""",
    "kotlin": """\
val arr = intArrayOf(1, 2, 3, 4, 5)
var answer = 0
var i = 0
while (i < 5) {
    answer = answer + arr[i]
    i = i + 1
}
""",
    "scala": """\
object M {
    val arr = Array(1, 2, 3, 4, 5)
    var answer = 0
    var i = 0
    while (i < 5) {
        answer = answer + arr(i)
        i = i + 1
    }
}
""",
    "lua": """\
arr = {1, 2, 3, 4, 5}
answer = 0
i = 1
while i <= 5 do
    answer = answer + arr[i]
    i = i + 1
end
""",
    "pascal": """\
program M;
var arr: array[0..4] of integer;
    answer, i: integer;
begin
    arr[0] := 1;
    arr[1] := 2;
    arr[2] := 3;
    arr[3] := 4;
    arr[4] := 5;
    answer := 0;
    i := 0;
    while i < 5 do
    begin
        answer := answer + arr[i];
        i := i + 1;
    end;
end.
""",
}

# Scala arr(i) emits CALL_FUNCTION (resolved to indexing by VM at runtime)
LANGUAGES_WITHOUT_LOAD_INDEX: frozenset[str] = frozenset({"scala"})

REQUIRED_OPCODES: set[Opcode] = {Opcode.BINOP, Opcode.BRANCH_IF}

MIN_INSTRUCTIONS = 10


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestArrayAccumulateLowering:
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

    def test_load_index_present(self, language_ir):
        lang, ir = language_ir
        if lang in LANGUAGES_WITHOUT_LOAD_INDEX:
            pytest.skip(
                f"{lang} uses CALL_FUNCTION for array access (VM resolves at runtime)"
            )
        load_indices = find_all(ir, Opcode.LOAD_INDEX)
        assert (
            len(load_indices) >= 1
        ), f"[{lang}] expected at least one LOAD_INDEX instruction, got {len(load_indices)}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestArrayAccumulateCrossLanguage:
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

ARRAY_EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 15  # 1 + 2 + 3 + 4 + 5 = 15


class TestArrayAccumulateExecution:
    @pytest.fixture(
        params=sorted(ARRAY_EXECUTABLE_LANGUAGES),
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
