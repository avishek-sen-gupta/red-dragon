"""Rosetta test: pattern matching / switch-case across all 15 deterministic frontends."""

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
# Programs: pattern matching in all 15 languages
# Each maps x=2 to answer=20 via conditional dispatch.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
x = 2
if x == 1:
    answer = 10
elif x == 2:
    answer = 20
elif x == 3:
    answer = 30
else:
    answer = 0
""",
    "javascript": """\
let x = 2;
let answer = 0;
if (x == 1) {
    answer = 10;
} else if (x == 2) {
    answer = 20;
} else if (x == 3) {
    answer = 30;
} else {
    answer = 0;
}
""",
    "typescript": """\
let x: number = 2;
let answer: number = 0;
if (x == 1) {
    answer = 10;
} else if (x == 2) {
    answer = 20;
} else if (x == 3) {
    answer = 30;
} else {
    answer = 0;
}
""",
    "java": """\
class M {
    static int solve(int x) {
        if (x == 1) {
            return 10;
        } else if (x == 2) {
            return 20;
        } else if (x == 3) {
            return 30;
        } else {
            return 0;
        }
    }

    static int answer = solve(2);
}
""",
    "ruby": """\
x = 2
if x == 1
    answer = 10
elsif x == 2
    answer = 20
elsif x == 3
    answer = 30
else
    answer = 0
end
""",
    "go": """\
package main

func main() {
    x := 2
    answer := 0
    if x == 1 {
        answer = 10
    } else if x == 2 {
        answer = 20
    } else if x == 3 {
        answer = 30
    } else {
        answer = 0
    }
    _ = answer
}
""",
    "php": """\
<?php
$x = 2;
$answer = 0;
if ($x == 1) {
    $answer = 10;
} elseif ($x == 2) {
    $answer = 20;
} elseif ($x == 3) {
    $answer = 30;
} else {
    $answer = 0;
}
?>
""",
    "csharp": """\
class M {
    static int solve(int x) {
        if (x == 1) {
            return 10;
        } else if (x == 2) {
            return 20;
        } else if (x == 3) {
            return 30;
        } else {
            return 0;
        }
    }

    static int answer = solve(2);
}
""",
    "c": """\
int solve(int x) {
    if (x == 1) {
        return 10;
    } else if (x == 2) {
        return 20;
    } else if (x == 3) {
        return 30;
    } else {
        return 0;
    }
}

int answer = solve(2);
""",
    "cpp": """\
int solve(int x) {
    if (x == 1) {
        return 10;
    } else if (x == 2) {
        return 20;
    } else if (x == 3) {
        return 30;
    } else {
        return 0;
    }
}

int answer = solve(2);
""",
    "rust": """\
fn solve(x: i32) -> i32 {
    if x == 1 {
        return 10;
    } else if x == 2 {
        return 20;
    } else if x == 3 {
        return 30;
    } else {
        return 0;
    }
}

let answer = solve(2);
""",
    "kotlin": """\
fun solve(x: Int): Int {
    if (x == 1) {
        return 10
    } else if (x == 2) {
        return 20
    } else if (x == 3) {
        return 30
    } else {
        return 0
    }
}

val answer = solve(2)
""",
    "scala": """\
object M {
    def solve(x: Int): Int = {
        if (x == 1) {
            return 10
        } else if (x == 2) {
            return 20
        } else if (x == 3) {
            return 30
        } else {
            return 0
        }
    }

    val answer = solve(2)
}
""",
    "lua": """\
function solve(x)
    if x == 1 then
        return 10
    elseif x == 2 then
        return 20
    elseif x == 3 then
        return 30
    else
        return 0
    end
end

answer = solve(2)
""",
    "pascal": """\
program M;

function solve(x: integer): integer;
begin
    if x = 1 then
        solve := 10
    else if x = 2 then
        solve := 20
    else if x = 3 then
        solve := 30
    else
        solve := 0;
end;

var answer: integer;
begin
    answer := solve(2);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.BRANCH_IF,
}

MIN_INSTRUCTIONS = 8


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestPatternMatchingLowering:
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

    def test_branch_if_instructions_present(self, language_ir):
        lang, ir = language_ir
        branches = find_all(ir, Opcode.BRANCH_IF)
        assert (
            len(branches) >= 2
        ), f"[{lang}] expected >= 2 BRANCH_IF instructions, got {len(branches)}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestPatternMatchingCrossLanguage:
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

PATTERN_MATCHING_EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 20


class TestPatternMatchingExecution:
    @pytest.fixture(
        params=sorted(PATTERN_MATCHING_EXECUTABLE_LANGUAGES),
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
