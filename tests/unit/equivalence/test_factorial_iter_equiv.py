"""Equivalence tests: iterative factorial produces identical IR across all 15 frontends."""

import logging

import pytest

from interpreter.cfg import extract_function_instructions
from interpreter.frontends import SUPPORTED_DETERMINISTIC_LANGUAGES
from interpreter.ir import Opcode

from tests.unit.rosetta.conftest import (
    parse_for_language,
    find_all,
    count_symbolic_unsupported,
)
from tests.unit.rosetta.test_rosetta_factorial_iter import PROGRAMS
from tests.unit.equivalence.conftest import function_opcode_sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-language IR structure tests (parametrized)
# ---------------------------------------------------------------------------


class TestFactorialIterIRStructure:
    @pytest.fixture(params=sorted(PROGRAMS.keys()), ids=lambda lang: lang)
    def language(self, request):
        return request.param

    def test_function_body_extractable(self, language):
        ir = parse_for_language(language, PROGRAMS[language])
        body = extract_function_instructions(ir, "factorial")
        assert len(body) > 0, f"[{language}] factorial function body is empty"

    def test_required_opcodes_in_function_body(self, language):
        opcodes = function_opcode_sequence(language, PROGRAMS[language], "factorial")
        opcode_set = set(opcodes)
        required = {Opcode.BRANCH_IF, Opcode.BINOP}
        missing = required - opcode_set
        assert not missing, f"[{language}] missing required opcodes in body: {missing}"

    def test_multiply_operator_in_body(self, language):
        ir = parse_for_language(language, PROGRAMS[language])
        body = extract_function_instructions(ir, "factorial")
        binops = find_all(body, Opcode.BINOP)
        operators = {str(inst.operands[0]) for inst in binops if inst.operands}
        assert "*" in operators, (
            f"[{language}] expected '*' in BINOP operators within "
            f"factorial body: {operators}"
        )

    def test_no_unsupported_symbolics(self, language):
        ir = parse_for_language(language, PROGRAMS[language])
        body = extract_function_instructions(ir, "factorial")
        unsupported = count_symbolic_unsupported(body)
        assert unsupported == 0, (
            f"[{language}] found {unsupported} unsupported SYMBOLIC "
            f"instructions in factorial body"
        )


# ---------------------------------------------------------------------------
# Cross-language opcode equivalence tests
# ---------------------------------------------------------------------------


class TestFactorialIterCrossLanguageEquivalence:
    @pytest.fixture(scope="class")
    def all_opcode_sequences(self):
        return {
            lang: function_opcode_sequence(lang, PROGRAMS[lang], "factorial")
            for lang in PROGRAMS
        }

    def test_all_languages_covered(self):
        assert set(PROGRAMS.keys()) == set(SUPPORTED_DETERMINISTIC_LANGUAGES), (
            f"Missing languages: "
            f"{set(SUPPORTED_DETERMINISTIC_LANGUAGES) - set(PROGRAMS.keys())}"
        )

    def test_all_languages_produce_identical_opcode_sequence(
        self, all_opcode_sequences
    ):
        sequences = all_opcode_sequences
        reference_lang = sorted(sequences.keys())[0]
        reference_seq = sequences[reference_lang]

        mismatches = [
            (lang, seq)
            for lang, seq in sorted(sequences.items())
            if seq != reference_seq
        ]
        assert not mismatches, (
            f"Opcode sequences differ from reference ({reference_lang}: {reference_seq}).\n"
            + "\n".join(f"  [{lang}]: {seq}" for lang, seq in mismatches)
        )
