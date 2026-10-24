# pyright: standard
"""HLASM lowering: statement labels, seed opcodes and computed-branch dispatch, run through the binder's start-up and job step; the start-up sums every signed RLD item at a field, wherever it sits among the records."""

import logging
from collections.abc import Sequence
from pathlib import Path

import pytest

from hlasm_asg.program.hlasm_program import HlasmProgram
from interpreter.address import Address
from interpreter.constants import Language
from interpreter.frontends import bind_image
from interpreter.frontends.symbol_table import SymbolTable
from interpreter.func_name import FuncName
from interpreter.hlasm.hlasm_frontend import HlasmFrontend
from interpreter.hlasm_run_inputs.job_parm_builtins import NO_PARM, job_parm_builtins
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    CallFunction,
    Const,
    InstructionBase,
    Label_,
    LoadVar,
    StoreVar,
    Symbolic,
    WriteRegion,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.project.compiler import build_export_table
from interpreter.project.control_section import ControlSection
from interpreter.project.entry_point import EntryPoint
from interpreter.project.external_dummy_section import ExternalDummySection
from interpreter.project.linker import link_every_module
from interpreter.project.named_end import NamedEnd
from interpreter.project.no_relocation_target import NoRelocationTarget
from interpreter.project.object_module import ObjectModule
from interpreter.project.relocation_kind import RelocationKind
from interpreter.project.relocation_name import RelocationName
from interpreter.project.relocation_record import RelocationRecord
from interpreter.project.relocation_sign import RelocationSign
from interpreter.project.relocation_target import RelocationTarget
from interpreter.project.types import ModuleUnit
from interpreter.refs.func_ref import FuncRef
from interpreter.register import Register
from interpreter.run import initial_vm_state, run_linked
from interpreter.types.type_environment_builder import TypeEnvironmentBuilder
from interpreter.var_name import VarName
from interpreter.vm.builtins import compose_builtins, core_builtins
from interpreter.vm.vm_types import VMState
from tests.covers import NotLanguageFeature, covers

FIXTURES = Path(__file__).parent / "fixtures"


def _program(name: str) -> HlasmProgram:
    return HlasmProgram.model_validate_json((FIXTURES / name).read_text())


def _labels(ir: Sequence[InstructionBase]) -> list[str]:
    return [str(i.label) for i in ir if isinstance(i, Label_)]


def _between(
    ir: Sequence[InstructionBase], start: str, end: str
) -> list[InstructionBase]:
    labels = _labels(ir)
    starts = [at for at, i in enumerate(ir) if isinstance(i, Label_)]
    return list(ir[starts[labels.index(start)] : starts[labels.index(end)]])


def _consts(ir: Sequence[InstructionBase]) -> dict[Register, int | str]:
    return {i.result_reg: i.value for i in ir if isinstance(i, Const)}


def _gpr_writes(ir: Sequence[InstructionBase]) -> list[tuple[int, int | str]]:
    consts = _consts(ir)
    return [(i.length, consts[i.offset_reg]) for i in ir if isinstance(i, WriteRegion)]


def _dispatch_comparands(ir: Sequence[InstructionBase]) -> list[int | str]:
    consts = _consts(ir)
    return [
        consts[i.right]
        for i in ir
        if isinstance(i, Binop) and i.operator == BinopKind.EQ and i.right in consts
    ]


def _branch_and_abend(ir: Sequence[InstructionBase]) -> list[str]:
    return [
        (
            f"{type(i).__name__}:{i.name}"
            if isinstance(i, StoreVar)
            else (
                f"Branch:{i.label}"
                if isinstance(i, Branch)
                else f"Const:{i.value}" if isinstance(i, Const) else type(i).__name__
            )
        )
        for i in ir
    ]


def _run(frontend: HlasmFrontend) -> VMState:
    return _run_bound(frontend, frontend.object_module)


