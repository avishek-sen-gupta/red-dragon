# pyright: standard
"""What the HLASM binder gives the link: the start-up module, the job-step module and each entry name's job-step function."""

from collections.abc import Mapping
from dataclasses import dataclass

from interpreter.ir import CodeLabel
from interpreter.project.types import ModuleUnit


@dataclass(frozen=True)
class BoundImage:
    start_up: ModuleUnit
    job_step: ModuleUnit
    programs: Mapping[str, CodeLabel]
