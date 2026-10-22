# pyright: standard
"""Storage compare programs leave the same declared registers and CC in RedDragon and in z390, bar z390's known CLCL pad, CLCLU, CLST and CUSE errors."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm import ss_compare_programs as programs
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_machine import HlasmMachine
from tests.integration.hlasm.hlasm_run import HlasmRun
from tests.integration.hlasm.load_store_programs import HIGH_FILL
from tests.z390.z390_runner import Z390Runner

pytestmark = pytest.mark.z390

ABENDED = HlasmRun(return_code=0, abend="U0001", stdout="")
SPECIFICATION = HlasmRun(return_code=0, abend="S0C6", stdout="")
OPERATION = HlasmRun(return_code=0, abend="S0C1", stdout="")
BOTH_ZERO = {3: HIGH_FILL, 5: HIGH_FILL}

ALL_CASES: Mapping[str, tuple[programs.Case, HlasmRun]] = {
    **{name: (case, ABENDED) for name, case in programs.CASES.items()},
    **{
        name: (case, SPECIFICATION)
        for name, case in programs.SPECIFICATION_EXCEPTIONS.items()
    },
}

Z390_MACHINE: Mapping[str, HlasmMachine] = {
    "CLCL pad low": HlasmMachine(ABENDED, 2, {3: HIGH_FILL, 5: HIGH_FILL | 0x40000004}),
    "CLCLU": HlasmMachine(OPERATION, 0, {3: HIGH_FILL | 6, 5: HIGH_FILL | 6}),
    "CLCLU registers": HlasmMachine(OPERATION, 0, {}),
    "CLCLU pad equal": HlasmMachine(OPERATION, 0, {3: HIGH_FILL | 4, 5: HIGH_FILL | 2}),
    "CLCLU pad high": HlasmMachine(OPERATION, 0, {3: HIGH_FILL | 2, 5: HIGH_FILL | 4}),
    "CLCLU odd length": HlasmMachine(
        OPERATION, 0, {3: HIGH_FILL | 5, 5: HIGH_FILL | 6}
    ),
    "CLST first ends first": HlasmMachine(ABENDED, 0, {}),
    "CLST first ends first registers": HlasmMachine(
        ABENDED, 1, {2: HIGH_FILL | 0xFFFFFFFE, 4: HIGH_FILL | 0xFFFFFFFE}
    ),
    "CLST clears bit 32": HlasmMachine(
        ABENDED, 3, {2: HIGH_FILL | 0x7FFFFFFE, 4: HIGH_FILL | 0x7FFFFFFE}
    ),
    "CLST second ends first": HlasmMachine(ABENDED, 0, {}),
    "CLST high ending character": HlasmMachine(ABENDED, 0, {}),
    "CLST reserved GR0 bits": HlasmMachine(ABENDED, 1, {}),
    "CUSE found": HlasmMachine(ABENDED, 2, BOTH_ZERO),
    "CUSE end equal": HlasmMachine(ABENDED, 1, BOTH_ZERO),
    "CUSE pad": HlasmMachine(ABENDED, 0, BOTH_ZERO),
    "CUSE pad registers": HlasmMachine(ABENDED, 2, {2: HIGH_FILL | 2, 4: HIGH_FILL}),
    "CUSE zero substring": HlasmMachine(ABENDED, 2, BOTH_ZERO),
    "CUSE zero substring clears bit 32": HlasmMachine(
        ABENDED, 3, {2: HIGH_FILL | 6, 4: HIGH_FILL | 6}
    ),
    "CUSE negative length": HlasmMachine(ABENDED, 2, BOTH_ZERO),
    "CUSE lengths zero": HlasmMachine(ABENDED, 1, BOTH_ZERO),
}

MATCHING = [name for name in ALL_CASES if name not in Z390_MACHINE]


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", MATCHING)
def test_compare_matches(z390: Z390Runner, tmp_path: Path, case: str):
    (body, results, cc), run = ALL_CASES[case]
    source = programs.compare_program(body)

    expected = HlasmMachine(run, cc, results)
    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(results),
    ) == (expected, expected)


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize("case", list(Z390_MACHINE))
def test_compare_follows_the_principles_of_operation_where_z390_does_not(
    z390: Z390Runner, tmp_path: Path, case: str
):
    (body, results, cc), run = ALL_CASES[case]
    source = programs.compare_program(body)
    z390_machine = Z390_MACHINE[case]

    assert (
        run_hlasm_machine(source).restricted_to(results),
        z390.run_machine(source, tmp_path).restricted_to(z390_machine.gprs),
    ) == (HlasmMachine(run, cc, results), z390_machine)
