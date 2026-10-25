"""What a run supplies a file provider: its SELECT entries, the paths that override their
assignments, the system input device's records, and the implementor switch settings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from cobol_asg.cobol_statements import FileControlEntry
from cobol_asg.switch_status import SwitchStatus


@dataclass(frozen=True)
class RunInputs:
    file_control: Sequence[FileControlEntry] = ()
    path_overrides: Mapping[str, Path] = field(
        default_factory=lambda: MappingProxyType({})
    )
    system_input: Sequence[str] = ()
    switches: Mapping[str, SwitchStatus] = field(
        default_factory=lambda: MappingProxyType({})
    )


NO_RUN_INPUTS = RunInputs()
