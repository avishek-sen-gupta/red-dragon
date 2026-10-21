# pyright: standard
"""Every z/Architecture problem-state machine instruction in the che4z table, bar the system set, is in exactly one opcode unit."""

from __future__ import annotations

import os
import subprocess
from collections import Counter
from pathlib import Path

import hlasm_asg
from hlasm_asg.instruction_table.architecture_level import ArchitectureLevel
from hlasm_asg.instruction_table.instruction_table import InstructionTable
from hlasm_asg.instruction_table.machine_instruction_row import MachineInstructionRow
from hlasm_asg.instruction_table.privilege import Privilege
from hlasm_asg.opcode_units import OpcodeUnits
from tests.covers import NotLanguageFeature, covers

OPCODE_UNITS_PATH = Path(hlasm_asg.__file__).parent / "opcode_units.json"

ARCHITECTURES_WITHOUT_Z = frozenset(
    {
        ArchitectureLevel.ESA_XA,
        ArchitectureLevel.ESA_XA_370,
        ArchitectureLevel.UNI_370,
        ArchitectureLevel.UNI_370_DOS,
    }
)

SIE_LINKAGE_STACK_ASN_MEASUREMENT_GUARDED_STORAGE = frozenset(
    {
        "SIE",
        "BAKR",
        "PR",
        "EREG",
        "EREGG",
        "ESTA",
        "MSTA",
        "SSAR",
        "SSAIR",
        "TAR",
        "BSG",
        "ECCTR",
        "EPCTR",
        "ECPGA",
        "LCCTL",
        "LPCTL",
        "LSCTL",
        "LPP",
        "QCTRI",
        "QSI",
        "SCCTR",
        "SPCTR",
        "STCCTM",
        "LGSC",
        "STGSC",
    }
)


def _covered_mnemonics() -> set[str]:
    completed = subprocess.run(
        [os.environ["HLASM_AST_BRIDGE"], "--instruction-table"],
        capture_output=True,
        check=True,
        text=True,
    )
    table = InstructionTable.model_validate_json(completed.stdout)
    return {
        row.mnemonic
        for row in table.instructions
        if isinstance(row, MachineInstructionRow)
        and row.privileged == Privilege.NOT_PRIVILEGED
        and row.arch not in ARCHITECTURES_WITHOUT_Z
        and row.mnemonic not in SIE_LINKAGE_STACK_ASN_MEASUREMENT_GUARDED_STORAGE
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_problem_state_instruction_is_in_exactly_one_unit() -> None:
    units = OpcodeUnits.model_validate_json(OPCODE_UNITS_PATH.read_text())
    assigned = [mnemonic for unit in units.units for mnemonic in unit.mnemonics]
    counts = Counter(assigned)

    assert [mnemonic for mnemonic, count in counts.items() if count > 1] == []
    assert sorted(assigned) == sorted(_covered_mnemonics())
