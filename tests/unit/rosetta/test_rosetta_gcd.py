"""Rosetta test: Euclidean GCD across all 15 deterministic frontends."""

import pytest

from interpreter.frontends import SUPPORTED_DETERMINISTIC_LANGUAGES
from interpreter.ir import Opcode

from tests.unit.rosetta.conftest import (
    parse_for_language,
    opcodes,
    find_all,
    assert_clean_lowering,
    assert_cross_language_consistency,
)

# ---------------------------------------------------------------------------
# Programs: Euclidean GCD in all 15 languages
# Each computes gcd(48, 18) and stores the result.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def gcd(a, b):
    while b != 0:
        temp = b
        b = a % b
        a = temp
    return a

answer = gcd(48, 18)
""",
    "javascript": """\
function gcd(a, b) {
    while (b != 0) {
        let temp = b;
        b = a % b;
        a = temp;
    }
    return a;
}

let answer = gcd(48, 18);
""",
    "typescript": """\
function gcd(a: number, b: number): number {
    while (b != 0) {
        let temp: number = b;
        b = a % b;
        a = temp;
    }
    return a;
}

let answer: number = gcd(48, 18);
""",
    "java": """\
class M {
    static int gcd(int a, int b) {
        while (b != 0) {
            int temp = b;
            b = a % b;
            a = temp;
        }
        return a;
    }

    static int answer = gcd(48, 18);
}
""",
    "ruby": """\
def gcd(a, b)
    while b != 0
        temp = b
        b = a % b
        a = temp
    end
    return a
end

answer = gcd(48, 18)
""",
    "go": """\
package main

func gcd(a int, b int) int {
    for b != 0 {
        temp := b
        b = a % b
        a = temp
    }
    return a
}

func main() {
    answer := gcd(48, 18)
    _ = answer
}
""",
    "php": """\
<?php
function gcd($a, $b) {
    while ($b != 0) {
        $temp = $b;
        $b = $a % $b;
        $a = $temp;
    }
    return $a;
}

$answer = gcd(48, 18);
?>
""",
    "csharp": """\
class M {
    static int gcd(int a, int b) {
        while (b != 0) {
            int temp = b;
            b = a % b;
            a = temp;
        }
        return a;
    }

    static int answer = gcd(48, 18);
}
""",
    "c": """\
int gcd(int a, int b) {
    while (b != 0) {
        int temp = b;
        b = a % b;
        a = temp;
    }
    return a;
}

int answer = gcd(48, 18);
""",
    "cpp": """\
int gcd(int a, int b) {
    while (b != 0) {
        int temp = b;
        b = a % b;
        a = temp;
    }
    return a;
}

int answer = gcd(48, 18);
""",
    "rust": """\
fn gcd(a: i32, b: i32) -> i32 {
    let mut a: i32 = a;
    let mut b: i32 = b;
    while b != 0 {
        let temp: i32 = b;
        b = a % b;
        a = temp;
    }
    return a;
}

let answer = gcd(48, 18);
""",
    "kotlin": """\
fun gcd(a: Int, b: Int): Int {
    var a: Int = a
    var b: Int = b
    while (b != 0) {
        val temp: Int = b
        b = a % b
        a = temp
    }
    return a
}

val answer = gcd(48, 18)
""",
    "scala": """\
object M {
    def gcd(a: Int, b: Int): Int = {
        var a2: Int = a
        var b2: Int = b
        while (b2 != 0) {
            val temp: Int = b2
            b2 = a2 % b2
            a2 = temp
        }
        return a2
    }

    val answer = gcd(48, 18)
}
""",
    "lua": """\
function gcd(a, b)
    while b ~= 0 do
        local temp = b
        b = a % b
        a = temp
    end
    return a
end

answer = gcd(48, 18)
""",
    "pascal": """\
program M;

function gcd(a, b: integer): integer;
var
    temp: integer;
begin
    while b <> 0 do
    begin
        temp := b;
        b := a mod b;
        a := temp;
    end;
    gcd := a;
end;

var answer: integer;
begin
    answer := gcd(48, 18);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.BINOP,
    Opcode.BRANCH_IF,
}

MIN_INSTRUCTIONS = 8


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestGcdLowering:
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
        has_modulo = "%" in operators or "mod" in operators
        assert (
            has_modulo
        ), f"[{lang}] expected '%' or 'mod' in BINOP operators: {operators}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestGcdCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, PROGRAMS[lang]) for lang in PROGRAMS}

    def test_all_languages_covered(self):
        assert set(PROGRAMS.keys()) == set(SUPPORTED_DETERMINISTIC_LANGUAGES)

    def test_cross_language_consistency(self, all_results):
        assert_cross_language_consistency(
            all_results, required_opcodes=REQUIRED_OPCODES
        )
