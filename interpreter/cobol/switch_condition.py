"""SwitchCondition — what a switch-status condition-name tests."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.switch_status import SwitchStatus


@dataclass(frozen=True)
class SwitchCondition:
    """True when the switch named ``environment_name`` is in ``status``."""

    environment_name: str
    status: SwitchStatus
