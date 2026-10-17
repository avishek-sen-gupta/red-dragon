"""Tests for INSPECT's scan as IR: one left-to-right scan with every phrase competing."""

from collections.abc import Sequence

from interpreter.cobol.features import CobolFeature
from interpreter.cobol.inspect_ir import (
    emit_inspect_convert,
    emit_inspect_replace,
    emit_inspect_tally,
)
from interpreter.cobol.inspect_mode import InspectMode
from interpreter.cobol.inspect_phrase_registers import InspectPhraseRegisters
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.register import NO_REGISTER, Register
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted

_ALL = InspectMode.ALL
_LEADING = InspectMode.LEADING
_FIRST = InspectMode.FIRST
_CHARS = InspectMode.CHARACTERS

_WC = "AH YES AH YES W.C. FRITOES HERE. ANYONE WHO HATES DOGS AND KIDS CAN NOT BE ALL BAD."

type _Phrase = tuple[InspectMode, str, str, str, str, int]


def _phrase(
    mode: InspectMode,
    pattern: str = "",
    replacement: str = "",
    after: str = "",
    before: str = "",
    counter: int = 0,
) -> _Phrase:
    return mode, pattern, replacement, after, before, counter


def _operands(phrase: _Phrase) -> tuple[str, ...]:
    """The phrase's written operands: a pattern unless CHARACTERS, the BY value
    when given, and AFTER / BEFORE when given."""
    mode, pattern, replacement, after, before, _ = phrase
    return (
        *((pattern,) if mode != _CHARS else ()),
        *(text for text in (replacement, after, before) if text),
    )


def _bound(phrase: _Phrase, registers: Sequence[Register]) -> InspectPhraseRegisters:
    mode, _, replacement, after, before, counter = phrase
    written = iter(registers)
    return InspectPhraseRegisters(
        mode=mode,
        pattern=next(written) if mode != _CHARS else NO_REGISTER,
        replacement=next(written) if replacement else NO_REGISTER,
        after=next(written) if after else NO_REGISTER,
        before=next(written) if before else NO_REGISTER,
        counter=counter,
    )


def _phrase_registers(
    phrases: Sequence[_Phrase], registers: Sequence[Register]
) -> tuple[InspectPhraseRegisters, ...]:
    sizes = [len(_operands(phrase)) for phrase in phrases]
    starts = [sum(sizes[:index]) for index in range(len(phrases))]
    return tuple(
        _bound(phrase, registers[start : start + size])
        for phrase, start, size in zip(phrases, starts, sizes, strict=True)
    )


def _params(source: str, phrases: Sequence[_Phrase]) -> tuple[ParamValue, ...]:
    return (source, *(text for phrase in phrases for text in _operands(phrase)))


def _tally(source: str, phrases: Sequence[_Phrase], counters: int) -> tuple[int, ...]:
    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        return emit_inspect_tally(
            e, registers[0], _phrase_registers(phrases, registers[1:]), counters
        )

    counts = run_emitted(emit, _params(source, phrases))
    assert isinstance(counts, list)
    return tuple(counts)


def _replace(source: str, phrases: Sequence[_Phrase]) -> ParamValue:
    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        return emit_inspect_replace(
            e, registers[0], _phrase_registers(phrases, registers[1:])
        )

    return run_emitted(emit, _params(source, phrases))


def _convert(
    source: str, from_chars: str, to_chars: str, after: str, before: str
) -> ParamValue:
    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        written = iter(registers[3:])
        return emit_inspect_convert(
            e,
            registers[0],
            (registers[1], registers[2]),
            (
                next(written) if after else NO_REGISTER,
                next(written) if before else NO_REGISTER,
            ),
        )

    bounds = tuple(text for text in (after, before) if text)
    return run_emitted(emit, (source, from_chars, to_chars, *bounds))


