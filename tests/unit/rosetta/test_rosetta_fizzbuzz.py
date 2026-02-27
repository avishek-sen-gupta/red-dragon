"""Rosetta test: FizzBuzz (1 to 20) across all 15 deterministic frontends."""

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
# Programs: FizzBuzz (1 to 20) in all 15 languages
# Each prints FizzBuzz output for numbers 1 through 20.
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
def fizzbuzz(n):
    i = 1
    while i <= n:
        if i % 15 == 0:
            print("FizzBuzz")
        elif i % 3 == 0:
            print("Fizz")
        elif i % 5 == 0:
            print("Buzz")
        else:
            print(i)
        i = i + 1

fizzbuzz(20)
""",
    "javascript": """\
function fizzbuzz(n) {
    let i = 1;
    while (i <= n) {
        if (i % 15 == 0) {
            console.log("FizzBuzz");
        } else if (i % 3 == 0) {
            console.log("Fizz");
        } else if (i % 5 == 0) {
            console.log("Buzz");
        } else {
            console.log(i);
        }
        i = i + 1;
    }
}

fizzbuzz(20);
""",
    "typescript": """\
function fizzbuzz(n: number): void {
    let i: number = 1;
    while (i <= n) {
        if (i % 15 == 0) {
            console.log("FizzBuzz");
        } else if (i % 3 == 0) {
            console.log("Fizz");
        } else if (i % 5 == 0) {
            console.log("Buzz");
        } else {
            console.log(i);
        }
        i = i + 1;
    }
}

fizzbuzz(20);
""",
    "java": """\
class M {
    static void fizzbuzz(int n) {
        int i = 1;
        while (i <= n) {
            if (i % 15 == 0) {
                System.out.println("FizzBuzz");
            } else if (i % 3 == 0) {
                System.out.println("Fizz");
            } else if (i % 5 == 0) {
                System.out.println("Buzz");
            } else {
                System.out.println(i);
            }
            i = i + 1;
        }
    }
}
""",
    "ruby": """\
def fizzbuzz(n)
    i = 1
    while i <= n
        if i % 15 == 0
            puts("FizzBuzz")
        elsif i % 3 == 0
            puts("Fizz")
        elsif i % 5 == 0
            puts("Buzz")
        else
            puts(i)
        end
        i = i + 1
    end
end

fizzbuzz(20)
""",
    "go": """\
package main

func fizzbuzz(n int) {
    i := 1
    for i <= n {
        if i % 15 == 0 {
            println("FizzBuzz")
        } else if i % 3 == 0 {
            println("Fizz")
        } else if i % 5 == 0 {
            println("Buzz")
        } else {
            println(i)
        }
        i = i + 1
    }
}

func main() {
    fizzbuzz(20)
}
""",
    "php": """\
<?php
function fizzbuzz($n) {
    $i = 1;
    while ($i <= $n) {
        if ($i % 15 == 0) {
            echo "FizzBuzz";
        } else if ($i % 3 == 0) {
            echo "Fizz";
        } else if ($i % 5 == 0) {
            echo "Buzz";
        } else {
            echo $i;
        }
        $i = $i + 1;
    }
}

fizzbuzz(20);
?>
""",
    "csharp": """\
class M {
    static void fizzbuzz(int n) {
        int i = 1;
        while (i <= n) {
            if (i % 15 == 0) {
                Console.WriteLine("FizzBuzz");
            } else if (i % 3 == 0) {
                Console.WriteLine("Fizz");
            } else if (i % 5 == 0) {
                Console.WriteLine("Buzz");
            } else {
                Console.WriteLine(i);
            }
            i = i + 1;
        }
    }
}
""",
    "c": """\
void fizzbuzz(int n) {
    int i = 1;
    while (i <= n) {
        if (i % 15 == 0) {
            printf("FizzBuzz");
        } else if (i % 3 == 0) {
            printf("Fizz");
        } else if (i % 5 == 0) {
            printf("Buzz");
        } else {
            printf(i);
        }
        i = i + 1;
    }
}
""",
    "cpp": """\
void fizzbuzz(int n) {
    int i = 1;
    while (i <= n) {
        if (i % 15 == 0) {
            printf("FizzBuzz");
        } else if (i % 3 == 0) {
            printf("Fizz");
        } else if (i % 5 == 0) {
            printf("Buzz");
        } else {
            printf(i);
        }
        i = i + 1;
    }
}
""",
    "rust": """\
