"""Rosetta test: variable scoping across function calls.

Verifies that a callee's local variable with the same name as a caller's
variable does not clobber the caller's value.  Each program defines:

    def callee(x):    # receives x=99, sets x=x*2 internally
        x = x * 2
        return x

    x = 42
    answer = callee(99)
    # x must still be 42, answer must be 198

Two variables checked:
    - ``answer`` = 198  (callee's return value)
    - ``x``      = 42   (caller's local, must survive the call)
"""

import pytest

from interpreter.ir import Opcode
from interpreter.typed_value import unwrap
from tests.unit.rosetta.conftest import (
    parse_for_language,
    assert_clean_lowering,
    execute_for_language,
    extract_answer,
    STANDARD_EXECUTABLE_LANGUAGES,
)

# ---------------------------------------------------------------------------
# Programs: variable scoping across function calls in all 15 languages
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def callee(x):
    x = x * 2
    return x

x = 42
answer = callee(99)
""",
    "javascript": """\
function callee(x) {
    x = x * 2;
    return x;
}

let x = 42;
let answer = callee(99);
""",
    "typescript": """\
function callee(x: number): number {
    x = x * 2;
    return x;
}

let x: number = 42;
let answer: number = callee(99);
""",
    "ruby": """\
def callee(x)
    x = x * 2
    return x
end

x = 42
answer = callee(99)
""",
    "php": """\
<?php
function callee($x) {
    $x = $x * 2;
    return $x;
}

$x = 42;
$answer = callee(99);
?>
""",
    "c": """\
int callee(int x) {
    x = x * 2;
    return x;
}

int x = 42;
int answer = callee(99);
""",
    "cpp": """\
int callee(int x) {
    x = x * 2;
    return x;
}

int x = 42;
int answer = callee(99);
""",
    "rust": """\
fn callee(mut x: i32) -> i32 {
    x = x * 2;
    return x;
}

let x = 42;
let answer = callee(99);
""",
    "kotlin": """\
fun callee(x: Int): Int {
    var y = x * 2
    return y
}

val x = 42
val answer = callee(99)
""",
    "lua": """\
function callee(x)
    x = x * 2
    return x
end

x = 42
answer = callee(99)
""",
    "java": """\
class M {
    static int callee(int x) {
        x = x * 2;
        return x;
    }

    static int x = 42;
    static int answer = callee(99);
}
""",
    "csharp": """\
class M {
    static int callee(int x) {
        x = x * 2;
        return x;
    }

    static int x = 42;
    static int answer = callee(99);
}
""",
    "scala": """\
def callee(x: Int): Int = {
    val y = x * 2
    return y
}

val x = 42
val answer = callee(99)
""",
    "pascal": """\
program ScopeTest;
var
    x: integer;
    answer: integer;

function callee(x: integer): integer;
begin
    x := x * 2;
    callee := x;
end;

begin
    x := 42;
    answer := callee(99);
end.
""",
    "go": """\
package main

func callee(x int) int {
    x = x * 2
    return x
}

func main() {
    x := 42
    answer := callee(99)
    _ = x
    _ = answer
}
""",
}

EXPECTED_ANSWER = 198
EXPECTED_CALLER_X = 42

MIN_INSTRUCTIONS = 8
REQUIRED_OPCODES: set[Opcode] = {Opcode.CALL_FUNCTION, Opcode.RETURN, Opcode.STORE_VAR}


# ---------------------------------------------------------------------------
# IR structure tests
# ---------------------------------------------------------------------------


class TestVariableScopingLowering:
    @pytest.fixture(params=sorted(PROGRAMS.keys()), ids=lambda lang: lang)
    def language(self, request):
        return request.param

    def test_clean_lowering(self, language):
        ir = parse_for_language(language, PROGRAMS[language])
        assert_clean_lowering(
            ir,
            min_instructions=MIN_INSTRUCTIONS,
            required_opcodes=REQUIRED_OPCODES,
            language=language,
        )


# ---------------------------------------------------------------------------
# Execution tests
# ---------------------------------------------------------------------------

EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES


def _extract_var(vm, var_name, language):
    """Extract a variable from frame 0 locals, handling PHP $ prefix."""
    name = f"${var_name}" if language == "php" else var_name
    frame = vm.call_stack[0]
    assert name in frame.local_vars, (
        f"[{language}] expected '{name}' in frame 0 locals, "
        f"got: {sorted(frame.local_vars.keys())}"
    )
    stored = frame.local_vars[name]
    return unwrap(stored)


class TestVariableScopingExecution:
    @pytest.fixture(
        params=sorted(EXECUTABLE_LANGUAGES), ids=lambda lang: lang, scope="class"
    )
    def execution_result(self, request):
        lang = request.param
        vm, stats = execute_for_language(lang, PROGRAMS[lang])
        return lang, vm, stats

    def test_callee_returns_correct_value(self, execution_result):
        lang, vm, _stats = execution_result
        answer = extract_answer(vm, lang)
        assert (
            answer == EXPECTED_ANSWER
        ), f"[{lang}] expected answer={EXPECTED_ANSWER}, got {answer}"

    def test_caller_variable_not_clobbered(self, execution_result):
        """The caller's `x` must still be 42 after callee sets its own `x`."""
        lang, vm, _stats = execution_result
        caller_x = _extract_var(vm, "x", lang)
        assert caller_x == EXPECTED_CALLER_X, (
            f"[{lang}] caller's x was clobbered: "
            f"expected {EXPECTED_CALLER_X}, got {caller_x}"
        )

    def test_zero_llm_calls(self, execution_result):
        lang, _vm, stats = execution_result
        assert (
            stats.llm_calls == 0
        ), f"[{lang}] expected 0 LLM calls, got {stats.llm_calls}"