def _run_bound(frontend: HlasmFrontend, object_module: ObjectModule) -> VMState:
    ir = frontend.lower(b"")
    unit = ModuleUnit(
        path=Path("M.asm"),
        language=Language.HLASM,
        ir=tuple(ir),
        exports=build_export_table(ir, frontend.func_symbol_table, {}),
        imports=(),
        object_module=object_module,
    )
    bound = bind_image((unit,))
    modules = {
        bound.start_up.path: bound.start_up,
        unit.path: unit,
        bound.job_step.path: bound.job_step,
    }
    linked = link_every_module(
        modules=modules,
        import_graph={path: () for path in modules},
        project_root=Path("/"),
        topo_order=tuple(modules),
        language=Language.HLASM,
        type_env_builder=TypeEnvironmentBuilder(),
        symbol_table=SymbolTable.empty(),
    )
    entry = bound.module_entries[unit.path]
    return run_linked(
        linked,
        EntryPoint.function(lambda ref: ref.label == entry),
        max_steps=2000,
        initial_vm=initial_vm_state(),
        builtins=compose_builtins(core_builtins(), job_parm_builtins(NO_PARM)),
    )


def _var(vm: VMState, name: str) -> int | str:
    return vm.call_stack[0].local_vars[VarName(name)].value


def _bytes_at(vm: VMState, address: int, width: int) -> list[int]:
    loaded = vm.load(address, width)
    assert isinstance(loaded, list)
    return loaded


def _low_words(vm: VMState) -> list[int]:
    gprs = int(_var(vm, "__hlasm_gprs"))
    return [
        int.from_bytes(bytes(_bytes_at(vm, gprs + 8 * r + 4, 4)), "big")
        for r in range(16)
    ]


