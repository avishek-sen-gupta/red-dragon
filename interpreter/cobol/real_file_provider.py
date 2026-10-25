# pyright: standard
"""RealFileIOProvider — disk-backed COBOL I/O: RealFileProvider's record operations, with
SYSIN for ACCEPT, the implementor switches and KEY OF REFERENCE."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from cobol_asg.switch_status import SwitchStatus
from interpreter.cobol.io_provider import CobolIOProvider
from interpreter.record_io.access_result import AccessCondition
from interpreter.record_io.io_provider import IOResult
from interpreter.record_io.real_file_provider import RealFileProvider, to_ioresult
from interpreter.record_io.run_inputs import NO_RUN_INPUTS, RunInputs

_INPUT_ENDED = IOResult(AccessCondition.END_OF_FILE, None)


class RealFileIOProvider(CobolIOProvider, RealFileProvider):
    """Disk-backed COBOL I/O provider.

    Args:
        base_dir: Root for resolving relative paths from ``assign_to``.
        inputs: The run's SELECT entries, path overrides (which take precedence
            over all other resolution), system input records (which ACCEPT reads
            in order) and implementor switch settings (a switch not named is OFF).
    """

    def __init__(self, base_dir: Path, inputs: RunInputs = NO_RUN_INPUTS) -> None:
        super().__init__(base_dir, inputs)
        self._system_input: Iterator[str] = iter(inputs.system_input)
        self._switches: dict[str, SwitchStatus] = {
            name.upper(): status for name, status in inputs.switches.items()
        }

    def _switch_status(self, environment_name: str) -> str:
        return self._switches.get(environment_name.upper(), SwitchStatus.OFF).value

    def _set_switch(self, environment_name: str, status: str) -> IOResult:
        self._switches = {
            **self._switches,
            environment_name.upper(): SwitchStatus(status),
        }
        return IOResult(AccessCondition.OK, None)

    def _accept(self, from_device: str) -> IOResult:
        return next(
            (IOResult(AccessCondition.OK, record) for record in self._system_input),
            _INPUT_ENDED,
        )

    def _key_of_reference(self, filename: str, number: int, program: str) -> IOResult:
        return to_ioresult(self._files[filename].key_of_reference(number))
