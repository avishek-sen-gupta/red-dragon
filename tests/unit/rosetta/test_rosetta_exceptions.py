"""Rosetta test: exception handling across deterministic frontends.

Verifies that the VM can lower and execute try/catch (or equivalent)
constructs. The try body sets ``answer = -1`` and branches past the catch
block, which is structurally present but unreachable in the current VM
(THROW is a no-op that does not redirect control flow).

C, Go, Rust, and Lua are excluded — they use fundamentally different
error handling paradigms (none, defer/recover, Result/panic, pcall).
See red-dragon-xvn (Go) and red-dragon-e2k (Lua) for those gaps.
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
# Programs: exception handling (try/catch) in 11 languages
# C, Go, Rust, Lua excluded (different error paradigms).
# Each sets answer = -1 via try body.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
answer = 0
try:
    answer = -1
except Exception as e:
    answer = 99
""",
    "javascript": """\
let answer = 0;
try {
    answer = -1;
} catch (e) {
    answer = 99;
}
""",
    "typescript": """\
let answer: number = 0;
try {
    answer = -1;
} catch (e) {
    answer = 99;
}
""",
    "java": """\
class M {
    static int answer = 0;
    static {
        try {
            answer = -1;
        } catch (Exception e) {
            answer = 99;
        }
    }
}
""",
    "ruby": """\
answer = 0
begin
    answer = -1
rescue => e
    answer = 99
end
""",
    "php": """\
<?php
$answer = 0;
try {
    $answer = -1;
} catch (Exception $e) {
    $answer = 99;
}
?>
""",
    "csharp": """\
int answer = 0;
try {
    answer = -1;
} catch (Exception e) {
    answer = 99;
}
""",
    "cpp": """\
int answer = 0;
try {
    answer = -1;
} catch (...) {
    answer = 99;
}
""",
    "kotlin": """\
var answer: Int = 0
try {
    answer = -1
} catch (e: Exception) {
    answer = 99
}
""",
    "scala": """\
object M {
    var answer: Int = 0
    try {
        answer = -1
    } catch {
        case e: Exception => answer = 99
    }
}
""",
    "pascal": """\
program M;
var answer: integer;
begin
    try
        answer := -1;
    except
        on e: Exception do
            answer := 99;
    end;
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.STORE_VAR,
}

MIN_INSTRUCTIONS = 3

# All languages in PROGRAMS have try/catch — no fallbacks
_EXCLUDED_LANGUAGES: frozenset[str] = frozenset({"c", "go", "rust", "lua"})


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestExceptionsLowering:
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

    def test_try_catch_structure(self, language_ir):
        """All programs should generate SYMBOLIC caught_exception."""
        lang, ir = language_ir
        symbolics = find_all(ir, Opcode.SYMBOLIC)
        caught = [
            s
            for s in symbolics
            if any("caught_exception" in str(op) for op in s.operands)
        ]
        assert len(caught) == 1, (
            f"[{lang}] expected exactly 1 SYMBOLIC caught_exception "
            f"in try/catch lowering, got {len(caught)}"
        )


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestExceptionsCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, PROGRAMS[lang]) for lang in PROGRAMS}

    def test_all_languages_covered(self):
        # C, Go, Rust, Lua excluded: different error paradigms
        expected = set(SUPPORTED_DETERMINISTIC_LANGUAGES) - _EXCLUDED_LANGUAGES
        assert set(PROGRAMS.keys()) == expected

    def test_cross_language_consistency(self, all_results):
        assert_cross_language_consistency(
            all_results,
            required_opcodes=REQUIRED_OPCODES,
            expected_languages=set(PROGRAMS.keys()),
        )


# ---------------------------------------------------------------------------
# VM execution tests (parametrized over executable languages)
# ---------------------------------------------------------------------------

EXECUTABLE_LANGUAGES: frozenset[str] = (
    STANDARD_EXECUTABLE_LANGUAGES - _EXCLUDED_LANGUAGES
)
EXPECTED_ANSWER = -1  # try body completes, catch is dead code in current VM


class TestExceptionsExecution:
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
