"""The start-up module a link carries when its language's frontend supplies start-up code."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from interpreter.constants import Language
from interpreter.instructions import InstructionBase
from interpreter.project.types import ExportTable, ModuleUnit

START_UP_PATH = Path("__start_up__")


def with_start_up(
    start_up: Sequence[InstructionBase],
    language: Language,
    modules: Mapping[Path, ModuleUnit],
    import_graph: Mapping[Path, Sequence[Path]],
) -> tuple[dict[Path, ModuleUnit], dict[Path, list[Path]]]:
    if not start_up:
        return dict(modules), {path: list(deps) for path, deps in import_graph.items()}
    module = ModuleUnit(
        path=START_UP_PATH,
        language=language,
        ir=tuple(start_up),
        exports=ExportTable(),
        imports=(),
    )
    return (
        {START_UP_PATH: module, **modules},
        {
            START_UP_PATH: [],
            **{path: [*deps, START_UP_PATH] for path, deps in import_graph.items()},
        },
    )
