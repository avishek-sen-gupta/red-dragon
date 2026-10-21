# pyright: standard
"""SVC 35 and SVC 13 reached through our WTO and ABEND macros."""

import logging
from pathlib import Path

import pytest

from interpreter.constants import Language
from interpreter.frontends import get_hlasm_frontend, get_hlasm_parser
from interpreter.func_name import FuncName
from interpreter.instructions import CallFunction
from interpreter.ir import SourceLocation
from interpreter.run import run
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import (
    MAX_STEPS,
    HlasmRun,
    hlasm_run_of,
    run_hlasm,
)

HELLO = (
    "HELLO    CSECT\n"
    "         WTO   'HELLO WORLD'\n"
    "         SR    15,15\n"
    "         BR    14\n"
    "         END\n"
)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_wto_writes_a_line():
    source = (
        "HELLO    CSECT\n"
        "         WTO   'HELLO WORLD'\n"
        "         WTO   'BYE'\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END\n"
    )

    assert run_hlasm(source) == HlasmRun(0, "", "HELLO WORLD\nBYE\n")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_run_assembles_against_our_maclib(capsys: pytest.CaptureFixture[str]):
    vm = run(HELLO, language=Language.HLASM, max_steps=MAX_STEPS)

    assert hlasm_run_of(vm, capsys.readouterr().out) == HlasmRun(0, "", "HELLO WORLD\n")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_abend_user_code():
    source = (
        "QUIT     CSECT\n"
        "         ABEND 42\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END\n"
    )

    assert run_hlasm(source) == HlasmRun(return_code=0, abend="U0042", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_abend_system_code():
    source = (
        "QUIT     CSECT\n"
        "         ABEND X'0C4',,,SYSTEM\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END\n"
    )

    assert run_hlasm(source) == HlasmRun(return_code=0, abend="S0C4", stdout="")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_svc_without_a_lowering_abends_s0c1(caplog: pytest.LogCaptureFixture):
    source = (
        "QUIT     CSECT\n"
        "         SVC   99\n"
        "         SR    15,15\n"
        "         BR    14\n"
        "         END\n"
    )

    with caplog.at_level(logging.WARNING, logger="interpreter.hlasm.opcodes.svc"):
        ran = run_hlasm(source)

    assert ran == HlasmRun(return_code=0, abend="S0C1", stdout="")
    assert [r.getMessage() for r in caplog.records] == [
        "SVC 99 has no lowering; it abends S0C1"
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_wto_from_macro_keeps_call_site_span(tmp_path: Path):
    parser = get_hlasm_parser()
    program = parser.read(
        parser.parse_to_file(HELLO.encode("utf-8"), "hello.asm", tmp_path / "p.json")
    )

    ir = get_hlasm_frontend(program).lower(b"")

    (println,) = [
        inst
        for inst in ir
        if isinstance(inst, CallFunction) and inst.func_name == FuncName("println")
    ]
    assert println.source_location == SourceLocation(
        start_line=2, start_col=0, end_line=2, end_col=0
    )
