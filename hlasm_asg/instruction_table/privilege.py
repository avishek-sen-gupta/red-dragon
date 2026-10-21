# pyright: standard
"""Whether an instruction may run in the problem state."""

from __future__ import annotations

from enum import StrEnum


class Privilege(StrEnum):
    NOT_PRIVILEGED = "not_privileged"
    PRIVILEGED = "privileged"
    CONDITIONALLY_PRIVILEGED = "conditionally_privileged"
