"""Rosetta test: class/object operations across all 15 deterministic frontends.

Verifies that the VM can execute programs using class instantiation, field
access, and method calls (or language-appropriate equivalents).

Tier 1 — Class with methods (Python, Java, C#, Kotlin, Scala):
    Class instantiation, field access via ``this``, method calls.

Tier 2 — Object/struct field access (JS, TS, PHP, Ruby, Lua, Go, C, C++, Rust):
    Object/struct creation + field read/write.

Tier 3 — Record field access (Pascal):
    Record type allocation + field read/write.

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
class Counter {
    constructor() { this.count = 0; }
    increment() { this.count = this.count + 1; }
    getValue() { return this.count; }
}
let c = new Counter();
c.increment(); c.increment(); c.increment();
let answer = c.getValue();
""",
    "typescript": """\
class Counter {
    count: number;
    constructor() { this.count = 0; }
    increment(): void { this.count = this.count + 1; }
    getValue(): number { return this.count; }
}
let c = new Counter();
c.increment(); c.increment(); c.increment();
let answer: number = c.getValue();
""",
    "java": """\
class Counter {
    int count;
    Counter() { this.count = 0; }
    void increment() { this.count = this.count + 1; }
    int getValue() { return this.count; }
}
class M {
    static int run() {
        Counter c = new Counter();
        c.increment();
        c.increment();
        c.increment();
        return c.getValue();
    }
    static int answer = run();
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

type Counter struct {
    count int
}

func main() {
    c := Counter{count: 0}
    c.count = c.count + 1
    c.count = c.count + 1
    c.count = c.count + 1
    answer := c.count
    _ = answer
}
""",
    "php": """\
<?php
class Counter {
    public $count;
    function __construct() { $this->count = 0; }
    function increment() { $this->count = $this->count + 1; }
    function getValue() { return $this->count; }
}
$c = new Counter();
$c->increment(); $c->increment(); $c->increment();
$answer = $c->getValue();
?>
""",
    "csharp": """\
class Counter {
    int count;
    Counter() { this.count = 0; }
    void Increment() { this.count = this.count + 1; }
    int GetValue() { return this.count; }
}
class M {
    static int Run() {
        Counter c = new Counter();
        c.Increment();
        c.Increment();
        c.Increment();
        return c.GetValue();
    }
    static int answer = Run();
}
""",
    "c": """\
struct Counter {
    int count;
};
struct Counter c;
c.count = 0;
c.count = c.count + 1;
c.count = c.count + 1;
c.count = c.count + 1;
int answer = c.count;
""",
    "cpp": """\
struct Counter {
    int count;
};
Counter c;
c.count = 0;
c.count = c.count + 1;
c.count = c.count + 1;
c.count = c.count + 1;
int answer = c.count;
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
class Counter {
    var count: Int = 0
    fun increment() { this.count = this.count + 1 }
    fun getValue(): Int { return this.count }
}
val c = Counter()
c.count = 0
c.increment()
c.increment()
c.increment()
val answer: Int = c.getValue()
""",
    "scala": """\
object M {
    class Counter {
        def increment(): Unit = { this.count = this.count + 1 }
        def getValue(): Int = { return this.count }
    }
    def run(): Int = {
        val c = new Counter()
        c.count = 0
        c.increment()
        c.increment()
        c.increment()
        return c.getValue()
    }
    val answer = run()
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
type TCounter = record count: integer; end;
var c: TCounter;
var answer: integer;
begin
    c.count := 0;
    c.count := c.count + 1;
    c.count := c.count + 1;
    c.count := c.count + 1;
    answer := c.count;
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
