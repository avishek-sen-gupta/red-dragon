# pyright: standard
"""Load and store instructions run on the VM leave the Principles of Operation results in registers and storage."""

from collections.abc import Callable, Mapping

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import load_store_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm, run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun

SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")


COMPLETED = HlasmRun(return_code=0, abend="", stdout="")
INITIAL_CC = 0


def _machine(
    program: Callable[[str, str], str], body: str, results: Mapping[int, int]
) -> HlasmMachine:
    return run_hlasm_machine(program(body, programs.RETURN_ZERO)).restricted_to(results)


def _completed(results: Mapping[int, int]) -> HlasmMachine:
    return HlasmMachine(COMPLETED, INITIAL_CC, results)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_storage_loads_into_low_word_extend_and_keep_high_word():
    based = programs.based_program
    assert _machine(
        based, programs.STORAGE_LOADS_32, programs.STORAGE_LOADS_32_RESULTS
    ) == _completed(programs.STORAGE_LOADS_32_RESULTS)
    assert _machine(
        based, programs.PARTIAL_INSERTS, programs.PARTIAL_INSERTS_RESULTS
    ) == _completed(programs.PARTIAL_INSERTS_RESULTS)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_storage_loads_into_full_register_extend_to_64_bits():
    based = programs.based_program
    assert _machine(
        based, programs.STORAGE_LOADS_64, programs.STORAGE_LOADS_64_RESULTS
    ) == _completed(programs.STORAGE_LOADS_64_RESULTS)
    assert _machine(
        based, programs.MORE_LOADS_64, programs.MORE_LOADS_64_RESULTS
    ) == _completed(programs.MORE_LOADS_64_RESULTS)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_guarded_loads_keep_bits_33_to_63_without_guarded_storage():
    assert _machine(
        programs.based_program,
        programs.GUARDED_LOADS,
        programs.GUARDED_LOADS_RESULTS,
    ) == _completed(programs.GUARDED_LOADS_RESULTS)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_register_loads_extend_reverse_and_mask():
    based = programs.based_program
    assert _machine(
        based, programs.REGISTER_LOADS, programs.REGISTER_LOADS_RESULTS
    ) == _completed(programs.REGISTER_LOADS_RESULTS)
    assert _machine(
        based, programs.MORE_REGISTER_LOADS, programs.MORE_REGISTER_LOADS_RESULTS
    ) == _completed(programs.MORE_REGISTER_LOADS_RESULTS)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_relative_loads_reach_another_section():
    assert _machine(
        programs.relative_program,
        programs.RELATIVE_LOADS,
        programs.RELATIVE_LOADS_RESULTS,
    ) == _completed(programs.RELATIVE_LOADS_RESULTS)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_stores_write_the_low_bytes_and_reversals():
    based = programs.based_program
    assert _machine(based, programs.STORES, programs.STORES_RESULTS) == (
        _completed(programs.STORES_RESULTS)
    )
    assert _machine(based, programs.MORE_STORES, programs.MORE_STORES_RESULTS) == (
        _completed(programs.MORE_STORES_RESULTS)
    )
    assert _machine(
        programs.relative_program,
        programs.RELATIVE_STORES,
        programs.RELATIVE_STORES_RESULTS,
    ) == _completed(programs.RELATIVE_STORES_RESULTS)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_multiples_wrap_from_r15_to_r0_and_move_words_or_doublewords():
    wrapped = run_hlasm_machine(
        programs.based_program(programs.LOAD_MULTIPLE_WRAPPING, programs.RETURN)
    )
    assert wrapped.restricted_to(programs.LOAD_MULTIPLE_WRAPPING_RESULTS) == (
        HlasmMachine(
            HlasmRun(return_code=2, abend="", stdout=""),
            0,
            programs.LOAD_MULTIPLE_WRAPPING_RESULTS,
        )
    )
    assert _machine(
        programs.based_program, programs.MULTIPLES, programs.MULTIPLES_RESULTS
    ) == _completed(programs.MULTIPLES_RESULTS)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_store_characters_under_mask_stores_the_selected_bytes_contiguously():
    assert _machine(
        programs.based_program, programs.STORE_MASKED, programs.STORE_MASKED_RESULTS
    ) == _completed(programs.STORE_MASKED_RESULTS)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_insert_characters_under_mask_sets_cc_from_the_inserted_bits():
    machines = [
        run_hlasm_machine(programs.based_program(body, programs.RETURN))
        for body, _value, _cc in programs.INSERT_MASKED_CASES
    ]
    assert [(m.run.abend, m.cc, m.gprs[2]) for m in machines] == [
        ("", cc, value) for _, value, cc in programs.INSERT_MASKED_CASES
    ]


MISALIGNED = (
    "         LRL   2,NEG+2\n",
    "         LGRL  2,POS\n",
    "         LGFRL 2,NEG+2\n",
    "         LLGFRL 2,NEG+2\n",
    "         STRL  2,NEG+2\n",
    "         STGRL 2,POS\n",
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_misaligned_operand_is_a_specification_exception():
    sources = [
        *(programs.relative_program(b, programs.RETURN) for b in MISALIGNED),
        programs.based_program("         LGG   2,POS\n", programs.RETURN),
        programs.based_program("         LLGFSG 2,NEG+2\n", programs.RETURN),
    ]
    assert [run_hlasm(source) for source in sources] == [SPECIFICATION] * 8
