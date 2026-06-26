from interpreter.project.cobol_compile import compile_cobol_module
from interpreter.project.types import ModuleUnit
from tests.covers import covers, NotLanguageFeature

_SRC = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO.
       PROCEDURE DIVISION.
           DISPLAY 'HI'.
           GOBACK.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_module_returns_frontend_and_module():
    frontend, module = compile_cobol_module(_SRC)
    assert isinstance(module, ModuleUnit)
    assert len(module.ir) > 0
    # frontend exposes the data the consumers read off it
    assert frontend.data_layout is not None
    assert frontend.func_symbol_table is not None
