# pyright: standard
"""The seam through which the bridge parser starts a child process."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from hlasm_asg.process_result import ProcessResult


class SubprocessRunner(Protocol):
    def run(self, command: Sequence[str]) -> ProcessResult: ...
