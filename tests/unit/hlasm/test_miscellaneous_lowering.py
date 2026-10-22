# pyright: standard
"""Miscellaneous lowerings: the PSW fields and registers each form reads and writes, access registers in their own region, clocks through their builtins, hints as nothing, and every validity check before the first store."""

from collections.abc import Mapping, Sequence
from functools import singledispatch

from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import DATA_FIELD_LOWERINGS, OPCODE_LOWERINGS
from interpreter.instructions import (
    CallFunction,
    Const,
    InstructionBase,
    LoadRegion,
    LoadVar,
    StoreVar,
    Symbolic,
    WriteRegion,
)
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    imm_operand,
    machine_statement,
    mask_operand,
    reg_operand,
    storage_operand,
)

REGIONS = {"__hlasm_gprs": "gpr", "__hlasm_ars": "ar"}
STORAGE = "storage"
CLOCK_BUILTINS = frozenset({"__hlasm_tod_clock", "__hlasm_cpu_timer"})
PSW_VARIABLES = frozenset({"__hlasm_cc", "__hlasm_pm", "__hlasm_tod_last"})
BASE = 12
D8 = storage_operand(8)
ADDRESS = f"read gpr {8 * BASE + 4}+4"
CHECK = "StoreVar __hlasm_abend S0C6"


def _lowered(mnemonic: str, operands: Sequence[Operand]) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](emitter, machine_statement(mnemonic, operands))
    return emitter.instructions()


type Regions = Mapping[Register, str]
type Consts = Mapping[Register, int | str]


def _access(
    verb: str, i: LoadRegion | WriteRegion, regions: Regions, consts: Consts
) -> str:
    region = regions.get(i.region_reg, STORAGE)
    offset = {STORAGE: ""}.get(region, f"{consts.get(i.offset_reg, '')}")
    return f"{verb} {region} {offset}+{i.length}"


@singledispatch
def _shown(i: InstructionBase, regions: Regions, consts: Consts) -> str:
    return ""


@_shown.register
def _shown_read(i: LoadRegion, regions: Regions, consts: Consts) -> str:
    return _access("read", i, regions, consts)


@_shown.register
def _shown_write(i: WriteRegion, regions: Regions, consts: Consts) -> str:
    return _access("write", i, regions, consts)


@_shown.register
def _shown_store(i: StoreVar, regions: Regions, consts: Consts) -> str:
    return f"StoreVar {i.name} {consts.get(i.value_reg, 'reg')}"


@_shown.register
def _shown_load(i: LoadVar, regions: Regions, consts: Consts) -> str:
    return {True: f"LoadVar {i.name}"}.get(str(i.name) in PSW_VARIABLES, "")


@_shown.register
def _shown_call(i: CallFunction, regions: Regions, consts: Consts) -> str:
    return {True: f"call {i.func_name}"}.get(str(i.func_name) in CLOCK_BUILTINS, "")


def _trace(ir: Sequence[InstructionBase]) -> list[str]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    regions = {
        i.result_reg: REGIONS[str(i.name)]
        for i in ir
        if isinstance(i, LoadVar) and str(i.name) in REGIONS
    }
    shown = (_shown(i, regions, consts) for i in ir)
    return [entry for entry in shown if entry]


