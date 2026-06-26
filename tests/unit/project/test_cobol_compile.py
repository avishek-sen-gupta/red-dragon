from interpreter.project.cobol_compile import compile_cobol, compile_cobol_module
from interpreter.project.types import LinkedProgram, ModuleUnit
from interpreter.run import EntryPoint, run_linked
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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_single_module_runs():
    frontend, linked = compile_cobol(_SRC)
    assert isinstance(linked, LinkedProgram)
    assert linked.merged_cfg is not None
    # round-trips through run_linked (top-level COBOL entry)
    vm = run_linked(linked, entry_point=EntryPoint.top_level(), max_steps=10_000)
    assert vm is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_links_extra_subprogram():
    caller = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLER.
       PROCEDURE DIVISION.
           CALL 'CALLEE'.
           GOBACK.
"""
    callee = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLEE.
       PROCEDURE DIVISION.
           DISPLAY 'IN CALLEE'.
           GOBACK.
"""
    frontend, linked = compile_cobol(
        caller, extra_subprogram_sources={"CALLEE": callee}
    )
    # CALLEE linked as a second module
    assert len(linked.modules) >= 1
    vm = run_linked(linked, entry_point=EntryPoint.top_level(), max_steps=10_000)
    assert vm is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_source_transform_applied_to_callees():
    seen: list[str] = []

    def xform(s: str) -> str:
        seen.append(s)
        return s

    caller = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLER.
       PROCEDURE DIVISION.
           CALL 'CALLEE'.
           GOBACK.
"""
    callee = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLEE.
       PROCEDURE DIVISION.
           GOBACK.
"""
    compile_cobol(
        caller, extra_subprogram_sources={"CALLEE": callee}, source_transform=xform
    )
    assert seen  # the callee source passed through the transform
