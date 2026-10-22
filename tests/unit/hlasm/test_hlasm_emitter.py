# pyright: standard
"""The emitter grows its instructions without copying and locates them per statement."""

import dataclasses
from itertools import accumulate

from interpreter.hlasm.chain_link import Chain, ChainLink, extended, flattened
from interpreter.hlasm.empty_chain import EmptyChain
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.instructions import Const, InstructionBase, Label_
from interpreter.ir import NO_SOURCE_LOCATION, CodeLabel, SourceLocation
from interpreter.register import Register


def _line(line: int) -> SourceLocation:
    return SourceLocation(start_line=line, start_col=0, end_line=line, end_col=0)


def _constant(value: int) -> InstructionBase:
    return Const.int_(Register(f"%{value}"), value)


def test_extending_a_chain_shares_the_chain_it_extends() -> None:
    empty: EmptyChain[int] = EmptyChain()
    chains: list[Chain[int]] = list(accumulate(range(1000), extended, initial=empty))
    links = chains[1:]
    assert all(
        isinstance(link, ChainLink) and link.previous is prior
        for link, prior in zip(links, chains, strict=False)
    )
    assert [chain.length for chain in chains] == list(range(1001))
    assert flattened(chains[-1]) == tuple(range(1000))
    assert flattened(chains[500]) == tuple(range(500))
    assert flattened(empty) == ()


def _statement(
    emitter: HlasmEmitter, insts: tuple[InstructionBase, ...], line: int
) -> int:
    start = emitter.emitted_count()
    emitted = [emitter.emit_inst(inst) for inst in insts]
    emitter.locate_from(start, _line(line))
    return start + len(emitted)


def test_emitter_returns_instructions_in_order_located_by_the_latest_span() -> None:
    emitter = HlasmEmitter()
    label = Label_(label=CodeLabel("entry"))
    emitter.emit_inst(label)
    constants = tuple(_constant(value) for value in range(4))
    ends = (
        _statement(emitter, constants[:2], 10),
        _statement(emitter, constants[2:], 20),
    )
    emitter.locate_from(emitter.emitted_count() - 1, _line(30))
    assert ends == (3, 5)
    assert [inst.source_location for inst in emitter.instructions()] == [
        NO_SOURCE_LOCATION,
        _line(10),
        _line(10),
        _line(20),
        _line(30),
    ]
    assert [
        dataclasses.replace(inst, source_location=NO_SOURCE_LOCATION)
        for inst in emitter.instructions()
    ] == [label, *constants]