def _is_storage(entry: str) -> bool:
    return " storage " in f"{entry} "


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_program_status_forms_read_and_write_the_cc_mask_and_registers():
    traces = {
        "SPM": _trace(_lowered("SPM", (reg_operand(3),))),
        "IPM": _trace(_lowered("IPM", (reg_operand(3),))),
        "EPSW": _trace(_lowered("EPSW", (reg_operand(3), reg_operand(4)))),
        "EPSW R2 zero": _trace(_lowered("EPSW", (reg_operand(3), reg_operand(0)))),
    }

    assert traces == {
        "SPM": ["read gpr 28+4", "StoreVar __hlasm_cc reg", "StoreVar __hlasm_pm reg"],
        "IPM": [
            "read gpr 28+4",
            "LoadVar __hlasm_cc",
            "LoadVar __hlasm_pm",
            "write gpr 28+4",
        ],
        "EPSW": [
            "LoadVar __hlasm_cc",
            "LoadVar __hlasm_pm",
            "write gpr 28+4",
            "write gpr 36+4",
        ],
        "EPSW R2 zero": ["LoadVar __hlasm_cc", "LoadVar __hlasm_pm", "write gpr 28+4"],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_access_register_forms_move_words_through_the_access_register_region():
    traces = {
        "CPYA": _trace(_lowered("CPYA", (reg_operand(1), reg_operand(2)))),
        "EAR": _trace(_lowered("EAR", (reg_operand(3), reg_operand(4)))),
        "SAR": _trace(_lowered("SAR", (reg_operand(5), reg_operand(6)))),
        "LAM": _trace(_lowered("LAM", (reg_operand(15), reg_operand(0), D8))),
        "STAMY": _trace(_lowered("STAMY", (reg_operand(2), reg_operand(3), D8))),
    }

    assert traces == {
        "CPYA": ["read ar 8+4", "write ar 4+4"],
        "EAR": ["read ar 16+4", "write gpr 28+4"],
        "SAR": ["read gpr 52+4", "write ar 20+4"],
        "LAM": [
            ADDRESS,
            CHECK,
            "read storage +4",
            "write ar 60+4",
            "read storage +4",
            "write ar 0+4",
        ],
        "STAMY": [
            ADDRESS,
            CHECK,
            "read ar 8+4",
            "write storage +4",
            "read ar 12+4",
            "write storage +4",
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_clock_forms_read_their_builtin_and_ectg_fetches_every_operand_first():
    traces = {
        "STCK": _trace(_lowered("STCK", (D8,))),
        "STCKF": _trace(_lowered("STCKF", (D8,))),
        "STCKE": _trace(_lowered("STCKE", (D8,))),
        "ECTG": _trace(
            _lowered("ECTG", (storage_operand(0), storage_operand(8), reg_operand(3)))
        ),
    }

    assert traces == {
        "STCK": [
            "call __hlasm_tod_clock",
            "LoadVar __hlasm_tod_last",
            "StoreVar __hlasm_tod_last reg",
            ADDRESS,
            "write storage +8",
            "StoreVar __hlasm_cc 0",
        ],
        "STCKF": [
            "call __hlasm_tod_clock",
            ADDRESS,
            "write storage +8",
            "StoreVar __hlasm_cc 0",
        ],
        "STCKE": [
            "call __hlasm_tod_clock",
            ADDRESS,
            "write storage +16",
            "StoreVar __hlasm_cc 0",
        ],
        "ECTG": [
            ADDRESS,
            "read storage +8",
            ADDRESS,
            "read storage +8",
            "read gpr 28+4",
            "read storage +8",
            "call __hlasm_cpu_timer",
            "write gpr 0+8",
            "write gpr 8+8",
            "write gpr 24+8",
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_hints_lower_to_nothing_and_traps_abend_s0d3():
    hints = (
        _lowered("NIAI", (imm_operand(1), imm_operand(2))),
        _lowered("PFD", (mask_operand(1), D8)),
        _lowered(
            "PFDRL",
            (
                mask_operand(2),
                RelocImmOperand(kind="RELOC_IMM", section="T", offset=8),
            ),
        ),
    )

    assert [len(ir) for ir in hints] == [0, 0, 0]
    assert [
        _trace(_lowered("TRAP2", ())),
        _trace(_lowered("TRAP4", (D8,))),
        _trace(_lowered("MC", (D8, imm_operand(15)))),
    ] == [["StoreVar __hlasm_abend S0D3"], ["StoreVar __hlasm_abend S0D3"], [CHECK]]
    assert "MC" in DATA_FIELD_LOWERINGS


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_validity_checks_abend_before_the_first_store():
    traces = {
        "CKSM odd": _trace(_lowered("CKSM", (reg_operand(2), reg_operand(5)))),
        "LCBB reserved": _trace(
            _lowered("LCBB", (reg_operand(2), D8, mask_operand(7)))
        ),
        "STFLE": _trace(_lowered("STFLE", (D8,))),
        "CKSM": _trace(_lowered("CKSM", (reg_operand(2), reg_operand(4)))),
        "LCBB": _trace(_lowered("LCBB", (reg_operand(2), D8, mask_operand(6)))),
    }

    assert [traces["CKSM odd"], traces["LCBB reserved"]] == [[CHECK], [CHECK]]
    assert traces["STFLE"][:2] == [ADDRESS, CHECK]
    assert [entry for entry in traces["STFLE"] if entry.startswith("write")] == [
        "write storage +8",
        "write storage +8",
        "write gpr 4+4",
    ]
    assert [entry for entry in traces["CKSM"] if entry.startswith("write")] == [
        "write gpr 20+4",
        "write gpr 36+4",
        "write gpr 44+4",
    ]
    assert [e for e in traces["CKSM"] if _is_storage(e)] == [
        "read storage +4",
        "read storage +1",
    ]
    assert traces["LCBB"] == [
        ADDRESS,
        "write gpr 20+4",
        "StoreVar __hlasm_cc 0",
        "StoreVar __hlasm_cc 3",
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_form_lowers_without_symbolic_and_ecag_reads_no_storage():
    statements = {
        "CKSM": (reg_operand(2), reg_operand(4)),
        "CPYA": (reg_operand(1), reg_operand(2)),
        "EAR": (reg_operand(1), reg_operand(2)),
        "ECAG": (reg_operand(1), reg_operand(0), D8),
        "ECTG": (D8, D8, reg_operand(3)),
        "EPSW": (reg_operand(1), reg_operand(2)),
        "IPM": (reg_operand(1),),
        "LAM": (reg_operand(1), reg_operand(2), D8),
        "LAMY": (reg_operand(1), reg_operand(2), D8),
        "LCBB": (reg_operand(1), D8, mask_operand(0)),
        "MC": (D8, imm_operand(0)),
        "SAR": (reg_operand(1), reg_operand(2)),
        "SPM": (reg_operand(1),),
        "STAM": (reg_operand(1), reg_operand(2), D8),
        "STAMY": (reg_operand(1), reg_operand(2), D8),
        "STCK": (D8,),
        "STCKE": (D8,),
        "STCKF": (D8,),
        "STFLE": (D8,),
        "SVC": (imm_operand(13),),
    }
    lowered = {m: _lowered(m, operands) for m, operands in statements.items()}

    assert [
        m for m, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)
    ] == []
    assert _trace(lowered["ECAG"]) == [ADDRESS] + ["write gpr 8+8"] * 11
