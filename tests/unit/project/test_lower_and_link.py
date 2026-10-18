"""Programs are lowered one at a time, linked into one image, and entered by name."""

import dataclasses
from pathlib import Path

import pytest

from interpreter.cobol.layout_data import field_positions
from interpreter.frontend import make_cobol_parser
from interpreter.handlers.calls import UnresolvedProgramError
from interpreter.instructions import Const, Data, Label_, Suspend
from interpreter.ir import CodeLabel
from interpreter.project.cobol_compile import compile_cobol, link_units
from interpreter.project.coprocessor_compile import lower_program
from interpreter.project.duplicate_program_in_image import DuplicateProgramInImage
from interpreter.project.ir_codec import IrCodec
from interpreter.project.program_entry import ProgramEntry
from interpreter.project.program_not_in_image import ProgramNotInImage
from interpreter.project.source_file import SourceFile
from interpreter.project.types import LinkedProgram
from interpreter.project.unit_codec import UnitCodec
from interpreter.register import Register
from interpreter.run import (
    Completed,
    EntryPoint,
    ExecutionState,
    Suspended,
    declarations_of,
    initial_vm_state,
    resume_linked,
    run_linked,
    run_linked_resumable,
    run_linked_traced,
)
from interpreter.trace_types import ExecutionTrace
from interpreter.types.type_expr import UNKNOWN
from interpreter.vm.builtins import core_builtins
from interpreter.vm.vm_types import VMState
from tests.covers import NotLanguageFeature, covers
from tests.integration.cobol_helpers import ws_region

_MAIN = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAIN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-N   PIC 9(4) VALUE 1.
       01  WS-OUT PIC X(4) VALUE SPACES.
       PROCEDURE DIVISION.
           CALL 'SUB' USING WS-N.
           ADD 1 TO WS-N.
           MOVE 'DONE' TO WS-OUT.
           GOBACK.
"""

_SUB = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SUB.
       DATA DIVISION.
       LINKAGE SECTION.
       01  LS-N PIC 9(4).
       PROCEDURE DIVISION USING LS-N.
           ADD 10 TO LS-N.
           GOBACK.
"""

_DYNAMIC_MAIN = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAIN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-PGM PIC X(8) VALUE 'SUB'.
       PROCEDURE DIVISION.
           CALL WS-PGM.
           GOBACK.
"""

_SAYS_SUB = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SUB.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-SAY PIC X(6) VALUE 'IN SUB'.
       PROCEDURE DIVISION.
           DISPLAY WS-SAY.
           GOBACK.
"""


def _says_own_name(name: str, width: int) -> bytes:
    return (
        "       IDENTIFICATION DIVISION.\n"
        f"       PROGRAM-ID. {name}.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        f"       01  WS-{name} PIC X({width}) VALUE '{name * width}'.\n"
        "       PROCEDURE DIVISION.\n"
        f"           DISPLAY WS-{name}.\n"
        "           GOBACK.\n"
    ).encode()


def _lowered(source: bytes, work_dir: Path) -> Path:
    (unit,) = lower_program(
        source,
        parser=make_cobol_parser(),
        specs=(),
        copybook_dirs=(),
        work_dir=work_dir,
        tolerant=False,
    )
    return unit


def _image(sources: tuple[bytes, ...], work_dir: Path) -> LinkedProgram:
    return link_units(tuple(_lowered(s, work_dir) for s in sources), work_dir)


def _entered(image: LinkedProgram, name: str) -> VMState:
    return run_linked(
        image,
        ProgramEntry(name),
        max_steps=20_000,
        initial_vm=initial_vm_state(),
        builtins=core_builtins(),
    )


