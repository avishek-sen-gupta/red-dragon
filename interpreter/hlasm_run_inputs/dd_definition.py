# pyright: standard
"""A DD definition, a run input: the data set's path and the DCB fields it supplies where the DCB leaves them zero."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from interpreter.hlasm_run_inputs.record_format import RecordFormat

SUPPLIED = 1


@dataclass(frozen=True)
class DdDefinition:
    path: Path
    recfm: RecordFormat = RecordFormat.UNSPECIFIED
    lrecl: int = 0
    blksize: int = 0

    def facts(self) -> Sequence[int]:
        return [SUPPLIED, self.recfm.value, self.lrecl, self.blksize]
