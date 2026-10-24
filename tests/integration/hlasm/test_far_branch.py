# pyright: standard
"""Control across modules: a linking branch out of a module calls its owner, a branch to the activation's return address returns whatever its mode bit, a non-linking branch into a module with an activation below returns to it (a level skipped, or B 4(,14)), any other branch out of the module calls, and an address nothing owns abends S0C1."""

from interpreter.project.source_file import SourceFile
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.far_branch_programs import (
    CALLEE,
    CALLER,
    INNER,
    MIDDLE,
    MODE_RETURN,
    PLAIN_RETURN,
    SKIPPER,
    SKIPS_A_BRANCH,
    SKIPS_ONE,
    module,
)
from tests.integration.hlasm.hlasm_helpers import run_hlasm_machine
from tests.integration.hlasm.hlasm_run import HlasmRun

LOW_WORD = 0xFFFFFFFF


def _low_words(main: str, *programs: SourceFile) -> tuple[HlasmRun, dict[int, int]]:
    machine = run_hlasm_machine(main, programs)
    return machine.run, {r: v & LOW_WORD for r, v in machine.gprs.items()}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_linking_branch_calls_another_module_which_returns_through_r14():
    run, words = _low_words(CALLER, module("SUB", CALLEE))

    assert (run, words[2], words[3]) == (
        HlasmRun(return_code=142, abend="", stdout=""),
        100,
        42,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_return_skips_a_level_and_a_linking_branch_into_a_module_below_calls_it():
    run, words = _low_words(SKIPPER, module("B", MIDDLE), module("C", INNER))

    assert (run, words[5], words[7], words[8]) == (
        HlasmRun(return_code=77, abend="", stdout=""),
        1,
        0,
        1,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_b_4_of_r14_returns_past_the_callers_branch_and_a_plain_branch_out_calls():
    run, words = _low_words(
        SKIPS_A_BRANCH,
        module("SUB", SKIPS_ONE),
        module("SUB2", PLAIN_RETURN),
        module("SUB3", MODE_RETURN),
    )

    assert (run, words[3]) == (HlasmRun(return_code=8, abend="", stdout=""), 0)


def _unowned(branch: str) -> tuple[HlasmRun, int]:
    run, words = _low_words(
        "MAIN     CSECT\n"
        "         USING MAIN,15\n"
        "         LA    4,1\n"
        "         L     2,=A(X'7FFFF000')\n"
        f"         {branch}\n"
        "         LTORG\n"
        "         END   MAIN\n"
    )
    return run, words[4]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_branch_to_an_address_nothing_owns_abends_s0c1():
    assert (_unowned("BR    2"), _unowned("BALR  14,2")) == (
        (HlasmRun(return_code=0, abend="S0C1", stdout=""), 1),
        (HlasmRun(return_code=0, abend="S0C1", stdout=""), 1),
    )
