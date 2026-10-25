# pyright: standard
"""Vector loads and stores run on the VM move the bytes the Principles of Operation name (SA22-7832-14 chapter 21), in each element order; an invalid M field, element index or register range abends S0C6 with storage unchanged; VLBB loads up to its block boundary."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import vector_memory_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_storage


def _run(body: str, data: str) -> tuple[str, bytes]:
    machine, image = run_hlasm_storage(
        programs.program(body, data), programs.SECTION, programs.OUT_SPAN
    )
    return machine.run.abend, image


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_vector_load_or_store_moves_the_named_bytes(case: str):
    body, image = programs.CASES[case]

    assert _run(body, "") == (programs.COMPLETED, image)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CHECKS))
def test_invalid_vector_field_abends_s0c6_before_any_access(case: str):
    assert _run(programs.CHECKS[case], "") == (
        programs.SPECIFICATION,
        programs.UNCHANGED,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_vlbb_loads_up_to_each_block_boundary_and_zeroes_the_rest():
    abend, image = _run(programs.VLBB_BODY, programs.BLOCK_BUFFER)

    assert (abend, image) == (programs.COMPLETED, programs.VLBB_EXPECTED)
