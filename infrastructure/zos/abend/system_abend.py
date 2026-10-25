# pyright: standard
"""A z/OS system abend code, rendered as S plus three hex digits."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemAbend:
    code: int

    def rendered(self) -> str:
        return f"S{self.code:03X}"
