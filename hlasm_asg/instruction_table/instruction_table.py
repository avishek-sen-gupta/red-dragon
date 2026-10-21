# pyright: standard
"""The whole table the bridge prints for `--instruction-table`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hlasm_asg.instruction_table.machine_instruction_row import MachineInstructionRow
from hlasm_asg.instruction_table.mnemonic_row import MnemonicRow


class InstructionTable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    format: int
    instructions: tuple[MachineInstructionRow | MnemonicRow, ...]