@covers(CobolFeature.INSPECT_TALLYING)
def test_tallying_counts_each_position_once_within_each_phrase_region():
    cases = [
        (_WC, (_phrase(_CHARS),), 1),
        (_WC, (_phrase(_CHARS, after=" W"),), 1),
        (_WC, (_phrase(_CHARS, after=" W", before="KI"),), 1),
        (_WC, (_phrase(_ALL, " ", after="C.", before="DO"),), 1),
        ("ABCXYZ", (_phrase(_ALL, "B", after="Q"),), 1),
        ("ABCXYZ", (_phrase(_ALL, "B", before="Q"),), 1),
        ("AABA", (_phrase(_ALL, "AA"), _phrase(_ALL, "A", counter=1)), 2),
        ("AAXAA", (_phrase(_LEADING, "A"),), 1),
        ("XAAXA", (_phrase(_LEADING, "A", after="X"),), 1),
        (
            "ABAB",
            (_phrase(_ALL, "A"), _phrase(_CHARS, counter=1)),
            2,
        ),
        ("AB", (_phrase(_ALL, ""),), 1),
        ("AXA", (_phrase(_ALL, "AX"), _phrase(_LEADING, "A", counter=1)), 2),
    ]
    assert [_tally(source, phrases, n) for source, phrases, n in cases] == [
        (83,),
        (68,),
        (44,),
        (6,),
        (0,),
        (1,),
        (1, 1),
        (2,),
        (2,),
        (2, 2),
        (0,),
        (1, 0),
    ]


@covers(CobolFeature.INSPECT_REPLACING)
def test_replacing_rewrites_matched_positions_in_one_scan():
    cases = [
        ("AB", (_phrase(_ALL, "A", "B"), _phrase(_ALL, "B", "C"))),
        ("AABAC", (_phrase(_FIRST, "A", "X"),)),
        ("AACAA", (_phrase(_LEADING, "A", "Z"),)),
        ("HELLO", (_phrase(_CHARS, "", "O", before="L"),)),
        ("HELLO", (_phrase(_CHARS, "", " "),)),
        ("ABCXYZ", (_phrase(_ALL, "B", "-", after="Q"),)),
        (
            "AAEECEE",
            (_phrase(_FIRST, "C", "2"), _phrase(_ALL, "E", "3", after="C")),
        ),
        ("A.B.", (_phrase(_ALL, ".", " "),)),
        ("ABAB", (_phrase(_ALL, "AB", " "),)),
    ]
    assert [_replace(source, phrases) for source, phrases in cases] == [
        "BC",
        "XABAC",
        "ZZCAA",
        "OOLLO",
        "     ",
        "ABCXYZ",
        "AAEE233",
        "A B ",
        "    ",
    ]


@covers(CobolFeature.INSPECT_CONVERTING)
def test_converting_translates_only_inside_its_region():
    assert [
        _convert("GAQAUZTABAGA", "AU", "23", "Q", "B"),
        _convert("GAQAUZTABAGA", "AU", "23", "", ""),
        _convert("ABCABC", "AA", "XY", "", ""),
        _convert("ABC", "A", "X", "Q", ""),
    ] == ["GAQ23ZT2BAGA", "G2Q23ZT2B2G2", "XBCXBC", "ABC"]


@covers(CobolFeature.INSPECT_REPLACING)
def test_a_symbolic_by_value_flows_through_the_scan_into_the_result():
    def emit(e: IrEmitter, registers: tuple[Register, ...]) -> Register:
        source, pattern, by = registers
        return emit_inspect_replace(
            e,
            source,
            (InspectPhraseRegisters(mode=_ALL, pattern=pattern, replacement=by),),
        )

    replaced = run_emitted(emit, ("XAXA", "A", SymbolicValue("by")))
    assert isinstance(replaced, SymbolicValue)
    assert replaced.constraints == [
        "__string_splice(__string_splice('XAXA', 1, 1, __string_slice(by, 0, 1)),"
        " 3, 1, __string_slice(by, 0, 1))"
    ]
