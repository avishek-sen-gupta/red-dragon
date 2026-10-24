# pyright: standard
"""What an RLD record relocates by: a name, or nothing for the external dummy total."""

from interpreter.project.no_relocation_target import NoRelocationTarget
from interpreter.project.relocation_name import RelocationName

type RelocationTarget = RelocationName | NoRelocationTarget
