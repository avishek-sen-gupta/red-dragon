"""Rosetta test: is_prime across all 15 deterministic frontends."""

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
# Programs: is_prime in all 15 languages
# Each computes isPrime(17) and stores the result.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def is_prime(n):
    if n < 2:
        return 0
    i = 2
    while i * i <= n:
        if n % i == 0:
            return 0
        i = i + 1
    return 1

answer = is_prime(17)
""",
    "javascript": """\
function isPrime(n) {
    if (n < 2) {
        return 0;
    }
    let i = 2;
    while (i * i <= n) {
        if (n % i == 0) {
            return 0;
        }
        i = i + 1;
    }
    return 1;
}

let answer = isPrime(17);
""",
    "typescript": """\
function isPrime(n: number): number {
    if (n < 2) {
        return 0;
    }
    let i: number = 2;
    while (i * i <= n) {
        if (n % i == 0) {
            return 0;
        }
        i = i + 1;
    }
    return 1;
}

let answer: number = isPrime(17);
""",
    "java": """\
class M {
    static int isPrime(int n) {
        if (n < 2) {
            return 0;
        }
        int i = 2;
        while (i * i <= n) {
            if (n % i == 0) {
                return 0;
            }
            i = i + 1;
        }
        return 1;
    }

    static int answer = isPrime(17);
}
""",
    "ruby": """\
def is_prime(n)
    if n < 2
        return 0
    end
    i = 2
    while i * i <= n
        if n % i == 0
            return 0
        end
        i = i + 1
    end
    return 1
end

answer = is_prime(17)
""",
    "go": """\
package main

func isPrime(n int) int {
    if n < 2 {
        return 0
    }
    i := 2
    for i * i <= n {
        if n % i == 0 {
            return 0
        }
        i = i + 1
    }
    return 1
}

func main() {
    answer := isPrime(17)
    _ = answer
}
""",
    "php": """\
<?php
function isPrime($n) {
    if ($n < 2) {
        return 0;
    }
    $i = 2;
    while ($i * $i <= $n) {
        if ($n % $i == 0) {
            return 0;
        }
        $i = $i + 1;
    }
    return 1;
}

$answer = isPrime(17);
?>
""",
    "csharp": """\
class M {
    static int isPrime(int n) {
        if (n < 2) {
            return 0;
        }
        int i = 2;
        while (i * i <= n) {
            if (n % i == 0) {
                return 0;
            }
            i = i + 1;
        }
        return 1;
    }

    static int answer = isPrime(17);
}
""",
    "c": """\
int isPrime(int n) {
    if (n < 2) {
        return 0;
    }
    int i = 2;
    while (i * i <= n) {
        if (n % i == 0) {
            return 0;
        }
        i = i + 1;
    }
    return 1;
}

int answer = isPrime(17);
""",
    "cpp": """\
int isPrime(int n) {
    if (n < 2) {
        return 0;
    }
    int i = 2;
    while (i * i <= n) {
        if (n % i == 0) {
            return 0;
        }
        i = i + 1;
    }
    return 1;
}

int answer = isPrime(17);
""",
    "rust": """\
fn is_prime(n: i32) -> i32 {
    if n < 2 {
        return 0;
    }
    let mut i: i32 = 2;
    while i * i <= n {
        if n % i == 0 {
            return 0;
        }
        i = i + 1;
    }
    return 1;
}

let answer = is_prime(17);
""",
    "kotlin": """\
fun isPrime(n: Int): Int {
    if (n < 2) {
        return 0
    }
    var i: Int = 2
    while (i * i <= n) {
        if (n % i == 0) {
            return 0
        }
        i = i + 1
    }
    return 1
}

val answer = isPrime(17)
""",
    "scala": """\
object M {
    def isPrime(n: Int): Int = {
        if (n < 2) {
            return 0
        }
        var i: Int = 2
        while (i * i <= n) {
            if (n % i == 0) {
                return 0
            }
            i = i + 1
        }
        return 1
    }

    val answer = isPrime(17)
}
""",
    "lua": """\
function isPrime(n)
    if n < 2 then
        return 0
    end
    local i = 2
    while i * i <= n do
        if n % i == 0 then
            return 0
        end
        i = i + 1
    end
    return 1
end

answer = isPrime(17)
""",
    "pascal": """\
program M;

function isPrime(n: integer): integer;
var
    i: integer;
begin
    if n < 2 then
    begin
        isPrime := 0;
        exit;
    end;
    i := 2;
    while i * i <= n do
    begin
        if n mod i = 0 then
        begin
            isPrime := 0;
            exit;
        end;
        i := i + 1;
    end;
    isPrime := 1;
end;

var answer: integer;
begin
    answer := isPrime(17);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.RETURN,
    Opcode.BRANCH_IF,
    Opcode.BINOP,
}

MIN_INSTRUCTIONS = 10


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestIsPrimeLowering:
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

    def test_modulo_operator_present(self, language_ir):
        lang, ir = language_ir
        binops = find_all(ir, Opcode.BINOP)
        operators = {str(inst.operands[0]) for inst in binops if inst.operands}
        modulo_variants = {"%", "mod"}
        assert (
            operators & modulo_variants
        ), f"[{lang}] expected '%' or 'mod' in BINOP operators: {operators}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestIsPrimeCrossLanguage:
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
EXPECTED_ANSWER = 1  # isPrime(17) = true (as int)


class TestIsPrimeExecution:
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