fn fizzbuzz(n: i32) {
    let mut i: i32 = 1;
    while i <= n {
        if i % 15 == 0 {
            println!("FizzBuzz");
        } else if i % 3 == 0 {
            println!("Fizz");
        } else if i % 5 == 0 {
            println!("Buzz");
        } else {
            println!(i);
        }
        i = i + 1;
    }
}

fizzbuzz(20);
""",
    "kotlin": """\
fun fizzbuzz(n: Int) {
    var i: Int = 1
    while (i <= n) {
        if (i % 15 == 0) {
            println("FizzBuzz")
        } else if (i % 3 == 0) {
            println("Fizz")
        } else if (i % 5 == 0) {
            println("Buzz")
        } else {
            println(i)
        }
        i = i + 1
    }
}

fizzbuzz(20)
""",
    "scala": """\
object M {
    def fizzbuzz(n: Int): Unit = {
        var i: Int = 1
        while (i <= n) {
            if (i % 15 == 0) {
                println("FizzBuzz")
            } else if (i % 3 == 0) {
                println("Fizz")
            } else if (i % 5 == 0) {
                println("Buzz")
            } else {
                println(i)
            }
            i = i + 1
        }
    }

    fizzbuzz(20)
}
""",
    "lua": """\
function fizzbuzz(n)
    local i = 1
    while i <= n do
        if i % 15 == 0 then
            print("FizzBuzz")
        elseif i % 3 == 0 then
            print("Fizz")
        elseif i % 5 == 0 then
            print("Buzz")
        else
            print(i)
        end
        i = i + 1
    end
end

fizzbuzz(20)
""",
    "pascal": """\
program M;

procedure fizzbuzz(n: integer);
var
    i: integer;
begin
    i := 1;
    while i <= n do
    begin
        if i mod 15 = 0 then
            writeln('FizzBuzz')
        else if i mod 3 = 0 then
            writeln('Fizz')
        else if i mod 5 = 0 then
            writeln('Buzz')
        else
            writeln(i);
        i := i + 1;
    end;
end;

begin
    fizzbuzz(20);
end.
""",
}

REQUIRED_OPCODES: set[Opcode] = {
    Opcode.BRANCH_IF,
    Opcode.BINOP,
    Opcode.CALL_FUNCTION,
}

MIN_INSTRUCTIONS = 15


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestFizzBuzzLowering:
    @pytest.fixture(params=sorted(PROGRAMS.keys()), ids=lambda lang: lang)
    def language_ir(self, request):
        lang = request.param
        ir = parse_for_language(lang, PROGRAMS[lang])
        return lang, ir

    def test_clean_lowering(self, language_ir):
        lang, ir = language_ir
        # Some languages produce CALL_METHOD instead of CALL_FUNCTION
        # for print-like calls (e.g., System.out.println, Console.WriteLine).
        # Accept either opcode as satisfying the CALL_FUNCTION requirement.
        effective_required = REQUIRED_OPCODES.copy()
        present = opcodes(ir)
        if Opcode.CALL_FUNCTION not in present and Opcode.CALL_METHOD in present:
            effective_required = (effective_required - {Opcode.CALL_FUNCTION}) | {
                Opcode.CALL_METHOD
            }
        assert_clean_lowering(
            ir,
            min_instructions=MIN_INSTRUCTIONS,
            required_opcodes=effective_required,
            language=lang,
        )

    def test_modulo_operator_present(self, language_ir):
        lang, ir = language_ir
        binops = find_all(ir, Opcode.BINOP)
        operators = {str(inst.operands[0]) for inst in binops if inst.operands}
        # Pascal uses 'mod' keyword instead of '%' operator
        assert (
            "%" in operators or "mod" in operators
        ), f"[{lang}] expected '%' or 'mod' in BINOP operators: {operators}"


# ---------------------------------------------------------------------------
# Cross-language consistency tests
# ---------------------------------------------------------------------------


class TestFizzBuzzCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, PROGRAMS[lang]) for lang in PROGRAMS}

    def test_all_languages_covered(self):
        assert set(PROGRAMS.keys()) == set(SUPPORTED_DETERMINISTIC_LANGUAGES)

    def test_cross_language_consistency(self, all_results):
        # Use a relaxed required set that accepts CALL_METHOD as alternative
        # since some languages produce CALL_METHOD for print calls.
        relaxed_required = {Opcode.BRANCH_IF, Opcode.BINOP}
        assert_cross_language_consistency(
            all_results, required_opcodes=relaxed_required
        )
