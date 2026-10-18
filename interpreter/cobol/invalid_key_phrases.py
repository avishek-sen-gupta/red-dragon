"""An I/O statement's INVALID KEY and NOT INVALID KEY phrases."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cobol_asg.cobol_statements import CobolStatementType


@dataclass(frozen=True)
class InvalidKeyPhrases:
    invalid_key: Sequence[CobolStatementType]
    not_invalid_key: Sequence[CobolStatementType]

    @property
    def written(self) -> bool:
        return bool(self.invalid_key or self.not_invalid_key)
