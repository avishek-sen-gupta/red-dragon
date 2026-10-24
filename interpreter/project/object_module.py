# pyright: standard
"""An assembled module as the binder reads it: its external symbols, text, relocations and entry point."""

from dataclasses import dataclass

from interpreter.project.default_end import DefaultEnd
from interpreter.project.esd_record import EsdRecord
from interpreter.project.module_end import ModuleEnd
from interpreter.project.relocation_record import RelocationRecord
from interpreter.project.text_record import TextRecord


@dataclass(frozen=True)
class ObjectModule:
    esd: tuple[EsdRecord, ...]
    text: tuple[TextRecord, ...]
    relocations: tuple[RelocationRecord, ...]
    end: ModuleEnd


NO_OBJECT_MODULE = ObjectModule(esd=(), text=(), relocations=(), end=DefaultEnd(""))
