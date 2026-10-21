# pyright: standard
"""HLASM lowering: statement labels, seed opcodes and computed-branch dispatch."""

import logging
from collections.abc import Sequence
from pathlib import Path

import pytest

from hlasm_asg.program.hlasm_program import HlasmProgram
from interpreter.address import Address
from interpreter.cfg import build_cfg
from interpreter.func_name import FuncName
from interpreter.hlasm.hlasm_frontend import HlasmFrontend
from interpreter.instructions import (
    Binop,
    Branch,
    BranchIf,
    Const,
    InstructionBase,
    Label_,
    StoreVar,
    Symbolic,
    WriteRegion,
)
from interpreter.ir import CodeLabel
from interpreter.operator_kind import BinopKind
from interpreter.refs.func_ref import FuncRef
from interpreter.register import Register
from interpreter.registry import build_registry
from interpreter.run import execute_cfg, initial_vm_state
from interpreter.run_types import VMConfig
from interpreter.var_name import VarName
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
        if isinstance(i, Binop) and i.operator == BinopKind.EQ
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
    lowered = frontend.lower(b"")
    ir = [lowered[0], *frontend.start_up_ir(), *lowered[1:]]
    cfg = build_cfg(ir)
    registry = build_registry(ir, cfg, func_symbol_table=frontend.func_symbol_table)
    config = VMConfig(max_steps=2000)
    started, _stats = execute_cfg(cfg, "entry", registry, config, vm=initial_vm_state())
    finished, _ran = execute_cfg(
        cfg, frontend.entry_label, registry, config, vm=started
    )
    return finished


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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_seed_program_lowers_to_labels_region_ops_and_dispatch():
    frontend = HlasmFrontend(_program("seed_program.json"))
    ir = frontend.lower(b"")
    dispatch = _between(ir, "hl_dispatch", "end_hello_1")
    assert _labels(ir)[:5] + _labels(ir)[-2:] == [
        "entry",
        "func_hello_0",
        "hl_HELLO_0",
        "hl_HELLO_4",
        "hl_dispatch",
        "hl_return",
        "end_hello_1",
    ]
    assert _gpr_writes(_between(ir, "hl_HELLO_0", "hl_HELLO_4")) == [(4, 124)]
    assert _branch_and_abend(_between(ir, "hl_HELLO_4", "hl_dispatch"))[-5:] == [
        "StoreVar:__hlasm_target",
        "Branch:hl_dispatch",
        "Const:S0C1",
        "StoreVar:__hlasm_abend",
        "Halt_",
    ]
    assert _dispatch_comparands(dispatch) == [0xFF0, 0, 4]
    assert [i.branch_targets[0] for i in dispatch if isinstance(i, BranchIf)] == [
        CodeLabel("hl_return"),
        CodeLabel("hl_HELLO_0"),
        CodeLabel("hl_HELLO_4"),
    ]
    assert [i for i in ir if isinstance(i, Symbolic)] == []
    assert frontend.func_symbol_table == {
        CodeLabel("func_hello_0"): FuncRef(
            name=FuncName("func_hello_0"), label=CodeLabel("func_hello_0")
        )
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_seed_opcodes_branch_link_and_return_through_the_dispatch():
    vm = _run(HlasmFrontend(_program("seed_branches.json")))
    words = _low_words(vm)
    base = int(_var(vm, "__hlasm_sect_MAIN"))
    gprs = int(_var(vm, "__hlasm_gprs"))
    back = base + 34
    assert [words[r] for r in (3, 4, 6, 7, 10, 11, 12, 14, 15)] == [
        0xFFFFFFFE,
        7,
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


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_unknown_opcode_abends_s0c1_and_names_the_mnemonic(
    caplog: pytest.LogCaptureFixture,
):
    frontend = HlasmFrontend(_program("unknown_opcode.json"))
    with caplog.at_level(logging.WARNING, logger="interpreter.hlasm.lower_statement"):
        vm = _run(frontend)
    assert frontend.entry_label == CodeLabel("func_odd_0")
    assert [r.getMessage() for r in caplog.records] == [
        "HLASM opcode SVC has no lowering; it abends S0C1"
    ]
    assert [_var(vm, "__hlasm_abend"), _low_words(vm)[15]] == ["S0C1", 3]
