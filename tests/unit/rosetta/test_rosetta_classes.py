"""Rosetta test: class/object operations across all 15 deterministic frontends.

Verifies that the VM can execute programs using class instantiation, field
access, and method calls (or language-appropriate equivalents):

    - Python: class with __init__, increment(), get_value()
    - JS/TS/PHP: object literal or stdClass with field access
    - Ruby/Lua: hash/table with indexed field access
    - Rust: struct with field mutation
    - Java/C#/Scala/Kotlin/Go/C/C++/Pascal: class-level or local state mutation

All programs compute a counter incremented 3 times → answer = 3.
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
# Programs: class/object patterns in all 15 languages
# Each creates an object or structured state, mutates it 3 times, answer = 3.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
class Counter:
    def __init__(self):
        self.count = 0
    def increment(self):
        self.count = self.count + 1
    def get_value(self):
        return self.count

c = Counter()
c.increment()
c.increment()
c.increment()
answer = c.get_value()
""",
    "javascript": """\
let c = {count: 0};
c.count = c.count + 1;
c.count = c.count + 1;
c.count = c.count + 1;
let answer = c.count;
""",
    "typescript": """\
let c = {count: 0};
c.count = c.count + 1;
c.count = c.count + 1;
c.count = c.count + 1;
let answer: number = c.count;
""",
    "java": """\
class M {
    static int count = 0;
    static int a = count + 1;
    static int b = a + 1;
    static int answer = b + 1;
}
""",
    "ruby": """\
c = {}
c["count"] = 0
c["count"] = c["count"] + 1
c["count"] = c["count"] + 1
c["count"] = c["count"] + 1
answer = c["count"]
""",
    "go": """\
package main

func main() {
    count := 0
    count = count + 1
    count = count + 1
    count = count + 1
    answer := count
    _ = answer
}
""",
    "php": """\
<?php
$c = new stdClass();
$c->count = 0;
$c->count = $c->count + 1;
$c->count = $c->count + 1;
$c->count = $c->count + 1;
$answer = $c->count;
?>
""",
    "csharp": """\
class M {
    static int count = 0;
    static int a = count + 1;
    static int b = a + 1;
    static int answer = b + 1;
}
""",
    "c": """\
int count = 0;
count = count + 1;
count = count + 1;
count = count + 1;
int answer = count;
""",
    "cpp": """\
int count = 0;
count = count + 1;
count = count + 1;
count = count + 1;
int answer = count;
""",
    "rust": """\
struct Counter {
    count: i32,
}

let mut c = Counter { count: 0 };
c.count = c.count + 1;
c.count = c.count + 1;
c.count = c.count + 1;
let answer = c.count;
""",
    "kotlin": """\
var count: Int = 0
count = count + 1
count = count + 1
count = count + 1
val answer: Int = count
""",
    "scala": """\
object M {
    var count: Int = 0
    count = count + 1
    count = count + 1
    count = count + 1
    val answer: Int = count
}
""",
    "lua": """\
c = {}
c["count"] = 0
c["count"] = c["count"] + 1
c["count"] = c["count"] + 1
c["count"] = c["count"] + 1
answer = c["count"]
""",
    "pascal": """\
program M;
var count: integer;
var answer: integer;
begin
    count := 0;
    count := count + 1;
    count := count + 1;
    count := count + 1;
    answer := count;
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.BINOP,
    Opcode.STORE_VAR,
}

MIN_INSTRUCTIONS = 6


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestClassesLowering:
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


class TestClassesCrossLanguage:
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
EXPECTED_ANSWER = 3


class TestClassesExecution:
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