def _ws_bytes(
    vm: VMState, program: str, declarations: tuple[Data, ...]
) -> dict[str, bytes]:
    region = ws_region(vm, program)
    return {
        name: bytes(region[p.offset : p.offset + p.length])
        for name, p in field_positions(declarations).items()
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_lowered_then_linked_equals_compile(tmp_path):
    image = _image((_MAIN, _SUB), tmp_path / "image")
    entered = _entered(image, "MAIN")
    compiled = compile_cobol(
        _MAIN,
        parser=make_cobol_parser(),
        programs=(SourceFile(Path("SUB.cbl"), _SUB),),
        work_dir=tmp_path / "compiled",
    )
    entry = compiled.entry_func_label
    reference = run_linked(
        compiled,
        EntryPoint.function(lambda ref: ref.label == entry),
        max_steps=20_000,
        initial_vm=initial_vm_state(),
        builtins=core_builtins(),
    )
    assert (
        _ws_bytes(entered, "MAIN", declarations_of(image, "MAIN")),
        _ws_bytes(reference, "MAIN", reference.declarations),
    ) == (
        {"WS-N": b"\xf0\xf0\xf1\xf2", "WS-OUT": b"\xc4\xd6\xd5\xc5"},
        {"WS-N": b"\xf0\xf0\xf1\xf2", "WS-OUT": b"\xc4\xd6\xd5\xc5"},
    )


def _starts_with(trace: ExecutionTrace) -> tuple[Data, ...]:
    match trace.initial_state:
        case VMState(declarations=declarations):
            return declarations
        case _:
            raise AssertionError("the trace has no initial state")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_image_runs_each_program_entered_by_name(tmp_path, capsys):
    image = _image(
        tuple(_says_own_name(n, w) for n, w in (("A", 1), ("B", 2), ("C", 3))),
        tmp_path,
    )
    capsys.readouterr()

    def entered(name: str) -> tuple[str, bool, tuple[str, ...]]:
        vm = _entered(image, name)
        return (
            capsys.readouterr().out,
            vm.declarations == declarations_of(image, name),
            tuple(field_positions(vm.declarations)),
        )

    traced, trace = run_linked_traced(
        image, ProgramEntry("C"), max_steps=20_000, builtins=core_builtins()
    )
    capsys.readouterr()
    assert (
        [entered(n) for n in ("B", "C", "A")],
        traced.declarations == declarations_of(image, "C"),
        _starts_with(trace) == declarations_of(image, "C"),
        tuple(field_positions(traced.declarations)),
    ) == (
        [
            ("BB\n", True, ("WS-B",)),
            ("CCC\n", True, ("WS-C",)),
            ("A\n", True, ("WS-A",)),
        ],
        True,
        True,
        ("WS-C",),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_entering_an_absent_program_names_it(tmp_path):
    image = _image((_says_own_name("A", 1),), tmp_path)
    with pytest.raises(ProgramNotInImage) as absent:
        _entered(image, "Z")
    with pytest.raises(ProgramNotInImage) as traced:
        run_linked_traced(
            image, ProgramEntry("Z"), max_steps=20_000, builtins=core_builtins()
        )
    with pytest.raises(ProgramNotInImage) as declared:
        declarations_of(image, "Z")
    assert (
        str(absent.value),
        absent.value.args,
        str(traced.value),
        str(declared.value),
    ) == (
        "program Z is not in the image",
        ("program Z is not in the image",),
        "program Z is not in the image",
        "program Z is not in the image",
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_program_is_entered_by_its_name_exactly_as_the_image_holds_it(tmp_path):
    image = _image((_says_own_name("ACCTRPT", 1),), tmp_path)
    with pytest.raises(ProgramNotInImage) as absent:
        _entered(image, "acctrpt")
    assert str(absent.value) == "program acctrpt is not in the image"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_two_units_of_one_program_are_refused_before_linking(tmp_path):
    first = _lowered(_says_own_name("X", 1), tmp_path)
    second = _lowered(_says_own_name("X", 2), tmp_path)
    other = _lowered(_says_own_name("Y", 1), tmp_path)
    with pytest.raises(DuplicateProgramInImage) as twice:
        link_units((first, other, second), tmp_path)
    with pytest.raises(DuplicateProgramInImage) as listed_twice:
        link_units((other, other), tmp_path)
    assert (
        str(twice.value),
        str(listed_twice.value),
        sorted(p.name for p in tmp_path.glob("*.linked.json")),
    ) == (
        f"program X is in the image twice: {first.name} and {second.name}",
        f"program Y is in the image twice: {other.name} and {other.name}",
        [],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_dynamic_call_resolves_in_image(tmp_path, capsys):
    with_sub = _image((_DYNAMIC_MAIN, _SAYS_SUB), tmp_path / "with")
    without_sub = _image((_DYNAMIC_MAIN,), tmp_path / "without")
    capsys.readouterr()
    _entered(with_sub, "MAIN")
    called = capsys.readouterr().out
    with pytest.raises(UnresolvedProgramError):
        _entered(without_sub, "MAIN")
    assert (called, sorted(with_sub.programs), sorted(without_sub.programs)) == (
        "IN SUB\n",
        ["MAIN", "SUB"],
        ["MAIN"],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def _rewritten(unit_file: Path, **changes: Path | str) -> Path:
    codec = UnitCodec(IrCodec())
    codec.write(dataclasses.replace(codec.read(unit_file), **changes), unit_file)
    return unit_file


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_program_index_comes_from_program_id(tmp_path):
    units = (
        _rewritten(_lowered(_says_own_name("A", 1), tmp_path), path=Path("OTHER.cbl")),
        _rewritten(_lowered(_says_own_name("B", 1), tmp_path), program="BETA"),
        _lowered(_says_own_name("C", 1), tmp_path),
    )
    assert link_units(units, tmp_path).programs == {
        "A": CodeLabel("OTHER.func_a_0"),
        "BETA": CodeLabel("B.func_b_0"),
        "C": CodeLabel("C.func_c_0"),
    }


def _suspending_at_entry(unit_file: Path) -> Path:
    codec = UnitCodec(IrCodec())
    unit = codec.read(unit_file)
    at = next(
        n
        for n, inst in enumerate(unit.ir)
        if isinstance(inst, Label_) and inst.label == unit.entry_label
    )
    yielded, injected = Register("%90000"), Register("%90001")
    suspension = (
        Const(result_reg=yielded, value=0, type_expr=UNKNOWN),
        Suspend(result_reg=injected, operand_reg=yielded),
    )
    codec.write(
        dataclasses.replace(
            unit, ir=(*unit.ir[: at + 1], *suspension, *unit.ir[at + 1 :])
        ),
        unit_file,
    )
    return unit_file


def _suspended(image: LinkedProgram, name: str) -> ExecutionState:
    match run_linked_resumable(
        image,
        ProgramEntry(name),
        max_steps=20_000,
        initial_vm=initial_vm_state(),
        builtins=core_builtins(),
    ):
        case Suspended(state=state):
            return state
        case other:
            raise AssertionError(f"the program did not suspend: {other!r}")


def _resumed(image: LinkedProgram, state: ExecutionState) -> VMState:
    match resume_linked(image, state, max_steps=20_000, builtins=core_builtins()):
        case Completed(vm=vm):
            return vm
        case other:
            raise AssertionError(f"the resumed program did not complete: {other!r}")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_resumed_run_holds_the_declarations_of_the_program_it_entered(
    tmp_path, capsys
):
    image = link_units(
        (
            _lowered(_says_own_name("A", 1), tmp_path),
            _suspending_at_entry(_lowered(_says_own_name("B", 2), tmp_path)),
        ),
        tmp_path,
    )
    state = _suspended(image, "B")
    capsys.readouterr()
    resumed = _resumed(
        image,
        dataclasses.replace(state, vm=dataclasses.replace(state.vm, declarations=())),
    )
    assert (
        state.entered,
        resumed.declarations == declarations_of(image, "B"),
        tuple(field_positions(resumed.declarations)),
        capsys.readouterr().out,
    ) == (CodeLabel("B.func_b_0"), True, ("WS-B",), "BB\n")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_lowered_program_never_reuses_a_compiled_callee_unit(tmp_path):
    compile_cobol(
        _DYNAMIC_MAIN,
        parser=make_cobol_parser(),
        programs=(SourceFile(Path("program.cbl"), _SAYS_SUB),),
        work_dir=tmp_path,
    )
    unit = UnitCodec(IrCodec()).read(_lowered(_SAYS_SUB, tmp_path))
    assert (unit.path, unit.program) == (Path("SUB.cbl"), "SUB")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_compile_with_two_programs_of_one_name_is_refused(tmp_path):
    with pytest.raises(DuplicateProgramInImage) as twice:
        compile_cobol(
            _DYNAMIC_MAIN,
            parser=make_cobol_parser(),
            programs=(
                SourceFile(Path("ONE.cbl"), _SAYS_SUB),
                SourceFile(Path("TWO.cbl"), _SAYS_SUB.replace(b"IN SUB", b"IN TWO")),
            ),
            work_dir=tmp_path,
        )
    (one,) = tmp_path.glob("ONE-*.unit.json")
    (two,) = tmp_path.glob("TWO-*.unit.json")
    assert str(twice.value) == (
        f"program SUB is in the image twice: {one.name} and {two.name}"
    )
