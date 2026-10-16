import dataclasses
import json
import logging
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from cobol_asg.ast_store import AstParseError
from cobol_asg.lp import LP
from interpreter.cobol.file_definitions_data import (
    FILE_DEFINITIONS,
    file_definitions_data,
)
from interpreter.cobol.layout_data import DATA_LAYOUT, FieldPosition, field_positions
from interpreter.constants import Language
from interpreter.frontend import make_cobol_parser
from interpreter.frontend_extension_lowering import (
    RedDragonExtensionLoweringStrategy,
)
from interpreter.instructions import Data
from interpreter.ir import NO_LABEL, CodeLabel
from interpreter.project.cobol_compile import (
    compile_cobol,
    compile_cobol_module,
    parse_stage,
)
from interpreter.project.compiler import compile_directory
from interpreter.project.lowering_settings import LoweringSettings
from interpreter.project.source_file import SourceFile
from interpreter.project.types import LinkedProgram, ModuleUnit
from interpreter.register import NO_REGISTER
from interpreter.run import (
    Completed,
    EntryPoint,
    ExecutionState,
    initial_vm_state,
    resume_linked,
    run_linked,
    run_linked_resumable,
    run_linked_traced,
)
from interpreter.vm.builtins import core_builtins
from interpreter.vm.vm_types import VMState
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
def test_compile_cobol_module_returns_a_unit_with_its_entry_label(tmp_path):
    parser = make_cobol_parser()
    ast_path = tmp_path / "prog.ast.json"
    parser.parse_to_file(_SRC, ast_path)
    module = compile_cobol_module(_SRC, parser=parser, ast_path=ast_path)
    assert (type(module), len(module.ir) > 0, module.entry_label) == (
        ModuleUnit,
        True,
        CodeLabel("func_hello_0"),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_single_module_runs():
    linked = compile_cobol(_SRC, parser=make_cobol_parser())
    assert isinstance(linked, LinkedProgram)
    assert linked.merged_cfg is not None
    vm = run_linked(
        linked,
        entry_point=EntryPoint.top_level(),
        max_steps=10_000,
        initial_vm=initial_vm_state(),
        builtins=core_builtins(),
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
    linked = compile_cobol(
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
        builtins=core_builtins(),
    )
    assert vm is not None


_FILE_CALLER = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FCALLER.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT MAIN-FILE ASSIGN TO MAINDD.
       DATA DIVISION.
       FILE SECTION.
       FD  MAIN-FILE.
       01  MAIN-REC PIC X(20).
       WORKING-STORAGE SECTION.
       01  WS-MAIN PIC X(4).
       PROCEDURE DIVISION.
           CALL 'FCALLEE'.
           GOBACK.
"""

_FILE_CALLEE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FCALLEE.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SUB-FILE ASSIGN TO SUBDD.
       DATA DIVISION.
       FILE SECTION.
       FD  SUB-FILE.
       01  SUB-REC PIC X(30).
       WORKING-STORAGE SECTION.
       01  WS-SUB PIC 9(3).
       PROCEDURE DIVISION.
           GOBACK.
"""


def _plain_run(linked: LinkedProgram, entry_point: EntryPoint) -> VMState:
    return run_linked(
        linked,
        entry_point=entry_point,
        max_steps=10_000,
        initial_vm=initial_vm_state(),
        builtins=core_builtins(),
    )


def _resumable_run(linked: LinkedProgram, entry_point: EntryPoint) -> VMState:
    match run_linked_resumable(
        linked,
        entry_point=entry_point,
        max_steps=10_000,
        initial_vm=initial_vm_state(),
        builtins=core_builtins(),
    ):
        case Completed(vm=vm):
            return vm
        case other:
            raise AssertionError(f"the program suspended: {other!r}")


def _traced_run(linked: LinkedProgram, entry_point: EntryPoint) -> VMState:
    vm, _trace = run_linked_traced(
        linked, entry_point=entry_point, max_steps=10_000, builtins=core_builtins()
    )
    return vm


def _resumed_run(linked: LinkedProgram, entry_point: EntryPoint) -> VMState:
    after_start_up = run_linked(
        linked,
        entry_point=EntryPoint.top_level(),
        max_steps=10_000,
        initial_vm=initial_vm_state(),
        builtins=core_builtins(),
    )
    state = ExecutionState(
        vm=dataclasses.replace(after_start_up, declarations=()),
        current_label=entry_point.resolve(
            list(linked.func_symbol_table.values())
        ).label,
        ip=0,
        resume_reg=NO_REGISTER,
        entered=linked.entry_func_label,
    )
    match resume_linked(linked, state, max_steps=10_000, builtins=core_builtins()):
        case Completed(vm=vm):
            return vm
        case other:
            raise AssertionError(f"the resumed program did not complete: {other!r}")


@covers(NotLanguageFeature.INFRASTRUCTURE)
@pytest.mark.parametrize(
    "run_program",
    [_plain_run, _resumable_run, _traced_run, _resumed_run],
    ids=["run_linked", "run_linked_resumable", "run_linked_traced", "resume_linked"],
)
def test_each_linked_program_declares_its_files_and_the_run_holds_the_mains(
    run_program: Callable[[LinkedProgram, EntryPoint], VMState],
):
    parser = make_cobol_parser()
    linked = compile_cobol(
        _FILE_CALLER,
        programs=(SourceFile(Path("FCALLEE.cbl"), _FILE_CALLEE),),
        parser=parser,
    )
    main_files = file_definitions_data(parser.parse(_FILE_CALLER))
    callee_files = file_definitions_data(parser.parse(_FILE_CALLEE))
    declared = [i for i in linked.merged_ir if isinstance(i, Data)]
    entry = linked.entry_func_label
    vm = run_program(
        dataclasses.replace(linked, modules=dict(reversed(linked.modules.items()))),
        EntryPoint.function(lambda ref: ref.label == entry),
    )
    assert (
        [d for d in declared if d.name == FILE_DEFINITIONS],
        [d.name for d in declared if d.name == DATA_LAYOUT],
        vm.declarations[0],
        field_positions(vm.declarations),
        len(vm.declarations),
    ) == (
        [callee_files, main_files],
        [DATA_LAYOUT, DATA_LAYOUT],
        main_files,
        {"WS-MAIN": FieldPosition(0, 4, "ALPHANUMERIC", 4, 0, False)},
        2,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_traced_run_starts_with_the_mains_declarations():
    parser = make_cobol_parser()
    linked = compile_cobol(
        _FILE_CALLER,
        programs=(SourceFile(Path("FCALLEE.cbl"), _FILE_CALLEE),),
        parser=parser,
    )
    entry = linked.entry_func_label
    _vm, trace = run_linked_traced(
        linked,
        entry_point=EntryPoint.function(lambda ref: ref.label == entry),
        max_steps=10_000,
        builtins=core_builtins(),
    )
    match trace.initial_state:
        case VMState(declarations=(first, *_)):
            assert first == file_definitions_data(parser.parse(_FILE_CALLER))
        case other:
            raise AssertionError(f"the trace starts without declarations: {other!r}")


_SETTINGS = LoweringSettings(LP.LP32, (), False, ())


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_stage_writes_one_named_file_per_source(tmp_path):
    programs = tuple(
        SourceFile(Path(f"prog_{n}.cbl"), _SRC.replace(b"HELLO", f"HELLO{n}".encode()))
        for n in "ABC"
    )
    result = parse_stage(programs, make_cobol_parser(), _SETTINGS, tmp_path)
    assert {
        source: (ast, json.loads(ast.read_text())["program_id"])
        for source, ast in result.items()
    } == {
        p.path: (_SETTINGS.artifact(p, tmp_path, "ast"), f"HELLO{p.path.stem[-1]}")
        for p in programs
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_stage_creates_the_work_directory(tmp_path):
    work = tmp_path / "nested" / "work"
    parse_stage(
        (SourceFile(Path("x.cbl"), _SRC),), make_cobol_parser(), _SETTINGS, work
    )
    assert work.is_dir()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_parse_stage_with_no_programs_writes_nothing(tmp_path):
    assert (
        parse_stage((), make_cobol_parser(), _SETTINGS, tmp_path),
        list(tmp_path.iterdir()),
    ) == ({}, [])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_work_dir_single_module_writes_json(tmp_path):
    cache = tmp_path / "ast-cache"
    linked = compile_cobol(_HELLO, parser=make_cobol_parser(), work_dir=cache)
    assert isinstance(linked, LinkedProgram)
    assert cache.is_dir()
    assert len(list(cache.glob("*.ast.json"))) == 1


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_work_dir_multi_module_writes_one_json_per_module(tmp_path):
    cache = tmp_path / "ast-cache"
    linked = compile_cobol(
        _CALLER,
        parser=make_cobol_parser(),
        programs=(SourceFile(Path("CALLEE.cbl"), _CALLEE),),
        work_dir=cache,
    )
    assert isinstance(linked, LinkedProgram)
    assert len(list(cache.glob("*.ast.json"))) == 2


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_work_dir_produces_runnable_program(tmp_path):
    linked = compile_cobol(
        _HELLO, parser=make_cobol_parser(), work_dir=tmp_path / "cache"
    )
    vm = run_linked(
        linked,
        entry_point=EntryPoint.top_level(),
        max_steps=10_000,
        initial_vm=initial_vm_state(),
        builtins=core_builtins(),
    )
    assert vm is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_without_work_dir_uses_auto_temp():
    linked = compile_cobol(_HELLO, parser=make_cobol_parser())
    assert isinstance(linked, LinkedProgram)
    assert linked.merged_cfg is not None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compile_cobol_persists_an_ast_for_every_compiled_program(tmp_path):
    compile_cobol(
        _CALLER,
        parser=make_cobol_parser(),
        programs=(SourceFile(Path("CALLEE.cbl"), _CALLEE),),
        work_dir=tmp_path,
    )

    assert sorted(
        (ast.name.rpartition("-")[0], json.loads(ast.read_text())["program_id"])
        for ast in tmp_path.glob("*.ast.json")
    ) == [("CALLEE", "CALLEE"), ("__main__", "CALLER")]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_compile_without_a_work_dir_gets_its_own_owner_only_directory():
    temp_root = Path(tempfile.gettempdir())
    before = set(temp_root.iterdir())
    first = compile_cobol(_HELLO, parser=make_cobol_parser())
    (first_dir,) = set(temp_root.iterdir()) - before
    second = compile_cobol(_HELLO, parser=make_cobol_parser())
    (second_dir,) = set(temp_root.iterdir()) - before - {first_dir}
    assert (
        first == second,
        [d.parent for d in (first_dir, second_dir)],
        [d.stat().st_mode & 0o777 for d in (first_dir, second_dir)],
        len(list(first_dir.glob("*.ast.json"))),
    ) == (True, [temp_root, temp_root], [0o700, 0o700], 1)


def _program(program_id: str) -> bytes:
    return (
        "       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. {program_id}.\n"
        "       PROCEDURE DIVISION.\n"
        "           GOBACK.\n"
    ).encode()


class _FailsToLower(RedDragonExtensionLoweringStrategy):
    """Raises while lowering the one program it names."""

    name = "fails-to-lower"

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
        linked = compile_cobol(
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
    assert [r.getMessage() for r in caplog.records] == [
        "compile_cobol: BROKEN failed to lower — skipping"
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_later_of_two_programs_with_the_same_path_is_compiled(tmp_path):
    compile_cobol(
        _CALLER,
        parser=make_cobol_parser(),
        programs=(
            SourceFile(Path("CALLEE.cbl"), _program("FIRSTONE")),
            SourceFile(Path("CALLEE.cbl"), _program("SECONDONE")),
        ),
        work_dir=tmp_path,
    )

    assert sorted(
        (ast.name.rpartition("-")[0], json.loads(ast.read_text())["program_id"])
        for ast in tmp_path.glob("*.ast.json")
    ) == [("CALLEE", "SECONDONE"), ("__main__", "CALLER")]


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


class _CountingParser:
    """The real parser, recording every program it is asked to parse."""

    def __init__(self, inner, parsed: list[str]) -> None:
        self._inner, self.parsed = inner, parsed

    def with_addressing_mode(self, mode):
        return _CountingParser(self._inner.with_addressing_mode(mode), self.parsed)

    def parse_to_file(self, source: bytes, out):
        self.parsed.append(out.name)
        return self._inner.parse_to_file(source, out)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_second_compile_in_the_same_work_directory_reuses_every_file(tmp_path):
    parsed: list[str] = []
    parser = _CountingParser(make_cobol_parser(), parsed)
    programs = (SourceFile(Path("CALLEE.cbl"), _CALLEE),)
    first = compile_cobol(_CALLER, parser=parser, programs=programs, work_dir=tmp_path)
    files = {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()}
    second = compile_cobol(_CALLER, parser=parser, programs=programs, work_dir=tmp_path)
    assert (
        len(parsed),
        sorted(p.name.split(".", 1)[1] for p in tmp_path.iterdir()),
        {p.name: p.stat().st_mtime_ns for p in tmp_path.iterdir()} == files,
        second.entry_func_label,
        second.merged_ir == first.merged_ir,
    ) == (
        2,
        ["ast.json", "ast.json", "linked.json", "unit.json", "unit.json"],
        True,
        CodeLabel("__main__.func_caller_0"),
        True,
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_edited_source_or_new_settings_gets_new_files(tmp_path):
    compile_cobol(_CALLER, parser=make_cobol_parser(), work_dir=tmp_path)
    edited = _CALLER.replace(b"GOBACK", b"STOP RUN")
    compile_cobol(edited, parser=make_cobol_parser(), work_dir=tmp_path)
    compile_cobol(_CALLER, parser=make_cobol_parser(), work_dir=tmp_path, tolerant=True)
    assert len(list(tmp_path.glob("__main__-*.unit.json"))) == 3


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_callee_that_fails_to_lower_has_no_unit_and_a_rerun_still_links(
    tmp_path, caplog
):
    programs = (SourceFile(Path("CALLEE.cbl"), _CALLEE),)
    strategies = [_FailsToLower("CALLEE")]
    compile_cobol(
        _CALLER,
        parser=make_cobol_parser(),
        programs=programs,
        extension_strategies=strategies,
        work_dir=tmp_path,
    )
    linked = compile_cobol(
        _CALLER,
        parser=make_cobol_parser(),
        programs=programs,
        extension_strategies=strategies,
        work_dir=tmp_path,
    )
    assert (
        sorted(p.name.split("-")[0] for p in tmp_path.glob("*.unit.json")),
        sorted(str(path) for path in linked.modules),
    ) == (["__main__"], ["__main__.cbl", "__start_up__"])
