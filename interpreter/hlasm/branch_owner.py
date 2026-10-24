# pyright: standard
"""Who owns an address range a far branch can reach."""

from interpreter.hlasm.cobol_owner import CobolOwner
from interpreter.hlasm.module_owner import ModuleOwner
from interpreter.hlasm.unresolved_owner import UnresolvedOwner

type BranchOwner = ModuleOwner | CobolOwner | UnresolvedOwner
