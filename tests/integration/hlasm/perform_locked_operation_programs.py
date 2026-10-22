# pyright: standard
"""PLO programs for every function code, built from the tests' own reading of Figure 7-380: each case sets up the compare values to match or miss, runs a byte model of the operation for the expected registers, storage and CC, and reads the stored places back."""

from collections.abc import Mapping, Sequence
from functools import reduce

from tests.integration.hlasm.load_store_programs import ABEND, FILL, HIGH_FILL
from tests.integration.hlasm.plo_function import Location, PloFunction

type Storage = tuple[tuple[int, bytes], ...]
type Case = tuple[str, Mapping[int, int], int, Storage]
type Memory = Mapping[str, bytes]
type Setup = tuple[Memory, tuple[str, ...]]

FW, DW, QW, OW = 4, 8, 16, 32
R1, R1_REPLACEMENT, R3, R3_REPLACEMENT = ("R4", 0), ("R5", 0), ("R6", 0), ("R7", 0)
REGISTERS = frozenset({"R4", "R5", "R6", "R7"})
REGISTER_NUMBERS: Mapping[str, int] = {"R4": 4, "R5": 5, "R6": 6, "R7": 7}
REGISTER_VALUES: Mapping[str, int] = {"R4": 444, "R5": 555, "R6": 666, "R7": 777}
SECOND: Location = ("OP2", 0)
FOURTH: Location = ("OP4", 0)
OP1: Location = ("OP1", 0)
OP3: Location = ("OP3", 0)
REGISTER_BYTES = 8
WORD = 4
MISSED_WORD = 999
UNEQUAL_RESULTS: Location = ("PL", 48)
ANY_UNEQUAL_CC = 2
NO_COMPARE_CC = 2
MULTIPLE_OPERANDS = 30
LIST_POINTERS: Mapping[str, int] = {"OP4": 72, "OP3": 104, "OP1": 136}
OPERANDS_AT = 0x480
PL_AT = 0x600
PL_BYTES = 320
DATA_SPAN = (OPERANDS_AT, PL_AT + PL_BYTES)


def pl(offset: int) -> Location:
    return ("PL", offset)


def _words(values: Sequence[int]) -> bytes:
    return b"".join(value.to_bytes(WORD, "big") for value in values)


def _operand_words(k: int) -> bytes:
    return _words([100 * k + j + 1 for j in range(8)])


INITIAL: Memory = {
    **{f"OP{k}": _operand_words(k) for k in range(1, 5)},
    "PL": _words([5000 + j for j in range(80)]),
    **{register: FILL.to_bytes(REGISTER_BYTES, "big") for register in REGISTERS},
}


def _start(location: Location, width: int) -> int:
    area, offset = location
    return REGISTER_BYTES - width if area in REGISTERS else offset


def read(memory: Memory, location: Location, width: int) -> int:
    start = _start(location, width)
    return int.from_bytes(memory[location[0]][start : start + width], "big")


def write(memory: Memory, location: Location, width: int, value: int) -> Memory:
    area, start = location[0], _start(location, width)
    image = memory[area]
    replaced = value.to_bytes(width, "big")
    return {**memory, area: image[:start] + replaced + image[start + width :]}


def _operand(k: int) -> Location:
    return (f"OP{k + 1}", 0)


def _data(width: int, k: int) -> Location:
    return pl(64 + max(width, DW) * k)


def _in_registers(
    width: int,
    compares: tuple[tuple[Location, Location], ...],
    stores: tuple[tuple[Location, Location], ...],
) -> PloFunction:
    return PloFunction(width, compares, stores, True, True, False)


def _with_list(
    width: int,
    compares: tuple[tuple[Location, Location], ...],
    stores: tuple[tuple[Location, Location], ...],
) -> PloFunction:
    return PloFunction(width, compares, stores, False, False, False)


def _registers_with_list(
    width: int, stores: tuple[tuple[Location, Location], ...]
) -> PloFunction:
    return PloFunction(width, ((R1, SECOND),), stores, True, False, False)


def _multiple_compare(operands: int, width: int) -> PloFunction:
    compares = tuple((_data(width, k), _operand(k)) for k in range(operands))
    order = (*range(1, operands), 0)
    stores = tuple((_data(width, operands + k), _operand(k)) for k in order)
    return PloFunction(width, compares, stores, False, False, True)


def _loads(operands: int, width: int) -> PloFunction:
    stores = tuple((_operand(k), _data(width, k)) for k in range(operands))
    return PloFunction(width, (), stores, False, False, False)


