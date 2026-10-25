# pyright: standard
"""Vector integer add, subtract, average, multiply, Galois-field multiply, checksum, sum and divide instructions run on the VM build the registers the Principles of Operation names (SA22-7832-14 chapter 22, page cited per case), with V1 equal to a source in every family; an integer-divide condition without IDC abends S0DB with the VXC in the FPC and V1 unchanged; an invalid M field abends S0C6 with storage unchanged."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import vector_integer_arithmetic_programs as programs
from tests.integration.hlasm import vector_memory_programs as memory
from tests.integration.hlasm.hlasm_helpers import (
    run_hlasm_storage,
    run_hlasm_vector_register,
)

VECTOR_PROCESSING = "S0DB"
SRC_IMAGE = int.from_bytes(bytes(range(16)), "big")
DXC_SHIFT = 8


def _run(body: str) -> tuple[str, bytes]:
    machine, image = run_hlasm_storage(
        memory.program(body, programs.DATA), memory.SECTION, memory.OUT_SPAN
    )
    return machine.run.abend, image


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_vector_integer_arithmetic_instruction_builds_the_named_register(case: str):
    body, image = programs.CASES[case]

    assert _run(body) == (memory.COMPLETED, image)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.TRAPS))
def test_integer_divide_exception_abends_s0db_with_the_vxc_and_v1_unchanged(
    case: str,
):
    body, vxc = programs.TRAPS[case]
    machine, image, fpc, v1 = run_hlasm_vector_register(
        memory.program(body, programs.DATA),
        memory.SECTION,
        memory.OUT_SPAN,
        programs.TRAPPED_V1,
    )

    assert (machine.run.abend, image, fpc, v1) == (
        VECTOR_PROCESSING,
        memory.UNCHANGED,
        vxc << DXC_SHIFT,
        SRC_IMAGE,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CHECKS))
def test_invalid_vector_integer_arithmetic_m_field_abends_s0c6_before_any_store(
    case: str,
):
    assert _run(programs.CHECKS[case]) == (memory.SPECIFICATION, memory.UNCHANGED)
