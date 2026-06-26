from pathlib import Path

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
    # CALLEE linked as a second module — merged_ir must contain callee's prefixed
    # labels (e.g. "...func_callee_0"), proving the callee IR was linked in.
    callee_label_instrs = [
        instr
        for instr in linked.merged_ir
        if hasattr(instr, "label")
        and "callee" in str(getattr(instr, "label", "")).lower()
    ]
    assert callee_label_instrs, (
        "callee IR must be present in merged_ir (linked in); "
        f"labels seen: {[str(getattr(i, 'label', '')) for i in linked.merged_ir if hasattr(i, 'label')]}"
    )
    vm = run_linked(linked, entry_point=EntryPoint.top_level(), max_steps=10_000)
    assert vm is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_source_transform_applied_to_on_disk_callees_only(tmp_path: Path):
    """source_transform is applied ONLY to on-disk-resolved callees.

    Verifies I1 contract: caller-supplied `source` and `extra_subprogram_sources`
    arrive pre-transformed; only disk-read callee text is passed through
    source_transform.
    """
    caller_src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLER.
       PROCEDURE DIVISION.
           CALL 'ONDISK'.
           GOBACK.
"""
    callee_src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. ONDISK.
       PROCEDURE DIVISION.
           GOBACK.
"""
    callee_path = tmp_path / "ONDISK.cbl"
    callee_path.write_text(callee_src)

    # An extra subprogram supplied by the caller (not on disk)
    extra_src = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. EXTRA.
       PROCEDURE DIVISION.
           GOBACK.
"""

    transformed_texts: list[str] = []

    def recording_transform(s: str) -> str:
        transformed_texts.append(s)
        return s

    compile_cobol(
        caller_src,
        program_source_dir=tmp_path,
        extra_subprogram_sources={"EXTRA": extra_src},
        source_transform=recording_transform,
    )

    # The on-disk callee MUST have been transformed
    assert any(
        "ONDISK" in t for t in transformed_texts
    ), "source_transform must be applied to the on-disk callee source"
    # The main caller source must NOT have been transformed
    assert not any(
        "CALLER" in t and "CALL" in t for t in transformed_texts
    ), "source_transform must NOT be applied to the main caller source"
    # The extra subprogram source must NOT have been transformed
    assert not any(
        "EXTRA" in t for t in transformed_texts
    ), "source_transform must NOT be applied to extra_subprogram_sources"
