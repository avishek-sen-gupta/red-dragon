"""The COBOL run unit's own storage, which the start-up module sets up before any program
runs: one region, and the directories of its EXTERNAL records and files."""

from __future__ import annotations

import logging

from cobol_asg.asg_types import CobolField
from interpreter.cobol.data_layout import build_data_layout
from interpreter.cobol.external_area import ExternalKind, external_directory
from interpreter.instructions import (
    AllocRegion,
    Const,
    DeclVar,
    InstructionBase,
    NewObject,
)
from interpreter.register import Register
from interpreter.var_name import VarName

logger = logging.getLogger(__name__)

RUN_UNIT_VAR = VarName("__cobol_run_unit")
RUN_UNIT_RETURN_CODE = "RUN-UNIT-RETURN-CODE"
RANDOM_STATE = "RANDOM-STATE"

RUN_UNIT_LAYOUT = build_data_layout(
    [
        CobolField(
            name=RUN_UNIT_RETURN_CODE, level=1, pic="S9(4)", usage="COMP", offset=0
        ),
        CobolField(name=RANDOM_STATE, level=1, pic="X(4)", usage="DISPLAY", offset=2),
    ]
)


def run_unit_allocation() -> tuple[InstructionBase, ...]:
    size, region = Register("%0"), Register("%1")
    records, files = Register("%2"), Register("%3")
    return (
        Const.int_(size, RUN_UNIT_LAYOUT.total_bytes),
        AllocRegion(result_reg=region, size_reg=size),
        DeclVar(name=RUN_UNIT_VAR, value_reg=region),
        NewObject(result_reg=records),
        DeclVar(name=external_directory(ExternalKind.RECORD), value_reg=records),
        NewObject(result_reg=files),
        DeclVar(name=external_directory(ExternalKind.FILE), value_reg=files),
    )


_MODULUS = 2**31 - 1
_MULTIPLIER = 16807
_DISTINCT_SEEDS = _MODULUS - 1


def restarted(seed: int) -> int:
    """The first state of the sequence FUNCTION RANDOM(seed) starts."""
    if seed < 0:
        logger.warning(
            "FUNCTION RANDOM seed %d is negative; IBM requires zero or positive, using 0",
            seed,
        )
    return _step(max(seed, 0) % _DISTINCT_SEEDS + 1)


def advanced(state: int) -> int:
    """The next state of the current sequence; state 0 means none started, so seed 0 starts one."""
    return _step(state) if state else restarted(0)


def value_of(state: int) -> float:
    return state / _MODULUS


def _step(state: int) -> int:
    return state * _MULTIPLIER % _MODULUS