def _stores(operands: int, width: int) -> PloFunction:
    stores = tuple((_data(width, k), _operand(k)) for k in range(operands))
    return PloFunction(width, (), stores, False, False, False)


WIDTHS = (FW, DW, QW, OW)

FUNCTIONS: Mapping[int, PloFunction] = {
    0: _in_registers(FW, ((R1, SECOND),), ((FOURTH, R3),)),
    1: _with_list(DW, ((pl(8), SECOND),), ((FOURTH, pl(40)),)),
    2: _in_registers(DW, ((R1, SECOND),), ((FOURTH, R3),)),
    3: _with_list(QW, ((pl(0), SECOND),), ((FOURTH, pl(32)),)),
    4: _in_registers(FW, ((R1, SECOND),), ((R1_REPLACEMENT, SECOND),)),
    5: _with_list(DW, ((pl(8), SECOND),), ((pl(24), SECOND),)),
    6: _in_registers(DW, ((R1, SECOND),), ((R1_REPLACEMENT, SECOND),)),
    7: _with_list(QW, ((pl(0), SECOND),), ((pl(16), SECOND),)),
    8: _in_registers(
        FW,
        ((R1, SECOND), (R3, FOURTH)),
        ((R3_REPLACEMENT, FOURTH), (R1_REPLACEMENT, SECOND)),
    ),
    9: _with_list(
        DW,
        ((pl(8), SECOND), (pl(40), FOURTH)),
        ((pl(56), FOURTH), (pl(24), SECOND)),
    ),
    10: _in_registers(
        DW,
        ((R1, SECOND), (R3, FOURTH)),
        ((R3_REPLACEMENT, FOURTH), (R1_REPLACEMENT, SECOND)),
    ),
    11: _with_list(
        QW,
        ((pl(0), SECOND), (pl(32), FOURTH)),
        ((pl(48), FOURTH), (pl(16), SECOND)),
    ),
    12: _in_registers(FW, ((R1, SECOND),), ((R3, FOURTH), (R1_REPLACEMENT, SECOND))),
    13: _with_list(DW, ((pl(8), SECOND),), ((pl(56), FOURTH), (pl(24), SECOND))),
    14: _in_registers(DW, ((R1, SECOND),), ((R3, FOURTH), (R1_REPLACEMENT, SECOND))),
    15: _with_list(QW, ((pl(0), SECOND),), ((pl(48), FOURTH), (pl(16), SECOND))),
    16: _registers_with_list(
        FW, ((pl(60), FOURTH), (pl(92), OP3), (R1_REPLACEMENT, SECOND))
    ),
    17: _with_list(
        DW,
        ((pl(8), SECOND),),
        ((pl(56), FOURTH), (pl(88), OP3), (pl(24), SECOND)),
    ),
    18: _registers_with_list(
        DW, ((pl(56), FOURTH), (pl(88), OP3), (R1_REPLACEMENT, SECOND))
    ),
    19: _with_list(
        QW,
        ((pl(0), SECOND),),
        ((pl(48), FOURTH), (pl(80), OP3), (pl(16), SECOND)),
    ),
    20: _registers_with_list(
        FW,
        (
            (pl(60), FOURTH),
            (pl(92), OP3),
            (pl(124), OP1),
            (R1_REPLACEMENT, SECOND),
        ),
    ),
    21: _with_list(
        DW,
        ((pl(8), SECOND),),
        ((pl(56), FOURTH), (pl(88), OP3), (pl(120), OP1), (pl(24), SECOND)),
    ),
    22: _registers_with_list(
        DW,
        (
            (pl(56), FOURTH),
            (pl(88), OP3),
            (pl(120), OP1),
            (R1_REPLACEMENT, SECOND),
        ),
    ),
    23: _with_list(
        QW,
        ((pl(0), SECOND),),
        ((pl(48), FOURTH), (pl(80), OP3), (pl(112), OP1), (pl(16), SECOND)),
    ),
    24: _with_list(OW, ((pl(0), SECOND),), ((FOURTH, pl(32)),)),
    25: _with_list(OW, ((pl(0), SECOND),), ((pl(32), SECOND),)),
    26: _with_list(
        OW,
        ((pl(0), SECOND), (pl(80), FOURTH)),
        ((pl(112), FOURTH), (pl(32), SECOND)),
    ),
    27: _with_list(OW, ((pl(0), SECOND),), ((pl(80), FOURTH), (pl(32), SECOND))),
    28: _with_list(
        OW,
        ((pl(0), SECOND),),
        ((pl(112), FOURTH), (pl(144), OP3), (pl(32), SECOND)),
    ),
    29: _with_list(
        OW,
        ((pl(0), SECOND),),
        ((pl(144), FOURTH), (pl(176), OP3), (pl(208), OP1), (pl(32), SECOND)),
    ),
    **{30 + k: _multiple_compare(3, width) for k, width in enumerate(WIDTHS)},
    **{34 + k: _multiple_compare(4, width) for k, width in enumerate(WIDTHS)},
    38: _loads(1, OW),
    39: _loads(2, QW),
    40: _loads(2, OW),
    **{41 + k: _loads(3, width) for k, width in enumerate(WIDTHS)},
    **{45 + k: _loads(4, width) for k, width in enumerate(WIDTHS)},
    49: _stores(1, OW),
    **{50 + k: _stores(2, width) for k, width in enumerate(WIDTHS)},
    **{54 + k: _stores(3, width) for k, width in enumerate(WIDTHS)},
    **{58 + k: _stores(4, width) for k, width in enumerate(WIDTHS)},
}


