# pyright: standard
"""The DPD codec IR: every declet encodes as PoO figure 20-32 gives it (the fixture transcribes the figure) and decodes back, and the noncanonical declets decode as figure 20-33 gives them, noncanonical declets included, and each format's image splits into sign, biased exponent or special code, and significand, and back canonically."""

from collections.abc import Callable, Sequence
from pathlib import Path

from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, SHORT_DFP, DfpLayout
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.dfp_codec import DECODERS, ENCODERS
from interpreter.hlasm.opcodes.dpd_lanes import declets_to_integer, integer_to_declets
from interpreter.instructions import Return_
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.straight_line_vm import returned_value

type Builder = Callable[[HlasmEmitter, Sequence[Register]], Register]

ALL_DECLETS = 1024
DECLET_VALUES = 1000
FIXTURES = Path(__file__).parent / "fixtures"


def _figure_20_32() -> dict[int, int]:
    rows = (FIXTURES / "dpd_figure_20_32.txt").read_text().splitlines()
    return {
        int(row[:2]) * 10 + column: int(declet, 16)
        for row in rows
        for column, declet in enumerate(row.split()[1:])
    }


NONCANONICAL = {
    0x16E: 888,
    0x16F: 889,
    0x17E: 898,
    0x17F: 899,
    0x1EE: 988,
    0x1EF: 989,
    0x1FE: 998,
    0x1FF: 999,
    0x26E: 888,
    0x26F: 889,
    0x27E: 898,
    0x27F: 899,
    0x2EE: 988,
    0x2EF: 989,
    0x2FE: 998,
    0x2FF: 999,
    0x36E: 888,
    0x36F: 889,
    0x37E: 898,
    0x37F: 899,
    0x3EE: 988,
    0x3EF: 989,
    0x3FE: 998,
    0x3FF: 999,
}


def _run(builder: Builder, *arguments: int) -> int | list[int]:
    emitter = HlasmEmitter()
    parameters = [Register(f"%p{at}") for at in range(len(arguments))]
    emitter.emit_inst(Return_(value_reg=builder(emitter, parameters)))
    return returned_value(
        emitter.instructions(),
        {f"%p{at}": value for at, value in enumerate(arguments)},
    )


def _every_declet_encoded() -> list[int]:
    packed = sum(n * DECLET_VALUES**n for n in range(DECLET_VALUES))
    encoded = _run(
        lambda emitter, p: integer_to_declets(emitter, p[0], DECLET_VALUES), packed
    )
    assert isinstance(encoded, int)
    return [(encoded >> (10 * n)) & 0x3FF for n in range(DECLET_VALUES)]


def _every_declet_decoded() -> list[int]:
    packed = sum(d << (10 * d) for d in range(ALL_DECLETS))
    decoded = _run(
        lambda emitter, p: declets_to_integer(emitter, p[0], ALL_DECLETS), packed
    )
    assert isinstance(decoded, int)
    return [(decoded // DECLET_VALUES**d) % DECLET_VALUES for d in range(ALL_DECLETS)]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_declets_follow_the_dpd_figures():
    declets = _every_declet_encoded()
    values = _every_declet_decoded()

    figure = _figure_20_32()

    assert dict(enumerate(declets)) == figure
    assert {figure[n]: values[figure[n]] for n in range(DECLET_VALUES)} == {
        figure[n]: n for n in range(DECLET_VALUES)
    }
    assert {
        d: values[d] for d in range(ALL_DECLETS) if d not in set(declets)
    } == NONCANONICAL


IMAGES: dict[str, tuple[DfpLayout, int, list[int]]] = {
    "short 1": (SHORT_DFP, 0x22500001, [0, 101, 1]),
    "short -9.999999E96 at the top exponent": (
        SHORT_DFP,
        0xF7F3FCFF,
        [1, 191, 9999999],
    ),
    "long 1": (LONG_DFP, 0x22380000_00000001, [0, 398, 1]),
    "long 9E15 with an LMD of 9": (
        LONG_DFP,
        0x6E380000_00000000,
        [0, 398, 9 * 10**15],
    ),
    "long -0 at the bottom exponent": (LONG_DFP, 0x80000000_00000000, [1, 0, 0]),
    "long noncanonical 888": (LONG_DFP, 0x22380000_0000016E, [0, 398, 888]),
    "long -infinity with reserved bits and digits": (
        LONG_DFP,
        0xF9FC0000_00000005,
        [1, -1, 5],
    ),
    "long QNaN payload 123": (LONG_DFP, 0x7C000000_000000A3, [0, -2, 123]),
    "long SNaN with reserved bits": (LONG_DFP, 0xFEFC0000_00000009, [1, -3, 9]),
    "extended 1": (EXTENDED_DFP, 0x22080000_00000000_00000000_00000001, [0, 6176, 1]),
    "extended 8E33 with the top biased exponent": (
        EXTENDED_DFP,
        0x73FFC000_00000000_00000000_00000000,
        [0, 12287, 8 * 10**33],
    ),
    "extended SNaN payload 1": (
        EXTENDED_DFP,
        0x7E000000_00000000_00000000_00000001,
        [0, -3, 1],
    ),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_images_decode_to_fields_and_encode_canonically():
    decoded = {
        name: _run(DECODERS[case[0]].body, case[1]) for name, case in IMAGES.items()
    }
    encoded = {
        name: _run(ENCODERS[case[0]].body, *case[2])
        for name, case in IMAGES.items()
        if case[0] in ENCODERS
    }

    assert decoded == {name: case[2] for name, case in IMAGES.items()}
    assert encoded == {
        "long 1": 0x22380000_00000001,
        "long 9E15 with an LMD of 9": 0x6E380000_00000000,
        "long -0 at the bottom exponent": 0x80000000_00000000,
        "long noncanonical 888": 0x22380000_0000006E,
        "long -infinity with reserved bits and digits": 0xF8000000_00000005,
        "long QNaN payload 123": 0x7C000000_000000A3,
        "long SNaN with reserved bits": 0xFE000000_00000009,
        "extended 1": 0x22080000_00000000_00000000_00000001,
        "extended 8E33 with the top biased exponent": 0x73FFC000_00000000_00000000_00000000,
        "extended SNaN payload 1": 0x7E000000_00000000_00000000_00000001,
    }
