# pyright: standard
"""Vector string lowerings: each form reads its sources whole, calls one element function per element size and IN/RT/ZS combination, writes V1 whole and sets the CC only with CS (VSTRS always); a reserved element size or a set reserved M bit abends S0C6 before any access; no SYMBOLIC at any allowed size and flag combination, and each function body's only SYMBOLICs are its parameters."""

from hlasm_asg.program.operand import Operand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.vector_string import (
    FIND_ANY,
    FIND_EQUAL,
    FIND_UNEQUAL,
    ISOLATE,
    RANGE,
    SEARCH,
    VECTOR_STRING_LOWERINGS,
)
from interpreter.instructions import CallFunction, Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.fp_trace import CC, SPECIFICATION, lowered_ir, trace
from tests.unit.hlasm.lowering_helpers import mask_operand
from tests.unit.hlasm.lowering_helpers import vec_reg_operand as vr

READ_V2 = "read vr 32+16"
READ_V3 = "read vr 48+16"
READ_V4 = "read vr 64+16"
WRITE_V1 = "write vr 16+16"
SIZES = range(3)
FUNCTION = "__hlasm_vector_"


def _forms(size: int, flags: int) -> dict[str, tuple[Operand, ...]]:
    two = (vr(1), vr(2), vr(3), mask_operand(size), mask_operand(flags))
    three = (vr(1), vr(2), vr(3), vr(4), mask_operand(size), mask_operand(flags))
    return {
        "VFAE": two,
        "VFEE": two,
        "VFENE": two,
        "VISTR": (vr(1), vr(2), mask_operand(size), mask_operand(flags)),
        "VSTRC": three,
        "VSTRS": three,
    }


def _called(mnemonic: str, operands: tuple[Operand, ...]) -> list[str]:
    return [
        str(i.func_name)
        for i in lowered_ir(mnemonic, operands)
        if isinstance(i, CallFunction) and str(i.func_name).startswith(FUNCTION)
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_string_forms_read_their_sources_call_one_function_and_set_the_cc_only_with_cs():
    without = {m: _forms(1, 0 if m == "VISTR" else 2)[m] for m in _forms(1, 0)}
    with_cs = {m: _forms(1, 1 if m == "VISTR" else 3)[m] for m in _forms(1, 0)}

    assert (
        {m: trace(m, operands) for m, operands in without.items()},
        {m: trace(m, operands) for m, operands in with_cs.items() if m != "VSTRS"},
        {m: _called(m, operands) for m, operands in without.items()},
        {m: _called(m, operands) for m, operands in with_cs.items() if m != "VSTRS"},
        _called("VFAE", _forms(0, 0b1101)["VFAE"])
        + _called("VFAE", _forms(2, 4)["VFAE"]),
        _called("VSTRC", _forms(0, 0b1001)["VSTRC"]),
    ) == (
        {
            "VFAE": [READ_V2, READ_V3, WRITE_V1],
            "VFEE": [READ_V2, READ_V3, WRITE_V1],
            "VFENE": [READ_V2, READ_V3, WRITE_V1],
            "VISTR": [READ_V2, WRITE_V1],
            "VSTRC": [READ_V2, READ_V3, READ_V4, WRITE_V1],
            "VSTRS": [READ_V2, READ_V3, READ_V4, WRITE_V1, CC],
        },
        {
            "VFAE": [READ_V2, READ_V3, WRITE_V1, CC],
            "VFEE": [READ_V2, READ_V3, WRITE_V1, CC],
            "VFENE": [READ_V2, READ_V3, WRITE_V1, CC],
            "VISTR": [READ_V2, WRITE_V1, CC],
            "VSTRC": [READ_V2, READ_V3, READ_V4, WRITE_V1, CC],
        },
        {
            "VFAE": ["__hlasm_vector_find_any_halfword_2"],
            "VFEE": ["__hlasm_vector_find_equal_halfword_2"],
            "VFENE": ["__hlasm_vector_find_unequal_halfword_2"],
            "VISTR": ["__hlasm_vector_isolate_halfword_0"],
            "VSTRC": ["__hlasm_vector_range_halfword_2"],
            "VSTRS": ["__hlasm_vector_search_halfword_2"],
        },
        {
            "VFAE": ["__hlasm_vector_find_any_halfword_2"],
            "VFEE": ["__hlasm_vector_find_equal_halfword_2"],
            "VFENE": ["__hlasm_vector_find_unequal_halfword_2"],
            "VISTR": ["__hlasm_vector_isolate_halfword_0"],
            "VSTRC": ["__hlasm_vector_range_halfword_2"],
        },
        ["__hlasm_vector_find_any_byte_12", "__hlasm_vector_find_any_word_4"],
        ["__hlasm_vector_range_byte_8"],
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_a_reserved_element_size_or_reserved_m_bit_abends_s0c6_before_any_access():
    invalid = [
        *((m, operands) for m, operands in _forms(3, 0).items()),
        *((m, operands) for m, operands in _forms(15, 0).items()),
        *(("VFEE", _forms(0, bit)["VFEE"]) for bit in (8, 4)),
        *(("VFENE", _forms(0, bit)["VFENE"]) for bit in (8, 4)),
        *(("VISTR", _forms(0, bit)["VISTR"]) for bit in (8, 4, 2)),
        *(("VSTRS", _forms(0, bit)["VSTRS"]) for bit in (8, 4, 1)),
    ]

    assert [trace(m, operands) for m, operands in invalid] == [
        [SPECIFICATION] for _ in invalid
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_vector_string_form_and_function_lowers_without_symbolic():
    allowed = {
        "VFAE": range(16),
        "VFEE": range(4),
        "VFENE": range(4),
        "VISTR": range(2),
        "VSTRC": range(16),
        "VSTRS": (0, 2),
    }
    lowered = {
        (m, size, flags): lowered_ir(m, _forms(size, flags)[m])
        for size in SIZES
        for m, flag_set in allowed.items()
        for flags in flag_set
    }
    functions = {
        function.name: function
        for registry in (FIND_ANY, FIND_EQUAL, FIND_UNEQUAL, ISOLATE, RANGE, SEARCH)
        for function in registry.values()
    }

    def symbolics(name: str) -> int:
        emitter = HlasmEmitter()
        functions[name].define(emitter)
        return sum(isinstance(i, Symbolic) for i in emitter.instructions())

    assert (
        sorted({form[0] for form in lowered}),
        len(VECTOR_STRING_LOWERINGS),
        [k for k, ir in lowered.items() if any(isinstance(i, Symbolic) for i in ir)],
        [
            k
            for k in lowered
            if trace(k[0], _forms(k[1], k[2])[k[0]]) == [SPECIFICATION]
        ],
        len(functions),
        {name: symbolics(name) for name in functions}
        == {name: function.arity for name, function in functions.items()},
    ) == (sorted(VECTOR_STRING_LOWERINGS), 6, [], [], 69, True)
