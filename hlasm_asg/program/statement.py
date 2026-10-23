# pyright: standard
"""A statement of the assembled program."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from hlasm_asg.program.ccw_statement import CcwStatement
from hlasm_asg.program.dc_statement import DcStatement
from hlasm_asg.program.ds_statement import DsStatement
from hlasm_asg.program.machine_statement import MachineStatement

Statement = Annotated[
    MachineStatement | DcStatement | DsStatement | CcwStatement,
    Field(discriminator="kind"),
]
