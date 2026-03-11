"""Rosetta test: iterative binary search (integer square root) across all 15 deterministic frontends.

Computes isqrt(49) = 7 using binary search.  A ``halve`` helper computes
integer halving via ``(x - x % 2) / 2`` to guarantee integer semantics
across all VM backends, and ``sq = mid * mid`` is pre-computed to avoid
operator-precedence differences in some tree-sitter grammars.
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
# Programs: Integer square root via binary search in all 15 languages
# Each computes isqrt(49) and stores the result in `answer`.
# isqrt(n) finds the largest x where x*x <= n, so isqrt(49) = 7.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def halve(x):
    r = x % 2
    return (x - r) // 2

def isqrt(n):
    low = 0
    high = n
    result = 0
    while low <= high:
        mid = halve(low + high)
        sq = mid * mid
        if sq == n:
            return mid
        elif sq < n:
            result = mid
            low = mid + 1
        else:
            high = mid - 1
    return result

answer = isqrt(49)
""",
    "javascript": """\
function halve(x) {
    let r = x % 2;
    return (x - r) / 2;
}

function isqrt(n) {
    let low = 0;
    let high = n;
    let result = 0;
    while (low <= high) {
        let mid = halve(low + high);
        let sq = mid * mid;
        if (sq == n) {
            return mid;
        } else if (sq < n) {
            result = mid;
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }
    return result;
}

let answer = isqrt(49);
""",
    "typescript": """\
function halve(x: number): number {
    let r: number = x % 2;
    return (x - r) / 2;
}

function isqrt(n: number): number {
    let low: number = 0;
    let high: number = n;
    let result: number = 0;
    while (low <= high) {
        let mid: number = halve(low + high);
        let sq: number = mid * mid;
        if (sq == n) {
            return mid;
        } else if (sq < n) {
            result = mid;
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }
    return result;
}

let answer: number = isqrt(49);
""",
    "java": """\
class M {
    static int halve(int x) {
        int r = x % 2;
        return (x - r) / 2;
    }

    static int isqrt(int n) {
        int low = 0;
        int high = n;
        int result = 0;
        while (low <= high) {
            int mid = halve(low + high);
            int sq = mid * mid;
            if (sq == n) {
                return mid;
            } else if (sq < n) {
                result = mid;
                low = mid + 1;
            } else {
                high = mid - 1;
            }
        }
        return result;
    }

    static int answer = isqrt(49);
}
""",
    "ruby": """\
def halve(x)
    r = x % 2
    return (x - r) / 2
end

def isqrt(n)
    low = 0
    high = n
    result = 0
    while low <= high
        mid = halve(low + high)
        sq = mid * mid
        if sq == n
            return mid
        elsif sq < n
            result = mid
            low = mid + 1
        else
            high = mid - 1
        end
    end
    return result
end

answer = isqrt(49)
""",
    "go": """\
package main

func halve(x int) int {
    r := x % 2
    return (x - r) / 2
}

func isqrt(n int) int {
    low := 0
    high := n
    result := 0
    for low <= high {
        mid := halve(low + high)
        sq := mid * mid
        if sq == n {
            return mid
        } else if sq < n {
            result = mid
            low = mid + 1
        } else {
            high = mid - 1
        }
    }
    return result
}

func main() {
    answer := isqrt(49)
    _ = answer
}
""",
    "php": """\
<?php
function halve($x) {
    $r = $x % 2;
    return ($x - $r) / 2;
}

function isqrt($n) {
    $low = 0;
    $high = $n;
    $result = 0;
    while ($low <= $high) {
        $mid = halve($low + $high);
        $sq = $mid * $mid;
        if ($sq == $n) {
            return $mid;
        } else if ($sq < $n) {
            $result = $mid;
            $low = $mid + 1;
        } else {
            $high = $mid - 1;
        }
    }
    return $result;
}

$answer = isqrt(49);
?>
""",
    "csharp": """\
class M {
    static int halve(int x) {
        int r = x % 2;
        return (x - r) / 2;
    }

    static int isqrt(int n) {
        int low = 0;
        int high = n;
        int result = 0;
        while (low <= high) {
            int mid = halve(low + high);
            int sq = mid * mid;
            if (sq == n) {
                return mid;
            } else if (sq < n) {
                result = mid;
                low = mid + 1;
            } else {
                high = mid - 1;
            }
        }
        return result;
    }

    static int answer = isqrt(49);
}
""",
    "c": """\
int halve(int x) {
    int r = x % 2;
    return (x - r) / 2;
}

int isqrt(int n) {
    int low = 0;
    int high = n;
    int result = 0;
    while (low <= high) {
        int mid = halve(low + high);
        int sq = mid * mid;
        if (sq == n) {
            return mid;
        } else if (sq < n) {
            result = mid;
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }
    return result;
}

int answer = isqrt(49);
""",
    "cpp": """\
int halve(int x) {
    int r = x % 2;
    return (x - r) / 2;
}

int isqrt(int n) {
    int low = 0;
    int high = n;
    int result = 0;
    while (low <= high) {
        int mid = halve(low + high);
        int sq = mid * mid;
        if (sq == n) {
            return mid;
        } else if (sq < n) {
            result = mid;
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }
    return result;
}

int answer = isqrt(49);
""",
    "rust": """\
fn halve(x: i32) -> i32 {
    let r: i32 = x % 2;
    return (x - r) / 2;
}

fn isqrt(n: i32) -> i32 {
    let mut low: i32 = 0;
    let mut high: i32 = n;
    let mut result: i32 = 0;
    while low <= high {
        let mid: i32 = halve(low + high);
        let sq: i32 = mid * mid;
        if sq == n {
            return mid;
        } else if sq < n {
            result = mid;
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }
    return result;
}

let answer = isqrt(49);
""",
    "kotlin": """\
fun halve(x: Int): Int {
    val r: Int = x % 2
    return (x - r) / 2
}

fun isqrt(n: Int): Int {
    var low: Int = 0
    var high: Int = n
    var result: Int = 0
    while (low <= high) {
        val mid: Int = halve(low + high)
        val sq: Int = mid * mid
        if (sq == n) {
            return mid
        } else if (sq < n) {
            result = mid
            low = mid + 1
        } else {
            high = mid - 1
        }
    }
    return result
}

val answer = isqrt(49)
""",
    "scala": """\
object M {
    def halve(x: Int): Int = {
        val r: Int = x % 2
        return (x - r) / 2
    }

    def isqrt(n: Int): Int = {
        var low: Int = 0
        var high: Int = n
        var result: Int = 0
        while (low <= high) {
            val mid: Int = halve(low + high)
            val sq: Int = mid * mid
            if (sq == n) {
                return mid
            } else if (sq < n) {
                result = mid
                low = mid + 1
            } else {
                high = mid - 1
            }
        }
        return result
    }

    val answer = isqrt(49)
}
""",
    "lua": """\
function halve(x)
    local r = x % 2
    return (x - r) / 2
end

function isqrt(n)
    local low = 0
    local high = n
    local result = 0
    while low <= high do
        local mid = halve(low + high)
        local sq = mid * mid
        if sq == n then
            return mid
        elseif sq < n then
            result = mid
            low = mid + 1
        else
            high = mid - 1
        end
    end
    return result
end

answer = isqrt(49)
""",
    "pascal": """\
program M;

function halve(x: integer): integer;
var
    r: integer;
begin
    r := x mod 2;
    halve := (x - r) div 2;
end;

function isqrt(n: integer): integer;
var
    low, high, mid, sq, result: integer;
begin
    low := 0;
    high := n;
    result := 0;
    while low <= high do
    begin
        mid := halve(low + high);
        sq := mid * mid;
        if sq = n then
        begin
            isqrt := mid;
            exit;
        end
        else if sq < n then
        begin
            result := mid;
            low := mid + 1;
        end
        else
        begin
            high := mid - 1;
        end;
    end;
    isqrt := result;
end;

var answer: integer;
begin
    answer := isqrt(49);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.BINOP,
    Opcode.BRANCH_IF,
}

MIN_INSTRUCTIONS = 10


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestBinarySearchLowering:
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

    def test_multiply_operator_present(self, language_ir):
        lang, ir = language_ir
        binops = find_all(ir, Opcode.BINOP)
        operators = {str(inst.operands[0]) for inst in binops if inst.operands}
        assert (
            "*" in operators
        ), f"[{lang}] expected '*' in BINOP operators: {operators}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestBinarySearchCrossLanguage:
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

BINARY_SEARCH_EXECUTABLE_LANGUAGES: frozenset[str] = STANDARD_EXECUTABLE_LANGUAGES
EXPECTED_ANSWER = 7  # isqrt(49)


class TestBinarySearchExecution:
    @pytest.fixture(
        params=sorted(BINARY_SEARCH_EXECUTABLE_LANGUAGES),
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
