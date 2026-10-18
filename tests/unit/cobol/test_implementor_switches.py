"""SPECIAL-NAMES implementor switches: the ASG, their index and their run-time state."""

from __future__ import annotations

from pathlib import Path

from cobol_asg.asg_types import CobolASG
from cobol_asg.implementor_switch import ImplementorSwitch
from cobol_asg.switch_status import SwitchStatus
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.io_provider import NullIOProvider
from interpreter.cobol.real_file_provider import RealFileIOProvider
from interpreter.cobol.run_inputs import RunInputs
from interpreter.cobol.switch_index import SwitchCondition, SwitchIndex
from tests.covers import covers

_SWITCHES = {
    "special_names": {
        "switches": [
            {
                "environment_name": "SWITCH-1",
                "mnemonic_name": "SW-1",
                "on_condition": "ON-SWITCH-1",
                "off_condition": "OFF-SWITCH-1",
            },
            {
                "environment_name": "SWITCH-2",
                "mnemonic_name": "",
                "on_condition": "",
                "off_condition": "OFF-SWITCH-2",
            },
        ]
    }
}


@covers(CobolFeature.IMPLEMENTOR_SWITCH)
def test_switches_parse_round_trip_and_index_their_names() -> None:
    asg = CobolASG.from_dict(_SWITCHES)
    index = SwitchIndex(asg.switches)

    assert asg.switches == [
        ImplementorSwitch("SWITCH-1", "SW-1", "ON-SWITCH-1", "OFF-SWITCH-1"),
        ImplementorSwitch("SWITCH-2", "", "", "OFF-SWITCH-2"),
    ]
    assert CobolASG.from_dict(asg.to_dict()) == asg
    assert (
        index.has_condition("on-switch-1"),
        index.condition("ON-SWITCH-1"),
        index.condition("OFF-SWITCH-2"),
        index.has_condition("ON-SWITCH-2"),
        index.has_mnemonic("SW-1"),
        index.environment_of("sw-1"),
        index.has_mnemonic("SW-2"),
    ) == (
        True,
        SwitchCondition("SWITCH-1", SwitchStatus.ON),
        SwitchCondition("SWITCH-2", SwitchStatus.OFF),
        False,
        True,
        "SWITCH-1",
        False,
    )


@covers(CobolFeature.IMPLEMENTOR_SWITCH)
def test_switch_state_starts_from_the_run_input_and_defaults_off(
    tmp_path: Path,
) -> None:
    prov = RealFileIOProvider(
        base_dir=tmp_path, inputs=RunInputs(switches={"SWITCH-1": SwitchStatus.ON})
    )
    before = [prov._switch_status(name) for name in ("SWITCH-1", "SWITCH-2")]
    prov._set_switch("SWITCH-1", "OFF")
    prov._set_switch("SWITCH-2", "ON")
    after = [prov._switch_status(name) for name in ("SWITCH-1", "SWITCH-2")]

    assert (before, after, NullIOProvider()._switch_status("SWITCH-1")) == (
        ["ON", "OFF"],
        ["OFF", "ON"],
        "OFF",
    )
