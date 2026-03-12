"""Rosetta test: genuine nested functions across 12 languages.

Verifies that languages whose frontends genuinely lower inner functions
nested inside outer functions emit a ``func_inner`` (or ``func___anon``)
label nested inside the ``func_outer`` body, with ``CALL_FUNCTION inner``
inside the outer function.

12 of the 15 deterministic frontends support nested function definitions:
  Python, JavaScript, TypeScript, Rust, Lua, Ruby, Go, Kotlin, Scala, PHP,
  C# (local functions, C# 7+), Pascal (nested procedures)

Excluded (3): C, C++, Java — no nested function syntax.

Program:
    def outer(x):
        def inner(y):
            return y * 2
        return inner(x) + 5
    answer = outer(3)  → inner(3) + 5 → 6 + 5 = 11
"""

import pytest

from interpreter.ir import IRInstruction, Opcode
from interpreter.typed_value import unwrap
from interpreter.vm_types import SymbolicValue, VMState

from tests.unit.rosetta.conftest import (
    parse_for_language,
    find_all,
    assert_clean_lowering,
    execute_for_language,
    extract_answer,
    _var_name_for_language,
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
    "csharp": """\
class M {
    static int outer(int a) {
        int inner(int y) {
            return y * 2;
        }
        return inner(a) + 5;
    }
    static int answer = outer(3);
}
""",
    "pascal": """\
program M;

function outer(x: integer): integer;
    function inner(y: integer): integer;
    begin
        inner := y * 2;
    end;
begin
    outer := inner(x) + 5;
end;

var answer: integer;
begin
    answer := outer(3);
end.
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
            "csharp",
            "pascal",
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


# ---------------------------------------------------------------------------
# Inner function scoping tests: verify inner is inaccessible outside outer
# ---------------------------------------------------------------------------
#
# 9 of 12 languages have genuine inner-function scoping (inner is local to
# outer's scope): Python, JavaScript, TypeScript, Rust, Go, Kotlin, Scala,
# C# (local functions), Pascal (nested procedures).
#
# Excluded (3): Ruby, PHP, Lua — in these languages inner functions leak to
# enclosing/global scope, so testing inaccessibility would not reflect actual
# language semantics.
#
# Each program calls outer(3) → 11, then attempts inner(3) from outside.
# The VM should resolve `inner` symbolically (frame-based lookup fails after
# outer's frame is popped).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Leaky inner-function scoping: Ruby, PHP, Lua
# ---------------------------------------------------------------------------
#
# In Ruby, PHP, and Lua, inner functions leak to enclosing/global scope:
#   - Ruby: `def inner(y)` inside `outer` defines a method on the default definee
#   - PHP: nested `function inner($y)` becomes global after enclosing is called
#   - Lua: `function inner(y)` without `local` assigns to global scope
#
# The VM enforces frame-based scoping, so `inner` becomes inaccessible after
# `outer` returns (producing a SymbolicValue). These xfail tests document the
# expected real-world behaviour and the VM's current limitation.
# ---------------------------------------------------------------------------

LEAKY_LANGUAGES: frozenset[str] = frozenset({"ruby", "php", "lua"})

LEAKY_PROGRAMS: dict[str, str] = {
    "ruby": """\
def outer(x)
    def inner(y)
        return y * 2
    end
    return inner(x) + 5
end

result = outer(3)
leaked = inner(3)
""",
    "php": """\
<?php
function outer($x) {
    function inner($y) {
        return $y * 2;
    }
    return inner($x) + 5;
}

$result = outer(3);
$leaked = inner(3);
?>
""",
    "lua": """\
function outer(x)
    function inner(y)
        return y * 2
    end
    return inner(x) + 5
end

result = outer(3)
leaked = inner(3)
""",
}

EXPECTED_LEAKED_VALUE = 6

SCOPED_LANGUAGES: frozenset[str] = frozenset(
    {
        "python",
        "javascript",
        "typescript",
        "rust",
        "go",
        "kotlin",
        "scala",
        "csharp",
        "pascal",
    }
)

SCOPING_PROGRAMS: dict[str, str] = {
    "python": """\
def outer(x):
    def inner(y):
        return y * 2
    return inner(x) + 5

result = outer(3)
leaked = inner(3)
""",
    "javascript": """\
function outer(x) {
    function inner(y) {
        return y * 2;
    }
    return inner(x) + 5;
}

let result = outer(3);
let leaked = inner(3);
""",
    "typescript": """\
function outer(x: number): number {
    function inner(y: number): number {
        return y * 2;
    }
    return inner(x) + 5;
}

let result: number = outer(3);
let leaked: number = inner(3);
""",
    "rust": """\
fn outer(x: i32) -> i32 {
    fn inner(y: i32) -> i32 {
        return y * 2;
    }
    return inner(x) + 5;
}

let result = outer(3);
let leaked = inner(3);
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
    result := outer(3)
    leaked := inner(3)
    _ = result
    _ = leaked
}
""",
    "kotlin": """\
