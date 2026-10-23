# pyright: standard
"""HFP conversion instructions run on the VM: every mnemonic's GR or FPR result and CC."""

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import hfp_conversion_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(programs.CASES))
def test_hfp_conversion_leaves_the_registers_and_cc(case: str):
    body, registers = programs.CASES[case][:2]
    machine = run_hlasm_machine(programs.program(body))

    assert machine.restricted_to(registers) == programs.expected(case)
