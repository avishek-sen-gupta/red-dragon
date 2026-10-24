# pyright: standard
"""One row of the far-branch table: an address range, from where it starts for this many bytes, and its owner."""

from dataclasses import dataclass

from interpreter.hlasm.branch_owner import BranchOwner
from interpreter.hlasm.placed_name import PlacedName
from interpreter.hlasm.stub_name import StubName


@dataclass(frozen=True)
class FarBranchEntry:
    start: PlacedName | StubName
    length: int
    owner: BranchOwner
