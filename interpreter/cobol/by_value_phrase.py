"""The two phrases that take BY VALUE operands, as a refusal names them."""

from __future__ import annotations

from enum import Enum


class ByValuePhrase(Enum):
    CALL = "CALL BY VALUE"
    PROCEDURE_DIVISION_USING = "PROCEDURE DIVISION USING BY VALUE"