fun outer(x: Int): Int {
    fun inner(y: Int): Int {
        return y * 2
    }
    return inner(x) + 5
}

val result = outer(3)
val leaked = inner(3)
""",
    "scala": """\
object M {
    def outer(x: Int): Int = {
        def inner(y: Int): Int = {
            return y * 2
        }
        return inner(x) + 5
    }

    val result = outer(3)
    val leaked = inner(3)
}
""",
    "csharp": """\
class M {
    static int outer(int a) {
        int inner(int y) {
            return y * 2;
        }
        return inner(a) + 5;
    }
    static int result = outer(3);
    static int leaked = inner(3);
}
""",
    "pascal": """\
program M;

function outer(x: integer): integer;
    function inner(y: integer): integer;
    begin
        inner := y * 2;
    end;
begin
    outer := inner(x) + 5;
end;

var result: integer;
var leaked: integer;
begin
    result := outer(3);
    leaked := inner(3);
end.
""",
}

EXPECTED_RESULT = 11


def _extract_var(vm: VMState, var_name: str, language: str = "") -> object:
    """Extract a variable from frame 0 locals, handling PHP ``$`` prefix."""
    name = _var_name_for_language(var_name, language)
    frame = vm.call_stack[0]
    assert name in frame.local_vars, (
        f"[{language}] expected '{name}' in frame 0 locals, "
        f"got: {sorted(frame.local_vars.keys())}"
    )
    return unwrap(frame.local_vars[name])


class TestNestedFunctionScoping:
    """Verify that inner functions are inaccessible outside outer's scope."""

    @pytest.fixture(
        params=sorted(SCOPED_LANGUAGES),
        ids=lambda lang: lang,
        scope="class",
    )
    def scoping_result(self, request):
        lang = request.param
        vm, stats = execute_for_language(lang, SCOPING_PROGRAMS[lang])
        return lang, vm, stats

    def test_inner_accessible_inside_outer(self, scoping_result):
        lang, vm, _stats = scoping_result
        result = _extract_var(vm, "result", lang)
        assert (
            result == EXPECTED_RESULT
        ), f"[{lang}] expected result={EXPECTED_RESULT}, got {result}"

    def test_inner_inaccessible_outside_outer(self, scoping_result):
        lang, vm, _stats = scoping_result
        leaked = _extract_var(vm, "leaked", lang)
        assert isinstance(leaked, SymbolicValue), (
            f"[{lang}] expected 'leaked' to be a SymbolicValue "
            f"(inner function not accessible outside outer), "
            f"got {type(leaked).__name__}: {leaked}"
        )

    def test_zero_llm_calls(self, scoping_result):
        lang, _vm, stats = scoping_result
        assert (
            stats.llm_calls == 0
        ), f"[{lang}] expected 0 LLM calls, got {stats.llm_calls}"


# ---------------------------------------------------------------------------
# Leaky inner-function scoping tests (Ruby, PHP, Lua)
# ---------------------------------------------------------------------------
#
# These languages do NOT scope inner functions to the enclosing function.
# In real execution, calling `inner(3)` from outside `outer` returns 6
# (concrete). The VM enforces stricter frame-based scoping, so `inner`
# becomes inaccessible after `outer` returns (producing a SymbolicValue).
#
# The xfail tests document the expected real-world behaviour and the VM's
# current limitation.
# ---------------------------------------------------------------------------


class TestNestedFunctionLeakyScoping:
    """Verify that leaky inner-function scoping is documented via xfail."""

    @pytest.fixture(
        params=sorted(LEAKY_LANGUAGES),
        ids=lambda lang: lang,
        scope="class",
    )
    def leaky_result(self, request):
        lang = request.param
        vm, stats = execute_for_language(lang, LEAKY_PROGRAMS[lang])
        return lang, vm, stats

    def test_inner_accessible_inside_outer(self, leaky_result):
        lang, vm, _stats = leaky_result
        result = _extract_var(vm, "result", lang)
        assert (
            result == EXPECTED_RESULT
        ), f"[{lang}] expected result={EXPECTED_RESULT}, got {result}"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "VM enforces frame-based scoping; in real Ruby/PHP/Lua, "
            "inner functions leak to enclosing/global scope"
        ),
    )
    def test_inner_leaks_outside_outer(self, leaky_result):
        lang, vm, _stats = leaky_result
        leaked = _extract_var(vm, "leaked", lang)
        assert leaked == EXPECTED_LEAKED_VALUE, (
            f"[{lang}] expected leaked={EXPECTED_LEAKED_VALUE} (concrete), "
            f"got {type(leaked).__name__}: {leaked}"
        )

    def test_zero_llm_calls(self, leaky_result):
        lang, _vm, stats = leaky_result
        assert (
            stats.llm_calls == 0
        ), f"[{lang}] expected 0 LLM calls, got {stats.llm_calls}"
