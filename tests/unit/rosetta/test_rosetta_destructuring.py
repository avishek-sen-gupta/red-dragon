"""Rosetta test: genuine destructuring across 6 languages with dedicated lowering.

Verifies that languages with dedicated destructuring lowering methods emit
LOAD_INDEX opcodes — proving the destructuring code path was taken, not just
manual array indexing.

6 of the 15 deterministic frontends have destructuring lowering:
  Python       — _lower_tuple_unpack
  JavaScript   — _lower_array_destructure
  TypeScript   — inherited from JS
  Rust         — _lower_tuple_destructure
  Scala        — _lower_scala_tuple_destructure
  Kotlin       — _lower_multi_variable_destructure (uses arrayOf builtin)

    a, b = [10, 5]   (or language equivalent)
    answer = a + b    → 15
"""

import pytest

from interpreter.ir import Opcode

from tests.unit.rosetta.conftest import (
    parse_for_language,
    find_all,
    assert_clean_lowering,
    execute_for_language,
    extract_answer,
)

# ---------------------------------------------------------------------------
# Programs: destructuring in 6 languages with dedicated lowering
# ---------------------------------------------------------------------------

PROGRAMS: dict[str, str] = {
    "python": """\
a, b = [10, 5]
answer = a + b
""",
    "javascript": """\
const [a, b] = [10, 5];
let answer = a + b;
""",
    "typescript": """\
const [a, b]: number[] = [10, 5];
let answer: number = a + b;
""",
    "rust": """\
let (a, b) = (10, 5);
let answer = a + b;
""",
    "scala": """\
object M {
  val (a, b) = (10, 5)
  val answer = a + b
}
""",
    "kotlin": """\
val arr = arrayOf(10, 5)
val (a, b) = arr
val answer = a + b
""",
}

DESTRUCTURING_LANGUAGES: frozenset[str] = frozenset(PROGRAMS.keys())

REQUIRED_OPCODES: set[Opcode] = {Opcode.LOAD_INDEX, Opcode.BINOP}

MIN_INSTRUCTIONS = 6

EXPECTED_ANSWER = 15


# ---------------------------------------------------------------------------
# Per-language lowering tests (parametrized)
# ---------------------------------------------------------------------------


class TestDestructuringLowering:
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

    def test_emits_load_index(self, language_ir):
        lang, ir = language_ir
        load_index_instrs = find_all(ir, Opcode.LOAD_INDEX)
        assert len(load_index_instrs) >= 2, (
            f"[{lang}] expected >= 2 LOAD_INDEX instructions "
            f"(one per destructured variable), got {len(load_index_instrs)}"
        )


# ---------------------------------------------------------------------------
# Cross-language consistency tests (6 languages only)
# ---------------------------------------------------------------------------


class TestDestructuringCrossLanguage:
    @pytest.fixture(scope="class")
    def all_results(self):
        return {lang: parse_for_language(lang, PROGRAMS[lang]) for lang in PROGRAMS}

    def test_all_destructuring_languages_covered(self):
        expected = {"python", "javascript", "typescript", "rust", "scala", "kotlin"}
        assert set(PROGRAMS.keys()) == expected

    def test_cross_language_load_index(self, all_results):
        for lang, ir in all_results.items():
            load_index_instrs = find_all(ir, Opcode.LOAD_INDEX)
            assert len(load_index_instrs) >= 2, (
                f"[{lang}] expected >= 2 LOAD_INDEX instructions, "
                f"got {len(load_index_instrs)}"
            )


# ---------------------------------------------------------------------------
# VM execution tests (parametrized over 6 destructuring languages)
# ---------------------------------------------------------------------------


class TestDestructuringExecution:
    @pytest.fixture(
        params=sorted(DESTRUCTURING_LANGUAGES),
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
