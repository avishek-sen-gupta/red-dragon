# pyright: standard
"""The language of the program a linked image holds under a given name."""

from interpreter.constants import Language
from interpreter.project.program_not_in_image import ProgramNotInImage
from interpreter.project.types import LinkedProgram


def program_language(linked: LinkedProgram, name: str) -> Language:
    named = [unit.language for unit in linked.modules.values() if unit.program == name]
    if not named:
        raise ProgramNotInImage(name)
    return named[0]
