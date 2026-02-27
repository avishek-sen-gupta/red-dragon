"""Rosetta test: bubble sort across all 15 deterministic frontends."""

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
    extract_array,
    STANDARD_EXECUTABLE_LANGUAGES,
)

# ---------------------------------------------------------------------------
# Programs: bubble sort in all 15 languages
# Each sorts an array of 5 elements: [5, 3, 8, 1, 2]
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
arr = [5, 3, 8, 1, 2]
n = len(arr)
i = 0
while i < n:
    j = 0
    while j < n - 1 - i:
        if arr[j] > arr[j + 1]:
            temp = arr[j]
            arr[j] = arr[j + 1]
            arr[j + 1] = temp
        j = j + 1
    i = i + 1
""",
    "javascript": """\
let arr = [5, 3, 8, 1, 2];
let n = 5;
let i = 0;
while (i < n) {
    let j = 0;
    while (j < n - 1 - i) {
        if (arr[j] > arr[j + 1]) {
            let temp = arr[j];
            arr[j] = arr[j + 1];
            arr[j + 1] = temp;
        }
        j = j + 1;
    }
    i = i + 1;
}
""",
    "typescript": """\
let arr: number[] = [5, 3, 8, 1, 2];
let n: number = 5;
let i: number = 0;
while (i < n) {
    let j: number = 0;
    while (j < n - 1 - i) {
        if (arr[j] > arr[j + 1]) {
            let temp: number = arr[j];
            arr[j] = arr[j + 1];
            arr[j + 1] = temp;
        }
        j = j + 1;
    }
    i = i + 1;
}
""",
    "java": """\
class M {
    static int[] arr = {5, 3, 8, 1, 2};
    static int n = 5;
    static void bubbleSort() {
        int i = 0;
        while (i < n) {
            int j = 0;
            while (j < n - 1 - i) {
                if (arr[j] > arr[j + 1]) {
                    int temp = arr[j];
                    arr[j] = arr[j + 1];
                    arr[j + 1] = temp;
                }
                j = j + 1;
            }
            i = i + 1;
        }
    }
}
""",
    "ruby": """\
arr = [5, 3, 8, 1, 2]
n = 5
i = 0
while i < n
    j = 0
    while j < n - 1 - i
        if arr[j] > arr[j + 1]
            temp = arr[j]
            arr[j] = arr[j + 1]
            arr[j + 1] = temp
        end
        j = j + 1
    end
    i = i + 1
end
""",
    "go": """\
package main

func main() {
    arr := [5]int{5, 3, 8, 1, 2}
    n := 5
    i := 0
    for i < n {
        j := 0
        for j < n - 1 - i {
            if arr[j] > arr[j + 1] {
                temp := arr[j]
                arr[j] = arr[j + 1]
                arr[j + 1] = temp
            }
            j = j + 1
        }
        i = i + 1
    }
    _ = arr
}
""",
    "php": """\
<?php
$arr = array(5, 3, 8, 1, 2);
$n = 5;
$i = 0;
while ($i < $n) {
    $j = 0;
    while ($j < $n - 1 - $i) {
        if ($arr[$j] > $arr[$j + 1]) {
            $temp = $arr[$j];
            $arr[$j] = $arr[$j + 1];
            $arr[$j + 1] = $temp;
        }
        $j = $j + 1;
    }
    $i = $i + 1;
}
?>
""",
    "csharp": """\
class M {
    static int[] arr = {5, 3, 8, 1, 2};
    static int n = 5;
    static void bubbleSort() {
        int i = 0;
        while (i < n) {
            int j = 0;
            while (j < n - 1 - i) {
                if (arr[j] > arr[j + 1]) {
                    int temp = arr[j];
                    arr[j] = arr[j + 1];
                    arr[j + 1] = temp;
                }
                j = j + 1;
            }
            i = i + 1;
        }
    }
}
""",
    "c": """\
int arr[5] = {5, 3, 8, 1, 2};
int n = 5;

void bubbleSort() {
    int i = 0;
    while (i < n) {
        int j = 0;
        while (j < n - 1 - i) {
            if (arr[j] > arr[j + 1]) {
                int temp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = temp;
            }
            j = j + 1;
        }
        i = i + 1;
    }
}
""",
    "cpp": """\
int arr[5] = {5, 3, 8, 1, 2};
int n = 5;

void bubbleSort() {
    int i = 0;
    while (i < n) {
        int j = 0;
        while (j < n - 1 - i) {
            if (arr[j] > arr[j + 1]) {
                int temp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = temp;
            }
            j = j + 1;
        }
        i = i + 1;
    }
}
""",
    "rust": """\
fn main() {
    let mut arr: [i32; 5] = [5, 3, 8, 1, 2];
    let n: i32 = 5;
    let mut i: i32 = 0;
    while i < n {
        let mut j: i32 = 0;
        while j < n - 1 - i {
            if arr[j] > arr[j + 1] {
                let temp: i32 = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = temp;
            }
            j = j + 1;
        }
        i = i + 1;
    }
}
""",
    "kotlin": """\
