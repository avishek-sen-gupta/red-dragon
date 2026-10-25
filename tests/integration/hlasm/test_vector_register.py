# pyright: standard
"""Vector register-manipulation instructions run on the VM build the registers the Principles of Operation names (SA22-7832-14 chapter 21, page cited per case), with V1 equal to a source where the family has one; VPKS and VPKLS saturate and set CC 0, 1 or 3 only with CS; an invalid element size or index abends S0C6 with storage unchanged."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import vector_memory_programs as memory
from tests.integration.hlasm import vector_register_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_storage


def _run(body: str) -> tuple[str, bytes]:
    machine, image = run_hlasm_storage(
        memory.program(body, programs.DATA), memory.SECTION, memory.OUT_SPAN
    )
    return machine.run.abend, image


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_vector_register_instruction_builds_the_named_register(case: str):
    body, image = programs.CASES[case]

    assert _run(body) == (memory.COMPLETED, image)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CHECKS))
def test_invalid_vector_register_field_abends_s0c6_before_any_store(case: str):
    assert _run(programs.CHECKS[case]) == (memory.SPECIFICATION, memory.UNCHANGED)
