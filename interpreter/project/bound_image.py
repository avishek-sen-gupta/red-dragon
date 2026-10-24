# pyright: standard
"""What the HLASM binder gives the link: the start-up module, the job-step module, each SD or LD name's job-step function, and each unit's job step entering at its END."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from interpreter.ir import CodeLabel
from interpreter.project.types import ModuleUnit


@dataclass(frozen=True)
class BoundImage:
    start_up: ModuleUnit
    job_step: ModuleUnit
    programs: Mapping[str, CodeLabel]
    module_entries: Mapping[Path, CodeLabel]
