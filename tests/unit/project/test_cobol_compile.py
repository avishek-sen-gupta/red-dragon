import hashlib
import json
import logging
from collections.abc import Mapping
from pathlib import Path

import pytest

from cobol_asg.ast_store import AstParseError
from interpreter.constants import Language
from interpreter.frontend import make_cobol_parser
from interpreter.frontend_extension_lowering import (
    RedDragonExtensionLoweringStrategy,
)
from interpreter.project.cobol_compile import (
    compile_cobol,
    compile_cobol_module,
    parallel_parse_to_cache,
)
from interpreter.ir import NO_LABEL
from interpreter.project.compiler import compile_directory
from interpreter.project.source_file import SourceFile
from interpreter.project.types import LinkedProgram, ModuleUnit
from interpreter.run import EntryPoint, initial_vm_state, run_linked
from tests.covers import NotLanguageFeature, covers

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
        caller,
        programs=(SourceFile(Path("CALLEE.cbl"), callee),),
        parser=make_cobol_parser(),
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
def test_parallel_parse_to_cache_writes_one_file_per_source(tmp_path):
    sources = {
        Path("prog_a.cbl"): _SRC,
        Path("prog_b.cbl"): _SRC,
        Path("prog_c.cbl"): _SRC,
    }
    result = parallel_parse_to_cache(sources, make_cobol_parser(), tmp_path)
    assert set(result.keys()) == set(sources.keys())
    for src_path, ast_path in result.items():
        path_hash = hashlib.md5(str(src_path).encode()).hexdigest()
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
        programs=(SourceFile(Path("CALLEE.cbl"), _CALLEE),),
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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_maps_every_compiled_program_to_its_persisted_ast():
    _, linked = compile_cobol(
        _CALLER,
        parser=make_cobol_parser(),
        programs=(SourceFile(Path("CALLEE.cbl"), _CALLEE),),
    )

    assert sorted(str(p) for p in linked.ast_paths) == ["CALLEE.cbl", "__main__.cbl"]
    assert {
        str(source): json.loads(ast.read_text())["program_id"]
        for source, ast in linked.ast_paths.items()
    } == {"__main__.cbl": "CALLER", "CALLEE.cbl": "CALLEE"}
    assert {ast.parent.parent for ast in linked.ast_paths.values()} == {Path("/tmp")}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_default_ast_cache_is_readable_only_by_its_owner():
    _, linked = compile_cobol(_HELLO, parser=make_cobol_parser())
    (cache,) = {ast.parent for ast in linked.ast_paths.values()}
    assert cache.stat().st_mode & 0o777 == 0o700


def _program(program_id: str) -> bytes:
    return (
        "       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. {program_id}.\n"
        "       PROCEDURE DIVISION.\n"
        "           GOBACK.\n"
    ).encode()


class _FailsToLower(RedDragonExtensionLoweringStrategy):
    """Raises while lowering the one program it names."""

    def __init__(self, program_id: str) -> None:
        self._program_id = program_id

    def handles(self, stmt) -> bool:
        return False

    def preprocess_program_dict[V](self, data: Mapping[str, V]) -> dict[str, V]:
        if data["program_id"] == self._program_id:
            raise ValueError(f"cannot lower {self._program_id}")
        return dict(data)

    def on_procedure_entry(self, ctx, materialised) -> None:
        return None

    def lower(self, ctx, stmt, materialised) -> None:
        return None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_program_that_fails_to_lower_is_skipped_with_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="interpreter.project.cobol_compile"):
        _, linked = compile_cobol(
            _CALLER,
            parser=make_cobol_parser(),
            programs=(
                SourceFile(Path("BROKEN.cbl"), _program("BROKEN")),
                SourceFile(Path("CALLEE.cbl"), _CALLEE),
            ),
            extension_strategies=(_FailsToLower("BROKEN"),),
        )

    assert {str(p) for p in linked.modules} == {
        "CALLEE.cbl",
        "__main__.cbl",
        "__start_up__",
    }
    assert {str(p) for p in linked.ast_paths} == {"CALLEE.cbl", "__main__.cbl"}
    assert [r.getMessage() for r in caplog.records] == [
        "compile_cobol: BROKEN failed to lower — skipping"
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_later_of_two_programs_with_the_same_path_is_compiled():
    _, linked = compile_cobol(
        _CALLER,
        parser=make_cobol_parser(),
        programs=(
            SourceFile(Path("CALLEE.cbl"), _program("FIRSTONE")),
            SourceFile(Path("CALLEE.cbl"), _program("SECONDONE")),
        ),
    )

    assert {
        str(source): json.loads(ast.read_text())["program_id"]
        for source, ast in linked.ast_paths.items()
    } == {"__main__.cbl": "CALLER", "CALLEE.cbl": "SECONDONE"}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_program_that_fails_to_parse_aborts_the_compile_even_when_tolerant():
    with pytest.raises(AstParseError, match="BROKEN"):
        compile_cobol(
            _CALLER,
            parser=make_cobol_parser(),
            programs=(
                SourceFile(Path("BROKEN.cbl"), b"THIS IS NOT COBOL AT ALL.\n"),
                SourceFile(Path("CALLEE.cbl"), _CALLEE),
            ),
            tolerant=True,
        )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_program_without_an_entry_function_carries_the_null_label(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n")
    assert compile_directory(tmp_path, Language.PYTHON).entry_func_label is NO_LABEL
