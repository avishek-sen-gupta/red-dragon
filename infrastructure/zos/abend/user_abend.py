# pyright: standard
"""A z/OS user abend code, rendered as U plus four decimal digits."""

from dataclasses import dataclass


@dataclass(frozen=True)
class UserAbend:
    code: int

    def rendered(self) -> str:
        return f"U{self.code:04d}"
