# pyright: standard
"""What the emitter records of an IR function a lowering calls, so the frontend defines it once after the entry function."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from interpreter.ir import CodeLabel

if TYPE_CHECKING:
    from interpreter.hlasm.hlasm_emitter import HlasmEmitter


class ProgramFunction(Protocol):
    name: str

    @property
    def label(self) -> CodeLabel: ...

    def define(self, emitter: HlasmEmitter) -> None: ...
