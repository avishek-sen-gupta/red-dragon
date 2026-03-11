"""Rosetta test: Ackermann function across all 15 deterministic frontends."""

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
# Programs: Ackermann function in all 15 languages
# Each computes ack(2, 3) and stores the result in `answer`.
# ack(2, 3) = 9
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def ack(m, n):
    if m == 0:
        return n + 1
    if n == 0:
        return ack(m - 1, 1)
    return ack(m - 1, ack(m, n - 1))

answer = ack(2, 3)
""",
    "javascript": """\
function ack(m, n) {
    if (m == 0) {
        return n + 1;
    }
    if (n == 0) {
        return ack(m - 1, 1);
    }
    return ack(m - 1, ack(m, n - 1));
}

let answer = ack(2, 3);
""",
    "typescript": """\
function ack(m: number, n: number): number {
    if (m == 0) {
        return n + 1;
    }
    if (n == 0) {
        return ack(m - 1, 1);
    }
    return ack(m - 1, ack(m, n - 1));
}

let answer: number = ack(2, 3);
""",
    "java": """\
class M {
    static int ack(int m, int n) {
        if (m == 0) {
            return n + 1;
        }
        if (n == 0) {
            return ack(m - 1, 1);
        }
        return ack(m - 1, ack(m, n - 1));
    }

    static int answer = ack(2, 3);
}
""",
    "ruby": """\
def ack(m, n)
    if m == 0
        return n + 1
    end
    if n == 0
        return ack(m - 1, 1)
    end
    return ack(m - 1, ack(m, n - 1))
end

answer = ack(2, 3)
""",
    "go": """\
package main

func ack(m int, n int) int {
    if m == 0 {
        return n + 1
    }
    if n == 0 {
        return ack(m - 1, 1)
    }
    return ack(m - 1, ack(m, n - 1))
}

func main() {
    answer := ack(2, 3)
    _ = answer
}
""",
    "php": """\
<?php
function ack($m, $n) {
    if ($m == 0) {
        return $n + 1;
    }
    if ($n == 0) {
        return ack($m - 1, 1);
    }
    return ack($m - 1, ack($m, $n - 1));
}

$answer = ack(2, 3);
?>
""",
    "csharp": """\
class M {
    static int ack(int m, int n) {
        if (m == 0) {
            return n + 1;
        }
        if (n == 0) {
            return ack(m - 1, 1);
        }
        return ack(m - 1, ack(m, n - 1));
    }

    static int answer = ack(2, 3);
}
""",
    "c": """\
int ack(int m, int n) {
    if (m == 0) {
        return n + 1;
    }
    if (n == 0) {
        return ack(m - 1, 1);
    }
    return ack(m - 1, ack(m, n - 1));
}

int answer = ack(2, 3);
""",
    "cpp": """\
int ack(int m, int n) {
    if (m == 0) {
        return n + 1;
    }
    if (n == 0) {
        return ack(m - 1, 1);
    }
    return ack(m - 1, ack(m, n - 1));
}

int answer = ack(2, 3);
""",
    "rust": """\
fn ack(m: i32, n: i32) -> i32 {
    if m == 0 {
        return n + 1;
    }
    if n == 0 {
        return ack(m - 1, 1);
    }
    return ack(m - 1, ack(m, n - 1));
}

let answer = ack(2, 3);
""",
    "kotlin": """\
fun ack(m: Int, n: Int): Int {
    if (m == 0) {
        return n + 1
    }
    if (n == 0) {
        return ack(m - 1, 1)
    }
    return ack(m - 1, ack(m, n - 1))
}

val answer = ack(2, 3)
""",
    "scala": """\
object M {
    def ack(m: Int, n: Int): Int = {
        if (m == 0) {
            return n + 1
        }
        if (n == 0) {
            return ack(m - 1, 1)
        }
        return ack(m - 1, ack(m, n - 1))
    }

    val answer = ack(2, 3)
}
""",
    "lua": """\
function ack(m, n)
    if m == 0 then
        return n + 1
    end
    if n == 0 then
        return ack(m - 1, 1)
    end
    return ack(m - 1, ack(m, n - 1))
end

answer = ack(2, 3)
""",
    "pascal": """\
program M;

function ack(m, n: integer): integer;
begin
    if m = 0 then
    begin
        ack := n + 1;
        exit;
    end;
    if n = 0 then
    begin
        ack := ack(m - 1, 1);
        exit;
    end;
    ack := ack(m - 1, ack(m, n - 1));
end;

var answer: integer;
begin
    answer := ack(2, 3);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.CALL_FUNCTION,
    Opcode.BRANCH_IF,
}

MIN_INSTRUCTIONS = 10


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestAckermannLowering:
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

    def test_recursive_call_present(self, language_ir):
        lang, ir = language_ir
        calls = find_all(ir, Opcode.CALL_FUNCTION)
        call_targets = {str(inst.operands[0]) for inst in calls if inst.operands}
        has_ack_call = any("ack" in target for target in call_targets)
        assert (
            has_ack_call
        ), f"[{lang}] expected at least one CALL_FUNCTION referencing 'ack': {call_targets}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestAckermannCrossLanguage:
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

ACKERMANN_EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 9  # ack(2, 3)


class TestAckermannExecution:
    @pytest.fixture(
        params=sorted(ACKERMANN_EXECUTABLE_LANGUAGES),
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
