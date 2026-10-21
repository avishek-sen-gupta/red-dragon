# pyright: standard
"""The che4z bridge exports its machine-instruction and extended-mnemonic tables as JSON."""

from __future__ import annotations

import os
import subprocess
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict

from tests.covers import NotLanguageFeature, covers


class Parameter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    bits: int
    signed: bool


class Operand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    bits: int
    signed: bool
    first: Parameter
    second: Parameter
    optional: bool


class Transform(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    skip: int
    value: int
    source: int
    insert: bool


class MachineInstructionRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mnemonic: str
    format: str
    privileged: Literal["not_privileged", "privileged", "conditionally_privileged"]
    arch: str
    operands: tuple[Operand, ...]
    base: None
    transforms: tuple[()]


class MnemonicRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mnemonic: str
    format: str
    privileged: Literal["not_privileged", "privileged", "conditionally_privileged"]
    arch: str
    operands: tuple[Operand, ...]
    base: str
    transforms: tuple[Transform, ...]


class InstructionTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    format: int
    instructions: tuple[MachineInstructionRow | MnemonicRow, ...]


NO_PARAMETER = Parameter(kind="NONE", bits=0, signed=False)
REGISTER = Operand(
    kind="REG",
    bits=4,
    signed=False,
    first=NO_PARAMETER,
    second=NO_PARAMETER,
    optional=False,
)


def _exported_table() -> InstructionTable:
    completed = subprocess.run(
        [os.environ["HLASM_AST_BRIDGE"], "--instruction-table"],
        capture_output=True,
        check=True,
        text=True,
    )
    return InstructionTable.model_validate_json(completed.stdout)


def _names_on_several_rows(table: InstructionTable) -> set[str]:
    counts = Counter(row.mnemonic for row in table.instructions)
    return {name for name, count in counts.items() if count > 1}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_instruction_table_lists_lr_lpsw_and_be() -> None:
    table = _exported_table()
    rows = {row.mnemonic: row for row in table.instructions}

    assert table.format == 1
    assert len(table.instructions) == 1395 + 1120
    assert _names_on_several_rows(table) == {"KIMD", "KLMD", "VTP"}
    assert rows["LR"] == MachineInstructionRow(
        mnemonic="LR",
        format="RR",
        privileged="not_privileged",
        arch="UNI_ESA_XA_370_DOS_SINCE_ZOP",
        operands=(REGISTER, REGISTER),
        base=None,
        transforms=(),
    )
    assert rows["LPSW"] == MachineInstructionRow(
        mnemonic="LPSW",
        format="SI",
        privileged="privileged",
        arch="UNI_ESA_XA_370_DOS_SINCE_ZOP",
        operands=(
            Operand(
                kind="DISP",
                bits=12,
                signed=False,
                first=NO_PARAMETER,
                second=Parameter(kind="BASE", bits=4, signed=False),
                optional=False,
            ),
        ),
        base=None,
        transforms=(),
    )
    assert rows["BE"] == MnemonicRow(
        mnemonic="BE",
        format="RX-b",
        privileged="not_privileged",
        arch="UNI_ESA_XA_370_DOS_SINCE_ZOP",
        operands=rows["BC"].operands,
        base="BC",
        transforms=(Transform(kind="value", skip=0, value=8, source=0, insert=True),),
    )
