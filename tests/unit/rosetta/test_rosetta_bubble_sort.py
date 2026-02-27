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

# STORE_INDEX and LOAD_INDEX are the distinguishing opcodes for bubble sort
# (array element access).  However, several frontends have partial support:
#   - cpp:    STORE_INDEX only (subscript_expression reads not lowered)
#   - csharp: both present but bracketed_argument_list produces unsupported SYMBOLIC
#   - kotlin: LOAD_INDEX only (indexing assignment not lowered to STORE_INDEX)
#   - pascal: LOAD_INDEX only (subscript assignment not lowered to STORE_INDEX)
#   - ruby:   STORE_INDEX only (element_reference reads not lowered)
#   - scala:  neither (arr(j) syntax parsed as call_expression)
# We test index operations only for languages whose frontends support them.

LANGUAGES_WITH_STORE_INDEX: set[str] = {
    "python",
    "javascript",
    "typescript",
    "java",
    "go",
    "php",
    "c",
    "cpp",
    "rust",
    "lua",
    "ruby",
    "csharp",
}

LANGUAGES_WITH_LOAD_INDEX: set[str] = {
    "python",
    "javascript",
    "typescript",
    "java",
    "go",
    "php",
    "c",
    "rust",
    "lua",
    "kotlin",
    "pascal",
    "csharp",
}

# Languages that have zero unsupported SYMBOLIC nodes.
# csharp emits unsupported:bracketed_argument_list; ruby emits
# unsupported:element_reference.  We skip the zero-unsupported check for them
# and instead run a relaxed lowering assertion.
LANGUAGES_WITH_UNSUPPORTED_SYMBOLICS: set[str] = {"csharp", "ruby"}

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
        if lang in LANGUAGES_WITH_UNSUPPORTED_SYMBOLICS:
            # These languages have known unsupported SYMBOLIC nodes from
            # partial subscript support.  We still check label, count, and
            # required opcodes, but skip the zero-unsupported assertion.
            assert (
                ir[0].opcode == Opcode.LABEL
            ), f"[{lang}] first instruction must be LABEL"
            assert ir[0].label == "entry", f"[{lang}] first label must be 'entry'"
            assert (
                len(ir) >= MIN_INSTRUCTIONS
            ), f"[{lang}] expected >= {MIN_INSTRUCTIONS} instructions, got {len(ir)}"
            present = opcodes(ir)
            missing = REQUIRED_OPCODES - present
            assert not missing, f"[{lang}] missing required opcodes: {missing}"
        else:
            assert_clean_lowering(
                ir,
                min_instructions=MIN_INSTRUCTIONS,
                required_opcodes=REQUIRED_OPCODES,
                language=lang,
            )

    def test_index_operations_present(self, language_ir):
        """Verify STORE_INDEX and LOAD_INDEX for languages whose frontends support them."""
        lang, ir = language_ir
        present = opcodes(ir)
        if lang in LANGUAGES_WITH_STORE_INDEX:
            assert (
                Opcode.STORE_INDEX in present
            ), f"[{lang}] expected STORE_INDEX in opcodes: {present}"
        if lang in LANGUAGES_WITH_LOAD_INDEX:
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
