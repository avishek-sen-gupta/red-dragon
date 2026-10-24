# pyright: standard
"""An object module's END record: a named entry point or the default."""

from interpreter.project.default_end import DefaultEnd
from interpreter.project.named_end import NamedEnd

type ModuleEnd = NamedEnd | DefaultEnd
