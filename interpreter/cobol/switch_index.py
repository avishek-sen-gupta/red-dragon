"""SwitchIndex — a program's implementor switches by status condition-name and mnemonic."""

from __future__ import annotations

from collections.abc import Sequence

from cobol_asg.implementor_switch import ImplementorSwitch
from cobol_asg.switch_status import SwitchStatus
from interpreter.cobol.switch_condition import SwitchCondition


class SwitchIndex:
    """The switch-status condition-names and mnemonic-names SPECIAL-NAMES declares."""

    def __init__(self, switches: Sequence[ImplementorSwitch]) -> None:
        self._conditions = {
            name.upper(): SwitchCondition(switch.environment_name, status)
            for switch in switches
            for name, status in (
                (switch.on_condition, SwitchStatus.ON),
                (switch.off_condition, SwitchStatus.OFF),
            )
            if name
        }
        self._environments = {
            switch.mnemonic_name.upper(): switch.environment_name
            for switch in switches
            if switch.mnemonic_name
        }

    def has_condition(self, name: str) -> bool:
        return name.upper() in self._conditions

    def condition(self, name: str) -> SwitchCondition:
        return self._conditions[name.upper()]

    def has_mnemonic(self, name: str) -> bool:
        return name.upper() in self._environments

    def environment_of(self, mnemonic_name: str) -> str:
        return self._environments[mnemonic_name.upper()]
