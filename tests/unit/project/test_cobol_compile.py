import hashlib
import json
from pathlib import Path

from interpreter.frontend import make_cobol_parser
from interpreter.project.cobol_compile import (
    compile_cobol,
    compile_cobol_module,
    parallel_parse_to_cache,
)
from interpreter.project.types import LinkedProgram, ModuleUnit
from interpreter.run import EntryPoint, run_linked, initial_vm_state
from tests.covers import covers, NotLanguageFeature

_SRC = b"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO.
       PROCEDURE DIVISION.
           DISPLAY 'HI'.
           GOBACK.
"""

_HELLO = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO.
       PROCEDURE DIVISION.
           DISPLAY 'HI'.
           GOBACK.
"""

_CALLER = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLER.
       PROCEDURE DIVISION.
           CALL 'CALLEE'.
           GOBACK.
"""

_CALLEE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLEE.
       PROCEDURE DIVISION.
           DISPLAY 'IN CALLEE'.
           GOBACK.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_module_returns_frontend_and_module(tmp_path):
    parser = make_cobol_parser()
    ast_path = tmp_path / "prog.ast.json"
    parser.parse_to_file(_SRC, ast_path)
    frontend, module = compile_cobol_module(_SRC, parser=parser, ast_path=ast_path)
    assert isinstance(module, ModuleUnit)
    assert len(module.ir) > 0
    assert frontend.data_layout is not None
    assert frontend.func_symbol_table is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_single_module_runs():
    _, linked = compile_cobol(_SRC, parser=make_cobol_parser())
    assert isinstance(linked, LinkedProgram)
    assert linked.merged_cfg is not None
    vm = run_linked(
        linked,
        entry_point=EntryPoint.top_level(),
        max_steps=10_000,
        initial_vm=initial_vm_state(),
    )
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
    _, linked = compile_cobol(
        caller, extra_subprogram_sources={"CALLEE": callee}, parser=make_cobol_parser()
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
    vm = run_linked(
        linked,
        entry_point=EntryPoint.top_level(),
        max_steps=10_000,
        initial_vm=initial_vm_state(),
    )
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
        parser=make_cobol_parser(),
        program_source_dirs=[tmp_path],
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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_writes_one_file_per_source(tmp_path):
    sources = {
        Path("prog_a.cbl"): _SRC,
        Path("prog_b.cbl"): _SRC,
        Path("prog_c.cbl"): _SRC,
    }
    result = parallel_parse_to_cache(sources, make_cobol_parser(), tmp_path)
    assert set(result.keys()) == set(sources.keys())
    for src_path, ast_path in result.items():
        path_hash = hashlib.md5(str(src_path).encode()).hexdigest()[:8]
        assert ast_path == tmp_path / f"{src_path.stem}-{path_hash}.ast.json"
        assert ast_path.exists()
        assert json.loads(ast_path.read_text())["program_id"] is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_creates_cache_dir(tmp_path):
    cache_dir = tmp_path / "nested" / "cache"
    assert not cache_dir.exists()
    parallel_parse_to_cache({Path("x.cbl"): _SRC}, make_cobol_parser(), cache_dir)
    assert cache_dir.is_dir()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_empty_sources(tmp_path):
    result = parallel_parse_to_cache({}, make_cobol_parser(), tmp_path)
    assert result == {}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_ast_cache_dir_single_module_writes_json(tmp_path):
    cache = tmp_path / "ast-cache"
    _, linked = compile_cobol(_HELLO, parser=make_cobol_parser(), ast_cache_dir=cache)
    assert isinstance(linked, LinkedProgram)
    assert cache.is_dir()
    assert len(list(cache.glob("*.ast.json"))) == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_ast_cache_dir_multi_module_writes_one_json_per_module(tmp_path):
    cache = tmp_path / "ast-cache"
    _, linked = compile_cobol(
        _CALLER,
        parser=make_cobol_parser(),
        extra_subprogram_sources={"CALLEE": _CALLEE},
        ast_cache_dir=cache,
    )
    assert isinstance(linked, LinkedProgram)
    assert len(list(cache.glob("*.ast.json"))) == 2


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_ast_cache_dir_produces_runnable_program(tmp_path):
    _, linked = compile_cobol(
        _HELLO, parser=make_cobol_parser(), ast_cache_dir=tmp_path / "cache"
    )
    vm = run_linked(
        linked,
        entry_point=EntryPoint.top_level(),
        max_steps=10_000,
        initial_vm=initial_vm_state(),
    )
    assert vm is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_without_ast_cache_dir_uses_auto_temp():
    _, linked = compile_cobol(_HELLO, parser=make_cobol_parser())
    assert isinstance(linked, LinkedProgram)
    assert linked.merged_cfg is not None