fun main() {
    var arr: IntArray = intArrayOf(5, 3, 8, 1, 2)
    var n: Int = 5
    var i: Int = 0
    while (i < n) {
        var j: Int = 0
        while (j < n - 1 - i) {
            if (arr[j] > arr[j + 1]) {
                var temp: Int = arr[j]
                arr[j] = arr[j + 1]
                arr[j + 1] = temp
            }
            j = j + 1
        }
        i = i + 1
    }
}
""",
    "scala": """\
object M {
    def main(): Unit = {
        var arr: Array[Int] = Array(5, 3, 8, 1, 2)
        var n: Int = 5
        var i: Int = 0
        while (i < n) {
            var j: Int = 0
            while (j < n - 1 - i) {
                if (arr(j) > arr(j + 1)) {
                    var temp: Int = arr(j)
                    arr(j) = arr(j + 1)
                    arr(j + 1) = temp
                }
                j = j + 1
            }
            i = i + 1
        }
    }
}
""",
    "lua": """\
local arr = {5, 3, 8, 1, 2}
local n = 5
local i = 0
while i < n do
    local j = 0
    while j < n - 1 - i do
        if arr[j + 1] > arr[j + 1 + 1] then
            local temp = arr[j + 1]
            arr[j + 1] = arr[j + 1 + 1]
            arr[j + 1 + 1] = temp
        end
        j = j + 1
    end
    i = i + 1
end
""",
    "pascal": """\
program M;

var
    arr: array[0..4] of integer;
    n: integer;
    i: integer;
    j: integer;
    temp: integer;

begin
    arr[0] := 5;
    arr[1] := 3;
    arr[2] := 8;
    arr[3] := 1;
    arr[4] := 2;
    n := 5;
    i := 0;
    while i < n do
    begin
        j := 0;
        while j < n - 1 - i do
        begin
            if arr[j] > arr[j + 1] then
            begin
                temp := arr[j];
                arr[j] := arr[j + 1];
                arr[j + 1] := temp;
            end;
            j := j + 1;
        end;
        i := i + 1;
    end;
end.
""",
}

# ---------------------------------------------------------------------------
# Opcode requirements
# ---------------------------------------------------------------------------
# Universal opcodes: present in all 15 languages.
REQUIRED_OPCODES: set[Opcode] = {
    Opcode.BINOP,
    Opcode.BRANCH_IF,
}

# STORE_INDEX and LOAD_INDEX are required for all languages except Scala.
# Scala's arr(j) syntax is indistinguishable from a method call without
# type inference, so it uses CALL_FUNCTION instead of index operations.
LANGUAGES_WITHOUT_INDEX_OPS: set[str] = {"scala"}

MIN_INSTRUCTIONS = 15


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestBubbleSortLowering:
    @pytest.fixture(params=sorted(PROGRAMS.keys()), ids=lambda lang: lang)
    def language_ir(self, request):
        lang = request.param
        ir = parse_for_language(lang, PROGRAMS[lang])
        return lang, ir

    def test_clean_lowering(self, language_ir):
        """Verify entry label, min instructions, required opcodes, and no unsupported symbolics."""
        lang, ir = language_ir
        assert_clean_lowering(
            ir,
            min_instructions=MIN_INSTRUCTIONS,
            required_opcodes=REQUIRED_OPCODES,
            language=lang,
        )

    def test_index_operations_present(self, language_ir):
        """Verify STORE_INDEX and LOAD_INDEX for all languages except Scala."""
        lang, ir = language_ir
        if lang in LANGUAGES_WITHOUT_INDEX_OPS:
            return
        present = opcodes(ir)
        assert (
            Opcode.STORE_INDEX in present
        ), f"[{lang}] expected STORE_INDEX in opcodes: {present}"
        assert (
            Opcode.LOAD_INDEX in present
        ), f"[{lang}] expected LOAD_INDEX in opcodes: {present}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestBubbleSortCrossLanguage:
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

# Bubble sort executable set: languages where arr is at top-level scope
# and accessible after execution. C/C++/Rust/Kotlin wrap logic in functions
# not called from top level; Go/Java/C#/Scala inside main()/class.
BUBBLE_SORT_EXECUTABLE_LANGUAGES: frozenset[str] = frozenset(
    {"python", "javascript", "typescript", "ruby", "php", "lua"}
)
EXPECTED_SORTED_ARRAY = [1, 2, 3, 5, 8]


class TestBubbleSortExecution:
    @pytest.fixture(
        params=sorted(BUBBLE_SORT_EXECUTABLE_LANGUAGES),
        ids=lambda lang: lang,
        scope="class",
    )
    def execution_result(self, request):
        lang = request.param
        vm, stats = execute_for_language(lang, PROGRAMS[lang], max_steps=5000)
        return lang, vm, stats

    def test_correct_result(self, execution_result):
        lang, vm, _stats = execution_result
        arr = extract_array(vm, "arr", 5, lang)
        assert (
            arr == EXPECTED_SORTED_ARRAY
        ), f"[{lang}] expected sorted array={EXPECTED_SORTED_ARRAY}, got {arr}"

    def test_zero_llm_calls(self, execution_result):
        lang, _vm, stats = execution_result
        assert (
            stats.llm_calls == 0
        ), f"[{lang}] expected 0 LLM calls, got {stats.llm_calls}"
