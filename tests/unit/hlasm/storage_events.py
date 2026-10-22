# pyright: standard
"""A lowering's storage reads and writes, abend codes and CC stores in order, repeats collapsed, for the decimal lowering unit tests."""

from collections.abc import Mapping, Sequence

from interpreter.instructions import (
    Const,
    InstructionBase,
    LoadRegion,
    LoadVar,
    StoreVar,
    WriteRegion,
)

GPRS = "__hlasm_gprs"
ABEND = "__hlasm_abend"
CC = "__hlasm_cc"
STORAGE_ACCESSES: Mapping[type[InstructionBase], str] = {
    LoadRegion: "read",
    WriteRegion: "write",
}


def _abend_or_cc(i: StoreVar, consts: Mapping[str, int | str]) -> str:
    return {ABEND: str(consts.get(str(i.value_reg), "")), CC: "cc"}.get(str(i.name), "")


def _access(i: InstructionBase, gprs: frozenset[str]) -> str:
    in_gprs = isinstance(i, LoadRegion) and str(i.region_reg) in gprs
    return "" if in_gprs else STORAGE_ACCESSES.get(type(i), "")


def _event(
    i: InstructionBase, gprs: frozenset[str], consts: Mapping[str, int | str]
) -> str:
    if isinstance(i, StoreVar):
        return _abend_or_cc(i, consts)
    return _access(i, gprs)


def storage_events(ir: Sequence[InstructionBase]) -> list[str]:
    gprs = frozenset(
        str(i.result_reg) for i in ir if isinstance(i, LoadVar) and str(i.name) == GPRS
    )
    consts = {str(i.result_reg): i.value for i in ir if isinstance(i, Const)}
    named = [e for e in (_event(i, gprs, consts) for i in ir) if e]
    return [e for k, e in enumerate(named) if k == 0 or named[k - 1] != e]
