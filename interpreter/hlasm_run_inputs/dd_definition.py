# pyright: standard
"""A DD definition, a run input: the data set's path and the DCB fields it supplies where the DCB leaves them zero."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from interpreter.hlasm_run_inputs.record_format import RecordFormat
from interpreter.hlasm_run_inputs.run_input_names import (
    DD_BLKSIZE_FACT,
    DD_FACTS,
    DD_LRECL_FACT,
    DD_RECFM_FACT,
    DD_SUPPLIED_FACT,
)

SUPPLIED = 1


@dataclass(frozen=True)
class DdDefinition:
    path: Path
    recfm: RecordFormat = RecordFormat.UNSPECIFIED
    lrecl: int = 0
    blksize: int = 0

    def facts(self) -> Sequence[int]:
        at = {
            DD_SUPPLIED_FACT: SUPPLIED,
            DD_RECFM_FACT: self.recfm.value,
            DD_LRECL_FACT: self.lrecl,
            DD_BLKSIZE_FACT: self.blksize,
        }
        return [at[position] for position in range(DD_FACTS)]
