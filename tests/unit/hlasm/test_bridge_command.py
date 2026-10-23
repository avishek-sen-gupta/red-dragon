# pyright: standard
"""The bridge parser hands each supplied assembly input and the assembly instant to the bridge as an option."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hlasm_asg.assembly_input import AssemblyInput
from hlasm_asg.assembly_inputs import AssemblyInputs
from hlasm_asg.hlasm_bridge_parser import HlasmBridgeParser
from hlasm_asg.process_result import ProcessResult
from hlasm_asg.subprocess_runner import SubprocessRunner
from tests.covers import NotLanguageFeature, covers

AT = datetime(2026, 1, 2, 0, 30, 15, 123456, tzinfo=timezone(timedelta(hours=1)))


class EchoingRunner(SubprocessRunner):
    def run(self, command: Sequence[str]) -> ProcessResult:
        return ProcessResult(0, json.dumps(list(command)), "")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bridge_command_carries_the_supplied_inputs_and_the_instant(tmp_path: Path):
    out = tmp_path / "out.json"
    inputs = AssemblyInputs(
        {AssemblyInput.SYSSTEP: "STEP1", AssemblyInput.SYSPARM: "-x"}, AT
    )

    HlasmBridgeParser(EchoingRunner(), "bridge", [Path("/lib")]).parse_to_file(
        b"X\n", "src/a.asm", out, inputs
    )

    bridge, _source, *options = json.loads(out.read_text(encoding="utf-8"))
    assert (bridge, options) == (
        "bridge",
        [
            "--source-name",
            "src/a.asm",
            "--syslib",
            "/lib",
            "--sysstep",
            "STEP1",
            "--sysparm",
            "-x",
            "--clock",
            "2026-01-02T00:30:15.123456+01:00",
        ],
    )
