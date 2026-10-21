# pyright: standard
"""Load address and immediate instructions run on the VM leave the Principles of Operation results and the CC unchanged."""

from collections.abc import Mapping

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import load_address_immediate_programs as programs
from tests.integration.hlasm import load_store_programs as storage
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine

HIGH_WORD_SHIFT = 32


def _cc_and_registers(
    body: str, results: Mapping[int, int]
) -> tuple[int, Mapping[int, int]]:
    machine = run_hlasm_machine(storage.based_program(body, storage.RETURN))
    return machine.cc, machine.restricted_to(results).gprs


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_load_address_places_the_31_bit_address_and_keeps_the_high_word():
    assert _cc_and_registers(programs.ADDRESSES, programs.ADDRESSES_RESULTS) == (
        programs.CC_TWO,
        programs.ADDRESSES_RESULTS,
    )
    assert _cc_and_registers(
        programs.BEYOND_STORAGE, programs.BEYOND_STORAGE_RESULTS
    ) == (0, programs.BEYOND_STORAGE_RESULTS)
    same = run_hlasm_machine(
        storage.based_program(programs.SAME_ADDRESS, storage.RETURN)
    ).gprs
    assert (same[10], same[10] >> HIGH_WORD_SHIFT) == (same[11], 0xA5A5A5A5)
    crossed = run_hlasm_machine(
        storage.relative_program(programs.OTHER_SECTION, storage.RETURN)
    )
    assert crossed.restricted_to(programs.OTHER_SECTION_RESULTS).gprs == (
        programs.OTHER_SECTION_RESULTS
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_indexed_addresses_scale_the_index_by_the_element_size():
    assert _cc_and_registers(programs.INDEXED, programs.INDEXED_RESULTS) == (
        programs.CC_TWO,
        programs.INDEXED_RESULTS,
    )
    assert _cc_and_registers(
        programs.LOGICAL_INDEXED, programs.LOGICAL_INDEXED_RESULTS
    ) == (programs.CC_TWO, programs.LOGICAL_INDEXED_RESULTS)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_immediates_extend_zero_fill_or_insert_their_bit_positions():
    assert _cc_and_registers(
        programs.LOADED_IMMEDIATES, programs.LOADED_IMMEDIATES_RESULTS
    ) == (programs.CC_TWO, programs.LOADED_IMMEDIATES_RESULTS)
    assert _cc_and_registers(
        programs.INSERTED_IMMEDIATES, programs.INSERTED_IMMEDIATES_RESULTS
    ) == (programs.CC_TWO, programs.INSERTED_IMMEDIATES_RESULTS)
