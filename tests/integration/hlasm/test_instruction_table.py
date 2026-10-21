# pyright: standard
"""The che4z bridge exports its machine-instruction and extended-mnemonic tables as JSON."""

from __future__ import annotations

import subprocess
from collections import Counter

from hlasm_asg.hlasm_bridge_parser import bridge_executable
from hlasm_asg.instruction_table.architecture_level import ArchitectureLevel
from hlasm_asg.instruction_table.instruction_table import InstructionTable
from hlasm_asg.instruction_table.machine_instruction_row import MachineInstructionRow
from hlasm_asg.instruction_table.mnemonic_row import MnemonicRow
from hlasm_asg.instruction_table.operand import Operand
from hlasm_asg.instruction_table.operand_kind import OperandKind
from hlasm_asg.instruction_table.parameter import Parameter
from hlasm_asg.instruction_table.parameter_kind import ParameterKind
from hlasm_asg.instruction_table.privilege import Privilege
from hlasm_asg.instruction_table.transform import Transform
from hlasm_asg.instruction_table.transform_kind import TransformKind
from tests.covers import NotLanguageFeature, covers

NO_PARAMETER = Parameter(kind=ParameterKind.NONE, bits=0, signed=False)
REGISTER = Operand(
    kind=OperandKind.REG,
    bits=4,
    signed=False,
    first=NO_PARAMETER,
    second=NO_PARAMETER,
    optional=False,
)


def _exported_table() -> InstructionTable:
    completed = subprocess.run(
        [bridge_executable(), "--instruction-table"],
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
        privileged=Privilege.NOT_PRIVILEGED,
        arch=ArchitectureLevel.UNI_ESA_XA_370_DOS_SINCE_ZOP,
        operands=(REGISTER, REGISTER),
        base=None,
        transforms=(),
    )
    assert rows["LPSW"] == MachineInstructionRow(
        mnemonic="LPSW",
        format="SI",
        privileged=Privilege.PRIVILEGED,
        arch=ArchitectureLevel.UNI_ESA_XA_370_DOS_SINCE_ZOP,
        operands=(
            Operand(
                kind=OperandKind.DISP,
                bits=12,
                signed=False,
                first=NO_PARAMETER,
                second=Parameter(kind=ParameterKind.BASE, bits=4, signed=False),
                optional=False,
            ),
        ),
        base=None,
        transforms=(),
    )
    assert rows["BE"] == MnemonicRow(
        mnemonic="BE",
        format="RX-b",
        privileged=Privilege.NOT_PRIVILEGED,
        arch=ArchitectureLevel.UNI_ESA_XA_370_DOS_SINCE_ZOP,
        operands=(
            Operand(
                kind=OperandKind.MASK,
                bits=4,
                signed=False,
                first=NO_PARAMETER,
                second=NO_PARAMETER,
                optional=False,
            ),
            Operand(
                kind=OperandKind.DISP,
                bits=12,
                signed=False,
                first=Parameter(kind=ParameterKind.IDX_REG, bits=4, signed=False),
                second=Parameter(kind=ParameterKind.BASE, bits=4, signed=False),
                optional=False,
            ),
        ),
        base="BC",
        transforms=(
            Transform(kind=TransformKind.VALUE, skip=0, value=8, source=0, insert=True),
        ),
    )
