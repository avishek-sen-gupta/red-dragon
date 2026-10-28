# pyright: standard
"""An HLASM run's return code, abend and entry-program language are read off the finished VM and the linked image."""

from pathlib import Path

from infrastructure.zos.abend.system_abend import SystemAbend
from infrastructure.zos.abend.user_abend import UserAbend
from interpreter.constants import Language
from interpreter.hlasm.hlasm_outcome import hlasm_abend, hlasm_return_code
from interpreter.project.program_language import program_language
from tests.covers import NotLanguageFeature, covers
from tests.integration.hlasm.hlasm_helpers import _run_vm
from tests.integration.hlasm.test_cobol_linkage import (
    ASM_NINE,
    COBOL_SAYS,
    _entered,
    _image,
)

RETURNS_EIGHT = "MAIN     CSECT\n         LA    15,8\n         BR    14\n         END\n"
ABENDS_42 = "MAIN     CSECT\n         ABEND 42\n         END\n"
PROGRAM_CHECK = "MAIN     CSECT\n         DC    H'0'\n         END\n"
ENTRY_ADDRESS = 0x1080
NEVER_SETS_R15 = "MAIN     CSECT\n         BR    14\n         END\n"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_hlasm_run_reports_its_return_code_and_abend():
    outcomes = [
        (hlasm_return_code(vm), hlasm_abend(vm))
        for vm, _ in (
            _run_vm(source)
            for source in (RETURNS_EIGHT, ABENDS_42, PROGRAM_CHECK, NEVER_SETS_R15)
        )
    ]

    assert outcomes == [
        (8, ()),
        (ENTRY_ADDRESS, (UserAbend(42),)),
        (ENTRY_ADDRESS, (SystemAbend(0x0C1),)),
        (ENTRY_ADDRESS, ()),
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_cobol_only_image_has_no_hlasm_abend_and_each_program_has_its_language(
    tmp_path: Path,
):
    cobol_only = _image((COBOL_SAYS,), (), tmp_path)
    mixed = _image((COBOL_SAYS,), (ASM_NINE,), tmp_path)

    assert (
        hlasm_abend(_entered(cobol_only, "COBMAIN")),
        program_language(mixed, "COBMAIN"),
        program_language(mixed, "ASMMAIN"),
    ) == ((), Language.COBOL, Language.HLASM)