def _dispatch_entries(
    ir: Sequence[InstructionBase],
) -> tuple[list[str], list[str], list[str]]:
    return (
        _branch_and_abend(_between(ir, "hl_link_dispatch", "hl_dispatch")),
        _branch_and_abend(_between(ir, "hl_dispatch", "hl_local_dispatch")),
        [
            str(i.name)
            for i in _between(ir, "hl_dispatch_next_1", "hl_dispatch_far_2")
            if isinstance(i, LoadVar)
        ],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_seed_program_lowers_to_labels_region_ops_and_dispatch():
    frontend = HlasmFrontend(_program("seed_program.json"), "M")
    ir = frontend.lower(b"")
    dispatch = _between(ir, "hl_dispatch", "end_hello_1")
    assert _labels(ir)[:8] + _labels(ir)[-2:] == [
        "entry",
        "func_hello_0",
        "hl_HELLO_0",
        "hl_HELLO_4",
        "hl_link_dispatch",
        "hl_dispatch",
        "hl_local_dispatch",
        "hl_dispatch_next_0",
        "hl_return",
        "end_hello_1",
    ]
    assert (
        _gpr_writes(_between(ir, "hl_HELLO_0", "hl_HELLO_4")),
        [str(i.hint) for i in ir if isinstance(i, Symbolic)],
    ) == ([(4, 124)], ["param:__hlasm_entry_target", "param:__hlasm_below"])
    assert _branch_and_abend(_between(ir, "hl_HELLO_4", "hl_link_dispatch"))[-5:] == [
        "StoreVar:__hlasm_target",
        "Branch:hl_dispatch",
        "Const:S0C1",
        "StoreVar:__hlasm_abend",
        "Halt_",
    ]
    assert _dispatch_entries(ir) == (
        ["Label_", "Const:1", "StoreVar:__hlasm_linking", "Branch:hl_local_dispatch"],
        ["Label_", "Const:0", "StoreVar:__hlasm_linking"],
        ["__hlasm_target", "__hlasm_return_to"],
    )
    assert (
        _dispatch_comparands(_between(ir, "hl_local_dispatch", "hl_return")),
        [i.branch_targets for i in dispatch if isinstance(i, BranchIf)],
    ) == (
        [0, 4, 0xFF0],
        [
            (CodeLabel("hl_HELLO_0"), CodeLabel("hl_dispatch_next_0")),
            (CodeLabel("hl_HELLO_4"), CodeLabel("hl_dispatch_next_1")),
            (CodeLabel("hl_return"), CodeLabel("hl_dispatch_far_2")),
            (CodeLabel("hl_return"), CodeLabel("hl_dispatch")),
        ],
    )
    assert [
        (str(i.func_name), len(i.args)) for i in dispatch if isinstance(i, CallFunction)
    ] == [
        ("__hlasm_far_branch", 4),
        ("__binary_bytes_to_int", 2),
    ]
    assert frontend.func_symbol_table == {
        CodeLabel("func_hello_0"): FuncRef(
            name=FuncName("func_hello_0"), label=CodeLabel("func_hello_0")
        )
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_seed_opcodes_branch_link_and_return_through_the_dispatch():
    vm = _run(HlasmFrontend(_program("seed_branches.json"), "M"))
    words = _low_words(vm)
    base = int(_var(vm, "__hlasm_sect_M.MAIN"))
    gprs = int(_var(vm, "__hlasm_gprs"))
    back = base + 34
    assert [words[r] for r in (2, 3, 4, 5, 6, 7, 10, 11, 12, 14, 15)] == [
        0x80000000 | (base + 42),
        0xFFFFFFFE,
        7,
        0x80000000 | (base + 48),
        base + 28,
        0x80000000 | back,
        back,
        base,
        0xFF0,
        0xFF0,
        9,
    ]
    assert _bytes_at(vm, gprs, 8 * 16)[0::8] == [0] * 16
    assert [_var(vm, "__hlasm_cc"), _var(vm, "__hlasm_abend")] == [1, ""]
    assert vm.region_get(Address(str(words[13]))) == bytearray(72)


def _miss(fixture: str) -> list[int | str]:
    vm = _run(HlasmFrontend(_program(fixture), "M"))
    words = _low_words(vm)
    return [
        _var(vm, "__hlasm_abend"),
        words[15],
        words[6] - int(_var(vm, "__hlasm_sect_M.MAIN")),
        words[6] - words[13],
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_unknown_opcodes_and_dispatch_misses_abend_s0c1(
    caplog: pytest.LogCaptureFixture,
):
    frontend = HlasmFrontend(_program("unknown_opcode.json"), "M")
    with caplog.at_level(logging.WARNING, logger="interpreter.hlasm.lower_statement"):
        vm = _run(frontend)
    assert frontend.entry_label == CodeLabel("func_odd_0")
    assert [r.getMessage() for r in caplog.records] == [
        "HLASM opcode PR has no lowering; it abends S0C1"
    ]
    assert [_var(vm, "__hlasm_abend"), _low_words(vm)[15]] == ["S0C1", 3]
    assert _miss("branch_into_data.json")[:3] == ["S0C1", 4, 16]
    assert [_miss("branch_into_dsect.json")[at] for at in (0, 1, 3)] == ["S0C1", 5, 4]


def _item(
    offset: int, kind: RelocationKind, target: RelocationTarget, addend: int
) -> RelocationRecord:
    return RelocationRecord(
        "HELLO", offset, 4, kind, target, RelocationSign.PLUS, addend
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_start_up_sums_every_signed_item_at_a_field_wherever_it_sits():
    address, total = RelocationKind.ADDRESS, RelocationKind.PR_TOTAL
    object_module = ObjectModule(
        esd=(
            ControlSection("HELLO", 16),
            ControlSection("DATA", 8),
            ExternalDummySection("PR", 6, 4),
        ),
        text=(),
        relocations=(
            _item(8, address, RelocationName("DATA"), 5),
            _item(12, total, NoRelocationTarget(), 0),
            RelocationRecord(
                "HELLO",
                8,
                4,
                address,
                RelocationName("HELLO"),
                RelocationSign.MINUS,
                0,
            ),
            _item(8, total, NoRelocationTarget(), 0),
        ),
        end=NamedEnd("HELLO", "HELLO", 0),
    )
    vm = _run_bound(HlasmFrontend(_program("seed_program.json"), "M"), object_module)
    hello = int(_var(vm, "__hlasm_sect_M.HELLO"))

    assert [
        int.from_bytes(bytes(_bytes_at(vm, hello + at, 4)), "big") for at in (8, 12)
    ] == [16 + 5 + 6, 6]
