# pyright: standard
"""A module the binder binds: its name, the file it came from and its object module."""

from dataclasses import dataclass

from interpreter.project.object_module import ObjectModule


@dataclass(frozen=True)
class ImageModule:
    name: str
    file: str
    object_module: ObjectModule