def _areas(function: PloFunction) -> frozenset[str]:
    pairs = (*function.compares, *function.stores)
    return frozenset(location[0] for pair in pairs for location in pair)


def pointers(code: int, function: PloFunction) -> Mapping[int, str]:
    used = _areas(function)
    if code >= MULTIPLE_OPERANDS:
        return {8 * k: f"OP{k + 1}" for k in range(4) if f"OP{k + 1}" in used}
    if function.fourth_is_operand:
        return {}
    return {at: area for area, at in LIST_POINTERS.items() if area in used}


def _register_line(register: str, width: int, source: str) -> str:
    load = {FW: "L", DW: "LG"}[width]
    return f"{load:<6}{REGISTER_NUMBERS[register]},{source}"


def _immediate_line(register: str, width: int, value: int) -> str:
    load = {FW: "LHI", DW: "LGHI"}[width]
    return f"{load:<6}{REGISTER_NUMBERS[register]},{value}"


def _missed(width: int) -> int:
    return int.from_bytes(_words([MISSED_WORD] * (width // WORD)), "big")


def _base_registers(function: PloFunction) -> Setup:
    if not function.in_registers:
        return INITIAL, ()
    w = function.width
    memory = reduce(
        lambda m, item: write(m, (item[0], 0), w, item[1]),
        REGISTER_VALUES.items(),
        INITIAL,
    )
    lines = tuple(_immediate_line(r, w, v) for r, v in REGISTER_VALUES.items())
    return memory, lines


def _compare_value(
    setup: Setup, compare: tuple[Location, Location], width: int, hit: bool
) -> Setup:
    memory, lines = setup
    value, operand = compare
    wanted = read(INITIAL, operand, width) if hit else _missed(width)
    written = write(memory, value, width, wanted)
    if value[0] not in REGISTERS:
        return written, lines
    line = (
        _register_line(value[0], width, operand[0])
        if hit
        else _immediate_line(value[0], width, MISSED_WORD)
    )
    return written, (*lines, line)


def prepared(function: PloFunction, missed_at: int) -> Setup:
    return reduce(
        lambda setup, item: _compare_value(
            setup, item[1], function.width, item[0] != missed_at
        ),
        enumerate(function.compares),
        _base_registers(function),
    )


def _first_unequal(function: PloFunction, memory: Memory) -> int:
    w = function.width
    return next(
        (
            k
            for k, (value, operand) in enumerate(function.compares)
            if read(memory, value, w) != read(memory, operand, w)
        ),
        len(function.compares),
    )


def _refreshed(function: PloFunction, memory: Memory, k: int) -> tuple[Memory, int]:
    value, operand = function.compares[k]
    w = function.width
    refreshed = write(memory, value, w, read(memory, operand, w))
    if function.recorded:
        return write(refreshed, UNEQUAL_RESULTS, 1, k + 1), ANY_UNEQUAL_CC
    return refreshed, k + 1


def _stored(function: PloFunction, memory: Memory) -> tuple[Memory, int]:
    w = function.width
    stored = reduce(
        lambda m, store: write(m, store[1], w, read(m, store[0], w)),
        function.stores,
        memory,
    )
    return stored, 0 if function.compares else NO_COMPARE_CC


def performed(function: PloFunction, memory: Memory) -> tuple[Memory, int]:
    k = _first_unequal(function, memory)
    if k < len(function.compares):
        return _refreshed(function, memory, k)
    return _stored(function, memory)


def _pl_word(image: bytes, at: int, pointed: Mapping[int, str]) -> str:
    if at in pointed:
        return "F'0'"
    if at - WORD in pointed:
        return f"A({pointed[at - WORD]})"
    return f"F'{int.from_bytes(image[at : at + WORD], 'big')}'"


def parameter_list(image: bytes, pointed: Mapping[int, str]) -> str:
    words = (_pl_word(image, at, pointed) for at in range(0, len(image), WORD))
    return "".join(f"         DC    {word}\n" for word in words)


def plo_program(body: str, parameters: str) -> str:
    operands = "".join(
        f"OP{k}      DC    F'{','.join(str(100 * k + j + 1) for j in range(8))}'\n"
        for k in range(1, 5)
    )
    return (
        "T        CSECT\n"
        "         BASR  12,0\n"
        "         USING *,12\n"
        "         LMG   2,11,FILL\n"
        f"{body}{ABEND}"
        "         ORG   T+X'400'\n"
        "FILL     DC    10X'A5A5A5A5A5A5A5A5'\n"
        "         ORG   T+X'480'\n"
        f"{operands}"
        "         ORG   T+X'600'\n"
        "PL       DS    0D\n"
        f"{parameters}"
        "         END\n"
    )


def _lines(*lines: str) -> str:
    return "".join(f"         {line}\n" for line in lines)


def _statement(function: PloFunction, register: int) -> str:
    fourth = "OP4" if function.fourth_is_operand else "PL"
    return f"PLO   {register},OP2,6,{fourth}"


def _reported(function: PloFunction, memory: Memory) -> Mapping[int, int]:
    if not function.in_registers:
        return {}
    return {
        REGISTER_NUMBERS[r]: read(memory, (r, 0), REGISTER_BYTES) for r in REGISTERS
    }


def _pl_segments(pointed: Mapping[int, str]) -> tuple[tuple[int, int], ...]:
    starts = (0, *(at + REGISTER_BYTES for at in sorted(pointed)))
    ends = (*sorted(pointed), PL_BYTES)
    return tuple(
        (start, end) for start, end in zip(starts, ends, strict=True) if end > start
    )


def storage_of(memory: Memory, pointed: Mapping[int, str]) -> Storage:
    operands = b"".join(memory[f"OP{k}"] for k in range(1, 5))
    listed = tuple(
        (PL_AT + start, memory["PL"][start:end]) for start, end in _pl_segments(pointed)
    )
    return ((OPERANDS_AT, operands), *listed)


def _function_program(code: int, missed_at: int) -> tuple[str, Memory]:
    function = FUNCTIONS[code]
    memory, setup = prepared(function, missed_at)
    preset = () if function.compares else ("LTR   0,0",)
    body = _lines(f"LA    0,{code}", *setup, *preset, _statement(function, 4))
    listed = parameter_list(memory["PL"], pointers(code, function))
    return plo_program(body, listed), memory


def function_case(code: int, missed_at: int) -> Case:
    function = FUNCTIONS[code]
    program, memory = _function_program(code, missed_at)
    after, cc = performed(function, memory)
    storage = storage_of(after, pointers(code, function))
    return (program, _reported(function, after), cc, storage)


def _outcomes(code: int) -> tuple[int, ...]:
    return tuple(range(len(FUNCTIONS[code].compares) + 1))


def _case_name(code: int, missed_at: int) -> str:
    compares = len(FUNCTIONS[code].compares)
    if missed_at == compares:
        return f"PLO {code}" if compares == 0 else f"PLO {code} all equal"
    return f"PLO {code} unequal at compare {missed_at + 1}"


FUNCTION_CASES: Mapping[str, Case] = {
    _case_name(code, missed_at): function_case(code, missed_at)
    for code in FUNCTIONS
    for missed_at in _outcomes(code)
}


def _special(body: str, results: Mapping[int, int], cc: int) -> Case:
    program = plo_program(body, parameter_list(INITIAL["PL"], {}))
    return (program, results, cc, storage_of(INITIAL, {}))


def _misaligned_listed_operand(code: int, missed_at: int, operand: str) -> Case:
    function = FUNCTIONS[code]
    program, memory = _function_program(code, missed_at)
    misaligned = program.replace(f"A({operand})", f"A({operand}+2)")
    storage = storage_of(memory, pointers(code, function))
    cc = 0 if function.compares else NO_COMPARE_CC
    return (misaligned, _reported(function, memory), cc, storage)


SPECIAL_CASES: Mapping[str, Case] = {
    "PLO test bit leaves the operation undone": _special(
        _lines("LA    0,X'104'", "L     4,OP2", "LHI   5,555", "PLO   4,OP2,6,OP4"),
        {4: HIGH_FILL | 201, 5: HIGH_FILL | 555},
        0,
    ),
    "PLO test bit, code 61": _special(
        _lines("LA    0,X'13D'", "LTR   0,0", "PLO   4,OP2,6,PL"), {}, 0
    ),
    "PLO test bit, code 62": _special(
        _lines("LA    0,X'13E'", "LTR   0,0", "PLO   4,OP2,6,PL"), {}, 3
    ),
    "PLO test bit, code 255": _special(
        _lines("LA    0,X'1FF'", "LTR   0,0", "PLO   4,OP2,6,PL"), {}, 3
    ),
    "PLO reserved GR0 bit": _special(
        _lines("LA    0,X'204'", "PLO   4,OP2,6,PL"), {4: FILL}, 0
    ),
    "PLO reserved GR0 bit with the test bit": _special(
        _lines("LA    0,X'304'", "PLO   4,OP2,6,PL"), {4: FILL}, 0
    ),
    "PLO code 62": _special(_lines("LA    0,62", "PLO   4,OP2,6,PL"), {4: FILL}, 0),
    "PLO odd R1 in compare and swap": _special(
        _lines("LA    0,4", "PLO   5,OP2,6,OP4"), {5: FILL}, 0
    ),
    "PLO odd R1 and R3 in compare and load": _special(
        _lines("LA    0,0", "L     5,OP2", "LHI   7,777", "PLO   5,OP2,7,OP4"),
        {5: HIGH_FILL | 201, 7: HIGH_FILL | 401},
        0,
    ),
    "PLO odd R3 in double compare and swap": _special(
        _lines("LA    0,8", "PLO   4,OP2,7,OP4"), {7: FILL}, 0
    ),
    "PLO second operand off its boundary": _special(
        _lines("LA    0,4", "L     4,OP2", "PLO   4,OP2+2,6,OP4"),
        {4: HIGH_FILL | 201},
        0,
    ),
    "PLO fourth operand off its boundary": _special(
        _lines("LA    0,0", "L     4,OP2", "PLO   4,OP2,6,OP4+2"),
        {4: HIGH_FILL | 201},
        0,
    ),
    "PLO parameter list off a doubleword": _special(
        _lines("LA    0,5", "PLO   4,OP2,6,PL+4"), {4: FILL}, 0
    ),
    "PLO 31 listed operand off its boundary": _misaligned_listed_operand(31, 3, "OP2"),
    "PLO 31 listed operand off its boundary, first compare missed": (
        _misaligned_listed_operand(31, 0, "OP2")
    ),
    "PLO 50 second store operand off its boundary": _misaligned_listed_operand(
        50, 0, "OP2"
    ),
    "PLO 16 second store operand off its boundary": _misaligned_listed_operand(
        16, 1, "OP3"
    ),
}

EXECUTED = (
    _lines("LA    0,4", "L     4,OP2", "LHI   5,555", "LHI   2,X'46'", "EX    2,PLOT")
    + _lines("J     EXECUTED")
    + "PLOT     PLO   0,OP2,0,OP4\n"
    + "EXECUTED DS    0H\n"
)

EXECUTE_CASES: Mapping[str, Case] = {
    "EX of PLO takes R1 and R3 from the EX register": (
        plo_program(EXECUTED, parameter_list(INITIAL["PL"], {})),
        {2: HIGH_FILL | 0x46, 4: HIGH_FILL | 201, 5: HIGH_FILL | 555},
        0,
        storage_of(write(INITIAL, SECOND, WORD, 555), {}),
    ),
}

CASES: Mapping[str, Case] = {**FUNCTION_CASES, **SPECIAL_CASES, **EXECUTE_CASES}

ABENDS: frozenset[str] = frozenset(
    {
        "PLO reserved GR0 bit",
        "PLO reserved GR0 bit with the test bit",
        "PLO code 62",
        "PLO odd R1 in compare and swap",
        "PLO odd R3 in double compare and swap",
        "PLO second operand off its boundary",
        "PLO fourth operand off its boundary",
        "PLO parameter list off a doubleword",
        "PLO 31 listed operand off its boundary",
        "PLO 31 listed operand off its boundary, first compare missed",
        "PLO 50 second store operand off its boundary",
        "PLO 16 second store operand off its boundary",
    }
)
