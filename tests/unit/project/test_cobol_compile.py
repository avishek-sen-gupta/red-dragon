import json
from pathlib import Path

from interpreter.project.cobol_compile import (
    compile_cobol,
    compile_cobol_module,
    parallel_parse_to_cache,
)
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


_MINIMAL_ASG_JSON = json.dumps(
    {
        "program_id": "PROG",
        "data_fields": [],
        "sections": [],
        "paragraphs": [{"name": "MAIN", "statements": [{"type": "STOP_RUN"}]}],
    }
)


class _FakeParseToFileParser:
    """Duck-typed fake: writes a fixed JSON string to out_path."""

    def parse_to_file(self, source: bytes, out_path: Path) -> Path:
        out_path.write_text(_MINIMAL_ASG_JSON, encoding="utf-8")
        return out_path


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_writes_one_file_per_source(tmp_path):
    sources = {
        Path("prog_a.cbl"): b"source a",
        Path("prog_b.cbl"): b"source b",
        Path("prog_c.cbl"): b"source c",
    }
    result = parallel_parse_to_cache(sources, _FakeParseToFileParser(), tmp_path)
    assert set(result.keys()) == set(sources.keys())
    for src_path, ast_path in result.items():
        assert ast_path == tmp_path / f"{src_path.stem}.ast.json"
        assert ast_path.exists()
        assert json.loads(ast_path.read_text())["program_id"] == "PROG"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_creates_cache_dir(tmp_path):
    cache_dir = tmp_path / "nested" / "cache"
    assert not cache_dir.exists()
    parallel_parse_to_cache(
        {Path("x.cbl"): b"src"}, _FakeParseToFileParser(), cache_dir
    )
    assert cache_dir.is_dir()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parallel_parse_to_cache_empty_sources(tmp_path):
    result = parallel_parse_to_cache({}, _FakeParseToFileParser(), tmp_path)
    assert result == {}


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
def test_compile_cobol_ast_cache_dir_single_module_writes_json(tmp_path):
    cache = tmp_path / "ast-cache"
    _, linked = compile_cobol(
        _HELLO, parser=_FakeParseToFileParser(), ast_cache_dir=cache
    )
    assert isinstance(linked, LinkedProgram)
    assert cache.is_dir()
    assert len(list(cache.glob("*.ast.json"))) == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_ast_cache_dir_multi_module_writes_one_json_per_module(tmp_path):
    cache = tmp_path / "ast-cache"
    _, linked = compile_cobol(
        _CALLER,
        parser=_FakeParseToFileParser(),
        extra_subprogram_sources={"CALLEE": _CALLEE},
        ast_cache_dir=cache,
    )
    assert isinstance(linked, LinkedProgram)
    assert len(list(cache.glob("*.ast.json"))) == 2


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_ast_cache_dir_produces_runnable_program(tmp_path):
    _, linked = compile_cobol(
        _HELLO, parser=_FakeParseToFileParser(), ast_cache_dir=tmp_path / "cache"
    )
    vm = run_linked(linked, entry_point=EntryPoint.top_level(), max_steps=10_000)
    assert vm is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_without_ast_cache_dir_unchanged():
    _, linked = compile_cobol(_HELLO)
    assert isinstance(linked, LinkedProgram)
    assert linked.merged_cfg is not None
