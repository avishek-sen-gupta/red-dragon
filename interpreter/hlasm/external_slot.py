# pyright: standard
"""Bytes of an address constant naming an external symbol, filled by the binder."""

from dataclasses import dataclass

from hlasm_asg.program.external_address import ExternalAddress


@dataclass(frozen=True)
class ExternalSlot:
    address: ExternalAddress
    width: int
