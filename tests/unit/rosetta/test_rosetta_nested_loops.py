"""Rosetta test: nested loops across all 15 deterministic frontends.

Count pairs (i,j) where 1 <= i < j <= 4. Expected: answer = 6.
Tests nested BRANCH_IF / BRANCH loop structures.
"""

import pytest

from interpreter.frontends import SUPPORTED_DETERMINISTIC_LANGUAGES
from interpreter.ir import Opcode

from tests.unit.rosetta.conftest import (
    parse_for_language,
    find_all,
    assert_clean_lowering,
    assert_cross_language_consistency,
    execute_for_language,
    extract_answer,
    STANDARD_EXECUTABLE_LANGUAGES,
)

# ---------------------------------------------------------------------------
# Programs: count pairs (i,j) with i < j from 1..4 in all 15 languages
# Pairs: (1,2),(1,3),(1,4),(2,3),(2,4),(3,4) = 6
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
answer = 0
i = 1
while i <= 4:
    j = i + 1
    while j <= 4:
        answer = answer + 1
        j = j + 1
    i = i + 1
""",
    "javascript": """\
let answer = 0;
let i = 1;
while (i <= 4) {
    let j = i + 1;
    while (j <= 4) {
        answer = answer + 1;
        j = j + 1;
    }
    i = i + 1;
}
""",
    "typescript": """\
let answer: number = 0;
let i: number = 1;
while (i <= 4) {
    let j: number = i + 1;
    while (j <= 4) {
        answer = answer + 1;
        j = j + 1;
    }
    i = i + 1;
}
""",
    "java": """\
class M {
    static int answer = 0;
    static {
        int i = 1;
        while (i <= 4) {
            int j = i + 1;
            while (j <= 4) {
                answer = answer + 1;
                j = j + 1;
            }
            i = i + 1;
        }
    }
}
""",
    "ruby": """\
answer = 0
i = 1
while i <= 4
    j = i + 1
    while j <= 4
        answer = answer + 1
        j = j + 1
    end
    i = i + 1
end
""",
    "go": """\
package main

func main() {
    answer := 0
    i := 1
    for i <= 4 {
        j := i + 1
        for j <= 4 {
            answer = answer + 1
            j = j + 1
        }
        i = i + 1
    }
    _ = answer
}
""",
    "php": """\
<?php
$answer = 0;
$i = 1;
while ($i <= 4) {
    $j = $i + 1;
    while ($j <= 4) {
        $answer = $answer + 1;
        $j = $j + 1;
    }
    $i = $i + 1;
}
?>
""",
    "csharp": """\
int answer = 0;
int i = 1;
while (i <= 4) {
    int j = i + 1;
    while (j <= 4) {
        answer = answer + 1;
        j = j + 1;
    }
    i = i + 1;
}
""",
    "c": """\
int answer = 0;
int i = 1;
while (i <= 4) {
    int j = i + 1;
    while (j <= 4) {
        answer = answer + 1;
        j = j + 1;
    }
    i = i + 1;
}
""",
    "cpp": """\
int answer = 0;
int i = 1;
while (i <= 4) {
    int j = i + 1;
    while (j <= 4) {
        answer = answer + 1;
        j = j + 1;
    }
    i = i + 1;
}
""",
    "rust": """\
let mut answer = 0;
let mut i = 1;
while i <= 4 {
    let mut j = i + 1;
    while j <= 4 {
        answer = answer + 1;
        j = j + 1;
    }
    i = i + 1;
}
""",
    "kotlin": """\
var answer = 0
var i = 1
while (i <= 4) {
    var j = i + 1
    while (j <= 4) {
        answer = answer + 1
        j = j + 1
    }
    i = i + 1
}
""",
    "scala": """\
object M {
    var answer = 0
    var i = 1
    while (i <= 4) {
        var j = i + 1
        while (j <= 4) {
            answer = answer + 1
            j = j + 1
        }
        i = i + 1
    }
}
""",
    "lua": """\
answer = 0
i = 1
while i <= 4 do
    j = i + 1
    while j <= 4 do
        answer = answer + 1
        j = j + 1
    end
    i = i + 1
end
""",
    "pascal": """\
program M;
var answer, i, j: integer;
begin
    answer := 0;
    i := 1;
    while i <= 4 do
    begin
        j := i + 1;
        while j <= 4 do
        begin
            answer := answer + 1;
            j := j + 1;
        end;
        i := i + 1;
    end;
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {Opcode.BINOP, Opcode.BRANCH_IF, Opcode.BRANCH}

MIN_INSTRUCTIONS = 15


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestNestedLoopsLowering:
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

    def test_multiple_branch_if(self, language_ir):
        """Nested loops need at least 2 BRANCH_IF instructions."""
        lang, ir = language_ir
        branches = find_all(ir, Opcode.BRANCH_IF)
        assert (
            len(branches) >= 2
        ), f"[{lang}] expected >= 2 BRANCH_IF for nested loops, got {len(branches)}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestNestedLoopsCrossLanguage:
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

NESTED_LOOPS_EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 6  # C(4,2) = 6 pairs


class TestNestedLoopsExecution:
    @pytest.fixture(
        params=sorted(NESTED_LOOPS_EXECUTABLE_LANGUAGES),
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
